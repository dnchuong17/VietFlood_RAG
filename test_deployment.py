"""Container initialization and deployment rollback tests without a Docker daemon."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import container_entrypoint as entry

ROOT = Path(__file__).resolve().parent
FAKE_DOCKER = r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
path=Path(os.environ['FAKE_DOCKER_STATE'])
state=json.loads(path.read_text());args=sys.argv[1:];state['events'].append(args)
mode=os.getenv('FAKE_DOCKER_MODE','healthy');code=0;out=''
containers=state['containers']
if args[:2]==['container','inspect']:
    code=0 if args[-1] in containers else 1
elif args[0]=='run':
    if '--prepare-volumes' in args:
        code=1 if mode=='prepare_failed' else 0
    elif '--prepare-release' in args:
        code=1 if mode=='candidate_failed' else 0
        if not code: state['candidate']='api_1536'
    elif '--check-release' in args:
        state['preflight_alias']=state['alias']
        code=1 if mode=='preflight_failed' or state.get('candidate')!='api_1536' else 0
    elif '--publish-release' in args:
        if mode!='publish_failed': state['alias']='api_1536'
        code=1 if mode in ['publish_failed','publish_uncertain'] else 0
    elif '--rollback-release' in args:
        if mode=='alias_rollback_failed': code=1
        else: state['alias']=state['previous_alias']
    else:
        name=args[args.index('--name')+1]
        containers[name]={'image':args[-1],'state':'running','health':'healthy'}
        if mode=='start_failed': containers[name]['state']='exited';code=1
        if mode in ['unhealthy','rollback_failed','alias_rollback_failed'] or state['alias']!='api_1536': containers[name]['health']='unhealthy'
        if mode=='timeout': containers[name]['health']='starting'
elif args[0]=='stop':
    containers[args[-1]]['state']='exited'
elif args[0]=='rename':
    if mode=='rename_failed' and args[-1].endswith('-previous'):
        code=1
    else:
        containers[args[-1]]=containers.pop(args[-2])
elif args[0]=='start':
    if mode=='rollback_failed' or state['alias']!=state['previous_alias']: code=1
    else: containers[args[-1]]['state']='running'
elif args[0]=='rm':
    if mode=='cleanup_failed' and args[-1].endswith('-previous'): code=1
    else: containers.pop(args[-1],None)
elif args[0]=='inspect':
    item=containers.get(args[-1])
    if item is None: code=1
    else: out=item['state'] if args[2]=='{{.State.Status}}' else item['health']
path.write_text(json.dumps(state))
if out: print(out)
sys.exit(code)
'''


class ArtifactBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/'data';self.seed=self.root/'image-seeds'
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(entry,'RAG_DATA_DIR',self.data))
        self.stack.enter_context(patch.object(entry,'BOOTSTRAP_DIR',self.seed))

    def write(self,relative,value):
        path=self.seed/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)

    def test_fresh_and_existing_volume_preserve_versions_and_receive_new_artifacts(self):
        self.write('releases/first.json','first release')
        self.write('snapshots/G01/1.json','original source')
        entry.seed_artifacts()
        (self.data/'snapshots/G01/1.json').write_text('existing volume source')
        self.write('releases/second.json','second release')
        self.write('snapshots/G01/2.json','new source')
        entry.seed_artifacts()
        self.assertEqual((self.data/'snapshots/G01/1.json').read_text(),'existing volume source')
        self.assertEqual((self.data/'snapshots/G01/2.json').read_text(),'new source')
        self.assertTrue((self.data/'releases/second.json').is_file())
        self.assertEqual(list(self.data.rglob('.seed-*')),[])

    def test_failed_copy_cleans_temporary_file(self):
        self.write('releases/first.json','first release')
        with patch.object(entry.shutil,'copyfile',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): entry.seed_artifacts()
        self.assertFalse((self.data/'releases/first.json').exists())
        self.assertEqual(list(self.data.rglob('.seed-*')),[])

    def test_exec_receives_command_after_initialization(self):
        with patch.object(entry,'initialize_corpus') as initialize, patch.object(entry.os,'execvp') as execute:
            entry.main(['uvicorn','retrieval_service:app'])
            initialize.assert_called_once()
            execute.assert_called_once_with('uvicorn',['uvicorn','retrieval_service:app'])

    def test_initialization_errors_hide_private_details(self):
        output=io.StringIO()
        with patch.object(entry,'initialize_corpus',side_effect=ValueError('SECRET')),contextlib.redirect_stderr(output):
            self.assertEqual(entry.main(['uvicorn']),1)
        self.assertNotIn('SECRET',output.getvalue())
        self.assertIn('ValueError',output.getvalue())

    def test_preflight_checks_release_and_closes_client(self):
        client=Mock()
        readiness=Mock(return_value={'status':'ready','collection':'release'})
        fake=SimpleNamespace(client=client,readiness=readiness)
        env={'RAG_SERVICE_TOKEN':'test-read','RAG_ADMIN_TOKEN':'test-admin','QDRANT_URL':'https://example.test'}
        with patch.object(entry,'initialize_corpus'),patch.dict(os.environ,env), \
             patch.dict('sys.modules',{'retrieval_service':fake}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(entry.main(['--check']),0)
        readiness.assert_called_once()
        client.close.assert_called_once()

    def test_incompatible_release_rejects_preflight_without_leaking_details(self):
        fake=SimpleNamespace(client=Mock(),readiness=Mock(side_effect=ValueError('SECRET')))
        output=io.StringIO()
        env={'RAG_SERVICE_TOKEN':'test-read','RAG_ADMIN_TOKEN':'test-admin','QDRANT_URL':'https://example.test'}
        with patch.object(entry,'initialize_corpus'),patch.dict(os.environ,env), \
             patch.dict('sys.modules',{'retrieval_service':fake}),contextlib.redirect_stderr(output):
            self.assertEqual(entry.main(['--check']),1)
        self.assertNotIn('SECRET',output.getvalue())
        fake.client.close.assert_called_once()

    def test_deployment_modes_dispatch_to_transaction(self):
        state={'status':'prepared','collection':'candidate'}
        fake=SimpleNamespace(prepare_release=Mock(return_value=state),check_release=Mock(return_value=state),publish_release=Mock(return_value=state),rollback_release=Mock(return_value=state))
        env={'RAG_SERVICE_TOKEN':'test-read','RAG_ADMIN_TOKEN':'test-admin','QDRANT_URL':'https://example.test'}
        with patch.object(entry,'initialize_corpus') as initialize,patch.dict(os.environ,env), \
             patch.dict('sys.modules',{'deployment_release':fake}),contextlib.redirect_stdout(io.StringIO()):
            for mode in ['--prepare-release','--check-release','--publish-release','--rollback-release']:
                self.assertEqual(entry.main([mode,'run1']),0,mode)
        self.assertEqual(initialize.call_count,3)
        for operation in [fake.prepare_release,fake.check_release,fake.publish_release,fake.rollback_release]:
            operation.assert_called_once_with('run1')

    def test_rollback_skips_source_bootstrap_and_new_model_configuration(self):
        fake=SimpleNamespace(rollback_release=Mock(return_value={'status':'rolled_back'}))
        with patch.object(entry,'initialize_corpus',side_effect=AssertionError('must not bootstrap')), \
             patch.object(entry,'seed_artifacts',side_effect=AssertionError('must not seed')), \
             patch.dict(os.environ,{'RAG_ADMIN_TOKEN':'','RAG_SERVICE_TOKEN':''}), \
             patch.dict('sys.modules',{'deployment_release':fake}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(entry.main(['--rollback-release','run1']),0)

    def test_volume_preparation_does_not_follow_symlinks(self):
        models=self.root/'models';models.mkdir()
        outside=self.root/'outside';outside.write_text('keep')
        (models/'link').symlink_to(outside)
        self.data.mkdir()
        account=SimpleNamespace(pw_uid=99999,pw_gid=99999)
        with patch.object(entry,'MODEL_DIR',models),patch.object(entry.os,'geteuid',return_value=0), \
             patch('pwd.getpwnam',return_value=account),patch.object(entry.os,'chown') as chown:
            entry.prepare_volumes()
        touched={call.args[0] for call in chown.call_args_list}
        self.assertIn(models,touched)
        self.assertIn(self.data,touched)
        self.assertNotIn(outside,touched)
        self.assertNotIn(models/'link',touched)


class DeploymentTests(unittest.TestCase):
    def run_deployment(self,mode,old=True,backup=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);binary=root/'docker';binary.write_text(FAKE_DOCKER);binary.chmod(0o755)
            containers={}
            if old: containers['rag']={'image':'previous-image','state':'running','health':'healthy'}
            if backup: containers['rag-previous']={'image':'older-image','state':'exited','health':'healthy'}
            state=root/'state.json';state.write_text(json.dumps({'containers':containers,'events':[],'alias':'old_e5' if old else None,'previous_alias':'old_e5' if old else None}))
            env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH'],
                'FAKE_DOCKER_STATE':str(state),'FAKE_DOCKER_MODE':mode,
                'IMAGE_NAME':'retrieval','BUILD_NUMBER':'2','CONTAINER_NAME':'rag','ENV_FILE':str(root/'test.env'),
                'RAG_NETWORK':'network','MODEL_VOLUME':'models','CORPUS_VOLUME':'corpus',
                'HOST_PORT':'8001','CONTAINER_PORT':'8001','HEALTH_ATTEMPTS':'2','HEALTH_DELAY':'0'}
            result=subprocess.run(['sh',str(ROOT/'deploy_rag.sh')],env=env,capture_output=True,text=True,timeout=30)
            return result,json.loads(state.read_text())

    def test_success_keeps_new_image_and_removes_previous_only_after_health(self):
        result,state=self.run_deployment('healthy')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(state['containers']['rag']['image'],'retrieval:2')
        self.assertEqual(state['alias'],'api_1536')
        self.assertEqual(state['preflight_alias'],'old_e5')
        events=state['events']
        prepare=next(i for i,x in enumerate(events) if '--prepare-release' in x)
        stop=next(i for i,x in enumerate(events) if x[0]=='stop')
        publish=next(i for i,x in enumerate(events) if '--publish-release' in x)
        start=next(i for i,x in enumerate(events) if x[0]=='run' and '-d' in x)
        self.assertLess(prepare,stop);self.assertLess(stop,publish);self.assertLess(publish,start)
        self.assertNotIn('rag-previous',state['containers'])
        events=state['events'];health=next(i for i,x in enumerate(events) if x[0]=='inspect' and 'State.Health' in x[2])
        remove=next(i for i,x in enumerate(events) if x==['rm','rag-previous'])
        self.assertGreater(remove,health)
        self.assertEqual(events[-1],['tag','retrieval:2','retrieval:latest'])

    def test_preflight_and_ownership_failures_do_not_stop_previous_container(self):
        for mode in ['preflight_failed','prepare_failed','candidate_failed']:
            result,state=self.run_deployment(mode)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(state['containers']['rag']['image'],'previous-image')
            self.assertEqual(state['containers']['rag']['state'],'running')
            self.assertFalse(any(x[0]=='stop' for x in state['events']))

    def test_start_health_timeout_and_rename_failures_restore_previous_container(self):
        for mode in ['start_failed','unhealthy','timeout','rename_failed','publish_failed','publish_uncertain']:
            result,state=self.run_deployment(mode)
            self.assertNotEqual(result.returncode,0,mode)
            self.assertEqual(state['containers']['rag']['image'],'previous-image',mode)
            self.assertEqual(state['containers']['rag']['state'],'running',mode)
            self.assertEqual(state['alias'],'old_e5',mode)
            self.assertNotIn('rag-previous',state['containers'])
            self.assertFalse(any(x[0]=='tag' for x in state['events']))

    def test_first_deployment_failure_removes_failed_container(self):
        result,state=self.run_deployment('unhealthy',old=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(state['containers'],{})

    def test_failed_rollback_keeps_previous_container_and_reports_manual_recovery(self):
        result,state=self.run_deployment('rollback_failed')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(state['containers']['rag']['image'],'previous-image')
        self.assertIn('Manual recovery required',result.stderr)
        self.assertNotIn('Previous retrieval container restored',result.stderr)

    def test_alias_rollback_failure_does_not_restart_service_with_wrong_vector_schema(self):
        result,state=self.run_deployment('alias_rollback_failed')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(state['alias'],'api_1536')
        self.assertEqual(state['containers']['rag']['state'],'exited')
        self.assertIn('Manual recovery required',result.stderr)
        self.assertFalse(any(x[0]=='start' for x in state['events']))

    def test_existing_backup_is_preserved(self):
        result,state=self.run_deployment('healthy',backup=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(len(state['containers']),2)
        self.assertFalse(any(x[0]=='run' for x in state['events']))

    def test_cleanup_failure_keeps_healthy_replacement(self):
        result,state=self.run_deployment('cleanup_failed')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(state['containers']['rag']['image'],'retrieval:2')
        self.assertEqual(state['containers']['rag-previous']['state'],'exited')

    def test_all_jenkins_shell_blocks_have_valid_shell_syntax(self):
        blocks=re.findall(r"sh '''(.*?)'''",(ROOT/'Jenkinsfile').read_text(),re.S)
        self.assertEqual(len(blocks),5)
        for block in blocks:
            result=subprocess.run(['sh','-n'],input=block,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run(['sh','-n',str(ROOT/'deploy_rag.sh')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
