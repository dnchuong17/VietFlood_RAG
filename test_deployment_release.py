"""Real local-Qdrant E5/768 to API/1536 migration and alias rollback tests."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import numpy as np
import httpx
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException
import deployment_release as deployment
import ingest_qdrant as ingest


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.data=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.client=QdrantClient(':memory:');self.stack.callback(self.client.close)
        self.chunks=self.data/'chunks.jsonl';self.docs=self.data/'docs.jsonl'
        self.manifest_path=self.data/'manifest.json'
        for module,values in [
            (ingest,{'RAG_DATA_DIR':self.data,'INGEST_MANIFEST_PATH':self.manifest_path,'PARSED_DOCUMENTS_PATH':self.docs}),
            (deployment,{'CHUNKS_PATH':self.chunks,'RAG_ALIAS':'test_active'})]:
            for name,value in values.items(): self.stack.enter_context(patch.object(module,name,value))
        self.stack.enter_context(patch.object(deployment,'prepare_corpus'))
        self.stack.enter_context(patch.object(ingest,'validate_embedding_configuration'))
        self.encode=self.stack.enter_context(patch.object(ingest,'encode_dense',side_effect=lambda texts,_:[[0.1]*1536 for _ in texts]))
        sparse=SimpleNamespace(embed=lambda texts:[SimpleNamespace(indices=np.array([1]),values=np.array([1.0])) for _ in texts])
        self.stack.enter_context(patch.object(ingest,'sparse_model',return_value=sparse))
        old_id='13912b36-321b-4571-b71d-96ff4068b48f'
        self.client.create_collection('old_e5',vectors_config={'dense':models.VectorParams(size=768,distance=models.Distance.COSINE)},sparse_vectors_config={'bm25':models.SparseVectorParams(modifier=models.Modifier.IDF)})
        self.client.upsert('old_e5',[models.PointStruct(id=old_id,vector={'dense':[0.1]*768,'bm25':models.SparseVector(indices=[1],values=[1.0])},payload={'document_id':'test'})])
        self.alias_to('old_e5')
        self.old_manifest={'collection':'old_e5','embedding_model':'intfloat/multilingual-e5-base','vector_size':768,'point_ids':[old_id]}
        self.manifest_path.write_text(json.dumps(self.old_manifest))
        chunk={'point_id':'b7f186de-263c-41da-a74e-9d29c9a4b92f','document_id':'test','document_version':1,
               'chunk_hash':'first','embedding_text':'Example guidance.','text':'Example guidance.',
               'metadata':{'license_status':'APPROVED_FOR_RAG'}}
        self.chunks.write_text(json.dumps(chunk)+'\n')
        self.docs.write_text(json.dumps({'document_id':'test','document_version':1,'title':'Example','body':'Example guidance.',
            'metadata':{'license_status':'APPROVED_FOR_RAG','source_url':'https://example.test'}})+'\n')

    def alias(self):
        return {a.alias_name:a.collection_name for a in self.client.get_aliases().aliases}.get('test_active')

    def alias_to(self,collection):
        changes=[]
        if self.alias() is not None: changes.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name='test_active')))
        if collection is not None: changes.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=collection,alias_name='test_active')))
        self.client.update_collection_aliases(changes)

    def prepare(self,id='run1'):
        return deployment.prepare_release(id,self.client)

    def test_prepare_keeps_768_alias_and_creates_valid_1536_candidate(self):
        state=self.prepare()
        self.assertEqual(self.alias(),'old_e5')
        self.assertEqual(self.client.get_collection('old_e5').config.params.vectors['dense'].size,768)
        self.assertEqual(self.client.get_collection(state['collection']).config.params.vectors['dense'].size,1536)
        self.assertEqual(json.loads(self.manifest_path.read_text()),self.old_manifest)
        self.assertTrue((self.data/'snapshots/test/1.json').exists())

    def test_publish_then_rollback_restores_old_alias_and_manifest(self):
        state=self.prepare()
        deployment.publish_release('run1',self.client)
        self.assertEqual(self.alias(),state['collection'])
        self.assertEqual(json.loads(self.manifest_path.read_text())['vector_size'],1536)
        deployment.rollback_release('run1',self.client)
        self.assertEqual(self.alias(),'old_e5')
        self.assertEqual(json.loads(self.manifest_path.read_text()),self.old_manifest)
        self.assertTrue(self.client.collection_exists(state['collection']))
        self.assertEqual(self.client.count('old_e5',exact=True).count,1)
        deployment.rollback_release('run1',self.client)
        self.assertEqual(self.alias(),'old_e5')

    def test_embedding_failure_leaves_old_alias_and_manifest(self):
        self.encode.side_effect=RuntimeError('provider failed')
        with self.assertRaises(RuntimeError): self.prepare()
        self.assertEqual(self.alias(),'old_e5')
        self.assertEqual(json.loads(self.manifest_path.read_text()),self.old_manifest)
        self.assertFalse(deployment.state_path('run1').exists())

    def test_lost_upsert_response_replays_identical_ids_without_duplicates(self):
        original = self.client.upsert
        calls = 0
        def upsert(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(*args, **kwargs)
            if calls == 1:
                raise ResponseHandlingException(httpx.ReadTimeout('response lost after write'))
            return result
        with patch.object(self.client, 'upsert', upsert), patch('runtime_diagnostics.time.sleep'):
            state = self.prepare()
        self.assertEqual(calls, 2)
        self.assertEqual(self.client.count(state['collection'], exact=True).count, 1)
        self.assertEqual(self.alias(), 'old_e5')

    def test_connectivity_failure_does_not_call_embedding_provider(self):
        with patch.object(self.client, 'get_aliases', side_effect=ResponseHandlingException(httpx.ConnectError('unreachable'))):
            with self.assertRaises(ResponseHandlingException): self.prepare()
        self.encode.assert_not_called()
        self.assertEqual(self.alias(), 'old_e5')

    def test_empty_corpus_cannot_replace_existing_knowledge(self):
        self.chunks.write_text('')
        with self.assertRaisesRegex(ValueError,'empty corpus'): self.prepare()
        self.assertEqual(self.alias(),'old_e5')
        self.encode.assert_not_called()

    def test_stale_publication_and_rollback_preserve_external_update(self):
        self.prepare()
        self.client.create_collection('external',vectors_config={'dense':models.VectorParams(size=768,distance=models.Distance.COSINE)})
        self.alias_to('external')
        with self.assertRaisesRegex(ValueError,'stale'): deployment.publish_release('run1',self.client)
        deployment.rollback_release('run1',self.client)
        deployment.rollback_release('run1',self.client)
        self.assertEqual(self.alias(),'external')

    def test_rollback_never_overwrites_a_later_publication(self):
        self.prepare();deployment.publish_release('run1',self.client)
        self.client.create_collection('external',vectors_config={'dense':models.VectorParams(size=1536,distance=models.Distance.COSINE)})
        self.alias_to('external')
        with self.assertRaisesRegex(ValueError,'advanced'): deployment.rollback_release('run1',self.client)
        self.assertEqual(self.alias(),'external')

    def test_crash_after_alias_update_can_restore_previous_state(self):
        self.prepare();original=ingest.atomic_json
        def write(path,value):
            if path==deployment.state_path('run1') and value.get('status')=='published': raise OSError('disk failed')
            original(path,value)
        with patch.object(ingest,'atomic_json',side_effect=write):
            with self.assertRaises(OSError): deployment.publish_release('run1',self.client)
        self.assertEqual(deployment.load_state('run1')['status'],'publishing')
        deployment.rollback_release('run1',self.client)
        self.assertEqual(self.alias(),'old_e5')
        self.assertEqual(json.loads(self.manifest_path.read_text()),self.old_manifest)

    def test_first_install_rollback_removes_alias_and_keeps_candidate(self):
        self.alias_to(None);self.manifest_path.unlink()
        state=self.prepare();deployment.publish_release('run1',self.client)
        deployment.rollback_release('run1',self.client)
        self.assertIsNone(self.alias())
        self.assertFalse(self.manifest_path.exists())
        self.assertTrue(self.client.collection_exists(state['collection']))

    def test_preflight_targets_candidate_without_switching_alias(self):
        state=self.prepare()
        # Preflight must not import the HTTP service or its short-timeout client.
        with patch.dict('sys.modules',{'retrieval_service':None}):
            ready=deployment.check_release('run1',self.client)
        self.assertEqual(ready['collection'],state['collection'])
        self.assertEqual(ready['pointCount'],1)
        self.assertEqual(self.alias(),'old_e5')

    def test_preflight_retries_the_reported_connect_timeout_then_validates_candidate(self):
        state=self.prepare()
        original=self.client.get_collection
        calls=0
        def get_collection(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==1:
                raise ResponseHandlingException(httpx.ConnectTimeout('connection timed out'))
            return original(*args,**kwargs)
        with patch.object(self.client,'get_collection',get_collection), patch('runtime_diagnostics.time.sleep') as sleep:
            ready=deployment.check_release('run1',self.client)
        self.assertEqual(ready['collection'],state['collection'])
        self.assertEqual(calls,2)
        sleep.assert_called_once_with(2)
        self.assertEqual(self.alias(),'old_e5')

    def test_preflight_owns_a_60_second_connection_and_closes_it_on_failure(self):
        self.prepare()
        client=Mock()
        client.get_collection.side_effect=ValueError('incompatible schema')
        with patch.object(deployment,'QdrantClient',return_value=client) as factory:
            with self.assertRaises(ValueError):deployment.check_release('run1')
        self.assertEqual(factory.call_args.kwargs['timeout'],60)
        client.close.assert_called_once()

    def test_preflight_rejects_corrupted_candidate_without_moving_alias(self):
        state=self.prepare()
        self.client.delete(state['collection'],models.PointIdsList(points=['b7f186de-263c-41da-a74e-9d29c9a4b92f']),wait=True)
        with self.assertRaisesRegex(ValueError,'count mismatch'):
            deployment.check_release('run1',self.client)
        self.assertEqual(self.alias(),'old_e5')

    def test_duplicate_or_invalid_deployment_id_is_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError): self.prepare()
        with self.assertRaises(ValueError): self.prepare('../outside')


if __name__=='__main__': unittest.main()
