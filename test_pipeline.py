"""Real cl100k_base tokenizer corpus checks without touching active data."""
import unittest
from kb_common import read_jsonl
from pipeline_config import SOURCE_REGISTRY_PATH, EMBEDDING_DOCUMENT_PREFIX
from chunk_documents import get_tokenizer, token_count, chunk_document
from parse_markdown import parse_registry_record


class PipelineArtifactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A fresh checkout intentionally excludes generated data. Derive the
        # complete approved corpus in memory, never read/write the active KB.
        cls.registry = read_jsonl(SOURCE_REGISTRY_PATH)
        cls.documents = [parse_registry_record(row) for row in cls.registry
                         if row['ingest_eligible'] and
                         row['license_status'] == 'APPROVED_FOR_RAG']
        cls.chunks = [chunk for doc in cls.documents
                      for chunk in chunk_document(doc)]

    def test_exact_document_partition(self):
        expected = {r['document_id'] for r in self.registry
                    if r['ingest_eligible'] and r['license_status'] == 'APPROVED_FOR_RAG'}
        self.assertTrue(expected)
        self.assertEqual(expected, {d['document_id'] for d in self.documents})
        self.assertEqual(expected, {c['document_id'] for c in self.chunks})
        self.assertEqual(len(self.chunks), len({c['point_id'] for c in self.chunks}))

    def test_real_model_tokens_include_context_and_prefix(self):
        tok = get_tokenizer()
        for chunk in self.chunks:
            actual = token_count(EMBEDDING_DOCUMENT_PREFIX + chunk['embedding_text'], tok)
            self.assertEqual(actual, chunk['token_count'])
            self.assertLessEqual(actual, 450)

    def test_long_sentence_has_no_lost_words(self):
        text = ' '.join('điều' + str(i) for i in range(1000))
        doc = {'title': 'Kiểm thử', 'document_id': 'test', 'document_version': 1,
               'metadata': {}, 'sections': [{'section_index': 0,
               'section_path': ['An toàn'], 'text': text}]}
        chunks = chunk_document(doc, 450, 0)
        self.assertEqual(' '.join(c['text'] for c in chunks).split(), text.split())
        self.assertTrue(all(c['token_count'] <= 450 for c in chunks))

    def test_neighbors_stay_in_same_section(self):
        by_id = {c['point_id']: c for c in self.chunks}
        for chunk in self.chunks:
            for key in ['previous_point_id', 'next_point_id']:
                if chunk[key]:
                    self.assertEqual(by_id[chunk[key]]['parent_section_id'], chunk['parent_section_id'])


if __name__ == '__main__':
    unittest.main()
