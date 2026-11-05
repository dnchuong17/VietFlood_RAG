"""Exercises the actual service's token dependency without loading the reranker."""
import os
import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from retrieval_service import app
from incident_processing import NORMALIZATION_VERSION, incident_embedding_fingerprint


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
        self.assertEqual(result.json()['pipeline'], 'incidents-v2')
        self.assertEqual(result.json()['normalizationVersion'], NORMALIZATION_VERSION)
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
        with patch('rag_models.encode_dense', side_effect=RuntimeError('private upstream body')), \
             self.assertLogs('vietflood.incidents', level='WARNING') as logs:
            response = self.client.post('/incidents/analyze', headers=self.headers, json={'description': 'Ngập 50 cm'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'detail': 'Incident analysis unavailable'})
        self.assertNotIn('private upstream body', response.text + '\n'.join(logs.output))
        self.assertTrue(all(not entry.exc_info for entry in logs.records))

    def test_wrong_token_does_not_reach_encoder(self):
        with patch('rag_models.encode_dense') as encode:
            response = self.client.post('/incidents/analyze', headers={'X-Rag-Token': 'wrong'},
                                        json={'description': 'Ngập 50 cm'})
        self.assertEqual(response.status_code, 401)
        encode.assert_not_called()

    def test_analyze_and_benchmark_share_incident_only_identity_and_encoder_input(self):
        import export_incident_embeddings as exporter
        source = 'ko ngap; co nguoi duoi nuoc'
        vector = [1.0] + [0.0] * 1535
        with patch('rag_models.encode_dense', return_value=[vector]) as route_encode, \
             patch('rag_models.embedding_fingerprint', return_value='global-model-identity') as base:
            response = self.client.post('/incidents/analyze', headers=self.headers,
                                        json={'description': source})
            self.assertEqual(base(), 'global-model-identity')
        self.assertEqual(response.status_code, 200)
        analysis = response.json()
        self.assertEqual(analysis['fingerprint'], incident_embedding_fingerprint('global-model-identity'))
        self.assertFalse(analysis['hasFloodEvidence'])
        self.assertTrue(analysis['lifeThreat'])
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = os.path.join(directory, 'cases.json')
            output_path = os.path.join(directory, 'embeddings.json')
            with open(dataset_path, 'w', encoding='utf-8') as stream:
                json.dump({'cases': [{'report': {'description': source},
                                      'candidate': {'description': source}}]}, stream)
            with patch.object(exporter, 'encode_dense', return_value=[vector]) as export_encode, \
                 patch.object(exporter, 'embedding_fingerprint', return_value='global-model-identity'), \
                 patch.object(sys, 'argv', ['export_incident_embeddings.py', dataset_path, output_path]), \
                 contextlib.redirect_stdout(io.StringIO()):
                exporter.main()
            with open(output_path, encoding='utf-8') as stream:
                artifact = json.load(stream)
        self.assertEqual(artifact['analyses'][source], analysis)
        self.assertEqual(export_encode.call_args, route_encode.call_args)
        self.assertEqual(len(artifact['analyses']), 1)

    def test_unconfigured_token_fails_closed_for_both_routes(self):
        with patch.dict(os.environ, {'RAG_SERVICE_TOKEN': ''}), patch('rag_models.encode_dense') as encode:
            for route, body in [('analyze', {'description': 'Ngập'}),
                                ('similarity', {'vector': [1.0] * 1536, 'candidates': [[1.0] * 1536]})]:
                response = self.client.post('/incidents/' + route, headers=self.headers, json=body)
                self.assertEqual(response.status_code, 401)
            encode.assert_not_called()

    def test_blank_input_is_rejected_without_calling_provider(self):
        with patch('rag_models.encode_dense') as encode:
            response = self.client.post('/incidents/analyze', headers=self.headers,
                                        json={'description': ' \t\n '})
        self.assertEqual(response.status_code, 422)
        encode.assert_not_called()

    def test_similarity_auth_and_raw_cosine_scores_not_probabilities(self):
        vector = [1.0] + [0.0] * 1535
        body = {'vector': vector, 'candidates': [vector, [-v for v in vector]]}
        self.assertEqual(self.client.post('/incidents/similarity', json=body).status_code, 401)
        self.assertEqual(self.client.post('/incidents/similarity', headers={'X-Rag-Token': 'wrong'}, json=body).status_code, 401)
        response = self.client.post('/incidents/similarity', headers=self.headers, json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'scores': [1.0, -1.0]})
        body['candidates'] = [[1.0]]
        response = self.client.post('/incidents/similarity', headers=self.headers, json=body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'detail': 'Invalid vectors'})

    def test_exporter_preserves_keys_deduplicates_and_includes_runner_up(self):
        import export_incident_embeddings as exporter
        sources = ['Đường ngp 0,5m', 'ko co nguoi macket', 'Có người đuối nước']
        vectors = [[float(i + 1)] + [0.0] * 1535 for i in range(3)]
        dataset = {'cases': [{'report': {'description': sources[0]},
                              'candidate': {'description': sources[1]},
                              'runnerUp': {'description': sources[2]}},
                             {'report': {'description': sources[0]},
                              'candidate': {'description': sources[1]}}]}
        with tempfile.TemporaryDirectory() as directory:
            dataset_path, output_path = os.path.join(directory, 'cases.json'), os.path.join(directory, 'embeddings.json')
            with open(dataset_path, 'w', encoding='utf-8') as stream:
                json.dump(dataset, stream)
            with patch.object(exporter, 'encode_dense', return_value=vectors) as encode, \
                 patch.object(exporter, 'embedding_fingerprint', return_value='base'), \
                 patch.object(sys, 'argv', ['export_incident_embeddings.py', dataset_path, output_path]), \
                 contextlib.redirect_stdout(io.StringIO()):
                exporter.main()
            with open(output_path, encoding='utf-8') as stream:
                analyses = json.load(stream)['analyses']
        self.assertEqual(list(analyses), sources)
        self.assertEqual(len(encode.call_args.args[0]), 3)
        for source, vector in zip(sources, vectors, strict=True):
            self.assertEqual(analyses[source]['normalizedText'], source)
            self.assertEqual(analyses[source]['embedding'], vector)
            self.assertEqual(analyses[source]['pipeline'], 'incidents-v2')
            self.assertEqual(analyses[source]['fingerprint'], incident_embedding_fingerprint('base'))


if __name__ == '__main__':
    unittest.main()
