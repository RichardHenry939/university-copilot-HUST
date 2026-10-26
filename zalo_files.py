# -*- coding: utf-8 -*-
"""(v1.00.36) File Zalo -> Uni-Documents -> Drive + 📥 University Inbox (Notion), như file Teams.

Zalo PC lưu file bạn tải về vào ZDIR (bạn đặt trong cài đặt Zalo). Tin nhắn Zalo bị Zalo mã hoá: UC KHÔNG đọc, chỉ lấy file bạn đã tải.
Luồng mỗi file (đã ghi xong, đứng yên STABLE_SEC giây):
  chép vào Uni-Documents\\00 · Inbox -> kiểm SHA-256 bản chép khớp bản gốc -> đưa agent xếp (Tika + LM Studio -> thư mục môn -> Drive + Notion)
  -> XOÁ bản trong ZDIR (máy chỉ giữ 1 bản, ở kho Uni-Documents).
Trùng nội dung với file đã có trong Uni-Documents / đang chờ trong Inbox -> không nạp lại, chỉ xoá bản trong ZDIR.
Chép lỗi hoặc SHA không khớp -> KHÔNG xoá, giữ nguyên để lượt sau thử lại.
Chỉ đụng tới ZDIR: các file khác trong Downloads (sao kê, file trình duyệt…) không bao giờ bị đọc hay xoá.
"""
import datetime as dt, json, shutil, time, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
def _zdir():
    try:
        import uc_config as cfg
        return Path(cfg.path('zalo_inbox'))   # config.json > paths > zalo_inbox: thư mục bạn đặt cho Zalo lưu file
    except Exception:
        return Path.home() / 'Downloads' / 'Zalo-Logistic-Checkpoint'


ZDIR = _zdir()
REG = HERE / 'school' / 'zalo' / 'files_done.json'
STABLE_SEC = 20   # Zalo còn đang ghi file thì giờ sửa vẫn nhảy: chờ đứng yên rồi mới lấy
SKIP_SUFFIX = {'.tmp', '.part', '.crdownload', '.download', '.partial'}


def _done():
    try: return json.loads(REG.read_text(encoding='utf-8'))
    except Exception: return {}


def _save_done(d):
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')


def _candidates(now=None):
    if not ZDIR.is_dir(): return []
    now = now or time.time()
    out = []
    for p in ZDIR.iterdir():   # chỉ cấp đầu của thư mục, không đi vào thư mục con
        if not p.is_file() or p.name.startswith(('.', '~$')) or p.name.lower() == 'desktop.ini' or p.suffix.lower() in SKIP_SUFFIX: continue
        try:
            if now - p.stat().st_mtime < STABLE_SEC: continue
        except OSError: continue
        out.append(p)
    return out


def sync_once(now=None):
    """-> danh sách kết quả từng file của lượt này (rỗng khi thư mục trống)."""
    files = _candidates(now)
    if not files: return []
    import copilot_app as app, teams_files as tf
    idx = tf.local_index()   # sha -> file đã có trong Uni-Documents (đệm theo kích thước + giờ sửa)
    with app.lock:
        pending = {it.get('sha'): it.get('name') for it in app.load_state()['items']
                   if it.get('sha') and it.get('status') in ('queued', 'reading', 'thinking', 'review')}
    done, out = _done(), []
    for p in files:
        try: h = tf.sha256_of(p)
        except OSError as e: out.append({'name': p.name, 'kq': f'chưa đọc được ({type(e).__name__}), lượt sau thử lại'}); continue
        at = dt.datetime.now().isoformat(timespec='minutes')
        if h in idx or h in pending:
            where = idx.get(h) or ('00 · Inbox/' + str(pending.get(h)))
            try: p.unlink()
            except OSError as e: out.append({'name': p.name, 'kq': f'trùng, chưa xoá được ({type(e).__name__})'}); continue
            done[h] = {'name': p.name, 'kq': 'trùng, đã xoá bản Zalo', 'rel': where, 'at': at}; out.append(done[h]); continue
        app.INBOX.mkdir(parents=True, exist_ok=True)
        dest = app.unique_path(app.INBOX, app.safe_name(p.name))
        tmp = dest.with_name(dest.name + '.part')
        try:
            shutil.copy2(p, tmp)
            if tf.sha256_of(tmp) != h: raise IOError('bản chép không khớp SHA')
            tmp.replace(dest)
        except Exception as e:
            try: tmp.unlink()
            except OSError: pass
            out.append({'name': p.name, 'kq': f'chép lỗi ({type(e).__name__}), giữ bản Zalo'}); continue
        item = {'id': str(uuid.uuid4()), 'name': dest.name, 'path': str(dest), 'size': dest.stat().st_size, 'status': 'queued',
                'createdAt': time.time(), 'updatedAt': time.time(), 'source': 'zalo', 'sha': h}
        with app.lock:
            st = app.load_state(); st['items'].append(item); app.save_state(st)
        app.jobs.put(item['id'])
        try: p.unlink(); kq = 'đã chuyển vào Inbox, đang xếp'
        except OSError as e: kq = f'đã chuyển vào Inbox, CHƯA xoá bản Zalo ({type(e).__name__})'
        done[h] = {'name': p.name, 'kq': kq, 'inbox': dest.name, 'at': at}; out.append(done[h])
    _save_done(done)
    return out


def loop(every=30):
    time.sleep(25)
    while True:
        try:
            for r in sync_once(): print('zalo:', r.get('name'), '-', r.get('kq'))
        except Exception as e: print('zalo:', e)
        time.sleep(every)
