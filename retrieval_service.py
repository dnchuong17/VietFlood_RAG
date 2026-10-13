"""Internal hybrid retrieval API. Never expose the import portal on this server."""
import json,logging,os,re,threading,unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI,HTTPException,Header,Depends
from pydantic import BaseModel,Field
from qdrant_client import QdrantClient,models
from pipeline_config import QDRANT_URL,QDRANT_API_KEY,RAG_ALIAS,RAG_DATA_DIR,EMBEDDING_MODEL,RERANK_MODEL,EMBEDDING_QUERY_PREFIX,EMBEDDING_DIMENSIONS
from rag_models import dense_model,sparse_model,rerank_model,encode_dense,embedding_identity,embedding_fingerprint,validate_embedding_configuration
logger=logging.getLogger('vietflood.retrieval')
client=QdrantClient(url=QDRANT_URL,api_key=QDRANT_API_KEY,timeout=10)
model_lock=threading.Lock()

def safe_error(exc):
    # Provider exceptions may contain private request/response bodies.
    if type(exc).__module__.startswith(('openai','httpx','httpcore')):
        return type(exc).__name__
    message=str(exc)
    for secret in (QDRANT_API_KEY,os.getenv('RAG_SERVICE_TOKEN',''),os.getenv('OPENAI_API_KEY','')):
        if secret: message=message.replace(secret,'[redacted]')
    return message[:500]

def authorization(x_rag_token:str=Header(default='')):
    import secrets
    token=os.getenv('RAG_SERVICE_TOKEN','')
    if not token or not secrets.compare_digest(token,x_rag_token): raise HTTPException(401,'Retrieval service authentication required')

def readiness():
    info=client.get_collection(RAG_ALIAS)
    vectors=info.config.params.vectors
    if not isinstance(vectors,dict) or 'dense' not in vectors or vectors['dense'].size!=EMBEDDING_DIMENSIONS or vectors['dense'].distance!=models.Distance.COSINE or 'bm25' not in (info.config.params.sparse_vectors or {}): raise ValueError('Incompatible vector schema')
    aliases={a.alias_name:a.collection_name for a in client.get_aliases().aliases}
    actual=aliases.get(RAG_ALIAS,RAG_ALIAS)
    manifest=json.loads((RAG_DATA_DIR/'releases'/(actual+'.json')).read_text())
    validate_embedding_configuration()
    if manifest['embedding_model']!=EMBEDDING_MODEL:
        raise ValueError(f"Embedding model mismatch: manifest={manifest['embedding_model']}, loaded={EMBEDDING_MODEL}")
    if any(manifest.get(k)!=v for k,v in embedding_identity().items()) or manifest.get('model_fingerprint')!=embedding_fingerprint():
        raise ValueError('Embedding identity/fingerprint mismatch')
    count=client.count(actual,exact=True).count
    if count!=manifest['point_count']: raise ValueError('Manifest/collection count mismatch')
    return {'status':'ready','alias':RAG_ALIAS,'collection':actual,'pointCount':count,'embeddingModel':EMBEDDING_MODEL,'modelRevision':None,'reranker':RERANK_MODEL,'vectorSize':EMBEDDING_DIMENSIONS}

@asynccontextmanager
async def lifespan(app):
    try:
        dense_model(); sparse_model(); rerank_model()
        logger.warning(json.dumps({'event':'retrieval_startup',**readiness()}))
        app.state.models_ready=True
    except Exception as exc:
        app.state.models_ready=False
        logger.error(json.dumps({'event':'retrieval_startup_failed','errorType':type(exc).__name__,'httpStatus':getattr(exc,'status_code',None),'error':safe_error(exc)}))
    yield
    client.close()
app=FastAPI(title='VietFlood Retrieval',lifespan=lifespan,dependencies=[Depends(authorization)])

class Search(BaseModel):
    queries:list[str]=Field(min_length=1,max_length=3)
    candidateLimit:int=Field(default=20,ge=1,le=60)
    limit:int=Field(default=6,ge=1,le=20)
    requestId:str=Field(default='',max_length=100)

@app.get('/health/ready')
def health():
    try:
        if not getattr(app.state,'models_ready',False): raise ValueError('Models are not loaded')
        return readiness()
    except Exception as exc:
        logger.error(json.dumps({'event':'readiness_failed','errorType':type(exc).__name__,'httpStatus':getattr(exc,'status_code',None),'error':safe_error(exc)}))
        raise HTTPException(503,'Retrieval is not ready')

