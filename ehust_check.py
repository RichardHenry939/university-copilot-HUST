# -*- coding: utf-8 -*-
"""(v1.00.49) Đối chiếu lịch học tuần này: app eHUST (trong máy ảo) với lịch UC đang hiện (qldt + Teams + ...).

UC tự chạy mỗi 3 giờ (06–22h): mở eHUST -> Thời khoá biểu -> bấm từng ngày trong tuần -> đọc các buổi học
-> so với /api/timetable/all (chỉ loại Class). Lệch thì báo bạn (mỗi kiểu lệch chỉ báo 1 lần) và ghi
school/ehust_check.json. Chỉ ĐỌC app, không bấm gì khác.

Giới hạn (đi tắt): đọc qua giao diện (uiautomator), nên app đổi nhãn / bố cục thì phải sửa;
tuần vắt sang tháng sau mà lịch tháng của app chưa hiện ô ngày đó thì bỏ qua ngày đó (ghi rõ trong kết quả).
So theo (ngày, giờ bắt đầu, mã học phần) + phòng; không so giảng viên (UC chưa có).
"""
import datetime as dt, hashlib, json, re, time, urllib.request
from pathlib import Path

from ictsv_login import adb, nodes, find, tap, UI

PKG = 'uni.hust.ehust'
OUT = Path(__file__).resolve().parent / 'school' / 'ehust_check.json'
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
SLOT = re.compile(r'^(\d\d:\d\d)\n(\d\d:\d\d)\n')


def day_label(d): return f'{DAYS[d.weekday()]}, {MONTHS[d.month - 1]} {d.day}, {d.year}'


def norm_room(r):
    r = (r or '').strip()
    return 'Online' if r.lower().startswith('online') else r.upper().replace(' ', '')


def parse_slot(label):
    """'06:45\\n09:10\\n171992 - Đại số\\nMã học phần: MI1141\\nOnline\\n...' -> dict hoặc None."""
    m = SLOT.match(label)
    code = re.search(r'Mã học phần:\s*(\w+)', label)
    if not (m and code): return None
    lines = label.split('\n')
    i = next(k for k, l in enumerate(lines) if l.startswith('Mã học phần'))
    return {'start': m.group(1), 'end': m.group(2), 'code': code.group(1),
            'name': re.sub(r'^\d+\s*-\s*', '', lines[2]) if len(lines) > 2 else '',
            'room': lines[i + 1] if len(lines) > i + 1 else '',
            'gv': next((l.split(':', 1)[1].strip() for l in lines if l.startswith('Giảng viên')), '')}


def open_tkb():
    """Mở eHUST tới màn Thời khoá biểu. App có lúc kẹt màn trống -> tắt hẳn mở lại 1 lần."""
    for attempt in range(2):
        if attempt: adb('shell', 'am', 'force-stop', PKG)
        adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1')
        for _ in range(10):
            time.sleep(2); ns = nodes()
            tile = find(ns, 'Thời khoá biểu')
            if tile: tap(tile); time.sleep(2); return True
            if find(ns, 'Thời khóa biểu', click=False):   # đã ở sẵn màn TKB (tiêu đề viết "khóa")
                return True
            back = find(ns, 'Quay lại')
            if back: tap(back)
            home = next((n for n in ns if n['label'].startswith('Trang chủ\nTab')), None)
            if home: tap(home)
    return False


def read_week(monday):
    """-> ({'YYYY-MM-DD': [buổi...]}, [ngày bỏ qua])"""
    out, skipped = {}, []
    for k in range(7):
        d = monday + dt.timedelta(days=k)
        cell = find(nodes(), day_label(d))
        if not cell: skipped.append(d.isoformat()); continue
        tap(cell)
        ns = []
        for _ in range(4):   # chờ danh sách ngày đó hiện ra
            ns = nodes()
            if any(n['label'].startswith(f'Bạn có') and d.strftime('%d/%m/%Y') in n['label'] for n in ns): break
            time.sleep(1)
        out[d.isoformat()] = [s for s in (parse_slot(n['label']) for n in ns) if s]
    return out, skipped


def uc_week(monday):
    r = json.load(urllib.request.urlopen('http://127.0.0.1:8320/api/timetable/all', timeout=120))
    end = (monday + dt.timedelta(days=7)).isoformat()
    out = {}
    for e in r.get('events', []):
        st = str(e.get('start') or '')
        if e.get('kind') != 'Class' or not (monday.isoformat() <= st[:10] < end): continue
        out.setdefault(st[:10], []).append({'start': st[11:16], 'end': str(e.get('end') or '')[11:16],
                                            'code': str(e.get('title', '')).split(' · ')[0].strip(),
                                            'title': e.get('title', ''), 'room': e.get('location', ''),
                                            'teams': e.get('source') == 'teams'})
    return out


