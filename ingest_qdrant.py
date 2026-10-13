"""Synchronize the exact approved corpus through immutable candidate releases."""
from __future__ import annotations
import argparse,json,os,uuid
from datetime import datetime,timezone
from pathlib import Path
from qdrant_client import QdrantClient,models
from kb_common import read_jsonl,sha256_text
from pipeline_config import CHUNKS_PATH,PARSED_DOCUMENTS_PATH,EMBEDDING_MODEL,EMBEDDING_DOCUMENT_PREFIX,QDRANT_URL,QDRANT_API_KEY,RAG_ALIAS,RAG_DATA_DIR,INGEST_MANIFEST_PATH
from rag_models import encode_dense,sparse_model,dense_model_revision

PIPELINE_VERSION='rag-v2-tokenizer450-bm25-nostem-256'

def payload_for_chunk(c):
    source=c['metadata']
    return {**{k:v for k,v in source.items() if k not in {'file_path','file_name'}},**{k:v for k,v in c.items() if k not in {'metadata','point_id'}},'embedding_model':EMBEDDING_MODEL,'license_status':source['license_status']}

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)

def synchronize():
    parser=argparse.ArgumentParser()
    parser.add_argument('--chunks',type=Path,default=CHUNKS_PATH)
    parser.add_argument('--url',default=QDRANT_URL)
    parser.add_argument('--collection',default=RAG_ALIAS,help='Active alias; publishes a new immutable candidate')
    parser.add_argument('--local-path',type=Path)
    parser.add_argument('--model',default=EMBEDDING_MODEL)
    parser.add_argument('--batch-size',type=int,default=16)
    parser.add_argument('--upsert-batch-size',type=int,default=64)
    parser.add_argument('--document-ids',help='Compatibility option: synchronize full corpus, reuse unchanged embeddings')
    parser.add_argument('--recreate',action='store_true',help='Build a candidate; never delete the currently active release')
    args=parser.parse_args()
    if args.model!=EMBEDDING_MODEL or args.batch_size<1 or args.upsert_batch_size<1: parser.error('Invalid model or batch size')
    chunks=[c for c in read_jsonl(args.chunks) if c['metadata'].get('license_status')=='APPROVED_FOR_RAG']
    if len({c['point_id'] for c in chunks})!=len(chunks): raise ValueError('Duplicate IDs')
    client=QdrantClient(path=str(args.local_path)) if args.local_path else QdrantClient(url=args.url,api_key=QDRANT_API_KEY,timeout=60)
    # An alias cannot have the same name as an existing physical collection.
    aliases={a.alias_name:a.collection_name for a in client.get_aliases().aliases}
    if args.collection not in aliases and client.collection_exists(args.collection):
        raise ValueError('Choose a new alias name, not an existing physical collection')
    previous=json.loads(INGEST_MANIFEST_PATH.read_text()) if INGEST_MANIFEST_PATH.exists() else {}
    source_hash=sha256_text(json.dumps([(c['point_id'],payload_for_chunk(c)) for c in chunks],sort_keys=True,ensure_ascii=False))
    cache_dir=RAG_DATA_DIR/'embedding_cache'; cache_dir.mkdir(parents=True,exist_ok=True)
    # Cache keys include the resolved tokenizer/model revision, not just dimensions.
    from rag_models import dense_model
    dense_model()
    revision=dense_model_revision()
    fingerprint=sha256_text(EMBEDDING_MODEL+str(revision)+PIPELINE_VERSION)
    if previous.get('corpus_hash')==source_hash and previous.get('model_fingerprint')==fingerprint and aliases.get(args.collection)==previous.get('collection'):
        print(json.dumps({'status':'unchanged','collection':previous['collection'],'point_count':len(chunks)})); client.close(); return
    collection=f"{args.collection}_{datetime.now(timezone.utc):%Y%m%d%H%M%S}_{uuid.uuid4().hex[:8]}"
    records=[]; missing=[]; added=0; reused=0
    for c in chunks:
        key=sha256_text(fingerprint+c['chunk_hash']); cached=cache_dir/(key+'.json')
        if cached.exists(): records.append(json.loads(cached.read_text())); reused+=1
        else: records.append(None); missing.append((len(records)-1,c,cached)); added+=1
    if missing:
        texts=[EMBEDDING_DOCUMENT_PREFIX+c['embedding_text'] for _,c,_ in missing]
        dense=encode_dense(texts,args.batch_size)
        for (index,c,path),vector in zip(missing,dense,strict=True):
            records[index]={'dense':vector}; atomic_json(path,records[index])
    sparse=list(sparse_model().embed([c['embedding_text'] for c in chunks])) if chunks else []
    client.create_collection(collection,vectors_config={'dense':models.VectorParams(size=768,distance=models.Distance.COSINE)},sparse_vectors_config={'bm25':models.SparseVectorParams(modifier=models.Modifier.IDF)})
    client.create_payload_index(collection,'license_status',models.PayloadSchemaType.KEYWORD,wait=True)
    try:
        for start in range(0,len(chunks),args.upsert_batch_size):
            points=[models.PointStruct(id=c['point_id'],vector={'dense':records[i]['dense'],'bm25':models.SparseVector(indices=sparse[i].indices.tolist(),values=sparse[i].values.tolist())},payload=payload_for_chunk(c)) for i,c in enumerate(chunks[start:start+args.upsert_batch_size],start)]
            client.upsert(collection,points,wait=True)
        if client.count(collection,exact=True).count!=len(chunks): raise ValueError('Exact collection count mismatch')
        for start in range(0,len(chunks),64):
            expected={c['point_id']:c['chunk_hash'] for c in chunks[start:start+64]}
            actual=client.retrieve(collection,list(expected),with_payload=True,with_vectors=True)
            if len(actual)!=len(expected) or any(p.payload['chunk_hash']!=expected[str(p.id)] or len(p.vector['dense'])!=768 or 'bm25' not in p.vector for p in actual): raise ValueError('Point integrity mismatch')
        docs=read_jsonl(PARSED_DOCUMENTS_PATH)
        for doc in docs:
            if doc['metadata'].get('license_status')=='APPROVED_FOR_RAG':
                atomic_json(RAG_DATA_DIR/'snapshots'/doc['document_id']/f"{doc['document_version']}.json",{'documentId':doc['document_id'],'version':doc['document_version'],'title':doc['title'],'text':doc['body'],'sourceUrl':doc['metadata']['source_url']})
        old_ids=set(previous.get('point_ids',[])); new_ids={c['point_id'] for c in chunks}
        manifest={'created_at':datetime.now(timezone.utc).isoformat(),'collection':collection,'alias':args.collection,'previous_collection':aliases.get(args.collection),'embedding_model':EMBEDDING_MODEL,'model_revision':revision,'model_fingerprint':fingerprint,'pipeline_version':PIPELINE_VERSION,'vector_size':768,'distance':'Cosine','sparse_model':'Qdrant/bm25','bm25':{'k':1.2,'b':0.75,'avg_len':256,'disable_stemmer':True},'corpus_hash':source_hash,'document_count':len({c['document_id'] for c in chunks}),'point_count':len(chunks),'added_points':len(new_ids-old_ids),'removed_points':len(old_ids-new_ids),'embedded_this_run':added,'reused_embeddings':reused,'point_ids':sorted(new_ids),'source_chunks':str(args.chunks),'status':'ready'}
        atomic_json(RAG_DATA_DIR/'releases'/(collection+'.json'),manifest)
        changes=[]
        if args.collection in aliases: changes.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=args.collection)))
        changes.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=collection,alias_name=args.collection)))
        client.update_collection_aliases(changes)
        atomic_json(INGEST_MANIFEST_PATH,manifest)
        print(json.dumps({k:v for k,v in manifest.items() if k!='point_ids'},ensure_ascii=False,indent=2))
    except Exception:
        # Candidate never replaces active alias unless all integrity checks succeeded.
        if not any(a.collection_name==collection for a in client.get_aliases().aliases): client.delete_collection(collection)
        raise
    finally: client.close()
def main():
    from filelock import FileLock
    RAG_DATA_DIR.mkdir(parents=True,exist_ok=True)
    with FileLock(str(RAG_DATA_DIR/'sync.lock'),timeout=120): synchronize()
if __name__=='__main__': main()
