# -*- coding: utf-8 -*-
"""💾 Đọc / ghi file trạng thái JSON an toàn (Claude 14/10/2026 — mục D-1 báo cáo đánh giá).

Trước đây các file trạng thái (events.json, alerts.json, …) ghi thẳng bằng write_text: tắt máy / mất điện đúng lúc ghi -> file cụt,
và mọi load() nuốt lỗi trả RỖNG -> UC coi như chưa xử lý thư nào (gửi lại hết cho Gemini, nhân đôi trang Notion, mất "Sẽ đi / Bỏ").
  save_json(path, obj): ghi file tạm riêng -> ép xuống đĩa (fsync) -> giữ bản cũ thành .bak -> os.replace (thử lại vì Windows hay khoá file).
  load_json(path, default): đọc; hỏng -> đọc .bak và GHI LỖI RÕ (school/state_errors.log + in ra); cả hai hỏng mới trả default.
Giới hạn: không thay thế khoá giữa các luồng (lock) — chỉ chống file hỏng nửa chừng."""
import json, os, threading, time
from datetime import datetime
from pathlib import Path

ERRLOG = Path(__file__).resolve().parent / 'school' / 'state_errors.log'
_n = 0
_nlock = threading.Lock()


def _err(msg):
    print('uc_state:', msg)
    try:
        ERRLOG.parent.mkdir(parents=True, exist_ok=True)
        with open(ERRLOG, 'a', encoding='utf-8') as f: f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n')
    except Exception: pass


def load_json(path, default):
    path = Path(path)
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception as e:
        bak = path.with_name(path.name + '.bak')
        try:
            v = json.loads(bak.read_text(encoding='utf-8-sig'))
            _err(f'{path.name} hỏng ({type(e).__name__}) -> dùng bản .bak'); return v
        except Exception:
            _err(f'{path.name} hỏng ({type(e).__name__}) và không có .bak dùng được -> trạng thái mặc định'); return default


def save_json(path, obj, indent=1):
    global _n
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with _nlock: _n += 1; n = _n
    tmp = path.with_name(f'{path.name}.{os.getpid()}.{n}.tmp')   # tên riêng: hai luồng / hai tiến trình không giẫm file tạm của nhau
    data = json.dumps(obj, ensure_ascii=False, indent=indent)
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    if path.exists():
        try:
            json.loads(path.read_text(encoding='utf-8-sig'))   # chỉ giữ .bak khi bản hiện tại còn tốt
            _copy(path, path.with_name(path.name + '.bak'))
        except Exception: pass
    for i in range(10):
        try: os.replace(tmp, path); return
        except PermissionError: time.sleep(0.1 * (i + 1))   # Windows: file đang được đọc -> thử lại
    os.replace(tmp, path)


def _copy(src, dst):
    tmp = dst.with_name(dst.name + '.tmp')
    tmp.write_bytes(src.read_bytes()); os.replace(tmp, dst)


_locks = {}


def lock(name):
    """(v1.00.27, D-3/D-5) Khoá dùng chung theo tên file trạng thái. Đặt ở đây vì uc_state KHÔNG bị importlib.reload
    (alerts / mail_events bị reload mỗi lượt nên khoá đặt trong chúng sẽ bị tạo lại). RLock: lồng nhau trong cùng luồng được."""
    with _nlock:
        return _locks.setdefault(name, threading.RLock())
