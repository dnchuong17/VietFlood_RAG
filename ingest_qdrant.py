"""Build immutable corpus candidates, validate them, then publish an active alias."""
from __future__ import annotations
import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from qdrant_client import QdrantClient, models
from kb_common import read_jsonl, sha256_text
from pipeline_config import (
    CHUNKS_PATH, PARSED_DOCUMENTS_PATH, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS,
    QDRANT_URL, QDRANT_API_KEY, RAG_ALIAS, RAG_DATA_DIR, INGEST_MANIFEST_PATH,
)
from rag_models import (
    encode_dense, sparse_model, embedding_identity, embedding_fingerprint,
    validate_dense_vector, validate_embedding_configuration,
)


def payload_for_chunk(chunk):
    source = chunk['metadata']
    return {**{k: v for k, v in source.items() if k not in {'file_path', 'file_name'}},
            **{k: v for k, v in chunk.items() if k not in {'metadata', 'point_id'}},
            'embedding_model': EMBEDDING_MODEL, 'license_status': source['license_status']}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    if path.exists():
        temporary.chmod(path.stat().st_mode & 0o777)
    temporary.replace(path)


def release_path(collection):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', collection):
        raise ValueError('Invalid release collection name')
    return RAG_DATA_DIR / 'releases' / (collection + '.json')


def validate_release(client, manifest):
    collection = manifest['collection']
    release_path(collection)
    if any(manifest.get(k) != v for k, v in embedding_identity().items()):
        raise ValueError('Embedding identity mismatch')
    if manifest.get('model_fingerprint') != embedding_fingerprint():
        raise ValueError('Embedding fingerprint mismatch')
    info = client.get_collection(collection)
    vectors = info.config.params.vectors
    if (not isinstance(vectors, dict) or 'dense' not in vectors
            or vectors['dense'].size != EMBEDDING_DIMENSIONS
            or vectors['dense'].distance != models.Distance.COSINE
            or 'bm25' not in (info.config.params.sparse_vectors or {})):
        raise ValueError('Incompatible vector schema')
    ids = manifest['point_ids']
    hashes = manifest['point_hashes']
    if (len(set(ids)) != len(ids) or set(ids) != set(hashes)
            or len(ids) != manifest['point_count']
            or client.count(collection, exact=True).count != len(ids)):
        raise ValueError('Exact collection count mismatch')
    documents = set()
    for start in range(0, len(ids), 64):
        expected = set(ids[start:start + 64])
        points = client.retrieve(collection, list(expected), with_payload=True, with_vectors=True)
        if {str(point.id) for point in points} != expected:
            raise ValueError('Point integrity mismatch')
        for point in points:
            payload = point.payload
            if (payload['chunk_hash'] != hashes[str(point.id)]
                    or payload.get('embedding_model') != EMBEDDING_MODEL
                    or payload.get('license_status') != 'APPROVED_FOR_RAG'
                    or 'bm25' not in point.vector):
                raise ValueError('Point integrity mismatch')
            validate_dense_vector(point.vector['dense'])
            document = (payload['document_id'], payload['document_version'])
            documents.add(document)
            path = RAG_DATA_DIR / 'snapshots' / document[0] / f'{document[1]}.json'
            snapshot = json.loads(path.read_text())
            if (snapshot['documentId'], snapshot['version']) != document or not snapshot['text']:
                raise ValueError('Source snapshot mismatch')
    if len({doc for doc, _ in documents}) != manifest['document_count']:
        raise ValueError('Document coverage mismatch')


def publish_release(client, manifest, alias):
    validate_release(client, manifest)
    if manifest['alias'] != alias:
        raise ValueError('Release alias mismatch')
    aliases = {a.alias_name: a.collection_name for a in client.get_aliases().aliases}
    previous = aliases.get(alias)
    collection = manifest['collection']
    if previous != collection and previous != manifest.get('previous_collection'):
        raise ValueError('Active alias changed since candidate build; refusing stale publication')
    if previous is None and client.collection_exists(alias):
        raise ValueError('Alias name is already a physical collection')
    changes = []
    if previous is not None:
        changes.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)))
    changes.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=collection, alias_name=alias)))
    client.update_collection_aliases(changes)
    try:
        atomic_json(INGEST_MANIFEST_PATH, manifest)
    except Exception:
        rollback = [models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))]
        if previous:
            rollback.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=previous, alias_name=alias)))
        client.update_collection_aliases(rollback)
        raise


