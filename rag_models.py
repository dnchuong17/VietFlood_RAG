"""Shared, lazy models and encoders for ingestion and production retrieval."""
from functools import lru_cache
from pipeline_config import EMBEDDING_MODEL, RERANK_MODEL

@lru_cache(maxsize=1)
def dense_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)

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
