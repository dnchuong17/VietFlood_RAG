"""Read-only connectivity probe, run on the same Docker network as deployment."""
import sys
from qdrant_client import QdrantClient
from pipeline_config import QDRANT_URL, QDRANT_API_KEY, RAG_ALIAS
from runtime_diagnostics import error_details, event, qdrant_call


def main():
    client = None
    try:
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=10)
        aliases = {a.alias_name: a.collection_name for a in qdrant_call(client.get_aliases).aliases}
        if RAG_ALIAS in aliases:
            qdrant_call(client.get_collection, aliases[RAG_ALIAS])
        elif qdrant_call(client.collection_exists, RAG_ALIAS):
            raise ValueError('Deployment requires an alias, not a physical collection')
        event('qdrant_connectivity_ready')
        return 0
    except Exception as error:
        event('qdrant_connectivity_failed', **error_details(error))
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == '__main__':
    sys.exit(main())
