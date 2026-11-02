# -*- coding: utf-8 -*-
"""(v1.00.51, chủ 02/11) Drive ngăn nắp như máy: cây `University/Uni-Documents/<thư mục như Uni-Documents trên máy>/<tên file thật>`.

Trước đây n8n đổ MỌI file vào một thư mục cố định ("Course Materials Backup") với tên là đường dẫn bị ép phẳng
("MI1111 … › Bài tập › x.pdf"). Giờ UC tự tìm / tạo thư mục rồi bảo n8n tải vào đó; chuyển file trên máy thì chuyển theo trên Drive.
Mọi thao tác đi qua webhook n8n `copilot-drive-api` (có khoá; chỉ Drive v3 files, chỉ GET/POST/PATCH — KHÔNG xoá).
LUẬT (chủ 02/11): ổ G: (Drive for desktop) là thực thể riêng — UC KHÔNG BAO GIỜ ghi / chuyển / xoá file qua ổ G:, chỉ qua API.
Giữ nguyên fileId khi chuyển -> driveLink cũ vẫn đúng, NotebookLM vẫn nạp được.
"""
import json, os, posixpath, urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / 'school' / 'drive_folders.json'   # {"<đường dẫn thư mục>": "<folderId>"}
API = 'https://www.googleapis.com/drive/v3/files'
OLD_FOLDER = os.environ.get('UC_DRIVE_OLD_FOLDER', '')   # thư mục n8n đổ file cũ (nếu có); thư mục chứa nó là nơi đặt Uni-Documents
ROOT_NAME = 'Uni-Documents'
FOLDER = 'application/vnd.google-apps.folder'


def api(call, method, url, body=None):
    r = call('copilot-drive-api', {'method': method, 'url': url, 'body': body or {}})
    r = r[0] if isinstance(r, list) else r
    if isinstance(r, dict) and r.get('error'): raise RuntimeError(f"Drive API: {r['error']}")
    return r or {}


def _q(s): return s.replace('\\', '\\\\').replace("'", "\\'")


def _cache():
    try: return json.loads(CACHE.read_text(encoding='utf-8'))
    except Exception: return {}


def _save(c):
    CACHE.parent.mkdir(parents=True, exist_ok=True); CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding='utf-8')


def child_folder(call, name, parent):
    """Thư mục con tên `name` trong `parent` (không có thì tạo). -> id"""
    q = f"name = '{_q(name)}' and '{parent}' in parents and mimeType = '{FOLDER}' and trashed = false"
    r = api(call, 'GET', API + '?' + urllib.parse.urlencode({'q': q, 'fields': 'files(id,name)', 'pageSize': 10}))
    if r.get('files'): return r['files'][0]['id']
    return api(call, 'POST', API + '?fields=id', {'name': name, 'mimeType': FOLDER, 'parents': [parent]})['id']


def root(call):
    c = _cache()
    if c.get(''): return c['']
    uni = api(call, 'GET', f'{API}/{OLD_FOLDER}?fields=parents')['parents'][0] if OLD_FOLDER else 'root'   # không cấu hình -> gốc My Drive
    c[''] = child_folder(call, ROOT_NAME, uni); _save(c); return c['']


def folder_for(call, rel_dir):
    """'MI1111 Giải tích I/Bài tập' (đường dẫn thư mục trong Uni-Documents) -> folderId trên Drive (tạo từng cấp nếu thiếu)."""
    rel_dir = str(rel_dir).replace('\\', '/').strip('/')
    c = _cache()
    if rel_dir in c: return c[rel_dir]
    parent, path = root(call), ''
    for part in [p for p in rel_dir.split('/') if p]:
        path = posixpath.join(path, part) if path else part
        if path not in c: c[path] = child_folder(call, part, parent); _save(c)
        parent = c[path]
    return parent


def place(call, file_id, rel_path):
    """Đưa file (giữ fileId) vào đúng thư mục theo rel_path và đổi về tên thật. -> folderId"""
    rel_path = str(rel_path).replace('\\', '/')
    fid = folder_for(call, posixpath.dirname(rel_path))
    cur = api(call, 'GET', f'{API}/{file_id}?fields=parents,name')
    rm = ','.join(p for p in cur.get('parents', []) if p != fid)
    qs = {'fields': 'id,parents,name'}
    if fid not in cur.get('parents', []): qs['addParents'] = fid
    if rm: qs['removeParents'] = rm
    api(call, 'PATCH', f'{API}/{file_id}?' + urllib.parse.urlencode(qs), {'name': posixpath.basename(rel_path)})
    return fid
