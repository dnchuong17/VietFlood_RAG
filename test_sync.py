"""Opt-in isolated local-Qdrant replacement/rollback test; no production mutation."""
import json,os,subprocess,sys,tempfile,unittest,uuid
from pathlib import Path
from qdrant_client import QdrantClient
from kb_common import read_jsonl,sha256_text
from pipeline_config import CHUNKS_PATH,PROJECT_ROOT

@unittest.skipUnless(os.getenv('RAG_SYNC_TESTS')=='1','Set RAG_SYNC_TESTS=1 to run isolated sync verification')
class SyncTest(unittest.TestCase):
 def test_replace_delete_and_failure_do_not_leave_stale_active_points(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);data=root/'data';data.mkdir();db=root/'qdrant'
   original=read_jsonl(CHUNKS_PATH)[0]
   env={**os.environ,'RAG_DATA_DIR':str(data)}
   (data/'parsed_documents.jsonl').write_text('')
   def run(chunks,success=True):
    (data/'chunks.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks))
    result=subprocess.run([sys.executable,'ingest_qdrant.py','--local-path',str(db),'--collection','test_active'],cwd=PROJECT_ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    self.assertEqual(result.returncode==0,success,result.stderr[-1000:])
   def inspect():
    client=QdrantClient(path=str(db));alias=next(a.collection_name for a in client.get_aliases().aliases if a.alias_name=='test_active');count=client.count('test_active',exact=True).count;client.close();return alias,count
   run([original]);self.assertEqual(inspect()[1],1)
   changed={**original,'point_id':str(uuid.uuid4()),'text':original['text']+'\nThông tin đã cập nhật.','embedding_text':original['embedding_text']+'\nThông tin đã cập nhật.'}
   changed['chunk_hash']=sha256_text(changed['embedding_text']);run([changed])
   client=QdrantClient(path=str(db));self.assertEqual(client.retrieve('test_active',[original['point_id']]),[]);self.assertEqual(len(client.retrieve('test_active',[changed['point_id']])),1);client.close()
   run([]);before=inspect();self.assertEqual(before[1],0)
   bad={**changed,'embedding_text':' '.join(['quá dài']*2000),'chunk_hash':'bad'}
   run([bad],False);self.assertEqual(inspect(),before)
if __name__=='__main__': unittest.main()
