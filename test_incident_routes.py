"""Exercises the actual service's token dependency without loading the reranker."""
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from retrieval_service import app


class IncidentRoutesTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'RAG_SERVICE_TOKEN': 'test-incidents-private-token'})
        self.env.start()
        self.client = TestClient(app)
        self.headers = {'X-Rag-Token': 'test-incidents-private-token'}

    def tearDown(self):
        self.client.close()
        self.env.stop()

    def test_requires_existing_private_service_token(self):
        self.assertEqual(self.client.post('/incidents/analyze', json={'description': 'Ngập 50 cm'}).status_code, 401)

    def test_reuses_embedding_client_without_knowledge_index(self):
        with patch('rag_models.encode_dense', return_value=[[1.0] + [0.0]*1535]) as encode:
            result = self.client.post('/incidents/analyze', headers=self.headers, json={'description': 'duong ngap 50cm xe chet may'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['pipeline'], 'incidents-v1')
        self.assertEqual(len(result.json()['embedding']), 1536)
        self.assertTrue(result.json()['strandedVehicles'])
        encode.assert_called_once()

    def test_embedding_input_preserves_diacritics_and_expands_abbreviations(self):
        with patch('rag_models.encode_dense', return_value=[[1.0] + [0.0]*1535]) as encode:
            result = self.client.post('/incidents/analyze', headers=self.headers, json={'description': 'Đường ko ngập 20cm'})
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()['hasFloodEvidence'])
        encode.assert_called_once_with(['Đường ko ngập 20cm\nduong khong ngap 20cm'])

    def test_rejects_account_details_and_oversized_input(self):
        self.assertEqual(self.client.post('/incidents/analyze', headers=self.headers, json={'description': 'ngập', 'email': 'private@example.test'}).status_code, 422)
        self.assertEqual(self.client.post('/incidents/analyze', headers=self.headers, json={'description': 'x'*6001}).status_code, 422)

    def test_provider_failure_does_not_expose_private_body(self):
        with patch('rag_models.encode_dense', side_effect=RuntimeError('private upstream body')):
            response = self.client.post('/incidents/analyze', headers=self.headers, json={'description': 'Ngập 50 cm'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private upstream body', response.text)


if __name__ == '__main__':
    unittest.main()
