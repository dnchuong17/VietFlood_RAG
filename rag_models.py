"""Shared, lazy models and encoders for ingestion and production retrieval."""
from functools import lru_cache
from pathlib import Path
import re
from pipeline_config import EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION, RERANK_MODEL

@lru_cache(maxsize=1)
def dense_model_revision():
    from huggingface_hub import hf_hub_download
    config_path=Path(hf_hub_download(
        repo_id=EMBEDDING_MODEL, filename='config.json', revision=EMBEDDING_MODEL_REVISION,
    ))
    # Hub cache paths identify the actual commit; Transformers' private
    # _commit_hash attributes are not available in every supported version.
    revision=config_path.parent.name
    if config_path.parent.parent.name!='snapshots' or not re.fullmatch(r'[0-9a-f]{40}',revision):
        raise ValueError('Cannot resolve embedding model commit from Hub cache')
    return revision

@lru_cache(maxsize=1)
def dense_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL, revision=dense_model_revision())

@lru_cache(maxsize=1)
def sparse_model():
    from fastembed import SparseTextEmbedding
    return SparseTextEmbedding(model_name='Qdrant/bm25', disable_stemmer=True, stopwords=set(), k=1.2, b=0.75, avg_len=256.0)

@lru_cache(maxsize=1)
def rerank_model():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(RERANK_MODEL, max_length=1024)

def encode_dense(texts, batch_size=16):
    model=dense_model()
    for text in texts:
        ids=model.tokenizer.encode(text,add_special_tokens=True,truncation=False)
        if len(ids)>min(512,model.max_seq_length):
            raise ValueError('Input exceeds E5 limit; refusing silent truncation')
    return model.encode(texts,batch_size=batch_size,normalize_embeddings=True).tolist()
