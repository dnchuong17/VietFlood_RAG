"""Shared API embeddings, token counting, BM25 and local reranking."""
from functools import lru_cache
import hashlib
import json
import math
from urllib.parse import urlparse

from pipeline_config import (
    EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, EMBEDDING_TOKENIZER,
    EMBEDDING_MAX_TOKENS, OPENAI_BASE_URL, OPENAI_API_KEY,
    PIPELINE_VERSION, RERANK_MODEL,
)


def embedding_identity():
    """API model aliases have no immutable Hugging Face commit."""
    return {
        'embedding_provider': 'openai-compatible',
        'embedding_base_url': OPENAI_BASE_URL,
        'embedding_model': EMBEDDING_MODEL,
        'vector_size': EMBEDDING_DIMENSIONS,
        'tokenizer': EMBEDDING_TOKENIZER,
        'pipeline_version': PIPELINE_VERSION,
        'model_revision': None,
    }


def embedding_fingerprint():
    return hashlib.sha256(json.dumps(embedding_identity(), sort_keys=True).encode()).hexdigest()


def validate_embedding_configuration():
    url = urlparse(OPENAI_BASE_URL)
    if (url.scheme != 'https' or not url.netloc or url.username or url.password
            or url.query or url.fragment):
        raise ValueError('Invalid embedding API URL')
    if not OPENAI_API_KEY:
        raise ValueError('Missing OPENAI_API_KEY')
    if EMBEDDING_MODEL != 'text-embedding-3-small' or EMBEDDING_DIMENSIONS != 1536:
        raise ValueError('Expected text-embedding-3-small with 1536 dimensions')


@lru_cache(maxsize=1)
def dense_model():
    from openai import OpenAI
    validate_embedding_configuration()
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL,
                  timeout=30.0, max_retries=1)


@lru_cache(maxsize=1)
def get_tokenizer():
    import tiktoken
    return tiktoken.get_encoding(EMBEDDING_TOKENIZER)


def token_count(text, tokenizer=None):
    return len((tokenizer or get_tokenizer()).encode(text, disallowed_special=()))


def validate_dense_vector(vector):
    if (not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS
            or any(isinstance(x, bool) or not isinstance(x, (int, float))
                   or not math.isfinite(x) for x in vector)):
        raise ValueError('Invalid embedding vector')
    return vector


def encode_dense(texts, batch_size=16):
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError('Invalid embedding batch size')
    texts = list(texts)
    lengths = []
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Empty embedding input')
        count = token_count(text)
        if count > EMBEDDING_MAX_TOKENS:
            raise ValueError('Input exceeds embedding token limit; refusing truncation')
        lengths.append(count)
    if not texts:
        return []
    result = []
    batch = []
    tokens = 0
    batches = []
    for text, count in zip(texts, lengths, strict=True):
        if batch and (len(batch) >= min(batch_size, 2048) or tokens + count > 300000):
            batches.append(batch)
            batch, tokens = [], 0
        batch.append(text)
        tokens += count
    if batch:
        batches.append(batch)
    for batch in batches:
        response = dense_model().embeddings.create(
            model=EMBEDDING_MODEL, input=batch, dimensions=EMBEDDING_DIMENSIONS,
            encoding_format='float',
        )
        ordered = [None] * len(batch)
        for item in response.data:
            index = item.index
            if (not isinstance(index, int) or isinstance(index, bool)
                    or not 0 <= index < len(batch) or ordered[index] is not None):
                raise ValueError('Invalid or duplicate embedding response index')
            ordered[index] = validate_dense_vector(item.embedding)
        if any(vector is None for vector in ordered):
            raise ValueError('Missing embedding response indices')
        result.extend(ordered)
    return result


@lru_cache(maxsize=1)
def sparse_model():
    from fastembed import SparseTextEmbedding
    return SparseTextEmbedding(model_name='Qdrant/bm25', disable_stemmer=True,
                               stopwords=set(), k=1.2, b=0.75, avg_len=256.0)


@lru_cache(maxsize=1)
def rerank_model():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(RERANK_MODEL, max_length=1024)