@app.post('/search')
def search(body:Search):
    try:
        if not getattr(app.state,'models_ready',False): raise HTTPException(503,'Models are not loaded')
        ready=readiness(); collection=ready['collection']
        queries=[unicodedata.normalize('NFC',q).strip() for q in body.queries]
        if any(not q or len(q)>2000 for q in queries): raise HTTPException(400,'Invalid query length')
        with model_lock:
            dense=encode_dense([EMBEDDING_QUERY_PREFIX+q for q in queries])
            sparse=list(sparse_model().query_embed(queries))
            candidates={}
            query_results=[]
            policy=models.Filter(must=[models.FieldCondition(key='license_status',match=models.MatchValue(value='APPROVED_FOR_RAG'))])
            for q,d,s in zip(queries,dense,sparse,strict=True):
                points=client.query_points(collection,prefetch=[models.Prefetch(query=d,using='dense',limit=body.candidateLimit,filter=policy),models.Prefetch(query=models.SparseVector(indices=s.indices.tolist(),values=s.values.tolist()),using='bm25',limit=body.candidateLimit,filter=policy)],query=models.FusionQuery(fusion=models.Fusion.RRF),limit=body.candidateLimit,with_payload=True).points
                query_results.append(points)
            from itertools import zip_longest
            for group in zip_longest(*query_results):
                for point in group:
                    if point and point.payload.get('license_status')=='APPROVED_FOR_RAG': candidates.setdefault(str(point.id),point)
            points=list(candidates.values())[:60]
            # Preserve candidate representation from every subquery before global reranking.
            if points:
                scores=rerank_model().predict([(q,p.payload.get('embedding_text',p.payload['text'])) for q in queries for p in points], batch_size=8).reshape(len(queries),len(points))
                per_query=[sorted(zip(points,row.tolist()),key=lambda pair:pair[1],reverse=True) for row in scores]
                chosen={}
                for group in zip_longest(*per_query):
                    for pair in group:
                        if pair: chosen.setdefault(str(pair[0].id),pair)
                        if len(chosen)>=body.limit: break
                    if len(chosen)>=body.limit: break
                ranked=list(chosen.values())
            else: ranked=[]
        if body.limit>6 and ranked:
            primary_count=max(6,body.limit-4)
            primary=ranked[:primary_count]
            neighbor_ids=[]
            for point,_score in primary:
                for key in ['previous_point_id','next_point_id']:
                    neighbor=point.payload.get(key)
                    if neighbor and neighbor not in {str(p.id) for p,_ in primary} and neighbor not in neighbor_ids: neighbor_ids.append(neighbor)
            if neighbor_ids:
                neighbors=client.retrieve(collection,neighbor_ids[:8],with_payload=True,with_vectors=False)
                available={str(p.id):p for p in neighbors if p.payload.get('license_status')=='APPROVED_FOR_RAG'}
                ranked=primary+[(available[id],0.0) for id in neighbor_ids if id in available][:body.limit-len(primary)]
        passages=[]
        for point,score in ranked:
            p=point.payload; url=p.get('source_url',''); parsed=urlparse(url)
            if parsed.scheme not in {'http','https'}: url=''
            passages.append({'id':str(point.id),'documentId':p['document_id'],'version':p['document_version'],'title':p['title'],'sectionPath':p['section_path'],'text':p['text'],'sourceUrl':url,'chunkHash':p['chunk_hash'],'score':float(score),'metadata':{k:p.get(k) for k in ['publisher','language','country_code','topics','source_ids','license_status','embedding_model','parent_section_id','previous_point_id','next_point_id']}})
        logger.warning(json.dumps({'event':'retrieval_complete','requestId':body.requestId,'candidateCount':len(points),'passageCount':len(passages),'collection':collection}))
        return {'passages':passages,'collection':collection,'candidateCount':len(points)}
    except HTTPException: raise
    except Exception as exc:
        logger.error(json.dumps({'event':'retrieval_failed','requestId':body.requestId,'errorType':type(exc).__name__,'httpStatus':getattr(exc,'status_code',None)}))
        raise HTTPException(503,'Retrieval failed')

@app.get('/documents/{document_id}/{version}')
def document(document_id:str,version:int):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',document_id) or version<1: raise HTTPException(400,'Invalid source')
    path=RAG_DATA_DIR/'snapshots'/document_id/f'{version}.json'
    if not path.exists(): raise HTTPException(404,'Source snapshot not found')
    snapshot=json.loads(path.read_text())
    snapshot['active']=client.count(RAG_ALIAS,count_filter=models.Filter(must=[models.FieldCondition(key='document_id',match=models.MatchValue(value=document_id)),models.FieldCondition(key='document_version',match=models.MatchValue(value=version))]),exact=True).count>0
    return snapshot
