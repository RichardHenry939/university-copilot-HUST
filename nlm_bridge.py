# -*- coding: utf-8 -*-
"""Gửi tài liệu Uni-Documents sang NotebookLM (Claude 2026-10-05) — UC chỉ làm hành chính, KHÔNG làm giảng viên.

Người dùng: "cắt bước đi lần file": ô tìm tài liệu trong Uni-Documents -> tích chọn -> thêm vào notebook có sẵn
hoặc tạo notebook mới (tự đặt tên). Không tạo task, không ghi Notion, không gọi AI. Chỉ chạy khi bạn bấm (có xác nhận).
Dùng CLI notebooklm-py (phiên Google giữ bởi tác vụ "NotebookLM keepalive")."""
import uc_config as cfg
import json, os, subprocess, threading, time, unicodedata, uuid
from pathlib import Path

UNI = Path(cfg.path("uni_documents"))
NLM = Path(os.environ.get('APPDATA', '')) / 'uv' / 'tools' / 'notebooklm-py' / 'Scripts' / 'notebooklm.exe'
EXT = {'.pdf', '.docx', '.doc', '.pptx', '.ppt', '.txt', '.md', '.xlsx', '.csv', '.png', '.jpg', '.jpeg', '.mp3', '.m4a', '.wav'}
_jobs, _idx, _nb = {}, {'at': 0, 'items': []}, {'at': 0, 'items': []}
_lk = threading.Lock()


def _fold(s):
    s = unicodedata.normalize('NFD', str(s).lower()).replace('đ', 'd')
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def _cli(*args, timeout=120):
    p = subprocess.run([str(NLM), *args], capture_output=True, timeout=timeout, creationflags=0x08000000,
                       env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
    out = (p.stdout or b'').decode('utf-8', 'ignore')
    try: return json.loads(out)
    except Exception: return {'error': True, 'message': (out or (p.stderr or b'').decode('utf-8', 'ignore'))[-400:]}


def _index():
    if time.time() - _idx['at'] < 120: return _idx['items']
    items = []
    for f in UNI.rglob('*'):
        if f.is_file() and f.suffix.lower() in EXT and not f.name.startswith(('~$', '.')):
            rel = f.relative_to(UNI)
            items.append({'rel': str(rel), 'name': f.name, 'folder': str(rel.parent), 'size': f.stat().st_size,
                          'mtime': f.stat().st_mtime, 'key': _fold(str(rel))})
    _idx.update(at=time.time(), items=items)
    return items


def search(q, limit=80):
    toks = [_fold(t) for t in str(q or '').split() if t.strip()]
    items = _index()
    hits = [i for i in items if all(t in i['key'] for t in toks)] if toks else sorted(items, key=lambda i: -i['mtime'])[:limit]
    hits.sort(key=lambda i: -i['mtime'])
    return {'ok': True, 'total': len(hits), 'items': [{k: v for k, v in i.items() if k != 'key'} for i in hits[:limit]]}


def notebooks(force=False):
    if not force and time.time() - _nb['at'] < 60: return {'ok': True, 'items': _nb['items']}
    d = _cli('list', '--json', timeout=60)
    if isinstance(d, dict) and d.get('error'):
        return {'ok': False, 'error': 'Chưa kết nối được NotebookLM: ' + str(d.get('message'))[:200] +
                ' — chạy notebooklm-keepalive/keepalive.ps1 hoặc "notebooklm login --browser chrome".'}
    nb = d.get('notebooks') if isinstance(d, dict) else d
    items = [{'id': x.get('id'), 'title': x.get('title') or '(không tên)', 'sources': x.get('sources_count') or x.get('source_count')} for x in (nb or [])]
    _nb.update(at=time.time(), items=items)
    return {'ok': True, 'items': items}


def _safe(rel):
    p = (UNI / rel).resolve()
    if UNI.resolve() not in p.parents or not p.is_file(): raise ValueError(f'không hợp lệ: {rel}')
    return p


def _run(jid, files, notebook_id, new_title):
    j = _jobs[jid]
    try:
        if not notebook_id:
            d = _cli('create', new_title, '--json', timeout=90)
            notebook_id = ((d.get('notebook') or {}).get('id') if isinstance(d, dict) else None) or (d.get('id') if isinstance(d, dict) else None)
            if not notebook_id: raise RuntimeError('không tạo được notebook: ' + str(d.get('message') if isinstance(d, dict) else d)[:200])
            j['log'].append(f'Đã tạo notebook “{new_title}”')
        j['notebook'] = notebook_id
        for rel in files:
            p = _safe(rel)
            d = _cli('source', 'add', str(p), '-n', notebook_id, '--type', 'file', '--title', p.stem, '--timeout', '300', '--json', timeout=420)
            ok = isinstance(d, dict) and not d.get('error') and (d.get('source') or {}).get('id')
            j['done'].append({'rel': rel, 'ok': bool(ok), 'error': None if ok else str(d.get('message') if isinstance(d, dict) else d)[:200]})
        _nb['at'] = 0
        j['status'] = 'xong'
    except Exception as e:
        j.update(status='lỗi', error=f'{type(e).__name__}: {e}'[:300])


def add(files, notebook_id=None, new_title=None):
    files = [str(f) for f in (files or [])][:20]
    if not files: return {'ok': False, 'error': 'Chưa chọn tài liệu nào.'}
    if not notebook_id and not (new_title or '').strip(): return {'ok': False, 'error': 'Chọn notebook có sẵn hoặc đặt tên notebook mới.'}
    for rel in files: _safe(rel)
    jid = uuid.uuid4().hex[:10]
    _jobs[jid] = {'status': 'đang gửi', 'total': len(files), 'done': [], 'log': [], 'notebook': notebook_id}
    threading.Thread(target=_run, args=(jid, files, notebook_id, (new_title or '').strip()[:120]), daemon=True).start()
    return {'ok': True, 'job': jid}


def job(jid):
    j = _jobs.get(jid)
    return {'ok': bool(j), **(j or {}), 'url': f"https://notebooklm.google.com/notebook/{j['notebook']}" if j and j.get('notebook') else None}
