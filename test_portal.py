"""Upload HTTP and local-Qdrant tests. Production is never contacted."""
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from filelock import FileLock
from qdrant_client import QdrantClient, models
import corpus_storage
import portal
from kb_common import read_markdown, sha256_text, normalize_text

PROJECT = Path(__file__).resolve().parent
NEW_GUIDE = PROJECT/'vietflood-user-guide.md'
if not NEW_GUIDE.exists():
    NEW_GUIDE = PROJECT.parent/'vietflood-user-guide.md'
OLD = '''---
source_ids: [VietFlood_FE_Clone, VietFlood_mobile]
title: Old user guide
source_url: https://github.com/dnchuong17/Vietflood_FE_Clone
language: en
representation: user-guide
accessed_at: 2026-10-12
rechecked_at: 2026-10-12
verification_status: verified
---
# Old user guide

Old mobile and website instructions.
'''

# Public tests use synthetic content; an operator-provided guide stays local.
GUIDE_BYTES = NEW_GUIDE.read_bytes() if NEW_GUIDE.exists() else (
    OLD.replace('[VietFlood_FE_Clone, VietFlood_mobile]', '[VietFlood_FE_Clone, VietFlood]')
       .replace('Old user guide', 'New website guide')
       .replace('language: en', 'language: vi')
    + '\n## Account instructions\n\n' + ('Example account guidance. ' * 200)
).encode('utf-8')
GUIDE_BODY = normalize_text(GUIDE_BYTES.decode('utf-8-sig').split('---', 2)[2])

class ImmediateThread:
    def __init__(self, target, args, **kwargs): self.target,self.args=target,args
    def start(self): self.target(*self.args)

