"""Private inference routes. The parent FastAPI app enforces X-Rag-Token."""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from incident_processing import PIPELINE, extract, cosine, embedding_text

router = APIRouter(prefix='/incidents', tags=['incidents'])
logger = logging.getLogger('vietflood.incidents')


class Analyze(BaseModel):
    model_config = ConfigDict(extra='forbid')
    description: str = Field(min_length=1, max_length=6000)
    province: str = Field(default='', max_length=200)
    ward: str = Field(default='', max_length=200)
    addressLine: str = Field(default='', max_length=500)
    requestId: str = Field(default='', max_length=100)


@router.post('/analyze')
def analyze(body: Analyze):
    # This route does not require Qdrant, BM25, or reranker readiness.
    from rag_models import encode_dense, embedding_fingerprint
    try:
        result = extract(body.description)
        embedding = encode_dense([embedding_text(result)])[0]
        return {**result, 'embedding': embedding, 'fingerprint': embedding_fingerprint(), 'pipeline': PIPELINE}
    except Exception as exc:
        logger.warning('incident_analysis_failed', extra={'requestId': body.requestId, 'errorType': type(exc).__name__})
        raise HTTPException(503, 'Incident analysis unavailable') from None


class Similarity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    vector: list[float] = Field(min_length=1536, max_length=1536)
    candidates: list[list[float]] = Field(min_length=1, max_length=100)


@router.post('/similarity')
def similarity(body: Similarity):
    try:
        return {'scores': [cosine(body.vector, candidate) for candidate in body.candidates]}
    except ValueError:
        raise HTTPException(400, 'Invalid vectors') from None
