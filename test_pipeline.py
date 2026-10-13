"""Integrity and token-boundary checks against the actual E5 tokenizer/artifacts."""
import json,unittest
from kb_common import read_jsonl
from pipeline_config import CHUNKS_PATH,PARSED_DOCUMENTS_PATH,SOURCE_REGISTRY_PATH,EMBEDDING_DOCUMENT_PREFIX
from chunk_documents import get_tokenizer,token_count,chunk_document

class PipelineArtifactsTest(unittest.TestCase):
 def test_exact_document_partition(self):
  registry=read_jsonl(SOURCE_REGISTRY_PATH);docs=read_jsonl(PARSED_DOCUMENTS_PATH);chunks=read_jsonl(CHUNKS_PATH)
  expected={r['document_id'] for r in registry if r['ingest_eligible'] and r['license_status']=='APPROVED_FOR_RAG'}
  self.assertEqual(expected,{d['document_id'] for d in docs});self.assertEqual(expected,{c['document_id'] for c in chunks})
  self.assertEqual(len(chunks),len({c['point_id'] for c in chunks}))
 def test_real_model_tokens_include_context_and_prefix(self):
  tok=get_tokenizer()
  for c in read_jsonl(CHUNKS_PATH):
   actual=token_count(EMBEDDING_DOCUMENT_PREFIX+c['embedding_text'],tok)
   self.assertEqual(actual,c['token_count']);self.assertLessEqual(actual,450)
 def test_long_sentence_has_no_lost_words(self):
  text=' '.join('điều'+str(i) for i in range(1000))
  doc={'title':'Kiểm thử','document_id':'test','document_version':1,'metadata':{},'sections':[{'section_index':0,'section_path':['An toàn'],'text':text}]}
  chunks=chunk_document(doc,450,0)
  self.assertEqual(' '.join(c['text'] for c in chunks).split(),text.split())
  self.assertTrue(all(c['token_count']<=450 for c in chunks))
 def test_neighbors_stay_in_same_section(self):
  chunks=read_jsonl(CHUNKS_PATH);by_id={c['point_id']:c for c in chunks}
  for c in chunks:
   for key in ['previous_point_id','next_point_id']:
    if c[key]: self.assertEqual(by_id[c[key]]['parent_section_id'],c['parent_section_id'])
if __name__=='__main__': unittest.main()
