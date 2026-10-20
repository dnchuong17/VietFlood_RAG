"""Transport failure diagnostics, bounded retries and read-only deployment probes."""
from contextlib import redirect_stderr
import io
import json
import socket
import ssl
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
import check_qdrant_runtime as probe
import runtime_diagnostics as diagnostics


class RuntimeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        redirect = redirect_stderr(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        self.sleep = patch.object(diagnostics.time, 'sleep').start()
        self.addCleanup(patch.stopall)

    def request(self, operation, effects):
        callback = Mock(side_effect=effects)
        callback.__name__ = operation
        return callback

    def test_wrapped_timeout_is_reported_without_sensitive_text(self):
        error = ResponseHandlingException(httpx.ReadTimeout('SECRET https://key:token@example.test'))
        details = diagnostics.error_details(error)
        self.assertEqual(details['errorChain'], ['ResponseHandlingException', 'ReadTimeout'])
        self.assertEqual(details['category'], 'timeout')
        diagnostics.event('failure', **details)
        self.assertNotIn('SECRET', self.output.getvalue())
        self.assertNotIn('token', self.output.getvalue())

    def test_dns_and_tls_causes_are_distinguished_and_cycles_bounded(self):
        for error, category in [(socket.gaierror(socket.EAI_AGAIN, 'SECRET'), 'dns'),
                                (ssl.SSLCertVerificationError(1, 'SECRET'), 'tls_certificate')]:
            wrapper = ResponseHandlingException(error)
            error.__cause__ = wrapper
            details = diagnostics.error_details(wrapper)
            self.assertEqual(details['category'], category)
            self.assertEqual(len(details['errorChain']), 2)
            self.assertNotIn('SECRET', json.dumps(details))

    def test_read_and_upsert_retry_transient_transport_failures(self):
        for operation in ['get_aliases', 'upsert']:
            callback = self.request(operation, [ResponseHandlingException(httpx.ReadTimeout('SECRET')), 'ok'])
            self.assertEqual(diagnostics.qdrant_call(callback, 'input'), 'ok')
            self.assertEqual(callback.call_count, 2)
            self.assertEqual(callback.call_args_list[0], callback.call_args_list[1])
        self.assertNotIn('SECRET', self.output.getvalue())

    def test_retries_stop_after_three_attempts(self):
        failure = ResponseHandlingException(httpx.ConnectError('SECRET'))
        callback = self.request('get_collection', [failure] * 3)
        with self.assertRaises(ResponseHandlingException): diagnostics.qdrant_call(callback)
        self.assertEqual(callback.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_alias_mutation_and_collection_creation_are_never_replayed(self):
        for operation in ['update_collection_aliases', 'create_collection', 'delete_collection']:
            callback = self.request(operation, [ResponseHandlingException(httpx.ReadTimeout('SECRET'))])
            with self.assertRaises(ResponseHandlingException): diagnostics.qdrant_call(callback)
            self.assertEqual(callback.call_count, 1)
        self.sleep.assert_not_called()

    def test_auth_and_validation_errors_are_not_retried_or_disclosed(self):
        for failure in [UnexpectedResponse(401, 'SECRET', b'SECRET', {}),
                        ResponseHandlingException(ValueError('SECRET')),
                        ResponseHandlingException(ssl.SSLCertVerificationError(1, 'SECRET'))]:
            callback = self.request('get_collection', [failure])
            with self.assertRaises(type(failure)): diagnostics.qdrant_call(callback)
            self.assertEqual(callback.call_count, 1)
        self.assertNotIn('SECRET', self.output.getvalue())
        self.assertIn('"httpStatus": 401', self.output.getvalue())

    def test_gateway_failure_is_retried_but_bad_request_is_not(self):
        callback = self.request('count', [UnexpectedResponse(503, 'SECRET', b'SECRET', {}), 'ok'])
        self.assertEqual(diagnostics.qdrant_call(callback), 'ok')
        callback = self.request('count', [UnexpectedResponse(400, 'SECRET', b'SECRET', {})])
        with self.assertRaises(UnexpectedResponse): diagnostics.qdrant_call(callback)
        self.assertEqual(callback.call_count, 1)

    def test_stage_preserves_original_error_and_records_failed_step(self):
        error = ValueError('SECRET')
        with self.assertRaises(ValueError) as raised:
            with diagnostics.stage('example'):
                raise error
        self.assertIs(raised.exception, error)
        self.assertIn('deployment_stage_failed', self.output.getvalue())
        self.assertNotIn('SECRET', self.output.getvalue())

    def test_probe_accepts_existing_768_release_and_only_reads(self):
        client = Mock()
        client.get_aliases = self.request('get_aliases', [SimpleNamespace(aliases=[SimpleNamespace(alias_name=probe.RAG_ALIAS, collection_name='old_768')])])
        client.get_collection = self.request('get_collection', [SimpleNamespace(vector_size=768)])
        with patch.object(probe, 'QdrantClient', return_value=client):
            self.assertEqual(probe.main(), 0)
        client.get_collection.assert_called_once_with('old_768')
        client.close.assert_called_once()
        client.update_collection_aliases.assert_not_called()
        client.upsert.assert_not_called()

    def test_probe_closes_connection_and_reports_wrapped_error(self):
        client = Mock()
        client.get_aliases = self.request('get_aliases', [ResponseHandlingException(httpx.ConnectError('SECRET'))] * 3)
        with patch.object(probe, 'QdrantClient', return_value=client):
            self.assertEqual(probe.main(), 1)
        client.close.assert_called_once()
        self.assertIn('qdrant_connectivity_failed', self.output.getvalue())
        self.assertIn('ConnectError', self.output.getvalue())
        self.assertNotIn('SECRET', self.output.getvalue())


if __name__ == '__main__':
    unittest.main()
