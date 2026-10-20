"""Stage an embedding migration, publish it, or restore its previous alias."""
from contextlib import contextmanager
import json
import re
from types import SimpleNamespace

from filelock import FileLock
from qdrant_client import QdrantClient, models
import ingest_qdrant as ingest
from kb_common import read_jsonl
from pipeline_config import CHUNKS_PATH, QDRANT_URL, QDRANT_API_KEY, RAG_ALIAS
from sync_pipeline import prepare_corpus


def state_path(deployment_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', deployment_id):
        raise ValueError('Invalid deployment ID')
    return ingest.RAG_DATA_DIR / 'deployments' / (deployment_id + '.json')


def load_state(deployment_id):
    state = json.loads(state_path(deployment_id).read_text())
    if state['alias'] != RAG_ALIAS:
        raise ValueError('Deployment alias mismatch')
    ingest.release_path(state['collection'])
    return state


@contextmanager
def connection(client=None):
    owned = client is None
    client = client if client is not None else QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60)
    try:
        yield client
    finally:
        if owned:
            client.close()


def current_alias(client):
    return {a.alias_name: a.collection_name for a in client.get_aliases().aliases}.get(RAG_ALIAS)


def prepare_release(deployment_id, client=None):
    path = state_path(deployment_id)
    ingest.RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(str(ingest.RAG_DATA_DIR / 'sync.lock'), timeout=120), connection(client) as client:
        if path.exists():
            raise ValueError('Deployment ID already exists')
        ingest.validate_embedding_configuration()
        prepare_corpus()
        if not read_jsonl(CHUNKS_PATH):
            raise ValueError('Refusing to deploy an empty corpus')
        args = SimpleNamespace(chunks=CHUNKS_PATH, collection=RAG_ALIAS, batch_size=16,
                               upsert_batch_size=64, no_publish=True)
        manifest = ingest.build_candidate(client, args)
        state = {'status': 'prepared', 'alias': RAG_ALIAS, 'collection': manifest['collection'],
                 'previous_collection': manifest['previous_collection']}
        ingest.atomic_json(path, state)
        return state


def check_release(deployment_id):
    state = load_state(deployment_id)
    if state['status'] != 'prepared':
        raise ValueError('Deployment is not prepared')
    from retrieval_service import client, readiness
    try:
        # Test the candidate itself while the old alias continues serving old vectors.
        return readiness(collection=state['collection'])
    finally:
        client.close()


def publish_release(deployment_id, client=None):
    path = state_path(deployment_id)
    with FileLock(str(ingest.RAG_DATA_DIR / 'sync.lock'), timeout=120), connection(client) as client:
        state = load_state(deployment_id)
        actual = current_alias(client)
        if state['status'] == 'published' and actual == state['collection']:
            return state
        if state['status'] != 'prepared' or actual != state['previous_collection']:
            raise ValueError('Active alias changed; refusing stale deployment')
        manifest = json.loads(ingest.release_path(state['collection']).read_text())
        if manifest.get('previous_collection') != state['previous_collection']:
            raise ValueError('Previous collection mismatch')
        previous = json.loads(ingest.INGEST_MANIFEST_PATH.read_text()) if ingest.INGEST_MANIFEST_PATH.exists() else None
        state.update(status='publishing', previous_manifest=previous)
        # Journal first: rollback can reconcile even if the alias update times out.
        ingest.atomic_json(path, state)
        ingest.publish_release(client, manifest, RAG_ALIAS)
        state['status'] = 'published'
        ingest.atomic_json(path, state)
        return state


def rollback_release(deployment_id, client=None):
    path = state_path(deployment_id)
    with FileLock(str(ingest.RAG_DATA_DIR / 'sync.lock'), timeout=120), connection(client) as client:
        state = load_state(deployment_id)
        if state['status'] in {'prepared', 'rolled_back'} and 'previous_manifest' not in state:
            # Publication was rejected before this deployment changed the alias.
            state['status'] = 'rolled_back'
            ingest.atomic_json(path, state)
            return state
        if state['status'] not in {'publishing', 'published', 'rolled_back'}:
            raise ValueError('Invalid deployment state')
        actual = current_alias(client)
        previous = state['previous_collection']
        if actual not in {state['collection'], previous}:
            raise ValueError('Alias advanced beyond deployment; manual recovery required')
        if actual != previous:
            if previous is not None and not client.collection_exists(previous):
                raise ValueError('Previous collection is missing')
            changes = [models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=RAG_ALIAS))]
            if previous is not None:
                changes.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=previous, alias_name=RAG_ALIAS)))
            client.update_collection_aliases(changes)
        # Old manifests may describe E5/768. Restoring them must not require the new model.
        if state.get('previous_manifest') is not None:
            ingest.atomic_json(ingest.INGEST_MANIFEST_PATH, state['previous_manifest'])
        else:
            ingest.INGEST_MANIFEST_PATH.unlink(missing_ok=True)
        state['status'] = 'rolled_back'
        ingest.atomic_json(path, state)
        return state
