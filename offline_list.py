# -*- coding: utf-8 -*-
"""(v1.00.42) Đối chiếu MSSV với "Danh sách học offline" (Google Sheet gắn ở tab của kênh 01. Lịch học, lớp IT2000).

Nguồn: tab Teams tên "Danh sách học offline" trong school/teams/files.json -> đọc trang FULL dạng CSV (chỉ đọc, không đăng nhập).
Cột A = MSSV, cột "Buổi học offline" = "B1: 10/09/2026, B7: 29/10/2026".
Riêng tư: cả bảng chỉ nằm trong bộ nhớ lúc đọc. Chỉ lưu school/offline_me.json gồm buổi -> ngày (chung cả lớp) và buổi của BẠN.
Không lưu MSSV, tên hay dòng của người khác.

Giới hạn: chỉ một lớp có loại danh sách này (IT2000). Bảng đổi cấu trúc (mất cột MSSV / cột buổi) thì báo lỗi, không đoán.
Buổi đã dời ngày (vd B7 29/10 -> 01/11) được nhận qua nhãn "Buổi học N" mà teams_overrides gắn vào sự kiện.
"""
import csv, datetime as dt, io, json, re, threading, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = HERE / 'school' / 'teams' / 'files.json'
OUT = HERE / 'school' / 'offline_me.json'
TZ = dt.timezone(dt.timedelta(hours=7))
TAB_NAME = 'Danh sách học offline'
CODE = 'IT2000'
MAX_AGE_H = 6
WAIT_MIN = 20
_lock = threading.Lock()


def sheet_url():
    try: d = json.loads(FILES.read_text(encoding='utf-8'))
    except Exception: return None
    for t in d.get('tabs') or []:
        u = t.get('url') or ''
        if t.get('name') == TAB_NAME and u.startswith('https://docs.google.com/spreadsheets/d/'): return u
    return None


def _csv_url(url, sheet='FULL'):
    sid = re.match(r'https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)', url).group(1)
    return f'https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(sheet)}'


def _parse_buoi(cell):
    """'B1: 10/09/2026, B7: 29/10/2026' -> {1: '2026-09-10', 7: '2026-10-29'}"""
    out = {}
    for n, d, m, y in re.findall(r'B\s*(\d{1,2})\s*:\s*(\d{1,2})/(\d{1,2})/(\d{4})', cell or ''):
        out[int(n)] = f'{y}-{int(m):02d}-{int(d):02d}'
    return out


def match(rows, mssv):
    """rows: bảng CSV (list of list). -> {'ok', 'found', 'mine': {n: date}, 'all': {n: date}} hoặc lỗi."""
    if not rows: return {'ok': False, 'loi': 'bảng rỗng'}
    head = [c.lower() for c in rows[0]]
    col = next((j for j, c in enumerate(head) if c.strip() == 'buổi học offline'), None)   # ô A1 là tiêu đề lớn cũng chứa cụm này
    if col is None: return {'ok': False, 'loi': 'bảng không có cột "Buổi học offline"'}
    allb, mine, found = {}, {}, False
    for r in rows[1:]:
        if len(r) <= col: continue
        b = _parse_buoi(r[col])
        for n, d in b.items(): allb.setdefault(n, d)
        if r[0].strip() == mssv: found, mine = True, b
    if not allb: return {'ok': False, 'loi': 'không đọc được buổi nào trong bảng'}
    return {'ok': True, 'found': found, 'mine': mine, 'all': allb}