def teams_moved():
    """{(ngày cũ, mã môn)} các buổi Teams đã dời đi. Teams đi trước cả eHUST (vd IT2000 tuần 26/10)."""
    try:
        import teams_overrides
        return {(o['date_old'], o['code']) for o in teams_overrides.overrides() if o.get('date_old')}
    except Exception as e: print('ehust_check teams:', e); return set()


def compare(eh, uc, days, moved=frozenset()):
    """Thứ tự tin: Teams > eHUST > qldt. Lệch do Teams đổi -> ghi 'theo_teams' (không báo), còn lại báo."""
    diffs = []
    # môn nào Teams đổi lịch trong tuần thì cả tuần đó tin Teams (vd tuần 26/10: eHUST xếp IT2000 31/10, Teams 01/11)
    teams_codes = {c for d, c in moved if d in days} | {s['code'] for d in days for s in uc.get(d, []) if s['teams']}
    for d in days:
        a = {(s['start'], s['code']): s for s in eh.get(d, [])}
        b = {(s['start'], s['code']): s for s in uc.get(d, [])}
        for k in a.keys() - b.keys():
            s = a[k]; diffs.append({'ngay': d, 'loai': 'chỉ eHUST có', 'mon': s['code'], 'gio': f"{s['start']}–{s['end']}",
                                    'phong': s['room'], 'theo_teams': s['code'] in teams_codes})
        for k in b.keys() - a.keys():
            s = b[k]; diffs.append({'ngay': d, 'loai': 'chỉ UC có', 'mon': s['code'], 'gio': f"{s['start']}–{s['end']}",
                                    'phong': s['room'], 'theo_teams': s['teams']})
        for k in a.keys() & b.keys():
            if norm_room(a[k]['room']) != norm_room(b[k]['room']):
                diffs.append({'ngay': d, 'loai': 'khác phòng', 'mon': k[1], 'gio': k[0], 'ehust': a[k]['room'],
                              'uc': b[k]['room'], 'theo_teams': b[k]['teams']})
    return sorted(diffs, key=lambda x: (x['ngay'], x['gio']))


def run(today=None, send=True):
    today = today or dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    t0 = time.time()
    with UI:   # không chen với lượt canh iCTSV (cùng dùng màn hình máy ảo)
        if b'device' not in adb('get-state').stdout: return {'ok': False, 'error': 'máy ảo chưa bật'}
        if not open_tkb(): return {'ok': False, 'error': 'không mở được Thời khoá biểu eHUST'}
        eh, skipped = read_week(monday)
        adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
    days = sorted(eh)
    diffs = compare(eh, uc_week(monday), days, teams_moved())
    real = [x for x in diffs if not x['theo_teams']]   # chỉ báo chỗ lệch mà Teams không giải thích được
    res = {'ok': True, 'at': dt.datetime.now().isoformat(timespec='seconds'), 'tuan': monday.isoformat(),
           'giay': round(time.time() - t0, 1), 'ngay_doc': days, 'ngay_bo_qua': skipped,
           'ehust': eh, 'lech': diffs}
    old = {}
    try: old = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: pass
    sig = hashlib.sha1(json.dumps(real, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    res['sig'], res['da_bao'] = sig, old.get('da_bao', [])
    if real and send and sig not in res['da_bao']:
        lines = [f"{x['ngay'][8:]}/{x['ngay'][5:7]} {x['mon']} {x['gio']}: {x['loai']}" +
                 (f" (eHUST {x['ehust']} / UC {x['uc']})" if x['loai'] == 'khác phòng' else f" ({x['phong']})") for x in real]
        try:
            import alerts
            alerts.notify('UC · eHUST lệch lịch', '\n'.join(lines[:6]) + (f'\n… và {len(lines) - 6} chỗ nữa' if len(lines) > 6 else ''), level='change')
        except Exception as e: print('ehust_check notify:', e)
        res['da_bao'] = (res['da_bao'] + [sig])[-20:]
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    return res


def loop(every=3 * 3600):
    time.sleep(120)   # để UC khởi động xong
    while True:
        try:
            if 6 <= dt.datetime.now().hour < 22:
                r = run(); print('ehust_check:', r.get('error') or f"{len(r['lech'])} chỗ lệch, {r['giay']}s")
        except Exception as e: print('ehust_check loop:', e)
        time.sleep(every)


if __name__ == '__main__':
    r = run(send='--no-notify' not in __import__('sys').argv)
    print(json.dumps({k: r.get(k) for k in ('ok', 'error', 'giay', 'ngay_doc', 'ngay_bo_qua', 'lech')}, ensure_ascii=False, indent=1))
