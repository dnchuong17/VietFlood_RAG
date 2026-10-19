# VietFlood RAG pipeline v3

The corpus contains 34 approved source documents. Dense vectors use the OpenAI-compatible API at `https://cheapkeyai.shop/v1`, model `text-embedding-3-small`, and 1536 dimensions. Both documents and queries use this configuration. Hybrid retrieval retains BM25/RRF and the local `BAAI/bge-reranker-v2-m3` reranker.

Keep these variables in ignored `.env` files locally and protected deployment environment files on the server:

```dotenv
OPENAI_BASE_URL=https://cheapkeyai.shop/v1
OPENAI_API_KEY=<provider key>
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
QDRANT_CHAT_COLLECTION=flood_kb_active
RAG_SERVICE_TOKEN=<same private token as the backend>
```

Use Python 3.11 or 3.12 in an environment outside OneDrive and install `requirements.txt`. The embedding API uses float vectors, a 30-second request timeout and at most one transient-error retry. Authentication failures are not retried. Chunking uses cl100k_base with a 450-token budget including titles/headings and 50-token overlap; no E5 passage/query prefixes are added. API inputs exceeding 8191 tokens are rejected.

## Prepare a candidate without switching production

First verify both providers from their project directories. These static probes incur small API usage:

```sh
# VietFlood backend
npm run check:openai
# VietFlood_RAG
python check_embedding_runtime.py
python sync_pipeline.py --no-publish
```

The last command rebuilds registry, parsed documents and chunks, embeds approved documents, and validates a new immutable Qdrant collection. It prints the candidate collection name and `published=false`. It leaves `flood_kb_active` and `data/ingest_manifest.json` unchanged. Releases record endpoint/model/dimensions/tokenizer/pipeline fingerprints and point hashes. API models have `model_revision=null`; immutable Hugging Face commits do not apply. Old E5 cache entries cannot be reused because the fingerprint changes.

## Prepared release

The candidate built for this migration is `flood_kb_active_20261013184458_2ba3cf78`: 34 approved documents, 220 points, all newly embedded at 1536 dimensions. The old active collection is `flood_kb_active_20261012170418_13a14650`. Production publication is pending your manual deployment.

For this release, the publication command in the maintenance step is:

```sh
python ingest_qdrant.py --publish-release flood_kb_active_20261013184458_2ba3cf78
```

## Manual cutover

1. Preserve the running image/configuration, old active collection, `data/ingest_manifest.json`, and source artifacts. Keep the prior E5 image for rollback; the new code intentionally rejects E5 releases.
2. Copy the new `data/releases/` and `data/snapshots/` to the deployment corpus directory. Build the updated retrieval image with `docker build -t vietflood-retrieval:local .`. Supply the embedding variables above in `/opt/env/vietflood-rag.env` or Compose. Update `/opt/env/vietflood.env` with the same key/base URL and `OPENAI_CHAT_MODEL=gpt-5-nano` for the gateway.
3. Optionally start the new retrieval image on a private alternate port with `QDRANT_CHAT_COLLECTION=<candidate collection>` and verify authenticated readiness and Vietnamese searches before maintenance. Its reported vector size must be 1536 and model must be text-embedding-3-small.
4. Pause the old retrieval service. From the RAG project, publish the exact candidate printed by the build:

```sh
python ingest_qdrant.py --publish-release <candidate collection>
```

Publication rechecks embedding identity, every point/hash/vector, source snapshots and document coverage. It refuses a stale candidate if another release replaced the active alias after its build. The alias changes atomically only after validation; a local manifest-write failure restores the previous alias.

5. Start the new retrieval deployment with `QDRANT_CHAT_COLLECTION=flood_kb_active` and the matching artifacts. Rebuild/restart the gateway. Check token-authenticated `/health/ready`, then a cited Vietnamese chat answer and its source snapshot endpoint. Do not resume traffic until these pass.

The standalone `docker-compose.rag.yml` and both backend Compose files pass embedding credentials to retrieval. Retrieval mounts corpus data read-only; only ingestion writes it. The Jenkins retrieval pipeline probes embedding access before stopping the existing service. Jenkins does not publish the corpus alias; coordinate that manual maintenance step yourself.

## Rollback

During maintenance, atomically restore `flood_kb_active` to the old physical collection saved in the candidate manifest's `previous_collection`. Use the Qdrant alias API with delete/create operations in one request. Restore the old retrieval image, E5 environment, manifest and source artifacts together, then verify readiness before resuming. Retain old collections and snapshots; do not publish an E5 release through the new API-embedding publication command.

## Verification

```sh
python -m unittest test_embeddings test_retrieval_readiness test_sync test_pipeline
```

Embedding, readiness and isolated local-Qdrant sync tests make no paid API calls. Pipeline tests inspect the generated corpus using the real tokenizer. `test_sync.py` covers candidate isolation, publication, stale candidates, cache reuse, deletions and publication rollback. `evaluate_production.py` needs `RAG_EVAL_API_URL` and `RAG_EVAL_BEARER_TOKEN` and exercises the deployed authenticated `/chat` route after manual cutover.

`portal.py` is a localhost corpus administration tool; `watch_corpus.py` synchronizes future edits using the configured embedding API. Normal synchronization publishes immediately; use `--no-publish` during model migration. API model aliases can change upstream without an immutable version being exposed. After a known provider/model change, bump the pipeline version and rebuild to invalidate the cache.


Administration uploads are available at `/admin/` with a separate `RAG_ADMIN_TOKEN` and a writable persistent corpus volume. See [UPLOAD_API.md](UPLOAD_API.md) for the API and deployment contract. The existing embedding migration is preserved.