def refresh(mssv=None, fetch=None):
    """Đọc lại bảng và ghi offline_me.json. fetch(url) -> text (để test)."""
    import mssv_store
    mssv = mssv or mssv_store.load()
    now = dt.datetime.now(TZ).isoformat(timespec='minutes')
    if not mssv: res = {'ok': False, 'loi': 'chưa lưu MSSV (tab Giới thiệu)'}
    else:
        url = sheet_url()
        if not url: res = {'ok': False, 'loi': f'không thấy tab "{TAB_NAME}" trong dữ liệu Teams'}
        else:
            try:
                text = fetch(url) if fetch else urllib.request.urlopen(_csv_url(url), timeout=30).read().decode('utf-8')
                res = match(list(csv.reader(io.StringIO(text))), mssv)
            except Exception as e: res = {'ok': False, 'loi': f'{type(e).__name__}: {e}'[:200]}
    res = {**res, 'at': now, 'code': CODE}
    res.pop('mssv', None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    return res


def load():
    try: return json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return None


def _stale(st, max_age_h=MAX_AGE_H):
    try: return (dt.datetime.now(TZ) - dt.datetime.fromisoformat(st['at'])).total_seconds() > max_age_h * 3600
    except Exception: return True


def _waiting_today(cal_events, st):
    """Hôm nay có buổi lý thuyết IT2000 chưa kết thúc mà danh sách chưa có buổi đó -> đang chờ lớp đăng danh sách."""
    if not cal_events or not st or not st.get('ok'): return False
    now = dt.datetime.now(TZ); today = now.date().isoformat()
    allb = {int(k): v for k, v in (st.get('all') or {}).items()}
    for ev in cal_events:
        if ev.get('kind') != 'Class' or f'{CODE} ·' not in (ev.get('title') or '') or 'Thực nghiệm' in ev['title']: continue
        if (ev.get('start') or '')[:10] != today: continue
        try:
            if dt.datetime.fromisoformat((ev.get('end') or ev['start']).replace('Z', '+00:00')) < now: continue
        except Exception: pass
        n = _buoi_of(ev, allb)
        if n is None or n not in allb: return True
    return False


def ensure_fresh(cal_events=None):
    """Không chặn API lịch: đọc lại ở luồng nền khi bảng cũ quá MAX_AGE_H giờ,
    hoặc quá WAIT_MIN phút nếu hôm nay có buổi đang chờ danh sách (lớp đăng DS đầu giờ chiều hôm học).
    Bản tóm tắt gửi mỗi 10 phút gọi API lịch, nên việc này tự chạy cả khi không mở UI."""
    st = load()
    age = WAIT_MIN / 60 if _waiting_today(cal_events, st) else MAX_AGE_H
    if st is None or _stale(st, age):
        def run():
            if _lock.acquire(blocking=False):
                try: refresh()
                finally: _lock.release()
        threading.Thread(target=run, daemon=True).start()
    return st


def _buoi_of(ev, allb):
    m = re.search(r'Buổi học\s*(\d{1,2})', ev.get('label') or '')
    if m: return int(m.group(1))
    d = (ev.get('start') or '')[:10]
    return next((n for n, x in allb.items() if x == d), None)


def verdict(ev, st):
    """-> ('truc_tiep'|'online', n) hoặc None (chưa xác định: không đoán)."""
    if not st or not st.get('ok'): return None
    if f'{CODE} ·' not in (ev.get('title') or '') or ev.get('kind') != 'Class': return None
    if 'Thực nghiệm' in (ev.get('title') or ''): return None   # danh sách chỉ cho buổi lý thuyết của lớp
    allb = {int(k): v for k, v in (st.get('all') or {}).items()}
    n = _buoi_of(ev, allb)
    if n is None or n not in allb: return None
    mine = {int(k) for k in (st.get('mine') or {})}
    return ('truc_tiep' if n in mine else 'online'), n


def annotate(cal_events, st=None):
    st = st if st is not None else ensure_fresh(cal_events)
    if not st or not st.get('ok'): return cal_events
    out = []
    for ev in cal_events:
        v = verdict(ev, st)
        if v:
            kind, n = v
            ev = dict(ev, attend=kind, notes=(f"🏫 Buổi {n}: bạn học TRỰC TIẾP (DS offline)" if kind == 'truc_tiep'
                                             else f"💻 Buổi {n}: bạn học ONLINE (không có tên trong DS offline)") +
                                            (f" · {ev['notes']}" if ev.get('notes') else ''))
        out.append(ev)
    return out


def summary(st=None):
    """Cho tab Giới thiệu: các dòng 'Buổi 7 (01/11): trực tiếp', không có MSSV."""
    st = st if st is not None else load()
    if not st: return {'ok': False, 'loi': 'chưa đọc danh sách'}
    if not st.get('ok'): return {'ok': False, 'loi': st.get('loi'), 'at': st.get('at')}
    mine = {int(k) for k in st.get('mine') or {}}
    rows = [{'buoi': int(n), 'ngay_ds': d, 'truc_tiep': int(n) in mine} for n, d in sorted(st['all'].items(), key=lambda x: int(x[0]))]
    return {'ok': True, 'at': st.get('at'), 'found': st.get('found'), 'code': st.get('code'), 'buoi': rows}
