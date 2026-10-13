"""Isolated local-Qdrant candidate, publication, cache and rollback checks."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from qdrant_client import QdrantClient
import ingest_qdrant as ingest


class SyncTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        self.client = QdrantClient(path=str(self.data / 'qdrant'))
        self.addCleanup(self.client.close)
        for name, value in [('RAG_DATA_DIR', self.data), ('INGEST_MANIFEST_PATH', self.data / 'manifest.json'),
                            ('PARSED_DOCUMENTS_PATH', self.data / 'docs.jsonl')]:
            patcher = patch.object(ingest, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.chunk = {'point_id': 'b7f186de-263c-41da-a74e-9d29c9a4b92f', 'document_id': 'test',
                      'document_version': 1, 'chunk_hash': 'first', 'embedding_text': 'An toàn trước lũ.',
                      'text': 'An toàn trước lũ.', 'metadata': {'license_status': 'APPROVED_FOR_RAG'}}
        self.args = SimpleNamespace(chunks=self.data / 'chunks.jsonl', collection='test_active',
                                    batch_size=16, upsert_batch_size=64, no_publish=False)
        self.args.chunks.write_text(json.dumps(self.chunk) + '\n')
        ingest.PARSED_DOCUMENTS_PATH.write_text(json.dumps({'document_id': 'test', 'document_version': 1,
            'title': 'Test', 'body': 'An toàn trước lũ.', 'metadata': {'license_status': 'APPROVED_FOR_RAG', 'source_url': 'https://example.test'}}) + '\n')
        sparse = SimpleNamespace(embed=lambda texts: [SimpleNamespace(indices=np.array([1]), values=np.array([1.0])) for _ in texts])
        patcher = patch.object(ingest, 'sparse_model', return_value=sparse)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(ingest, 'encode_dense', side_effect=lambda texts, _: [[0.1] * 1536 for _ in texts])
        self.encode = patcher.start()
        self.addCleanup(patcher.stop)

    def alias(self):
        return {a.alias_name: a.collection_name for a in self.client.get_aliases().aliases}.get('test_active')

    def test_candidate_does_not_switch_alias_until_publication(self):
        old = ingest.build_candidate(self.client, self.args)
        self.args.no_publish = True
        candidate = ingest.build_candidate(self.client, self.args)
        self.assertEqual(self.alias(), old['collection'])
        self.assertEqual(json.loads(ingest.INGEST_MANIFEST_PATH.read_text())['collection'], old['collection'])
        self.assertEqual(candidate['embedded_this_run'], 0)
        self.assertEqual(candidate['reused_embeddings'], 1)
        self.assertEqual(self.encode.call_count, 1)
        ingest.publish_release(self.client, candidate, 'test_active')
        self.assertEqual(self.alias(), candidate['collection'])

    def test_invalid_candidate_preserves_active_alias(self):
        old = ingest.build_candidate(self.client, self.args)
        self.args.no_publish = True
        candidate = ingest.build_candidate(self.client, self.args)
        candidate['model_fingerprint'] = 'invalid'
        with self.assertRaisesRegex(ValueError, 'fingerprint'):
            ingest.publish_release(self.client, candidate, 'test_active')
        self.assertEqual(self.alias(), old['collection'])

    def test_manifest_write_failure_restores_previous_alias(self):
        old = ingest.build_candidate(self.client, self.args)
        self.args.no_publish = True
        candidate = ingest.build_candidate(self.client, self.args)
        with patch.object(ingest, 'atomic_json', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                ingest.publish_release(self.client, candidate, 'test_active')
        self.assertEqual(self.alias(), old['collection'])

    def test_stale_candidate_is_rejected(self):
        ingest.build_candidate(self.client, self.args)
        self.args.no_publish = True
        first = ingest.build_candidate(self.client, self.args)
        second = ingest.build_candidate(self.client, self.args)
        ingest.publish_release(self.client, first, 'test_active')
        with self.assertRaisesRegex(ValueError, 'stale'):
            ingest.publish_release(self.client, second, 'test_active')

    def test_delete_sync_removes_active_points_and_preserves_old_collection(self):
        old = ingest.build_candidate(self.client, self.args)
        self.args.chunks.write_text('')
        empty = ingest.build_candidate(self.client, self.args)
        self.assertEqual(empty['point_count'], 0)
        self.assertEqual(self.client.count('test_active', exact=True).count, 0)
        self.assertEqual(self.client.count(old['collection'], exact=True).count, 1)

    def test_corrupt_cache_and_vector_schema_cannot_be_published(self):
        old = ingest.build_candidate(self.client, self.args)
        cache = next((self.data / 'embedding_cache').glob('*.json'))
        cache.write_text('{"dense":[1]}')
        self.args.no_publish = True
        with self.assertRaisesRegex(ValueError, 'embedding vector'):
            ingest.build_candidate(self.client, self.args)
        self.assertEqual(self.alias(), old['collection'])


if __name__ == '__main__':
    unittest.main()