class PortalTest(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.data=self.root/'data';self.data.mkdir()
        self.seed=self.root/'seed';(self.seed/'markdown').mkdir(parents=True)
        (self.seed/'markdown/guide.md').write_text(OLD)
        (self.seed/'markdown/other.md').write_text(OLD.replace('[VietFlood_FE_Clone, VietFlood_mobile]','[G02]').replace('Old user guide','Other document'))
        rows=[]
        for p in (self.seed/'markdown').glob('*.md'):
            m,b=read_markdown(p)
            rows.append(dict(document_id=m['source_ids'][0],source_ids=m['source_ids'],file_name=p.name,
                file_path='rag_sources/markdown/'+p.name,title=m['title'],source_url=m['source_url'],
                document_version=1,content_hash=sha256_text(b),ingest_eligible=True))
        (self.seed/'source_registry.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        self.sources=self.data/'sources';self.registry=self.data/'source_registry.jsonl';self.db=self.root/'qdrant'
        self.env={'RAG_ADMIN_TOKEN':'test-admin-secret','RAG_SERVICE_TOKEN':'test-read-secret',
            'RAG_SOURCE_DIR':str(self.sources),'RAG_DATA_DIR':str(self.data),'QDRANT_CHAT_COLLECTION':'test_active',
            'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','PYTHONDONTWRITEBYTECODE':'1',
            'OPENAI_API_KEY':'test-only-unused-key'}
        self.stack.enter_context(patch.dict(os.environ,self.env))
        for module,values in [
            (portal,dict(RAG_DATA_DIR=self.data,MARKDOWN_DIR=self.sources,SOURCE_REGISTRY_PATH=self.registry,
                JOB_PATH=self.data/'upload_job.json',INGEST_MANIFEST_PATH=self.data/'ingest_manifest.json')),
            (corpus_storage,dict(RAG_DATA_DIR=self.data,MARKDOWN_DIR=self.sources,SEED_MARKDOWN_DIR=self.seed/'markdown',
                PROJECT_ROOT=self.seed,SOURCE_REGISTRY_PATH=self.registry))]:
            for k,v in values.items(): self.stack.enter_context(patch.object(module,k,v))
        self.client=TestClient(portal.app);self.headers={'X-Rag-Admin-Token':'test-admin-secret'}
        self.real_run=subprocess.run

    def upload(self,body=None,name='guide.md',target='VietFlood_FE_Clone'):
        return self.client.put('/api/documents/'+target,files={'file':(name,GUIDE_BYTES if body is None else body)},headers=self.headers)

    def run_pipeline(self,*args,**kwargs):
        script='''
import sys,types,hashlib
from unittest.mock import patch
from chunk_documents import get_tokenizer
import pipeline_config
model=types.SimpleNamespace(tokenizer=get_tokenizer())
if hasattr(model.tokenizer,'init_kwargs'):
    model.tokenizer.init_kwargs['_commit_hash']='test-model-revision'
def encode(texts,batch_size=16):
    dimensions=getattr(pipeline_config,'EMBEDDING_DIMENSIONS',768)
    return [[1.0]+[b/255 for b in hashlib.sha256(t.encode()).digest()]+[0.0]*(dimensions-33) for t in texts]
sys.argv=['sync_pipeline.py','--local-path',sys.argv[1],'--collection','test_active']
with patch('rag_models.dense_model',return_value=model),patch('rag_models.encode_dense',side_effect=encode):
    import sync_pipeline
    sync_pipeline.main()
'''
        return self.real_run([sys.executable,'-c',script,str(self.db)],cwd=PROJECT,
            env={**os.environ,**self.env},capture_output=True,text=True,timeout=120)

    def test_auth_and_disabled_admin_before_body_parsing(self):
        for method,path in [('GET','/api/status'),('GET','/api/documents'),('POST','/api/import'),
                ('PUT','/api/documents/VietFlood_FE_Clone'),('POST','/api/retry')]:
            self.assertEqual(self.client.request(method,path,content=b'invalid multipart').status_code,401)
        with patch.dict(os.environ,{'RAG_ADMIN_TOKEN':''}):
            self.assertEqual(self.client.get('/api/status',headers=self.headers).status_code,503)
        self.assertFalse(self.sources.exists())

    def test_mount_uses_separate_admin_auth(self):
        with patch('qdrant_client.QdrantClient'):
            service=importlib.import_module('retrieval_service')
        client=TestClient(service.app)
        self.assertEqual(client.get('/').status_code,200)
        self.assertIn('Kết nối quản trị',client.get('/admin/').text)
        self.assertEqual(client.get('/admin/api/status',headers={'X-Rag-Token':'test-read-secret'}).status_code,401)
        self.assertEqual(client.get('/admin/api/status',headers=self.headers).status_code,200)
        self.assertEqual(client.get('/health/ready',headers=self.headers).status_code,401)

    def test_validation_does_not_modify_sources(self):
        cases=[('bad.txt',OLD.encode(),400),('bad.md',b'\xff',400),('bad.md',b'# no metadata',400),
            ('large.md',b'x'*(portal.MAX_UPLOAD_BYTES+1),413),
            ('bad.md',OLD.replace('user-guide','[user-guide]').encode(),400),
            ('bad.md',OLD.replace('title: Old user guide','title: &x [*x]').encode(),400),
            ('bad.md',OLD.replace('https://github.com/dnchuong17/Vietflood_FE_Clone','file:///etc/passwd').encode(),400)]
        for name,body,code in cases:
            response=self.client.post('/api/import',files={'file':(name,body)},headers=self.headers)
            self.assertEqual(response.status_code,code,response.text)
        self.assertEqual(self.upload(target='UNKNOWN').status_code,404)
        self.assertEqual(self.upload(body=OLD.replace('[VietFlood_FE_Clone, VietFlood_mobile]','[CHANGED]').encode()).status_code,400)
        self.assertEqual((self.sources/'guide.md').read_text(),OLD)

    def test_initial_readiness_failure_can_recover_after_upload(self):
        with patch('qdrant_client.QdrantClient'):
            service=importlib.import_module('retrieval_service')
        with patch.object(service,'dense_model',return_value=object()), \
             patch.object(service,'sparse_model',return_value=object()), \
             patch.object(service,'rerank_model',return_value=object()), \
             patch.object(service,'readiness',side_effect=[ValueError('No release yet'),{'status':'ready'}]):
            with TestClient(service.app) as client:
                response=client.get('/health/ready',headers={'X-Rag-Token':'test-read-secret'})
                self.assertEqual(response.status_code,200,response.text)

    def test_chunked_size_limit(self):
        response=self.client.post('/api/import',content=(b'x'*(1024*1024) for _ in range(12)),headers=self.headers)
        self.assertEqual(response.status_code,413)

    def test_seed_persists_edits_and_deletions(self):
        corpus_storage.initialize_corpus()
        (self.sources/'guide.md').write_text('operator edit');(self.sources/'other.md').unlink()
        corpus_storage.initialize_corpus()
        self.assertEqual((self.sources/'guide.md').read_text(),'operator edit')
        self.assertFalse((self.sources/'other.md').exists())

    def test_busy_rejected_before_source_write(self):
        corpus_storage.initialize_corpus()
        with FileLock(str(self.data/'upload.lock'),timeout=0): self.assertEqual(self.upload().status_code,409)
        self.assertEqual((self.sources/'guide.md').read_text(),OLD)

    def test_pagination_and_redacted_manifest(self):
        response=self.client.get('/api/documents?limit=1',headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertEqual(len(response.json()['items']),1)
        self.assertEqual(response.json()['nextOffset'],1)
        self.assertEqual(self.client.get('/api/documents?limit=101',headers=self.headers).status_code,422)
        (self.data/'ingest_manifest.json').write_text(json.dumps({'collection':'safe','source_chunks':'SECRET_PATH','point_ids':['SECRET_ID']}))
        self.assertNotIn('SECRET',self.client.get('/api/status',headers=self.headers).text)

    def test_failure_is_persisted_sanitized_and_retryable(self):
        with patch('portal.threading.Thread',ImmediateThread),patch('portal.subprocess.run',return_value=types.SimpleNamespace(returncode=1,stdout='SECRET /private/path')):
            self.assertEqual(self.upload().status_code,202)
            status=self.client.get('/api/status',headers=self.headers)
            self.assertEqual(status.json()['job']['status'],'failed');self.assertNotIn('SECRET',status.text)
            self.assertEqual(self.client.post('/api/retry',headers=self.headers).status_code,202)
        self.assertEqual(json.loads((self.data/'upload_job.json').read_text())['status'],'failed')

    def test_real_pipeline_replacement_preserves_other_document_and_versions(self):
        corpus_storage.initialize_corpus()
        initial=self.run_pipeline();self.assertEqual(initial.returncode,0,initial.stderr)
        db=QdrantClient(path=str(self.db));points,_=db.scroll('test_active',limit=100,with_vectors=True)
        old_guide=[p for p in points if p.payload['document_id']=='VietFlood_FE_Clone']
        other={str(p.id):p for p in points if p.payload['document_id']=='G02'};db.close()
        with patch('portal.threading.Thread',ImmediateThread),patch('portal.subprocess.run',side_effect=self.run_pipeline):
            for _ in range(2):
                response=self.upload(name='../../escape.md');self.assertEqual(response.status_code,202,response.text)
                status=self.client.get('/api/status',headers=self.headers).json()
                self.assertEqual(status['job']['status'],'complete',status)
        snap=json.loads((self.data/'snapshots/VietFlood_FE_Clone/2.json').read_text())
        self.assertEqual(snap['text'],GUIDE_BODY)
        self.assertTrue((self.data/'snapshots/VietFlood_FE_Clone/1.json').exists())
        self.assertFalse((self.root/'escape.md').exists())
        rows=[json.loads(line) for line in self.registry.read_text().splitlines()]
        self.assertEqual(next(r for r in rows if r['document_id']=='VietFlood_FE_Clone')['document_version'],2)
        db=QdrantClient(path=str(self.db));self.assertEqual(db.retrieve('test_active',[p.id for p in old_guide]),[])
        for p in db.retrieve('test_active',list(other),with_vectors=True):
            self.assertEqual(p.payload,other[str(p.id)].payload)
            for a,b in zip(p.vector['dense'],other[str(p.id)].vector['dense']): self.assertAlmostEqual(a,b,places=6)
        guide_filter=models.Filter(must=[models.FieldCondition(key='document_id',match=models.MatchValue(value='VietFlood_FE_Clone'))])
        self.assertGreater(db.count('test_active',count_filter=guide_filter,exact=True).count,1);db.close()

if __name__=='__main__': unittest.main()
