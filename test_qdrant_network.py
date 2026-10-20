"""Run the real shell resolver against Docker metadata, without guessing names."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent
DOCKER=r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
p=Path(os.environ['DOCKER_STATE']);s=json.loads(p.read_text());a=sys.argv[1:]
s['events'].append(a);out='';code=0
if a[0]=='ps':out='\n'.join(name+' '+item['image'] for name,item in s['containers'].items() if item['running'])
elif a[0]=='inspect':
 item=s['containers'].get(a[-1]);code=0 if item else 1
 if item:out=('/'+a[-1]) if a[2]=='{{.Name}}' else str(item['running']).lower()
elif a[:2]==['network','inspect'] and '--format' in a:out='\n'.join(s['members'])
elif a[:2]==['network','connect']:
 if s.get('connect_failed'):code=1
 else:s['members'].append(a[-1])
p.write_text(json.dumps(s))
if out:print(out)
sys.exit(code)
'''


class QdrantNetworkTests(unittest.TestCase):
    def resolve(self,containers=None,members=None,env_text='',extra=None,connect_failed=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);binary=root/'docker';binary.write_text(DOCKER);binary.chmod(0o755)
            state=root/'state.json'
            state.write_text(json.dumps({'containers':containers or {},'members':members or [],'events':[],'connect_failed':connect_failed}))
            config=root/'deployment.env';config.write_text(env_text)
            env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH'],
                 'DOCKER_STATE':str(state),'ENV_FILE':str(config),'RAG_NETWORK':'jenkins_default',
                 'QDRANT_LOCAL_DOCKER':'1','QDRANT_INTERNAL_URL':'','QDRANT_CONTAINER':'',**(extra or {})}
            result=subprocess.run(['sh','-eu','-c','. "$1"; printf "%s" "$QDRANT_INTERNAL_URL"',
                                   'resolver',str(ROOT/'qdrant_network.sh')],env=env,capture_output=True,text=True,timeout=10)
            return result,json.loads(state.read_text())

    def containers(self,*names):
        return {name:{'image':'qdrant/qdrant:v1.15.5','running':True} for name in names}

    def test_discovers_actual_container_and_connects_to_shared_network(self):
        result,state=self.resolve(self.containers('storage-vectors-1'))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'http://storage-vectors-1:6333')
        self.assertEqual(state['members'],['storage-vectors-1'])

    def test_existing_membership_is_not_changed(self):
        result,state=self.resolve(self.containers('vectors'),members=['vectors'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(any(a[:2]==['network','connect'] for a in state['events']))

    def test_ambiguous_and_absent_containers_fail_without_guessing(self):
        for containers in [{},self.containers('first','second')]:
            result,state=self.resolve(containers)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('QDRANT_CONTAINER',result.stderr)
            self.assertFalse(any(a[:2]==['network','connect'] for a in state['events']))

    def test_explicit_container_is_read_without_evaluating_env_file(self):
        result,state=self.resolve(self.containers('first','second'),env_text='OTHER=$(exit 71)\nSECRET=private-key\nQDRANT_CONTAINER=second\n')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'http://second:6333')
        self.assertNotIn('private-key',result.stderr+result.stdout)
        self.assertFalse(any(a[0]=='ps' for a in state['events']))

    def test_explicit_internal_url_preserves_custom_port_and_skips_discovery(self):
        result,state=self.resolve(env_text='QDRANT_INTERNAL_URL=http://custom-db:7333\n')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'http://custom-db:7333')
        self.assertEqual(state['events'],[])

    def test_remote_deployment_mode_does_not_discover_local_databases(self):
        result,state=self.resolve(extra={'QDRANT_LOCAL_DOCKER':'0'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'')
        self.assertEqual(state['events'],[])

    def test_stopped_container_is_rejected_before_network_change(self):
        result,state=self.resolve({'db':{'image':'custom/db','running':False}},env_text='QDRANT_CONTAINER=db\n')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(state['members'],[])

    def test_failed_network_attachment_stops_deployment(self):
        result,state=self.resolve(self.containers('db'),connect_failed=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(state['members'],[])

    def test_invalid_explicit_container_name_is_not_executed(self):
        result,state=self.resolve(env_text='QDRANT_CONTAINER=$(exit 71)\n')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Invalid QDRANT_CONTAINER',result.stderr)
        self.assertEqual(state['events'],[])


if __name__=='__main__':unittest.main()
