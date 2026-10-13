"""Authenticated readiness and API embedding identity checks."""
import importlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from qdrant_client import models
from rag_models import embedding_identity, embedding_fingerprint


class RetrievalReadinessTests(unittest.TestCase):
    def setUp(self):
        key = patch('rag_models.OPENAI_API_KEY', 'test-key')
        key.start()
        self.addCleanup(key.stop)
        with patch('qdrant_client.QdrantClient'):
            self.service = importlib.import_module('retrieval_service')
        self.manifest = {**embedding_identity(), 'model_fingerprint': embedding_fingerprint(), 'point_count': 212}
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        (self.data / 'releases').mkdir()
        self.write_manifest()
        self.params = SimpleNamespace(vectors={'dense': SimpleNamespace(size=1536, distance=models.Distance.COSINE)}, sparse_vectors={'bm25': object()})
        self.client = Mock()
        self.client.get_collection.return_value = SimpleNamespace(config=SimpleNamespace(params=self.params))
        self.client.get_aliases.return_value = SimpleNamespace(aliases=[SimpleNamespace(alias_name=self.service.RAG_ALIAS, collection_name='test_release')])
        self.client.count.return_value = SimpleNamespace(count=212)
        for attribute, value in [('client', self.client), ('RAG_DATA_DIR', self.data)]:
            patcher = patch.object(self.service, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_manifest(self):
        (self.data / 'releases' / 'test_release.json').write_text(json.dumps(self.manifest))

    def test_startup_and_authenticated_health_report_api_embeddings(self):
        with patch.object(self.service, 'dense_model', return_value=object()), \
             patch.object(self.service, 'sparse_model', return_value=object()), \
             patch.object(self.service, 'rerank_model', return_value=object()), \
             patch.dict(os.environ, {'RAG_SERVICE_TOKEN': 'test-token'}):
            with TestClient(self.service.app) as http:
                response = http.get('/health/ready', headers={'x-rag-token': 'test-token'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['vectorSize'], 1536)
                self.assertIsNone(response.json()['modelRevision'])
                self.assertEqual(http.get('/health/ready').status_code, 401)

    def test_wrong_model_endpoint_tokenizer_and_fingerprint_remain_unhealthy(self):
        for key in ['embedding_model', 'embedding_base_url', 'tokenizer', 'model_fingerprint']:
            with self.subTest(key=key):
                self.manifest[key] = 'incorrect'
                self.write_manifest()
                with self.assertRaises(ValueError):
                    self.service.readiness()
                self.manifest = {**embedding_identity(), 'model_fingerprint': embedding_fingerprint(), 'point_count': 212}

    def test_old_768_vector_schema_is_rejected(self):
        self.params.vectors['dense'].size = 768
        with self.assertRaisesRegex(ValueError, 'vector schema'):
            self.service.readiness()

    def test_collection_count_mismatch_is_rejected(self):
        self.client.count.return_value.count = 1
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            self.service.readiness()

    def test_missing_credentials_are_unhealthy(self):
        with patch('rag_models.OPENAI_API_KEY', ''):
            with self.assertRaisesRegex(ValueError, 'Missing OPENAI_API_KEY'):
                self.service.readiness()

    def test_provider_errors_and_credentials_are_redacted(self):
        from openai import APIConnectionError
        import httpx
        error = APIConnectionError(message='private provider body', request=httpx.Request('GET', 'https://example.test'))
        self.assertEqual(self.service.safe_error(error), 'APIConnectionError')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'private-key'}):
            self.assertNotIn('private-key', self.service.safe_error(ValueError('bad private-key')))


if __name__ == '__main__':
    unittest.main()
