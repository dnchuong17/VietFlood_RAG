"""Regression checks for model revision resolution and authenticated readiness."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from qdrant_client import models
import rag_models
import chunk_documents


class RetrievalReadinessTests(unittest.TestCase):
    def setUp(self):
        rag_models.dense_model.cache_clear()
        rag_models.dense_model_revision.cache_clear()
        chunk_documents.get_tokenizer.cache_clear()
        self.addCleanup(rag_models.dense_model.cache_clear)
        self.addCleanup(rag_models.dense_model_revision.cache_clear)
        self.addCleanup(chunk_documents.get_tokenizer.cache_clear)
        with patch('qdrant_client.QdrantClient'):
            self.service=importlib.import_module('retrieval_service')
        self.revision='d128750597153bb5987e10b1c3493a34e5a4502a'
        self.collection='test_release'
        self.manifest={'embedding_model':self.service.EMBEDDING_MODEL,
                       'model_revision':self.revision,'point_count':212}
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data=Path(temporary.name)
        (self.data/'releases').mkdir()
        self.write_manifest()
        params=SimpleNamespace(
            vectors={'dense':SimpleNamespace(size=768,distance=models.Distance.COSINE)},
            sparse_vectors={'bm25':object()},
        )
        client=Mock()
        client.get_collection.return_value=SimpleNamespace(config=SimpleNamespace(params=params))
        client.get_aliases.return_value=SimpleNamespace(aliases=[SimpleNamespace(
            alias_name=self.service.RAG_ALIAS,collection_name=self.collection)])
        client.count.return_value=SimpleNamespace(count=212)
        for attribute,value in [('client',client),('RAG_DATA_DIR',self.data)]:
            patcher=patch.object(self.service,attribute,value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher=patch('huggingface_hub.hf_hub_download',return_value=
                      f'/cache/models--intfloat--multilingual-e5-base/snapshots/{self.revision}/config.json')
        self.download=patcher.start()
        self.addCleanup(patcher.stop)

    def write_manifest(self):
        (self.data/'releases'/f'{self.collection}.json').write_text(json.dumps(self.manifest))

    def test_model_loads_the_resolved_commit(self):
        constructor=Mock(return_value=SimpleNamespace())
        with patch.dict(sys.modules,{'sentence_transformers':SimpleNamespace(SentenceTransformer=constructor)}):
            rag_models.dense_model()
        constructor.assert_called_once_with(self.service.EMBEDDING_MODEL,revision=self.revision)
        self.download.assert_called_once_with(repo_id=self.service.EMBEDDING_MODEL,
                                              filename='config.json',
                                              revision=rag_models.EMBEDDING_MODEL_REVISION)

    def test_startup_and_health_work_without_private_commit_metadata(self):
        # Deliberately omit both tokenizer and model config _commit_hash fields.
        embedder=SimpleNamespace(tokenizer=SimpleNamespace(init_kwargs={}),
                                 auto_model=SimpleNamespace(config=SimpleNamespace()))
        with patch.object(self.service,'dense_model',return_value=embedder), \
             patch.object(self.service,'sparse_model',return_value=object()), \
             patch.object(self.service,'rerank_model',return_value=object()), \
             patch.dict(os.environ,{'RAG_SERVICE_TOKEN':'test-token'}):
            with TestClient(self.service.app) as http:
                response=http.get('/health/ready',headers={'x-rag-token':'test-token'})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['modelRevision'],self.revision)
                self.assertEqual(http.get('/health/ready').status_code,401)

    def test_chunk_tokenizer_uses_the_same_commit(self):
        constructor=Mock()
        with patch.dict(sys.modules,{'transformers':SimpleNamespace(AutoTokenizer=constructor)}):
            chunk_documents.get_tokenizer()
        constructor.from_pretrained.assert_called_once_with(self.service.EMBEDDING_MODEL,
                                                            revision=self.revision)

    def test_an_actual_revision_mismatch_remains_unhealthy(self):
        self.manifest['model_revision']='b'*40
        self.write_manifest()
        with self.assertRaisesRegex(ValueError,'Model revision mismatch: manifest=b+, loaded=d128'):
            self.service.readiness()

    def test_unresolved_snapshot_path_is_rejected(self):
        self.download.return_value='/cache/config.json'
        with self.assertRaisesRegex(ValueError,'Cannot resolve embedding model commit'):
            rag_models.dense_model_revision()


if __name__=='__main__':
    unittest.main()
