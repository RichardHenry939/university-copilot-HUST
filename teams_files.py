# -*- coding: utf-8 -*-
"""Tài liệu hai chiều cho Uni-Documents (Claude 2026-10-04).

1) Teams → máy: file tài liệu trong thư mục kênh của mỗi lớp (pdf/docx/pptx/xlsx/…; bỏ ảnh chụp chat, video, .loop)
   tải về đúng thư mục MÔN / loại (Slide · Bài tập · Đề thi · Tham khảo). Từ đó uni_sync tự nạp lên Drive + Notion như file bạn tự bỏ vào.
2) Notion → máy: file đính kèm trong 📥 University Inbox chưa có bản trên máy (bạn tải thẳng lên Notion) -> tải về, xếp đúng chỗ,
   KHÔNG nạp lại lên Notion (đã có ở đó).
Chống trùng: vân tay SHA-256 so với MỌI file trong Uni-Documents trước khi đặt file; trùng thì không đặt (ghi lại là "đã có ở …").
Không bao giờ xoá / di chuyển file đã có trên máy.
  python teams_files.py [--dry]"""
import uc_config as cfg
import json, os, re, hashlib, unicodedata, urllib.request, datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNI = Path(cfg.path("uni_documents"))
TDIR = HERE / 'school' / 'teams'
REG = TDIR / 'files_done.json'          # id Teams / file Notion -> kết quả
FOLDERS = HERE / 'uni_folders.json'     # môn mới -> thư mục tự tạo (bổ sung COURSE_FOLDERS)
DOC_EXT = {'.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.md', '.zip', '.rar', '.7z', '.c', '.cpp', '.h', '.py', '.ipynb', '.java', '.csv'}
SKIP_CHANNEL = re.compile(r'trao đổi|thảo luận|discussion', re.I)
INBOX_DB = cfg.notion("inbox")


def norm(s):
    s = unicodedata.normalize('NFD', (s or '').lower())
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd'))).strip()


def sha256_of(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def local_index():
    """sha -> đường dẫn tương đối, cho MỌI file trong Uni-Documents (có đệm theo kích thước + giờ sửa)."""
    cache_p = HERE / 'uni_sha_cache.json'
    try: cache = json.loads(cache_p.read_text(encoding='utf-8'))
    except Exception: cache = {}
    out, keep = {}, {}
    for root, dirs, files in os.walk(UNI):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not (Path(root) == UNI and d.startswith('00 · Inbox'))]
        for fn in files:
            p = Path(root) / fn
            try: st = p.stat()
            except OSError: continue
            rel = str(p.relative_to(UNI)); sig = f'{st.st_size}:{int(st.st_mtime)}'
            c = cache.get(rel)
            h = c['sha'] if c and c['sig'] == sig else sha256_of(p)
            keep[rel] = {'sig': sig, 'sha': h}; out.setdefault(h, rel)
    cache_p.write_text(json.dumps(keep, ensure_ascii=False), encoding='utf-8')
    return out


# ------------------------------------------------------------------ môn ↔ lớp Teams ↔ thư mục
def course_table():
    """[(mã môn, tên môn, {mã lớp})] từ TKB qldt (school/latest.json) + thư mục môn đã biết."""
    import copilot_app as app
    rows = {}
    try:
        tkb = json.loads((HERE / 'school' / 'latest.json').read_text(encoding='utf-8')).get('tkb') or {}
        for r in tkb.get('rows', []):
            if len(r) < 2: continue
            m = re.search(r'^(.*?)\n\s*(\d{5,6})\s*-\s*([A-Z]{2,4}\d{4})', r[1])
            if m: rows.setdefault(m.group(3), [m.group(1).strip(), set()])[1].add(m.group(2))
    except Exception: pass
    for rel, (code, name) in {**app.COURSE_FOLDERS, **extra_folders()}.items():
        if code: rows.setdefault(code, [name, set()])
    return [(c, n, cl) for c, (n, cl) in rows.items()]