def build_candidate(client, args):
    chunks = [c for c in read_jsonl(args.chunks) if c['metadata'].get('license_status') == 'APPROVED_FOR_RAG']
    if len({c['point_id'] for c in chunks}) != len(chunks):
        raise ValueError('Duplicate IDs')
    aliases = {a.alias_name: a.collection_name for a in client.get_aliases().aliases}
    if args.collection not in aliases and client.collection_exists(args.collection):
        raise ValueError('Choose a new alias name, not an existing physical collection')
    previous = json.loads(INGEST_MANIFEST_PATH.read_text()) if INGEST_MANIFEST_PATH.exists() else {}
    source_hash = sha256_text(json.dumps([(c['point_id'], payload_for_chunk(c)) for c in chunks], sort_keys=True, ensure_ascii=False))
    fingerprint = embedding_fingerprint()
    if (not args.no_publish and previous.get('corpus_hash') == source_hash
            and previous.get('model_fingerprint') == fingerprint
            and aliases.get(args.collection) == previous.get('collection')):
        validate_release(client, previous)
        return {**previous, 'status': 'unchanged'}
    cache_dir = RAG_DATA_DIR / 'embedding_cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    records, missing = [], []
    for chunk in chunks:
        cached = cache_dir / (sha256_text(fingerprint + chunk['chunk_hash']) + '.json')
        if cached.exists():
            vector = json.loads(cached.read_text())['dense']
            records.append(validate_dense_vector(vector))
        else:
            records.append(None)
            missing.append((len(records) - 1, chunk, cached))
    if missing:
        dense = encode_dense([c['embedding_text'] for _, c, _ in missing], args.batch_size)
        for (index, _, path), vector in zip(missing, dense, strict=True):
            records[index] = vector
            atomic_json(path, {'dense': vector})
    sparse = list(sparse_model().embed([c['embedding_text'] for c in chunks])) if chunks else []
    if len(sparse) != len(chunks):
        raise ValueError('Sparse embedding count mismatch')
    collection = f"{args.collection}_{datetime.now(timezone.utc):%Y%m%d%H%M%S}_{uuid.uuid4().hex[:8]}"
    release_path(collection)
    client.create_collection(collection, vectors_config={'dense': models.VectorParams(size=EMBEDDING_DIMENSIONS, distance=models.Distance.COSINE)}, sparse_vectors_config={'bm25': models.SparseVectorParams(modifier=models.Modifier.IDF)})
    try:
        client.create_payload_index(collection, 'license_status', models.PayloadSchemaType.KEYWORD, wait=True)
        for start in range(0, len(chunks), args.upsert_batch_size):
            points = [models.PointStruct(id=c['point_id'], vector={
                'dense': records[i], 'bm25': models.SparseVector(indices=sparse[i].indices.tolist(), values=sparse[i].values.tolist())},
                payload=payload_for_chunk(c)) for i, c in enumerate(chunks[start:start + args.upsert_batch_size], start)]
            client.upsert(collection, points, wait=True)
        docs = read_jsonl(PARSED_DOCUMENTS_PATH)
        for doc in docs:
            if doc['metadata'].get('license_status') == 'APPROVED_FOR_RAG':
                atomic_json(RAG_DATA_DIR / 'snapshots' / doc['document_id'] / f"{doc['document_version']}.json", {
                    'documentId': doc['document_id'], 'version': doc['document_version'], 'title': doc['title'],
                    'text': doc['body'], 'sourceUrl': doc['metadata']['source_url']})
        old_ids = set(previous.get('point_ids', []))
        new_ids = {c['point_id'] for c in chunks}
        manifest = {
            **embedding_identity(), 'created_at': datetime.now(timezone.utc).isoformat(),
            'collection': collection, 'alias': args.collection, 'previous_collection': aliases.get(args.collection),
            'model_fingerprint': fingerprint, 'distance': 'Cosine', 'sparse_model': 'Qdrant/bm25',
            'bm25': {'k': 1.2, 'b': 0.75, 'avg_len': 256, 'disable_stemmer': True},
            'corpus_hash': source_hash, 'document_count': len({c['document_id'] for c in chunks}),
            'point_count': len(chunks), 'added_points': len(new_ids - old_ids), 'removed_points': len(old_ids - new_ids),
            'embedded_this_run': len(missing), 'reused_embeddings': len(chunks) - len(missing),
            'point_ids': sorted(new_ids), 'point_hashes': {c['point_id']: c['chunk_hash'] for c in chunks},
            'source_chunks': str(args.chunks), 'status': 'ready',
        }
        validate_release(client, manifest)
        atomic_json(release_path(collection), manifest)
        if not args.no_publish:
            publish_release(client, manifest, args.collection)
        return manifest
    except Exception:
        if not any(a.collection_name == collection for a in client.get_aliases().aliases):
            client.delete_collection(collection)
        raise


def synchronize():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chunks', type=Path, default=CHUNKS_PATH)
    parser.add_argument('--url', default=QDRANT_URL)
    parser.add_argument('--collection', default=RAG_ALIAS, help='Stable active alias')
    parser.add_argument('--local-path', type=Path)
    parser.add_argument('--model', default=EMBEDDING_MODEL)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--upsert-batch-size', type=int, default=64)
    parser.add_argument('--document-ids', help='Compatibility option: synchronize full corpus')
    parser.add_argument('--recreate', action='store_true', help='Build a candidate; retain old releases')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--no-publish', action='store_true', help='Validate candidate without changing the active alias')
    mode.add_argument('--publish-release', help='Validate and publish an existing candidate')
    args = parser.parse_args()
    if args.model != EMBEDDING_MODEL or args.batch_size < 1 or args.upsert_batch_size < 1:
        parser.error('Invalid model or batch size')
    release_path(args.collection)
    validate_embedding_configuration()
    client = QdrantClient(path=str(args.local_path)) if args.local_path else QdrantClient(url=args.url, api_key=QDRANT_API_KEY, timeout=60)
    try:
        if args.publish_release:
            manifest = json.loads(release_path(args.publish_release).read_text())
            if manifest['collection'] != args.publish_release:
                raise ValueError('Release collection mismatch')
            publish_release(client, manifest, args.collection)
        else:
            manifest = build_candidate(client, args)
        print(json.dumps({**{k: v for k, v in manifest.items() if k not in {'point_ids', 'point_hashes'}},
                          'published': not args.no_publish}, ensure_ascii=False, indent=2))
    finally:
        client.close()


def main():
    from filelock import FileLock
    RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(str(RAG_DATA_DIR / 'sync.lock'), timeout=120):
        synchronize()


if __name__ == '__main__':
    main()
