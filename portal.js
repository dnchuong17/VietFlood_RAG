'use strict';
const $ = id => document.getElementById(id);
let token = '', timer = null, busy = false, offset = 0, nextOffset = null;
let generation = 0;
const apiURL = path => new URL('./api/' + path, window.location.href);
function message(id, text, failed = false) {
  $(id).textContent = text;
  $(id).classList.toggle('error', failed);
}
function controls() {
  $('upload-fields').disabled = !token || busy;
  $('submit').disabled = !token || busy || !$('file').files.length;
  $('prev').disabled = offset === 0;
  $('next').disabled = nextOffset === null;
  $('progress').classList.toggle('on', busy);
}
function disconnect() {
  generation++;
  token = '';
  clearTimeout(timer);
  busy = false;
  $('admin-token').value = '';
  $('file').value = '';
  $('selection').classList.remove('visible');
  $('target').replaceChildren(new Option('Thêm tài liệu mới', ''));
  $('recent').replaceChildren();
  for (const id of ['docs', 'eligible', 'collection', 'points', 'source-count', 'page-label']) $(id).textContent = '—';
  $('connection').textContent = 'Chưa kết nối';
  $('logout').hidden = true;
  $('retry').hidden = true;
  message('toast', '');
  controls();
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  headers.set('X-Rag-Admin-Token', token);
  const response = await fetch(apiURL(path), {...options, headers, cache: 'no-store', credentials: 'omit'});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) disconnect();
    throw new Error(data.detail?.message || (typeof data.detail === 'string' ? data.detail : 'Yêu cầu chưa thực hiện được.'));
  }
  return data;
}
async function loadDocuments() {
  const currentGeneration = generation;
  const data = await api(`documents?offset=${offset}&limit=50`);
  if (generation !== currentGeneration || !token) return;
  nextOffset = data.nextOffset;
  const selected = $('target').value;
  $('target').replaceChildren(new Option('Thêm tài liệu mới', ''));
  $('recent').replaceChildren();
  for (const item of data.items) {
    $('target').add(new Option(`${item.id} — ${item.title}`, item.id));
    const row = document.createElement('div');
    row.className = 'row';
    for (const [text, style] of [[item.id, 'docid'], [item.title, 'doctitle'], [`Phiên bản ${item.version}`, 'docstatus']]) {
      const cell = document.createElement('span');
      cell.className = style;
      cell.textContent = text;
      row.append(cell);
    }
    $('recent').append(row);
  }
  if ([...$('target').options].some(o => o.value === selected)) $('target').value = selected;
  $('source-count').textContent = `${data.total} tài liệu được lập chỉ mục`;
  $('page-label').textContent = data.total ? `${offset + 1}–${offset + data.items.length} / ${data.total}` : 'Chưa có tài liệu';
  controls();
}
async function refresh() {
  clearTimeout(timer);
  if (!token) return;
  const currentGeneration = generation;
  try {
    const data = await api('status');
    if (generation !== currentGeneration || !token) return;
    $('docs').textContent = data.documents;
    $('eligible').textContent = `${data.eligible} tài liệu được lập chỉ mục`;
    $('collection').textContent = data.manifest.collection || 'Chưa phát hành';
    $('points').textContent = `${data.manifest.point_count ?? 0} đoạn trong bộ dữ liệu đang phục vụ`;
    busy = ['queued', 'processing'].includes(data.job.status);
    message('toast', data.job.message || '', data.job.status === 'failed');
    $('retry').hidden = data.job.status !== 'failed';
    if (!busy) await loadDocuments();
    if (token && generation === currentGeneration) timer = setTimeout(refresh, busy ? 2000 : 15000);
  } catch (error) {
    message('toast', error.message, true);
    if (token) timer = setTimeout(refresh, 5000);
  }
  controls();
}
$('auth-form').addEventListener('submit', async event => {
  event.preventDefault();
  generation++;
  token = $('admin-token').value.trim();
  $('admin-token').value = '';
  if (!token) return;
  try {
    await api('status');
    $('connection').textContent = 'Đã kết nối quản trị';
    $('logout').hidden = false;
    message('auth-message', 'Đã kết nối. Chọn tài liệu để thay thế hoặc thêm nguồn mới.');
    offset = 0;
    await loadDocuments();
    await refresh();
  } catch (error) {
    disconnect();
    message('auth-message', error.message, true);
  }
});
$('logout').addEventListener('click', () => { disconnect(); message('auth-message', 'Đã ngắt kết nối.'); });
$('file').addEventListener('change', () => {
  const file = $('file').files[0];
  if (file && (!file.name.toLowerCase().endsWith('.md') || file.size > 10 * 1024 * 1024)) {
    $('file').value = '';
    $('selection').classList.remove('visible');
    message('toast', 'Chọn file .md có dung lượng tối đa 10 MB.', true);
  } else {
    $('selection').classList.toggle('visible', !!file);
    if (file) {
      $('filename').textContent = file.name;
      $('filesize').textContent = `${Math.ceil(file.size / 1024)} KB`;
      message('toast', '');
    }
  }
  controls();
});
for (const name of ['dragenter', 'dragover']) $('drop').addEventListener(name, event => {
  event.preventDefault();
  if (token && !busy) $('drop').classList.add('hot');
});
for (const name of ['dragleave', 'drop']) $('drop').addEventListener(name, event => {
  event.preventDefault(); $('drop').classList.remove('hot');
});
$('drop').addEventListener('drop', event => {
  if (!token || busy || event.dataTransfer.files.length !== 1) return;
  $('file').files = event.dataTransfer.files;
  $('file').dispatchEvent(new Event('change'));
});
$('form').addEventListener('submit', async event => {
  event.preventDefault();
  const file = $('file').files[0], target = $('target').value;
  if (!file || busy || !token) return;
  if (target && !confirm(`Thay thế tài liệu ${target} bằng nội dung file ${file.name}?`)) return;
  busy = true;
  clearTimeout(timer);
  controls();
  const form = new FormData(); form.append('file', file);
  try {
    await api(target ? 'documents/' + encodeURIComponent(target) : 'import', {method: target ? 'PUT' : 'POST', body: form});
    $('file').value = '';
    $('selection').classList.remove('visible');
    await refresh();
  } catch (error) {
    busy = false;
    message('toast', error.message, true);
    controls();
  }
});
$('retry').addEventListener('click', async () => {
  try { await api('retry', {method: 'POST'}); $('retry').hidden = true; await refresh(); }
  catch (error) { message('toast', error.message, true); }
});
$('prev').addEventListener('click', async () => {
  offset = Math.max(0, offset - 50);
  try { await loadDocuments(); } catch (error) { message('toast', error.message, true); }
});
$('next').addEventListener('click', async () => {
  if (nextOffset === null) return;
  offset = nextOffset;
  try { await loadDocuments(); } catch (error) { message('toast', error.message, true); }
});
controls();