def course_of_team(team, table=None):
    table = table or course_table()
    T = team.upper()
    for code, name, cls in table:
        if code in T: return code, name
    for code, name, cls in table:
        if any(c in T for c in cls): return code, name
    nt = norm(team)   # theo tên môn: ưu tiên môn đang học kỳ này (có mã lớp trong TKB), rồi tên ngắn nhất (Giải tích I trước Giải tích II)
    best = [(not cls, len(norm(name)), code, name) for code, name, cls in table
            if len(norm(name).split(' ')) >= 2 and ' '.join(norm(name).split(' ')[:2]) in nt]
    return (min(best)[2], min(best)[3]) if best else (None, None)


def extra_folders():
    try: return {k: tuple(v) for k, v in json.loads(FOLDERS.read_text(encoding='utf-8')).items()}
    except Exception: return {}


def folder_for(code, name):
    """Thư mục môn trong Uni-Documents; môn chưa có thư mục -> tạo '<Tên môn>' ở gốc và ghi nhớ."""
    import copilot_app as app
    for rel, (c, _) in {**app.COURSE_FOLDERS, **extra_folders()}.items():
        if c == code: return rel
    rel = re.sub(r'[<>:"/\\|?*]', ' ', name).strip() or code
    (UNI / rel).mkdir(parents=True, exist_ok=True)
    ex = {k: list(v) for k, v in extra_folders().items()}; ex[rel] = [code, name]
    FOLDERS.write_text(json.dumps(ex, ensure_ascii=False, indent=1), encoding='utf-8')
    return rel


CATS = [  # (regex trên tên file + đường dẫn Teams, thư mục con chuẩn)
    (r'\bde\b.*\b(thi|kiem tra|tham khao thi)|giua ky|cuoi ky|\bexam|\bquiz|\bmidterm', 'Đề thi - Kiểm tra'),
    (r'bai tap|\bbt\b|\bbt[_ ]|btvn|exercise|homework|lab\b|thuc hanh', 'Bài tập'),
    (r'slide|chap\s*\d|chuong|chapter|lecture|bai giang|\bbai \d', 'Slide Bài giảng'),
    (r'ghi chep|ghi chu|note', 'Ghi chú Bài giảng'),
]


def category_for(course_rel, name, teams_path=''):
    for root, _, files in os.walk(UNI / course_rel):   # đã có file cùng tên trong môn -> đặt cạnh nó (theo cách bạn đang xếp)
        if name in files: return str(Path(root).relative_to(UNI))
    s = norm(teams_path + ' ' + Path(name).stem)
    cat = next((c for rx, c in CATS if re.search(rx, s)), 'Tài liệu tham khảo')
    # thư mục môn đang dùng tên khác cho slide (vd "Slide Lý thuyết") -> theo thói quen sẵn có
    base = UNI / course_rel
    if cat == 'Slide Bài giảng' and not (base / cat).exists() and (base / 'Slide Lý thuyết').exists(): cat = 'Slide Lý thuyết'
    return os.path.join(course_rel, cat)


def _done():
    try: return json.loads(REG.read_text(encoding='utf-8'))
    except Exception: return {}


def _save_done(d): REG.parent.mkdir(parents=True, exist_ok=True); REG.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')


def _place(data, rel_folder, name, idx, dry):
    """Đặt nội dung vào thư mục, chống trùng theo SHA. -> (kết quả, đường dẫn tương đối)."""
    h = hashlib.sha256(data).hexdigest()
    if h in idx: return 'đã có', idx[h]
    if dry: return 'sẽ tải', os.path.join(rel_folder, name)
    import copilot_app as app
    d = UNI / rel_folder; d.mkdir(parents=True, exist_ok=True)
    p = d / app.safe_name(name)
    if p.exists(): p = app.unique_path(d, p.stem + ' (bản mới)' + p.suffix)   # cùng tên khác nội dung: giữ cả hai, uni_sync so phiên bản
    tmp = p.with_name(p.name + '.part'); tmp.write_bytes(data); tmp.replace(p)
    rel = str(p.relative_to(UNI)); idx[h] = rel
    return 'đã tải', rel


