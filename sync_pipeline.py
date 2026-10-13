"""Single synchronized entrypoint for portal, CLI and watcher."""
import sys
from filelock import FileLock
from pipeline_config import RAG_DATA_DIR,PARSED_DOCUMENTS_PATH,CHUNKS_PATH,SOURCE_REGISTRY_PATH,MARKDOWN_DIR
from kb_common import write_jsonl
from build_source_registry import build_registry
from parse_markdown import parse_registry_record
from chunk_documents import chunk_document
from ingest_qdrant import synchronize

def main():
    # Publishing a prepared release must not regenerate the corpus.
    if '--publish-release' in sys.argv:
        from ingest_qdrant import main as publish
        publish()
        return
    RAG_DATA_DIR.mkdir(parents=True,exist_ok=True)
    with FileLock(str(RAG_DATA_DIR/'sync.lock'),timeout=120):
        registry=build_registry(MARKDOWN_DIR); write_jsonl(SOURCE_REGISTRY_PATH,registry)
        docs=[parse_registry_record(r) for r in registry if r.get('ingest_eligible') and r.get('license_status')=='APPROVED_FOR_RAG']
        write_jsonl(PARSED_DOCUMENTS_PATH,docs)
        write_jsonl(CHUNKS_PATH,[c for doc in docs for c in chunk_document(doc)])
        synchronize()
if __name__=='__main__': main()
