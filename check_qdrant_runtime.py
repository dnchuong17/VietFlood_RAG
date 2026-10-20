"""Read-only connectivity probe, run on the same Docker network as deployment."""
import sys
from qdrant_client import QdrantClient
from pipeline_config import QDRANT_URL, QDRANT_CONFIGURED_URL, QDRANT_INTERNAL_URL, QDRANT_API_KEY, RAG_ALIAS
from runtime_diagnostics import error_details, event, qdrant_call


def main():
    client = None
    try:
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=10)
        aliases = {a.alias_name: a.collection_name for a in qdrant_call(client.get_aliases).aliases}
        if QDRANT_INTERNAL_URL and QDRANT_CONFIGURED_URL.rstrip('/') != QDRANT_URL.rstrip('/'):
            # Reject an unrelated local database before embedding or mutation.
            public = QdrantClient(url=QDRANT_CONFIGURED_URL, api_key=QDRANT_API_KEY, timeout=10)
            try:
                expected = {a.alias_name: a.collection_name for a in qdrant_call(public.get_aliases).aliases}
                if expected.get(RAG_ALIAS) != aliases.get(RAG_ALIAS):
                    raise ValueError('Internal Qdrant active alias does not match configured endpoint')
                if RAG_ALIAS not in expected:
                    # For first installs, compare collection names rather than accepting
                    # any empty/missing alias as proof that the databases match.
                    actual_names = {c.name for c in qdrant_call(client.get_collections).collections}
                    expected_names = {c.name for c in qdrant_call(public.get_collections).collections}
                    if actual_names != expected_names:
                        raise ValueError('Internal Qdrant collections do not match configured endpoint')
            finally:
                public.close()
            event('qdrant_internal_identity_verified')
        if RAG_ALIAS in aliases:
            qdrant_call(client.get_collection, aliases[RAG_ALIAS])
        elif qdrant_call(client.collection_exists, RAG_ALIAS):
            raise ValueError('Deployment requires an alias, not a physical collection')
        event('qdrant_connectivity_ready', transport='internal' if QDRANT_INTERNAL_URL else 'configured')
        return 0
    except Exception as error:
        event('qdrant_connectivity_failed', **error_details(error))
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == '__main__':
    sys.exit(main())
