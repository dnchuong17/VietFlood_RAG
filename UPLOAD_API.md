# Uploading documents

The retrieval service serves its administration page at `/admin/`; `/` redirects there. This page accepts UTF-8 Markdown files up to 10 MiB, adds new sources, replaces existing sources and reports indexing progress. A replacement retains its primary document ID and old citation snapshots. Identical content does not increment the document version.

## Deployment

1. Set a new, independent `RAG_ADMIN_TOKEN` in `/opt/env/vietflood-rag.env`, alongside the existing `RAG_SERVICE_TOKEN` and Qdrant configuration. Generate a random value with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep it out of Git and browser storage.
2. Build and deploy using `Jenkinsfile` (or `VietFlood/Jenkinsfile` for a nested checkout). It detects the Docker build context, persists corpus data in `vietflood-rag-data` and models in `vietflood-rag-models`, prepares volume ownership for the non-root application user, and prepares a new release using the configured embedding model and checks that candidate before stopping the current container. It publishes the new alias only after the old container stops. If publication, startup or health verification fails, it restores the previous Qdrant alias, ingest manifest and container.
3. If deploying through Compose, use `docker-compose.rag.yml`. For another Compose deployment, add `RAG_ADMIN_TOKEN`, set `RAG_SOURCE_DIR=/app/data/sources`, and change the corpus mount from `:ro` to writable. Ensure the image's `app` user can write that directory.
4. The reverse proxy must forward `/admin/` and `/admin/api/*` to the same service as `/search`. Allow an HTTP request body of at least 11 MiB for multipart overhead. The application rejects files larger than 10 MiB. No CORS access is needed.
5. Open `https://vietflood-rag.ndtd.indevs.in/admin/`, enter the admin token, select `VietFlood_FE_Clone`, and upload `vietflood-user-guide.md`. Wait for the completed status. Check `/health/ready` with the retrieval token and the new version's source snapshot before treating the deployment as complete.

The container entrypoint initializes `/app/data/sources` and `/app/data/source_registry.jsonl` from the image. Subsequent starts preserve edits and deletions. Image snapshots/manifests are stored at `/app/bootstrap` and copied into the writable volume only when missing, including on existing volumes. All service replicas must share the same corpus volume and locks; use one worker on a single host for this deployment. Do not publish a local candidate by switching the live alias before its snapshots and manifest exist on the service host.

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
python -m unittest test_deployment test_portal test_pipeline -v
node --check portal.js
```

The integration test runs the actual tokenizer, BM25 encoder, pipeline and a temporary local Qdrant database with deterministic test-only dense vectors. It verifies replacement, version stability on repeat uploads, archived snapshots, unchanged unrelated vectors, authentication, size limits, metadata validation and persistent storage. It does not mutate production or establish production model quality.

The repository also contains an embedding migration. Before replacing a running E5/768 service with the API/1536 image, prepare and publish the matching release and deploy its metadata using the migration instructions in `PIPELINE_README.md`. Upload UI tests do not establish that production migration has been performed.

Jenkins requires Docker CLI access to the host daemon. Its deployment container stays on localhost port 8001; the reverse proxy continues to serve the configured public domain. An existing `rag-retrieval-previous` backup stops another rollout until an operator inspects it. The `latest` image tag is updated only after a healthy rollout. For an existing Compose bind mount, prepare ownership once with `docker compose -f docker-compose.rag.yml run --rm --user root --entrypoint python retrieval /app/container_entrypoint.py --prepare-volumes`.


## Automatic embedding migration during Jenkins deployment

The deployment script now handles an existing E5/768 active collection with the API/1536 service:

1. `--prepare-release <id>` parses persistent sources, creates API embeddings and validates a new collection with snapshots/manifest. The old alias keeps serving old vectors.
2. `--check-release <id>` checks the candidate directly rather than testing it through the old alias.
3. After stopping the old container, `--publish-release <id>` switches the stable alias and ingest manifest, then Jenkins starts the new container.
4. A failed publication/start/healthcheck invokes `--rollback-release <id>` before restarting the old container. Rollback restores E5 metadata without requiring the new embedding model and refuses to overwrite an unrelated later alias update.

The embedding API key must be valid for the configured model. Initial migration embeds the corpus once; subsequent deployments reuse fingerprinted cached vectors. Candidate collections and prior releases are retained. Automatic deployment rejects an empty source corpus, stale publication and conflicting deployment IDs. Transaction journals live in `data/deployments/` on the persistent volume.
