# Incident source recovery

The incident implementation was transferred into this repository on 2026-11-02.
The earlier implementation used a recovered checkout of upstream revision `90467f8` in an old OneDrive workspace. macOS now denies reads of that directory.

The original file writes and subsequent fixes were reconstructed chronologically from the implementation session history, including the negation fix, sanitized export errors, and the final diacritic-preserving embedding input. The original directory was left untouched. The existing retrieval service here was unchanged at `90467f8`; only its original incident router registration was added.

Recovered files:

- `incident_processing.py`: Vietnamese normalization, evidence extraction, and similarity.
- `incident_routes.py`: inference routes protected by the existing service token.
- `export_incident_embeddings.py`: synthetic benchmark export using the existing embedding client.
- `test_incidents.py` and `test_incident_routes.py`: extraction and authenticated endpoint tests.

Verify with `python -m unittest test_incidents test_incident_routes test_embeddings test_retrieval_readiness -v`. The route tests additionally verify the final accented and abbreviation-expanded embedding input.

The existing Dockerfile copies the Python modules. No new service, collection, dependency, or corpus migration is required. Real provider and full deployment validation remain separate; keep backend matching in review mode.
