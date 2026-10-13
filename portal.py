"""Small web portal for adding Markdown sources to the VietFlood Qdrant KB."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from build_source_registry import build_registry
from kb_common import read_jsonl, read_markdown, write_jsonl
from pipeline_config import (
    CHUNKS_PATH,
    DATA_DIR,
    INGEST_MANIFEST_PATH,
    MARKDOWN_DIR,
    PARSED_DOCUMENTS_PATH,
    PROJECT_ROOT,
    SOURCE_REGISTRY_PATH,
)
from pipeline_config import ELIGIBLE_REPRESENTATIONS


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
REQUIRED_FIELDS = (
    "source_ids",
    "title",
    "source_url",
    "language",
    "representation",
    "accessed_at",
    "rechecked_at",
    "verification_status",
)
SAFE_SOURCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")

app = FastAPI(title="VietFlood Knowledge Base Portal")
_lock = threading.Lock()
_job: dict[str, Any] = {"status": "idle", "message": "Ready for an import."}


def _set_job(**updates: Any) -> None:
    global _job
    with _lock:
        _job = {**_job, **updates, "updated_at": datetime.now(timezone.utc).isoformat()}


def _registry() -> list[dict[str, Any]]:
    if not SOURCE_REGISTRY_PATH.exists():
        return []
    return read_jsonl(SOURCE_REGISTRY_PATH)


def _validate_upload(filename: str, content: bytes, replace_id: str | None = None) -> tuple[dict[str, Any], str, str]:
    if not filename.lower().endswith(".md"):
        raise HTTPException(400, "Upload a Markdown .md file.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 10 MB upload limit.")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "File must be UTF-8 encoded Markdown.") from exc

    temporary = DATA_DIR / f".portal-validation-{uuid.uuid4().hex}.md"
    try:
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(decoded, encoding="utf-8")
        metadata, body = read_markdown(temporary)
    except (ValueError, yaml.YAMLError, OSError) as exc:
        message = str(exc)
        if "Missing YAML front matter" in message:
            message = (
                "This Markdown file has no YAML front matter. Add a metadata block "
                "at the top of the file, or download the portal template."
            )
        raise HTTPException(400, f"Invalid Markdown front matter: {message}") from exc
    finally:
        temporary.unlink(missing_ok=True)

    missing = [key for key in REQUIRED_FIELDS if not metadata.get(key)]
    if missing:
        raise HTTPException(400, f"Missing required front matter: {', '.join(missing)}")
    if not body.strip():
        raise HTTPException(400, "Markdown body is empty.")
    if metadata.get("representation") not in ELIGIBLE_REPRESENTATIONS:
        raise HTTPException(
            400,
            "Auto-indexing requires representation to be faithful_paraphrase or "
            "structured_faithful_paraphrase or user-guide.",
        )
    source_ids = metadata.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        raise HTTPException(400, "source_ids must be a non-empty YAML list.")
    source_ids = [str(item).strip() for item in source_ids]
    if any(not SAFE_SOURCE_ID.fullmatch(item) for item in source_ids):
        raise HTTPException(400, "Each source_id must use letters, numbers, _ or - (max 40).")
    if len(source_ids) != len(set(source_ids)):
        raise HTTPException(400, "source_ids must be unique within the file.")

    registry = _registry()
    existing_ids = {item for row in registry for item in row.get("source_ids", [])}
    collisions = sorted(existing_ids.intersection(source_ids))
    if collisions and not (replace_id and any(r["document_id"] == replace_id and r["source_ids"] == source_ids for r in registry)):
        raise HTTPException(409, f"These source IDs already exist: {', '.join(collisions)}")
    safe_name = Path(filename).name
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.md", safe_name, re.IGNORECASE):
        safe_name = f"{source_ids[0]}_{uuid.uuid4().hex[:8]}.md"
    target = MARKDOWN_DIR / safe_name
    if target.exists() and not replace_id:
        raise HTTPException(409, f"A file named {safe_name} already exists.")
    if replace_id:
        record = next((r for r in registry if r["document_id"] == replace_id), None)
        if not record or source_ids != record["source_ids"]: raise HTTPException(400, "Source IDs must match the document being updated")
        safe_name = record["file_name"]
    return metadata, decoded, safe_name


def _run_import(document_id: str) -> None:
    try:
        _set_job(status="processing", stage="Registry", message="Updating source registry…")
        steps = [([sys.executable, "sync_pipeline.py"], "Corpus synchronization", "Parsing, embedding and publishing the full approved corpus…")]
        for command, stage, message in steps:
            _set_job(stage=stage, message=message)
            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(result.stdout[-5000:] or f"{stage} failed.")
        manifest = json.loads(INGEST_MANIFEST_PATH.read_text(encoding="utf-8"))
        _set_job(
            status="complete",
            stage="Complete",
            message=f"{document_id} added to {manifest['collection']}.",
            document_id=document_id,
            point_count=manifest.get("point_count"),
            collection=manifest.get("collection"),
            log_tail=result.stdout[-2000:],
        )
    except Exception as exc:  # Keep import failures visible in the portal.
        _set_job(status="failed", stage="Needs attention", message=str(exc))


@app.get("/api/status")
def status() -> dict[str, Any]:
    with _lock:
        job = dict(_job)
    manifest = {}
    if INGEST_MANIFEST_PATH.exists():
        try:
            manifest = json.loads(INGEST_MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    registry = _registry()
    return {
        "job": job,
        "manifest": manifest,
        "documents": len(registry),
        "sources": [{"id":r["document_id"],"title":r["title"]} for r in registry if r["ingest_eligible"]],
        "eligible": sum(bool(item.get("ingest_eligible")) for item in registry),
        "recent": [
            {"id": item["document_id"], "title": item["title"], "status": item["review_status"]}
            for item in registry[-6:][::-1]
        ],
    }


@app.post("/api/import")
async def import_source(file: UploadFile = File(...)) -> dict[str, Any]:
    if _job.get("status") in {"queued", "processing"}:
        raise HTTPException(409, "An import is already running. Wait for it to finish.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    _, decoded, safe_name = _validate_upload(file.filename or "source.md", content)
    # Rebuild after the file is safely validated; source IDs are collision checked above.
    metadata, _ = read_markdown_from_text(decoded)
    document_id = str(metadata["source_ids"][0])
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    target = MARKDOWN_DIR / safe_name
    target.write_text(decoded, encoding="utf-8")
    write_jsonl(SOURCE_REGISTRY_PATH, build_registry(MARKDOWN_DIR))
    _set_job(
        status="queued",
        stage="Queued",
        message=f"{document_id} is queued for indexing.",
        document_id=document_id,
    )
    threading.Thread(target=_run_import, args=(document_id,), daemon=True).start()
    return {"status": "queued", "document_id": document_id, "file_name": safe_name}


@app.post("/api/retry")
def retry_import() -> dict[str, Any]:
    with _lock:
        job = dict(_job)
    if job.get("status") != "failed" or not job.get("document_id"):
        raise HTTPException(409, "There is no failed import to retry.")
    document_id = str(job["document_id"])
    _set_job(
        status="queued",
        stage="Queued",
        message=f"Retrying {document_id}…",
    )
    threading.Thread(target=_run_import, args=(document_id,), daemon=True).start()
    return {"status": "queued", "document_id": document_id}


def read_markdown_from_text(value: str) -> tuple[dict[str, Any], str]:
    temporary = DATA_DIR / f".portal-metadata-{uuid.uuid4().hex}.md"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    try:
        temporary.write_text(value, encoding="utf-8")
        return read_markdown(temporary)
    finally:
        temporary.unlink(missing_ok=True)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return PAGE


@app.get("/template.md", response_class=HTMLResponse)
def template() -> str:
    return '''---
source_ids: [NEW01]
title: "Publisher — Source title"
source_url: https://example.org/guidance
language: vi
representation: faithful_paraphrase
accessed_at: 2026-10-12
rechecked_at: 2026-10-12
verification_status: VERIFIED_AGAINST_WEB
medical_review_required: false
chemical_dosing_review_required: false
---

# Document title

Add the faithful source content or paraphrase here.
'''


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VietFlood · Knowledge intake</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap" rel="stylesheet">
<style>
:root{--ink:#142525;--muted:#71817a;--paper:#f2f2e9;--white:#fffef8;--line:#d9ded2;--green:#176f58;--lime:#c7e96a;--orange:#ee8a50;--mono:'DM Mono',monospace;--sans:'DM Sans',sans-serif;--serif:'Newsreader',serif}*{box-sizing:border-box}body{margin:0;background-color:var(--paper);color:var(--ink);font-family:var(--sans);background-image:radial-gradient(#263a3110 .8px,transparent .8px);background-size:13px 13px}.shell{max-width:1360px;margin:auto;padding:0 54px}.top{height:82px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:12px;font-size:13px;font-weight:700;letter-spacing:.04em}.mark{width:30px;height:30px;background:var(--green);border-radius:50% 50% 50% 6px;position:relative}.mark:after{content:'';position:absolute;width:11px;height:11px;border:2px solid var(--lime);border-radius:50%;left:8px;top:7px}.topmeta{font:11px var(--mono);color:var(--muted);letter-spacing:.08em}.hero{padding:49px 0 37px;display:grid;grid-template-columns:1fr auto;align-items:end}.eyebrow,.label{font:10px var(--mono);letter-spacing:.13em;text-transform:uppercase;color:var(--green)}h1{font:500 clamp(40px,5vw,63px)/.98 var(--serif);letter-spacing:-.045em;margin:16px 0 12px;max-width:600px}.hero p{font-size:14px;color:#61716a;margin:0;line-height:1.7}.live{display:flex;align-items:center;gap:9px;font:10px var(--mono);letter-spacing:.1em;text-transform:uppercase;margin-bottom:5px;color:#61716a}.dot{width:8px;height:8px;border-radius:100%;background:#51a780;box-shadow:0 0 0 4px #51a78020}.grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,.8fr);gap:20px}.card{background:var(--white);border:1px solid var(--line);border-radius:5px}.intake{padding:26px 28px 25px}.cardhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.cardhead h2{font:500 26px var(--serif);margin:6px 0 0;letter-spacing:-.02em}.step{font:10px var(--mono);color:var(--muted)}.drop{position:relative;min-height:194px;border:1px dashed #9eb5a5;background:#f7f8f0;border-radius:4px;display:flex;align-items:center;justify-content:center;text-align:center;transition:.2s}.drop.hot{border-color:var(--green);background:#eef5e5}.drop input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer}.uploadicon{margin:0 auto 12px;width:36px;height:36px;border-radius:50%;background:#e5eddd;display:grid;place-items:center;color:var(--green);font-size:19px}.drop strong{display:block;font-size:13px}.drop p{font-size:11px;color:var(--muted);margin:7px 0}.browse{color:var(--green);font-weight:700}.micro{font:9px var(--mono)!important;letter-spacing:.05em}.selection{display:none;margin-top:12px;padding:10px 12px;background:#f1f4eb;border-radius:3px;font:11px var(--mono);justify-content:space-between}.selection.visible{display:flex}.actions{display:flex;justify-content:space-between;align-items:center;margin-top:18px}.hint{font-size:10px;color:var(--muted)}button{background:var(--green);color:white;border:0;padding:13px 19px;border-radius:3px;font:600 11px var(--sans);cursor:pointer;display:flex;gap:12px;align-items:center;transition:background .2s,transform .2s}button:hover{background:#105842;transform:translateY(-1px)}button:disabled{opacity:.45;cursor:wait;transform:none}.arrow{color:var(--lime);font-size:15px}.aside{display:grid;grid-template-rows:1fr 1fr;gap:20px}.stat{padding:21px 23px;position:relative;overflow:hidden}.stat:after{content:'';position:absolute;right:-29px;bottom:-68px;width:155px;height:155px;border:1px solid #d8e1d1;border-radius:50%;box-shadow:0 0 0 17px #fff0,0 0 0 18px #d8e1d1,0 0 0 39px #fff0,0 0 0 40px #d8e1d1}.statname{font:10px var(--mono);color:var(--muted);letter-spacing:.1em;text-transform:uppercase}.statval{font:500 45px/.98 var(--serif);margin:17px 0 8px}.statfoot{font-size:10px;color:var(--muted)}.statfoot b{color:var(--green);font-weight:600}.collection{background:var(--ink);color:#f2f2e9;border-color:var(--ink)}.collection:after{border-color:#ffffff20;box-shadow:0 0 0 18px #ffffff08,0 0 0 19px #ffffff20,0 0 0 39px #ffffff08,0 0 0 40px #ffffff20}.collection .statname,.collection .statfoot{color:#a7b7ad}.collection .statval{font-size:23px;margin:17px 0 10px;max-width:240px;word-break:break-word}.statusrow{display:flex;align-items:center;gap:7px;font:9px var(--mono);color:#cae676}.section{margin-top:38px}.sectionhead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}.sectionhead h2{font:500 25px var(--serif);margin:0}.sectionhead span{font:9px var(--mono);color:var(--muted)}.recent{overflow:hidden}.row{display:grid;grid-template-columns:54px 1fr auto;align-items:center;padding:14px 19px;border-top:1px solid #e6e8df;gap:13px}.row:first-child{border-top:0}.docid{font:10px var(--mono);color:var(--green)}.doctitle{font-size:11px;font-weight:600}.docstatus{font:9px var(--mono);color:#78857d;text-transform:uppercase;letter-spacing:.04em}.foot{display:flex;justify-content:space-between;padding:29px 0 34px;color:#8a958c;font:9px var(--mono);letter-spacing:.05em}.toast{font:11px var(--mono);color:var(--muted);margin-top:12px;min-height:16px}.toast.error{color:#a64231}.progress{height:2px;background:#e4e9df;margin-top:14px;display:none}.progress.on{display:block}.progress i{display:block;height:100%;width:35%;background:var(--green);animation:travel 1.3s ease-in-out infinite alternate}@keyframes travel{to{transform:translateX(180%)}}@media(max-width:800px){.shell{padding:0 22px}.grid{grid-template-columns:1fr}.aside{grid-template-columns:1fr 1fr;grid-template-rows:auto}.hero{padding-top:36px}.topmeta{display:none}}@media(max-width:520px){.aside{grid-template-columns:1fr}.intake{padding:22px 18px}.row{grid-template-columns:43px 1fr}.docstatus{grid-column:2}.foot{gap:18px;flex-direction:column}}
</style></head><body><div class="shell"><header class="top"><div class="brand"><i class="mark"></i><span>VIETFLOOD <span style="color:#839187;font-weight:500">/ KNOWLEDGE SYSTEM</span></span></div><div class="topmeta">FIELD LIBRARY &nbsp;·&nbsp; INTAKE CONSOLE &nbsp; / &nbsp; 01</div></header>
<section class="hero"><div><div class="eyebrow">Knowledge operations &nbsp; / &nbsp; 01</div><h1>Bring good guidance<br>into reach.</h1><p>Add a Markdown source and send it through parsing, chunking, and vector indexing.</p></div><div class="live"><i class="dot"></i> Staging target configured</div></section>
<main class="grid"><section class="card intake"><div class="cardhead"><div><div class="label">Source intake</div><h2>Import a document</h2></div><div class="step">STEP 01 — 04</div></div><form id="form"><label for="target">Nguồn cần cập nhật</label><select id="target"><option value="">Thêm nguồn mới</option></select><button type="button" id="delete-source">Xóa nguồn đang chọn</button><label id="drop" class="drop"><input id="file" type="file" accept=".md,text/markdown"><span><i class="uploadicon">↥</i><strong>Drop your .md source here</strong><p>or <span class="browse">browse files</span></p><p class="micro">UTF-8 MARKDOWN &nbsp;·&nbsp; MAX 10 MB &nbsp;·&nbsp; YAML FRONT MATTER REQUIRED</p></span></label><div id="selection" class="selection"><span id="filename"></span><span id="filesize"></span></div><div class="actions"><span class="hint">Nguồn thuộc corpus APPROVED_FOR_RAG được phát hành qua alias active. <a href="/template.md" style="color:var(--green);font-weight:700">Get template ↗</a></span><button id="submit" disabled>Import &amp; index <span class="arrow">↗</span></button></div><div id="progress" class="progress"><i></i></div><div id="toast" class="toast"></div></form></section>
<aside class="aside"><article class="card stat"><div class="statname">Sources in registry</div><div id="docs" class="statval">—</div><div class="statfoot"><b id="eligible">— eligible</b> &nbsp;·&nbsp; staging collection</div></article><article class="card stat collection"><div class="statname">Active collection</div><div id="collection" class="statval">Loading…</div><div class="statusrow"><i class="dot" style="background:#c7e96a;box-shadow:0 0 0 4px #c7e96a20"></i><span id="points">Awaiting manifest</span></div></article></aside></main>
<section class="section"><div class="sectionhead"><h2>Source registry</h2><span>REGISTERED SOURCES &nbsp; / &nbsp; LAST 06</span></div><div id="recent" class="card recent"><div class="row"><span class="docid">—</span><span class="doctitle">Loading registry…</span><span class="docstatus">—</span></div></div></section><footer class="foot"><span>VIETFLOOD KNOWLEDGE BASE &nbsp;·&nbsp; LOCAL OPERATIONS</span><span>MARKDOWN → CHUNKS → TEXT-EMBEDDING-3-SMALL → QDRANT</span></footer></div>
<script>
const file=document.querySelector('#file'),drop=document.querySelector('#drop'),selection=document.querySelector('#selection'),submit=document.querySelector('#submit'),toast=document.querySelector('#toast'),progress=document.querySelector('#progress');let busy=false;
toast.addEventListener('click',async e=>{if(e.target.id!=='retry')return;try{const r=await fetch('/api/retry',{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.detail||'Retry failed');toast.textContent=d.document_id+' queued again.';poll()}catch(err){toast.textContent=err.message;toast.className='toast error'}});
file.addEventListener('change',()=>{const f=file.files[0];selection.classList.toggle('visible',!!f);submit.disabled=!f||busy;if(f){document.querySelector('#filename').textContent=f.name;document.querySelector('#filesize').textContent=(f.size/1024).toFixed(0)+' KB';toast.textContent='';toast.className='toast'}});
for(const ev of ['dragenter','dragover'])drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('hot')});for(const ev of ['dragleave','drop'])drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('hot')});drop.addEventListener('drop',e=>{if(e.dataTransfer.files.length){file.files=e.dataTransfer.files;file.dispatchEvent(new Event('change'))}});
document.querySelector('#form').addEventListener('submit',async e=>{e.preventDefault();const f=file.files[0];if(!f)return;busy=true;submit.disabled=true;submit.innerHTML='Uploading <span class="arrow">…</span>';progress.classList.add('on');toast.textContent='Validating source metadata…';toast.className='toast';try{const fd=new FormData();fd.append('file',f);const target=document.querySelector('#target').value;const res=await fetch(target?'/api/documents/'+encodeURIComponent(target):'/api/import',{method:target?'PUT':'POST',body:fd});const data=await res.json();if(!res.ok)throw Error(data.detail||'Import failed');toast.textContent=data.document_id+' queued for indexing.';file.value='';selection.classList.remove('visible');poll()}catch(err){toast.textContent=err.message;toast.className='toast error';progress.classList.remove('on')}finally{busy=false;submit.innerHTML='Import &amp; index <span class="arrow">↗</span>';submit.disabled=true}});
async function poll(){await refresh();const s=window.currentJob;if(s&&['queued','processing'].includes(s.status)){busy=true;submit.disabled=true;toast.textContent=(s.stage||'Processing')+' · '+(s.message||'');progress.classList.add('on');setTimeout(poll,1800)}else{busy=false;progress.classList.remove('on');if(s?.status==='complete'){toast.textContent=s.message+' ('+(s.point_count??'')+' total points)';toast.className='toast'}else if(s?.status==='failed'){toast.innerHTML=esc(s.message)+' <button id="retry" type="button">Retry indexing</button>';toast.className='toast error'}}}
async function refresh(){try{const d=await(await fetch('/api/status')).json();window.currentJob=d.job;const selector=document.querySelector('#target');if(selector&&selector.options.length!==d.sources.length+1){const selected=selector.value;selector.innerHTML='<option value="">Thêm nguồn mới</option>'+d.sources.map(x=>`<option value="${esc(x.id)}">${esc(x.id)} — ${esc(x.title)}</option>`).join('');selector.value=selected;}document.querySelector('#docs').textContent=d.documents;document.querySelector('#eligible').textContent=d.eligible+' eligible';document.querySelector('#collection').textContent=d.manifest.collection||'Not indexed yet';document.querySelector('#points').textContent=d.manifest.point_count?d.manifest.point_count.toLocaleString()+' indexed points':(d.job.message||'Awaiting first import');if(d.recent.length)document.querySelector('#recent').innerHTML=d.recent.map(x=>`<div class="row"><span class="docid">${esc(x.id)}</span><span class="doctitle">${esc(x.title)}</span><span class="docstatus">${esc(x.status||'STAGING')}</span></div>`).join('');if(d.job.status==='processing'||d.job.status==='queued')setTimeout(poll,1800)}catch{}}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}refresh();
document.querySelector('#delete-source').addEventListener('click',async()=>{const id=document.querySelector('#target').value;if(!id)return;if(!confirm('Xóa nguồn '+id+' khỏi kho tra cứu hiện tại?'))return;const response=await fetch('/api/documents/'+encodeURIComponent(id),{method:'DELETE'});const data=await response.json();toast.textContent=response.ok?'Đang đồng bộ xóa nguồn.':data.detail;poll();});
</script></body></html>'''


def _queue_sync(document_id: str) -> None:
    with _lock:
        if _job.get("status") in {"queued", "processing"}: raise HTTPException(409, "Another synchronization is running")
        _job.update(status="queued", document_id=document_id)
    threading.Thread(target=_run_import,args=(document_id,),daemon=True).start()

@app.put("/api/documents/{document_id}")
async def update_document(document_id: str, file: UploadFile = File(...)):
    if not SAFE_SOURCE_ID.fullmatch(document_id): raise HTTPException(400, "Invalid document ID")
    content=await file.read(MAX_UPLOAD_BYTES+1)
    _,decoded,name=_validate_upload(file.filename or "source.md",content,replace_id=document_id)
    with _lock:
        if _job.get("status") in {"queued", "processing"}: raise HTTPException(409, "Another synchronization is running")
        (MARKDOWN_DIR/name).write_text(decoded,encoding="utf-8")
        _job.update(status="queued",document_id=document_id)
    threading.Thread(target=_run_import,args=(document_id,),daemon=True).start()
    return {"status":"queued","document_id":document_id}

@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str):
    row=next((r for r in _registry() if r["document_id"]==document_id),None)
    if not row: raise HTTPException(404,"Document not found")
    with _lock:
        if _job.get("status") in {"queued", "processing"}: raise HTTPException(409, "Another synchronization is running")
        (PROJECT_ROOT/row["file_path"]).unlink()
        _job.update(status="queued",document_id=document_id)
    threading.Thread(target=_run_import,args=(document_id,),daemon=True).start()
    return {"status":"queued","document_id":document_id}
