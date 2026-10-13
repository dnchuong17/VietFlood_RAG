# VietFlood RAG pipeline v2

34 supplied sources are accepted as APPROVED_FOR_RAG. Eight excluded records are not published.

Use a Python environment outside OneDrive; install requirements, then run:

```sh
python sync_pipeline.py
python -m uvicorn retrieval_service:app --host 127.0.0.1 --port 8001
```

`sync_pipeline.py` is the single entrypoint for parse, tokenizer-aware chunking, embedding and candidate/alias publishing. `watch_corpus.py` synchronizes source file edits/additions/deletions automatically. `portal.py` provides import/update/delete on localhost for corpus administration. Explicit updates retain source IDs; document version increments when content/title/source URL changes.

The shared private token RAG_SERVICE_TOKEN must match API Gateway. QDRANT_CHAT_COLLECTION defaults to flood_kb_active. Runtime retrieval uses dense E5 + BM25 sparse Query API / RRF / multilingual BGE reranking, without scroll or match.text.

Use `Dockerfile.rag` to build vietflood-retrieval:local, and `docker-compose.rag.yml` for standalone local service. Backend Docker Compose uses that image with a read-only mounted data directory and persistent model cache. Source snapshots/releases must be deployed with the collection, not just embeddings.

The new local artifacts contain 34 documents and 212 section-aware chunks. Token budgets include E5 prefix/title/heading/special tokens; no input may exceed the hard model ceiling. Manifests report full desired collection counts, model/tokenizer fingerprint, additions/deletions/cache reuse and previous collection.

Old releases remain for rollback; the active alias never queries them. Source snapshots remain readable for old citations. `test_pipeline.py` checks integrity and the actual tokenizer. `evaluate_production.py` / `verify_retrieval.py` require RAG_EVAL_API_URL and RAG_EVAL_BEARER_TOKEN and exercise the authenticated production /chat route.

Detailed API/deployment/diagnostics documentation is in the backend `docs/rag-implementation.md`.
