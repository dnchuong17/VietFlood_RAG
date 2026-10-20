"""Initialize persistent upload sources once, without overwriting operator edits."""
from pathlib import Path
import shutil
import uuid

from filelock import FileLock
from pipeline_config import (
    MARKDOWN_DIR, SEED_MARKDOWN_DIR, PROJECT_ROOT, SOURCE_REGISTRY_PATH, RAG_DATA_DIR,
)


def initialize_corpus():
    if MARKDOWN_DIR.resolve() == SEED_MARKDOWN_DIR.resolve():
        return
    if MARKDOWN_DIR.exists() and SOURCE_REGISTRY_PATH.exists():
        return
    RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(str(RAG_DATA_DIR / 'sync.lock'), timeout=5):
        if MARKDOWN_DIR.exists():
            # An existing directory is authoritative, including intentional deletions.
            if not SOURCE_REGISTRY_PATH.exists():
                raise RuntimeError('Persistent source registry is missing')
            return
        seed_registry = PROJECT_ROOT / 'source_registry.jsonl'
        if not seed_registry.is_file() or not list(SEED_MARKDOWN_DIR.glob('*.md')):
            raise RuntimeError('Image does not contain the seed corpus')
        MARKDOWN_DIR.parent.mkdir(parents=True, exist_ok=True)
        temporary = MARKDOWN_DIR.with_name('.sources-' + uuid.uuid4().hex)
        temporary.mkdir()
        try:
            for source in SEED_MARKDOWN_DIR.glob('*.md'):
                shutil.copy2(source, temporary / source.name)
            if not SOURCE_REGISTRY_PATH.exists():
                registry_tmp = SOURCE_REGISTRY_PATH.with_suffix('.jsonl.tmp')
                shutil.copy2(seed_registry, registry_tmp)
                registry_tmp.replace(SOURCE_REGISTRY_PATH)
            temporary.replace(MARKDOWN_DIR)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
