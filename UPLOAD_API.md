# Uploading documents

The retrieval service serves its administration page at `/admin/`; `/` redirects there. This page accepts UTF-8 Markdown files up to 10 MiB, adds new sources, replaces existing sources and reports indexing progress. A replacement retains its primary document ID and old citation snapshots. Identical content does not increment the document version.

## Deployment

1. Set a new, independent `RAG_ADMIN_TOKEN` in `/opt/env/vietflood-rag.env`, alongside the existing `RAG_SERVICE_TOKEN` and Qdrant configuration. Generate a random value with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep it out of Git and browser storage.
2. Build and deploy using `Jenkinsfile`. It includes the source Markdown and registry in the image, sets `RAG_SOURCE_DIR=/app/data/sources`, mounts a persistent named corpus volume `vietflood-rag-data` at `/app/data` writable. The initial image populates its existing snapshots/releases and application ownership on first use. Existing model and corpus volumes remain persistent.
3. If deploying through Compose, use `docker-compose.rag.yml`. For another Compose deployment, add `RAG_ADMIN_TOKEN`, set `RAG_SOURCE_DIR=/app/data/sources`, and change the corpus mount from `:ro` to writable. Ensure the image's `app` user can write that directory.
4. The reverse proxy must forward `/admin/` and `/admin/api/*` to the same service as `/search`. Allow an HTTP request body of at least 11 MiB for multipart overhead. The application rejects files larger than 10 MiB. No CORS access is needed.
5. Open `https://vietflood-rag.ndtd.indevs.in/admin/`, enter the admin token, select `VietFlood_FE_Clone`, and upload `vietflood-user-guide.md`. Wait for the completed status. Check `/health/ready` with the retrieval token and the new version's source snapshot before treating the deployment as complete.

The first administrative request initializes `/app/data/sources` and `/app/data/source_registry.jsonl` from the image. Subsequent starts preserve edits and deletions. All service replicas must share the same corpus volume and locks; use one worker on a single host for this deployment. Do not publish a local candidate by switching the live alias before its snapshots and manifest exist on the service host.

## HTTP contract

These are additive endpoints under `/admin/api`; existing retrieval endpoints retain `X-Rag-Token` authentication. Every administration API request requires `X-Rag-Admin-Token`. Missing configuration returns 503; invalid credentials return 401. The HTML shell and static template contain no private corpus data.

| Method and endpoint | Request | Response |
| --- | --- | --- |
| `GET /admin/api/status` | None | 200: `job`, registry counts and active manifest summary |
| `GET /admin/api/documents?offset=0&limit=50` | `offset >= 0`; `1 <= limit <= 100` | 200: `items: [{id,title,version}]`, `nextOffset`, `total` |
| `POST /admin/api/import` | Multipart `file` field containing `.md` | 202: `{status:"queued",document_id}` |
| `PUT /admin/api/documents/{document_id}` | Multipart `file`; first `source_ids` entry must match the target ID | 202: `{status:"queued",document_id}` |
| `POST /admin/api/retry` | None | 202: retry the failed/interrupted job |

Use the status endpoint to poll; 202 means accepted, rather than published. `job.status` is `idle`, `queued`, `processing`, `complete` or `failed`. Completed jobs include the physical collection and point count. Job state is persisted across restarts; interrupted jobs can be retried. Only one upload can run; conflicts return 409. Files and job IDs are logged without credentials, document contents or provider responses.

Application errors use `{"detail":{"code":"source_id_conflict","message":"…"}}`. Validation errors for query parameters/multipart shape use FastAPI's standard 422 `detail` array. File/metadata validation returns 400, unknown replacement targets 404, conflicting source IDs 409, oversized requests/files 413, and unavailable writable storage 503. No errors are reported as HTTP 200.

Retries of PUT are safe for document identity/version: the registry compares normalized content, title and source URL. A repeated import returns 409 once its source IDs exist. Uploads run asynchronously and are serialized with a process-shared file lock; a failed attempt keeps the staged source for retry. The existing pipeline checks the complete candidate, writes snapshots and release metadata, then atomically switches the live alias. The administration API does not accept a client-selected collection or arbitrary filesystem path.

Example replacement (the environment variable holds the admin token):

```sh
curl --fail-with-body -X PUT \
  -H "X-Rag-Admin-Token: $RAG_ADMIN_TOKEN" \
  -F 'file=@vietflood-user-guide.md;type=text/markdown' \
  https://vietflood-rag.ndtd.indevs.in/admin/api/documents/VietFlood_FE_Clone
```

## Verification

```sh
python -m unittest test_portal test_pipeline -v
node --check portal.js
```

The integration test runs the actual tokenizer, BM25 encoder, pipeline and a temporary local Qdrant database with deterministic test-only dense vectors. It verifies replacement, version stability on repeat uploads, archived snapshots, unchanged unrelated vectors, authentication, size limits, metadata validation and persistent storage. It does not mutate production or establish production model quality.

The repository also contains an embedding migration. Before replacing a running E5/768 service with the API/1536 image, prepare and publish the matching release and deploy its metadata using the migration instructions in `PIPELINE_README.md`. Upload UI tests do not establish that production migration has been performed.