def sync_teams(dry=False):
    try: files = json.loads((TDIR / 'files.json').read_text(encoding='utf-8'))['items']
    except Exception: return {'ok': False, 'error': 'chưa đọc Teams'}
    done, idx, table, out = _done(), local_index(), course_table(), []
    for f in files:
        key = f"teams:{f['id']}"
        prev = done.get(key)
        if prev and prev.get('modified') == f['modified']: continue
        ext = Path(f['name']).suffix.lower()
        if ext not in DOC_EXT or SKIP_CHANNEL.search(f['channel']) or re.match(r'^\d{10,}_', f['name']):
            done[key] = {'modified': f['modified'], 'kq': 'bỏ qua', 'name': f['name']}; continue
        code, cname = course_of_team(f['team'], table)
        if not code:
            done[key] = {'modified': f['modified'], 'kq': 'bỏ qua (nhóm không phải lớp môn)', 'name': f['name'], 'team': f['team']}; continue
        try:
            with urllib.request.urlopen(f['url'], timeout=180) as r: data = r.read()
        except Exception as e:
            out.append({'name': f['name'], 'kq': f'lỗi tải ({type(e).__name__}) — lượt sau thử lại'}); continue   # link tạm hết hạn -> lần đọc Teams sau có link mới
        kq, rel = _place(data, category_for(folder_for(code, cname), f['name'], f.get('path', '')), f['name'], idx, dry)
        out.append({'name': f['name'], 'mon': code, 'kq': kq, 'rel': rel})
        if not dry: done[key] = {'modified': f['modified'], 'kq': kq, 'rel': rel, 'name': f['name'], 'mon': code, 'at': dt.datetime.now().isoformat(timespec='minutes')}
    if not dry: _save_done(done)
    return {'ok': True, 'items': out}


def sync_notion(post, dry=False):
    """File trong 📥 University Inbox mà trên máy chưa có -> tải về, xếp qua agent (không nạp lại lên Notion)."""
    import academic, copilot_app as app
    nt = academic.Notion(post)
    done, idx, out = _done(), local_index(), []
    with app.lock:
        known = {(it.get('inboxUrl') or '').rstrip('/').split('-')[-1] for it in app.load_state()['items'] if it.get('inboxUrl')}
    for r in nt.query(INBOX_DB):
        rid = r['id'].replace('-', '')
        if rid in known: continue   # dòng sinh ra từ file trên máy
        files = [f for v in r['properties'].values() if v['type'] == 'files' for f in v['files']]
        course = r['properties'].get('Detected Course', {}).get('relation') or []
        for f in files:
            key = f"notion:{rid}:{f.get('name')}"
            if key in done: continue
            url = (f.get('file') or {}).get('url') if f['type'] == 'file' else (f.get('external') or {}).get('url')
            if not url or re.search(r'drive\.google\.com|docs\.google\.com', url):   # link Drive cần đăng nhập Google: không tự tải
                done[key] = {'kq': 'bỏ qua (link Drive)', 'name': f.get('name')}; continue
            try:
                with urllib.request.urlopen(url, timeout=180) as resp: data = resp.read()
            except Exception as e:
                out.append({'name': f.get('name'), 'kq': f'lỗi tải ({type(e).__name__})'}); continue
            h = hashlib.sha256(data).hexdigest()
            if h in idx:
                done[key] = {'kq': 'đã có', 'rel': idx[h], 'name': f.get('name')}; out.append(done[key]); continue
            if dry: out.append({'name': f.get('name'), 'kq': 'sẽ tải'}); continue
            # vào 00 · Inbox -> agent xếp như tab Inbox; đánh dấu đã có trên Notion để không nạp lại
            app.INBOX.mkdir(parents=True, exist_ok=True)
            p = app.unique_path(app.INBOX, app.safe_name(f.get('name') or 'file')); p.write_bytes(data)
            item = {'id': __import__('uuid').uuid4().hex, 'name': p.name, 'path': str(p), 'size': len(data), 'status': 'queued',
                    'createdAt': __import__('time').time(), 'updatedAt': __import__('time').time(), 'source': 'notion',
                    'fromNotion': r.get('url'), 'inboxUrl': r.get('url'), 'sha': h}
            with app.lock:
                st = app.load_state(); st['items'].append(item); app.save_state(st)
            app.jobs.put(item['id']); idx[h] = '00 · Inbox/' + p.name
            done[key] = {'kq': 'đã tải, đang xếp', 'name': p.name}; out.append(done[key])
    if not dry: _save_done(done)
    return {'ok': True, 'items': out}


if __name__ == '__main__':
    import sys
    dry = '--dry' in sys.argv
    print(json.dumps(sync_teams(dry), ensure_ascii=False, indent=1))
