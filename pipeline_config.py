"""Shared configuration for the VietFlood Qdrant ingestion pipeline."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
# Local development only; containers supply environment variables directly.
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _key, _sep, _value = _line.partition("=")
        if _sep and _key.strip() in {"QDRANT_URL", "QDRANT_API_KEY", "QDRANT_CHAT_COLLECTION", "RAG_SERVICE_TOKEN", "RAG_DATA_DIR", "EMBEDDING_MODEL", "RERANK_MODEL"}:
            os.environ.setdefault(_key.strip(), _value.strip().strip("\"'"))
MARKDOWN_DIR = PROJECT_ROOT / "rag_sources" / "markdown"
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", str(PROJECT_ROOT / "data")))
DEFAULT_MODEL_CACHE_DIR = (
    Path.home() / ".cache" / "huggingface"
    if os.name == "posix"
    else PROJECT_ROOT / ".model_cache"
)
MODEL_CACHE_DIR = Path(os.getenv("HF_HOME", str(DEFAULT_MODEL_CACHE_DIR)))
# Set this before importing transformers/sentence-transformers in the CLI scripts.
os.environ.setdefault("HF_HOME", str(MODEL_CACHE_DIR))
SOURCE_REGISTRY_PATH = PROJECT_ROOT / "source_registry.jsonl"
PARSED_DOCUMENTS_PATH = DATA_DIR / "parsed_documents.jsonl"
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
INGEST_MANIFEST_PATH = DATA_DIR / "ingest_manifest.json"

# Selected baseline: multilingual, supports Vietnamese and English, modest enough
# for a local thesis prototype. E5 requires passage/query prefixes.
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "intfloat/multilingual-e5-base"
)
EMBEDDING_DOCUMENT_PREFIX = "passage: "
EMBEDDING_QUERY_PREFIX = "query: "

QDRANT_URL = os.getenv(
    "QDRANT_URL", "https://qdrant.ndtd.indevs.in:443"
)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv(
    "QDRANT_COLLECTION",
    os.getenv("QDRANT_COLLECTION_NAME", "flood_kb_staging_2026_01"),
)

ELIGIBLE_REPRESENTATIONS = {
    "faithful_paraphrase",
    "structured_faithful_paraphrase",
    "user-guide",
}
TOPICS_BY_PREFIX = {
    "G": ["VIETFLOOD_APP_GUIDANCE"],
    "F": ["FLOOD_KNOWLEDGE", "DROWNING_PREVENTION"],
    "S": ["FLOOD_SAFETY"],
    "M": ["FIRST_AID", "HEALTH"],
    "E": ["EMERGENCY_PREPAREDNESS"],
    "H": ["WATER_SANITATION_HYGIENE"],
    "P": ["POST_FLOOD_CLEANUP", "HOME_SAFETY"],
    "V": ["VULNERABLE_GROUPS"],
    "W": ["DISASTER_RISK_REDUCTION"],
    "L": ["LIVE_ALERT"],
}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

RAG_ALIAS = os.getenv("QDRANT_CHAT_COLLECTION", "flood_kb_active")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RAG_DATA_DIR = Path(os.getenv("RAG_DATA_DIR", str(DATA_DIR)))
