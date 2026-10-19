"""Authenticated Markdown uploads, shared by standalone and /admin deployments."""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from filelock import FileLock, Timeout

from corpus_storage import initialize_corpus
from kb_common import read_jsonl, read_markdown
from pipeline_config import (
    ELIGIBLE_REPRESENTATIONS, INGEST_MANIFEST_PATH, MARKDOWN_DIR,
    PROJECT_ROOT, RAG_DATA_DIR, SOURCE_REGISTRY_PATH,
)

logger = logging.getLogger('vietflood.upload')
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
SAFE_SOURCE_ID = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
REQUIRED_FIELDS = (
    'source_ids', 'title', 'source_url', 'language', 'representation',
    'accessed_at', 'rechecked_at', 'verification_status',
)
JOB_PATH = RAG_DATA_DIR / 'upload_job.json'
app = FastAPI(title='VietFlood Knowledge Base Administration', docs_url=None, redoc_url=None)


def error(status, code, message):
    return JSONResponse({'detail': {'code': code, 'message': message}}, status_code=status)


def fail(status, code, message):
    raise HTTPException(status, {'code': code, 'message': message})


class AdminBoundary:
    """Authenticate before multipart parsing, with a bounded in-memory request body."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        if scope['path'].startswith('/api/') or '/api/' in scope['path']:
            expected = os.getenv('RAG_ADMIN_TOKEN', '').encode()
            supplied = headers.get(b'x-rag-admin-token', b'')
            if not expected:
                return await error(503, 'admin_not_configured', 'Chưa cấu hình RAG_ADMIN_TOKEN trên server.')(scope, receive, send)
            if not secrets.compare_digest(expected, supplied):
                return await error(401, 'unauthorized', 'Khóa quản trị không hợp lệ.')(scope, receive, send)
            if scope['method'] in {'POST', 'PUT'}:
                try:
                    size = int(headers.get(b'content-length', b'0'))
                    if size < 0:
                        raise ValueError
                except ValueError:
                    return await error(400, 'invalid_length', 'Content-Length không hợp lệ.')(scope, receive, send)
                if size > MAX_REQUEST_BYTES:
                    return await error(413, 'file_too_large', 'File vượt giới hạn 10 MB.')(scope, receive, send)
                body = bytearray()
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    body.extend(message.get('body', b''))
                    if len(body) > MAX_REQUEST_BYTES:
                        return await error(413, 'file_too_large', 'File vượt giới hạn 10 MB.')(scope, receive, send)
                    if not message.get('more_body', False):
                        break
                async def once():
                    nonlocal body
                    if body is None:
                        return {'type': 'http.disconnect'}
                    message = {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                    body = None
                    return message
                receive = once
        async def secured_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] += [
                    (b'cache-control', b'no-store'),
                    (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'"),
                ]
            await send(message)
        await self.app(scope, receive, secured_send)


app.add_middleware(AdminBoundary)


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def _job():
    if JOB_PATH.exists():
        return json.loads(JOB_PATH.read_text())
    return {'status': 'idle', 'message': 'Sẵn sàng nhận tài liệu.'}


def _set_job(**values):
    values['updated_at'] = datetime.now(timezone.utc).isoformat()
    _atomic_json(JOB_PATH, values)


def _registry():
    return read_jsonl(SOURCE_REGISTRY_PATH) if SOURCE_REGISTRY_PATH.exists() else []


def _initialize():
    try:
        RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
        initialize_corpus()
    except (OSError, RuntimeError, Timeout):
        logger.error('upload_storage_unavailable')
        fail(503, 'storage_unavailable', 'Kho nguồn chưa sẵn sàng. Kiểm tra volume dữ liệu và quyền ghi trên server.')


def _validate_upload(filename, content, replace_id=None):
    if not filename.lower().endswith('.md'):
        fail(400, 'invalid_file_type', 'Chỉ nhận tài liệu Markdown (.md).')
    if len(content) > MAX_UPLOAD_BYTES:
        fail(413, 'file_too_large', 'File vượt giới hạn 10 MB.')
    try:
        decoded = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        fail(400, 'invalid_encoding', 'File phải dùng mã hóa UTF-8.')
    temporary = RAG_DATA_DIR / ('.validate-' + uuid.uuid4().hex + '.md')
    try:
        front_matter = decoded.lstrip('\n').split('\n---', 1)[0]
        if len(front_matter) > 64 * 1024:
            fail(400, 'invalid_metadata', 'Metadata vượt giới hạn 64 KB.')
        if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
               for token in yaml.scan(front_matter)):
            fail(400, 'invalid_metadata', 'Metadata không được dùng YAML anchors hoặc aliases.')
        temporary.write_text(decoded, encoding='utf-8')
        metadata, body = read_markdown(temporary)
    except (ValueError, yaml.YAMLError, RecursionError):
        fail(400, 'invalid_metadata', 'File cần YAML front matter hợp lệ ở đầu tài liệu.')
    finally:
        temporary.unlink(missing_ok=True)
    if any(not metadata.get(key) for key in REQUIRED_FIELDS) or not body:
        fail(400, 'missing_metadata', 'Thiếu nội dung hoặc metadata bắt buộc. Tải mẫu để xem định dạng.')
    if not isinstance(metadata['representation'], str) or metadata['representation'] not in ELIGIBLE_REPRESENTATIONS:
        fail(400, 'invalid_representation', 'representation không thuộc nhóm được phép lập chỉ mục.')
    if any(not isinstance(metadata[key], str) for key in REQUIRED_FIELDS if key != 'source_ids'):
        fail(400, 'invalid_metadata', 'Các trường metadata phải là chuỗi, ngoại trừ source_ids.')
    if urlparse(metadata['source_url']).scheme not in {'http', 'https'} or not urlparse(metadata['source_url']).netloc:
        fail(400, 'invalid_source_url', 'source_url phải là địa chỉ HTTP hoặc HTTPS hợp lệ.')
    ids = metadata['source_ids']
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not SAFE_SOURCE_ID.fullmatch(i) for i in ids):
        fail(400, 'invalid_source_ids', 'source_ids phải là danh sách mã gồm chữ, số, dấu _ hoặc -, tối đa 40 ký tự.')
    if len(set(ids)) != len(ids):
        fail(400, 'duplicate_source_ids', 'Các source_ids trong file phải khác nhau.')
    registry = _registry()
    current = next((r for r in registry if r['document_id'] == replace_id), None) if replace_id else None
    if replace_id and not current:
        fail(404, 'document_not_found', 'Không tìm thấy tài liệu cần thay thế.')
    if replace_id and ids[0] != replace_id:
        fail(400, 'document_id_mismatch', 'source_ids đầu tiên phải giữ nguyên mã tài liệu đang thay thế.')
    other_ids = {i for row in registry if row['document_id'] != replace_id for i in row['source_ids']}
    if other_ids.intersection(ids):
        fail(409, 'source_id_conflict', 'Mã nguồn trùng tài liệu khác. Chọn đúng tài liệu để thay thế.')
    # Replacement keeps its trusted existing filename; new files derive from a validated ID.
    name = Path(current['file_name']).name if current else ids[0] + '.md'
    if (MARKDOWN_DIR / name).exists() and not current:
        fail(409, 'file_conflict', 'File nguồn đã tồn tại.')
    return ids[0], decoded, name


def _run_import(document_id, upload_lock):
    job_id = uuid.uuid4().hex
    try:
        _set_job(status='processing', job_id=job_id, document_id=document_id, message='Đang chia đoạn, tạo embedding và đồng bộ Qdrant…')
        result = subprocess.run(
            [sys.executable, 'sync_pipeline.py'], cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3600,
        )
        if result.returncode:
            raise RuntimeError('Synchronization failed')
        manifest = json.loads(INGEST_MANIFEST_PATH.read_text())
        _set_job(status='complete', job_id=job_id, document_id=document_id,
                 collection=manifest['collection'], point_count=manifest['point_count'],
                 message='Đã cập nhật tài liệu và chuyển sang bộ dữ liệu mới.')
        logger.info(json.dumps({'event': 'upload_complete', 'document_id': document_id, 'job_id': job_id, 'collection': manifest['collection']}))
    except Exception as exc:
        # Never return model/provider output, environment values, or server paths to callers.
        logger.error(json.dumps({'event': 'upload_failed', 'document_id': document_id, 'job_id': job_id, 'error_type': type(exc).__name__}))
        _set_job(status='failed', job_id=job_id, document_id=document_id,
                 message='Đồng bộ chưa được xác nhận. Kiểm tra log server rồi thử lại.')
    finally:
        upload_lock.release()


def _accept(content=None, filename=None, replace_id=None, retry=False):
    _initialize()
    upload_lock = FileLock(str(RAG_DATA_DIR / 'upload.lock'), timeout=0, thread_local=False)
    try:
        upload_lock.acquire()
    except Timeout:
        fail(409, 'upload_busy', 'Đang đồng bộ tài liệu khác. Chờ tác vụ hoàn tất.')
    try:
        with FileLock(str(RAG_DATA_DIR / 'sync.lock'), timeout=0):
            if retry:
                job = _job()
                if job.get('status') not in {'failed', 'queued', 'processing'} or not job.get('document_id'):
                    fail(409, 'no_failed_upload', 'Không có tác vụ lỗi để thử lại.')
                document_id = job['document_id']
            else:
                document_id, decoded, name = _validate_upload(filename or 'source.md', content, replace_id)
                temporary = MARKDOWN_DIR / ('.upload-' + uuid.uuid4().hex)
                try:
                    temporary.write_text(decoded, encoding='utf-8')
                    temporary.replace(MARKDOWN_DIR / name)
                finally:
                    temporary.unlink(missing_ok=True)
            _set_job(status='queued', document_id=document_id, message='Đã nhận tài liệu, đang chờ đồng bộ.')
        worker = threading.Thread(target=_run_import, args=(document_id, upload_lock), daemon=True)
        worker.start()
        return {'status': 'queued', 'document_id': document_id}
    except Timeout:
        upload_lock.release()
        fail(409, 'sync_busy', 'Pipeline đang chạy. Thử lại sau khi đồng bộ hoàn tất.')
    except Exception:
        upload_lock.release()
        raise


@app.get('/api/status')
def status():
    _initialize()
    registry = _registry()
    job = _job()
    # A persisted active job without a live lock was interrupted by a process restart.
    if job.get('status') in {'queued', 'processing'}:
        lock = FileLock(str(RAG_DATA_DIR / 'upload.lock'), timeout=0)
        try:
            with lock:
                job = {**job, 'status': 'failed', 'message': 'Tác vụ bị gián đoạn. Chọn thử lại để tiếp tục.'}
        except Timeout:
            pass
    manifest = json.loads(INGEST_MANIFEST_PATH.read_text()) if INGEST_MANIFEST_PATH.exists() else {}
    return {'job': job, 'documents': len(registry), 'eligible': sum(bool(r['ingest_eligible']) for r in registry),
            'manifest': {k: manifest[k] for k in ['collection', 'point_count', 'document_count'] if k in manifest}}


@app.get('/api/documents')
def documents(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    _initialize()
    sources = [r for r in _registry() if r['ingest_eligible']]
    page = sources[offset:offset+limit]
    return {'items': [{'id': r['document_id'], 'title': r['title'], 'version': r['document_version']} for r in page],
            'nextOffset': offset+limit if offset+limit < len(sources) else None, 'total': len(sources)}


@app.post('/api/import', status_code=202)
async def import_source(file: UploadFile = File(...)):
    try:
        return _accept(await file.read(MAX_UPLOAD_BYTES+1), file.filename)
    finally:
        await file.close()


@app.put('/api/documents/{document_id}', status_code=202)
async def update_document(document_id: str, file: UploadFile = File(...)):
    if not SAFE_SOURCE_ID.fullmatch(document_id):
        fail(400, 'invalid_document_id', 'Mã tài liệu không hợp lệ.')
    try:
        return _accept(await file.read(MAX_UPLOAD_BYTES+1), file.filename, document_id)
    finally:
        await file.close()


@app.post('/api/retry', status_code=202)
def retry_import():
    return _accept(retry=True)


@app.get('/', response_class=HTMLResponse)
def home():
    return (PROJECT_ROOT / 'portal.html').read_text(encoding='utf-8')


@app.get('/portal.js')
def javascript():
    return FileResponse(PROJECT_ROOT / 'portal.js', media_type='text/javascript')


@app.get('/template.md')
def template():
    return FileResponse(PROJECT_ROOT / 'upload-template.md', media_type='text/markdown', filename='vietflood-source-template.md')
