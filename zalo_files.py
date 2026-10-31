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
    tmp = REG.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(REG)


def _signature(path):
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def _candidates(now=None):
    if not ZDIR.is_dir(): return []
    now = time.time() if now is None else now
    out = []
    for p in ZDIR.rglob('*'):
        try:
            if not p.resolve().is_relative_to(ZDIR.resolve()) or p.is_symlink(): continue
            if not p.is_file() or p.name.startswith(('.', '~$')) or p.name.lower() == 'desktop.ini' or p.suffix.lower() in SKIP_SUFFIX: continue
            if now - p.stat().st_mtime >= STABLE_SEC: out.append(p)
        except OSError: continue
    return out


def _verified(path, sha, tf, root):
    try:
        return path.resolve().is_relative_to(root.resolve()) and path.is_file() and tf.sha256_of(path) == sha
    except OSError:
        return False


def sync_once(now=None):
    """Persist Inbox state before queueing; remove a source only with a verified local copy."""
    files = _candidates(now)
    if not files: return []
    import copilot_app as app, teams_files as tf
    root = app.INBOX.parent
    idx = {h: root / rel for h, rel in tf.local_index().items()}
    with app.lock:
        for it in app.load_state()['items']:
            if it.get('sha') and it.get('path'):
                idx[it['sha']] = Path(it['path'])
    done, out = _done(), []
    for p in files:
        try:
            before = _signature(p); h = tf.sha256_of(p)
            if _signature(p) != before: continue
            at = dt.datetime.now().isoformat(timespec='minutes')
            dest = idx.get(h)
            duplicate = dest is not None and _verified(dest, h, tf, root)
            if not duplicate:
                app.INBOX.mkdir(parents=True, exist_ok=True)
                dest = app.unique_path(app.INBOX, app.safe_name(p.name))
                tmp = dest.with_name(dest.name + '.part')
                try:
                    shutil.copy2(p, tmp)
                    if tf.sha256_of(tmp) != h or _signature(p) != before:
                        raise IOError('file nguồn đang đổi hoặc bản chép không khớp SHA')
                    tmp.replace(dest)
                except Exception as e:
                    tmp.unlink(missing_ok=True)
                    out.append({'name': p.name, 'kq': f'chép lỗi ({type(e).__name__}), giữ bản Zalo'})
                    continue
                item = dict(id=str(uuid.uuid4()), name=dest.name, path=str(dest), size=before[0],
                    status='queued', createdAt=time.time(), updatedAt=time.time(), source='zalo', sha=h)
                try:
                    with app.lock:
                        st = app.load_state(); st['items'].append(item); app.save_state(st)
                except Exception:
                    dest.unlink(missing_ok=True)  # our unregistered copy; source is still untouched
                    raise
                idx[h] = dest
            # Queue only after source cleanup, so the worker cannot move the verified copy mid-check.
            kq = 'trùng, đã xoá bản Zalo' if duplicate else 'đã chuyển vào Inbox, đang xếp'
            try:
                if _signature(p) != before or tf.sha256_of(p) != h or not _verified(dest, h, tf, root):
                    kq = 'giữ bản Zalo: nguồn/đích đã thay đổi, sẽ kiểm lại'
                else: p.unlink()
            except OSError:
                kq = 'đã có bản Inbox, chưa xoá được bản Zalo'
            finally:
                if not duplicate: app.jobs.put(item['id'])
            done[h] = dict(name=p.name, kq=kq, rel=str(dest.relative_to(root)), at=at)
            out.append(done[h])
        except Exception as e:
            out.append(dict(name=p.name, kq=f'lỗi {type(e).__name__}; giữ bản Zalo'))
    _save_done(done)
    return out


def status():
    """Expose source readiness without implying that UC downloads Zalo messages."""
    return dict(folderExists=ZDIR.is_dir(), readyFiles=len(_candidates()),
        mode='downloaded-files', message='UC nhận file đã tải vào Zalo-Logistic-Checkpoint; không tự tải từ tin nhắn Zalo.')


def loop(every=30):
    time.sleep(25)
    while True:
        try:
            for r in sync_once(): print('zalo:', r.get('name'), '-', r.get('kq'))
        except Exception as e: print('zalo:', e)
        time.sleep(every)
