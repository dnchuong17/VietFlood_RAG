"""Embedding contracts tested without paid API calls."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import httpx
from openai import OpenAI
import rag_models as models


def vector(value=0.1):
    return [value] * 1536


def item(index, value=0.1):
    return SimpleNamespace(index=index, embedding=vector(value))


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.embeddings.create.return_value = SimpleNamespace(data=[item(0)])
        self.patch = patch.object(models, 'dense_model', return_value=self.client)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_request_and_out_of_order_indices(self):
        self.client.embeddings.create.return_value = SimpleNamespace(data=[item(1, 0.2), item(0)])
        self.assertEqual(models.encode_dense(['ngập lụt', 'an toàn']), [vector(), vector(0.2)])
        self.client.embeddings.create.assert_called_once_with(
            model='text-embedding-3-small', input=['ngập lụt', 'an toàn'],
            dimensions=1536, encoding_format='float')

    def test_batch_order_is_preserved(self):
        self.client.embeddings.create.side_effect = [SimpleNamespace(data=[item(0, n)]) for n in [0.1, 0.2, 0.3]]
        self.assertEqual(models.encode_dense(['one', 'two', 'three'], 1), [vector(n) for n in [0.1, 0.2, 0.3]])

    def test_missing_duplicate_and_out_of_range_indices_are_rejected(self):
        for data in [[], [item(1)], [item(-1)], [item(0), item(0)], [item(True)]]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.client.embeddings.create.return_value = SimpleNamespace(data=data)
                models.encode_dense(['flood'])

    def test_invalid_vectors_are_rejected(self):
        for value in [[0.1], vector(float('nan')), vector(float('inf')), vector('bad'), vector(True)]:
            with self.subTest(value=value[:1]), self.assertRaises(ValueError):
                self.client.embeddings.create.return_value = SimpleNamespace(data=[SimpleNamespace(index=0, embedding=value)])
                models.encode_dense(['flood'])

    def test_empty_inputs_and_token_limits(self):
        self.assertEqual(models.encode_dense([]), [])
        for texts in [[''], ['  '], [None]]:
            with self.assertRaises(ValueError):
                models.encode_dense(texts)
        with patch.object(models, 'token_count', return_value=8192), self.assertRaisesRegex(ValueError, 'token limit'):
            models.encode_dense(['too long'])
        self.client.embeddings.create.assert_not_called()

    def test_aggregate_request_limit(self):
        self.client.embeddings.create.side_effect = lambda **kw: SimpleNamespace(data=[item(i) for i in range(len(kw['input']))])
        with patch.object(models, 'token_count', return_value=8000):
            models.encode_dense(['text'] * 40, batch_size=100)
        self.assertEqual([len(call.kwargs['input']) for call in self.client.embeddings.create.call_args_list], [37, 3])

    def test_provider_failure_is_not_silently_replaced(self):
        self.client.embeddings.create.side_effect = RuntimeError('provider failure')
        with self.assertRaisesRegex(RuntimeError, 'provider failure'):
            models.encode_dense(['flood'])

    def test_fingerprint_includes_endpoint_model_dimensions_tokenizer_and_pipeline(self):
        original = models.embedding_fingerprint()
        for name, value in [('OPENAI_BASE_URL', 'https://another.example/v1'), ('EMBEDDING_MODEL', 'other'),
                            ('EMBEDDING_DIMENSIONS', 768), ('EMBEDDING_TOKENIZER', 'other'), ('PIPELINE_VERSION', 'other')]:
            with patch.object(models, name, value):
                self.assertNotEqual(original, models.embedding_fingerprint())
        self.assertNotIn('api_key', json.dumps(models.embedding_identity()))
        self.assertIsNone(models.embedding_identity()['model_revision'])

    def test_sdk_retries_transient_status_once_and_does_not_retry_auth(self):
        for status, expected in [(503, 2), (429, 2), (401, 1), (403, 1)]:
            calls = []
            def respond(request):
                calls.append(request)
                return httpx.Response(status, json={'error': {'message': 'failure'}}, headers={'retry-after-ms': '1'})
            client = OpenAI(api_key='test-key', base_url='https://example.test/v1', timeout=30, max_retries=1,
                            http_client=httpx.Client(transport=httpx.MockTransport(respond)))
            with self.subTest(status=status), patch.object(models, 'dense_model', return_value=client):
                with self.assertRaises(Exception):
                    models.encode_dense(['flood'])
                self.assertEqual(len(calls), expected)
            client.close()


if __name__ == '__main__':
    unittest.main()
