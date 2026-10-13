"""Token-budgeted Markdown chunks; all budgets include the full E5 input."""
from __future__ import annotations
import argparse
import re
import unicodedata
import uuid
from functools import lru_cache
from kb_common import read_jsonl, sha256_text, write_jsonl
from pipeline_config import CHUNKS_PATH, PARSED_DOCUMENTS_PATH, EMBEDDING_MODEL, EMBEDDING_DOCUMENT_PREFIX
from rag_models import dense_model_revision

@lru_cache(maxsize=1)
def get_tokenizer():
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(EMBEDDING_MODEL, revision=dense_model_revision())

def token_count(text, tokenizer=None):
    return len((tokenizer or get_tokenizer()).encode(text, add_special_tokens=True, truncation=False))

def chunk_document(document, max_tokens=450, overlap_tokens=50, tokenizer=None):
    tok = tokenizer or get_tokenizer()
    hard = min(512, tok.model_max_length)
    budget = min(max_tokens, hard)
    chunks=[]
    for section in document['sections']:
        path=[x for x in section['section_path'] if x]
        heading='\n'.join([document['title'], ' > '.join(path)]).strip()
        prefix=EMBEDDING_DOCUMENT_PREFIX + heading + '\n\n'
        if token_count(prefix,tok)>=budget:
            raise ValueError(f"Heading exceeds token budget: {document['document_id']} section {section['section_index']}")
        def fits(text): return token_count(prefix+text,tok)<=budget
        # Paragraphs and complete list blocks stay together whenever they fit.
        blocks=[x.strip() for x in re.split(r'\n\s*\n',unicodedata.normalize('NFC',section['text'])) if x.strip()]
        units=[]
        for block in blocks:
            if fits(block):
                units.append(block); continue
            sentences=[x.strip() for x in re.split(r'(?<=[.!?…])\s+|\n(?=\s*(?:[-*+] |\d+[.)] ))',block) if x.strip()]
            for sentence in sentences:
                if fits(sentence): units.append(sentence); continue
                # Oversized individual sentences split by word offsets, with no lost words.
                words=sentence.split(); current=[]
                for word in words:
                    if not fits(word): raise ValueError(f"Unsplittable token: {document['document_id']} section {section['section_index']}")
                    if current and not fits(' '.join(current+[word])):
                        units.append(' '.join(current)); current=[]
                    current.append(word)
                if current: units.append(' '.join(current))
        groups=[]; current=[]
        for unit in units:
            if current and not fits('\n\n'.join(current+[unit])):
                groups.append(current)
                overlap=[]
                for old in reversed(current):
                    candidate=[old]+overlap
                    if token_count('\n\n'.join(candidate),tok)>overlap_tokens: break
                    overlap=candidate
                while overlap and not fits('\n\n'.join(overlap+[unit])): overlap.pop(0)
                current=overlap
            current.append(unit)
        if current: groups.append(current)
        section_chunks=[]
        for group in groups:
            text='\n\n'.join(group)
            embedding_text=heading+'\n\n'+text
            count=token_count(EMBEDDING_DOCUMENT_PREFIX+embedding_text,tok)
            if count>hard: raise ValueError('Embedding input would be truncated')
            digest=sha256_text(embedding_text)
            index=len(chunks)
            point_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f"{document['document_id']}:{document['document_version']}:{index}:{digest}"))
            row=dict(point_id=point_id,document_id=document['document_id'],document_version=document['document_version'],chunk_id=point_id,chunk_index=index,section_index=section['section_index'],section_path=path,section_paths=[path],parent_section_id=f"{document['document_id']}:{section['section_index']}",title=document['title'],text=text,embedding_text=embedding_text,token_count=count,estimated_tokens=count,chunk_hash=digest,metadata=document['metadata'])
            chunks.append(row); section_chunks.append(row)
        for i,row in enumerate(section_chunks):
            row['previous_point_id']=section_chunks[i-1]['point_id'] if i else None
            row['next_point_id']=section_chunks[i+1]['point_id'] if i+1<len(section_chunks) else None
    return chunks

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=__import__('pathlib').Path,default=PARSED_DOCUMENTS_PATH)
    parser.add_argument('--output',type=__import__('pathlib').Path,default=CHUNKS_PATH)
    parser.add_argument('--max-tokens',type=int,default=450)
    parser.add_argument('--overlap-tokens',type=int,default=50)
    args=parser.parse_args()
    if not 100<=args.max_tokens<=512 or not 0<=args.overlap_tokens<args.max_tokens: parser.error('Invalid token budget')
    chunks=[chunk for doc in read_jsonl(args.input) for chunk in chunk_document(doc,args.max_tokens,args.overlap_tokens)]
    write_jsonl(args.output,chunks)
    print(f"Built {len(chunks)} chunks; maximum actual E5 tokens: {max((c['token_count'] for c in chunks),default=0)}")
if __name__=='__main__': main()
