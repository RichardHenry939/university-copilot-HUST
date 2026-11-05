# -*- coding: utf-8 -*-
"""(chủ 05/11) CHỐNG MUỘN — chỉ buổi học TRỰC TIẾP.

- Bạn luôn ra khỏi nhà trước giờ vào lớp 15 phút -> 15 phút đó là TÍM (chuẩn bị / đi đường); buổi đầu ngày trước 8:00 thì tím từ 06:00.
- Nhắc thêm mốc 14, 13, ..., 1 phút trước giờ vào lớp (alerts.py), trừ khi đã được THA:
    * hai lần kiểm cách nhau 1 phút mà vị trí khác nhau (đang đi), hoặc
    * vị trí trùng toà của buổi học (vd B3) trên bản đồ khuôn viên.
- RIÊNG TƯ: toạ độ KHÔNG rời điện thoại. UC chỉ gửi xuống toạ độ tâm TOÀ của trường (dữ liệu bản đồ, không phải của bạn);
  điện thoại tự so, chỉ báo về "khác chỗ: có/không", "tới toà: có/không". UC chỉ lưu đúng mấy cờ đó (school/late.json).
Đi tắt: định vị mức tiết kiệm pin lệch vài chục mét -> "tới toà" = trong 80 m quanh tâm toà, "khác chỗ" = lệch > 100 m (điện thoại tính)."""
import datetime as dt, json, re, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / 'school' / 'late.json'
PLAN = HERE / 'ui' / 'assets' / 'hust-plan.json'
TZ = dt.timezone(dt.timedelta(hours=7))
PREP_MIN = 15          # ra khỏi nhà trước giờ vào lớp
EARLY_FROM = '06:00'   # buổi đầu ngày trước 8:00: tím từ lúc dậy
RADIUS_M = 80
MARKS = tuple(range(14, 0, -1))   # mốc nhắc thêm (phút)
S, N, W_, E = 21.0012, 21.0082, 105.8395, 105.8500   # khung bản đồ (build_campus_map.py)
_lock = threading.Lock()


def online(c):
    """Buổi học online? Đối chiếu DS học trực tiếp (attend) đứng trên chữ trong tiêu đề / phòng."""
    if c.get('attend') == 'online': return True
    if c.get('attend') == 'truc_tiep': return False
    return bool(re.search(r'online', str(c.get('title') or ''), re.I) or re.search(r'online|teams', str(c.get('location') or ''), re.I))


def offline_classes(events, day):
    out = []
    for c in events or []:
        st = str(c.get('start') or '')
        if c.get('kind') != 'Class' or 'T' not in st or st[:10] != day or 'NGHỈ' in str(c.get('title') or '') or online(c): continue
        out.append(c)
    return sorted(out, key=lambda c: c['start'])


def prep_spans(events, day):
    """Các đoạn TÍM chuẩn bị / đi đường hôm nay: [[ISO đầu, ISO cuối], ...]."""
    cs = offline_classes(events, day); out = []
    for i, c in enumerate(cs):
        s = dt.datetime.fromisoformat(c['start']).astimezone(TZ)
        a = s - dt.timedelta(minutes=PREP_MIN)
        if i == 0 and s.strftime('%H:%M') < '08:00':
            a = min(a, dt.datetime.fromisoformat(f"{day}T{EARLY_FROM}:00+07:00"))
        out.append([a.isoformat(timespec='minutes'), s.isoformat(timespec='minutes')])
    return out


def building(loc):
    """Mã toà từ phòng học: 'D3-401' -> 'D3'; 'Phòng 103, tầng 1, toà nhà B1 và MS Teams' -> 'B1'. Không rõ -> None."""
    import unicodedata
    s = unicodedata.normalize('NFD', str(loc or '').upper()).encode('ascii', 'ignore').decode().replace('Đ', 'D')
    if re.match(r'\s*(SVD|SAN\s*VAN\s*DONG)', s): return 'SVD'
    m = (re.search(r'(?:TOA\s*NHA|NHA|TOA)\s*([A-Z]{1,2}\d{1,2}[A-Z]?)', s) or re.search(r'\b([A-Z]{1,2}\d{0,2}[A-Z]?)-\d{2,4}\b', s)
         or re.search(r'^\s*([A-D]\d{1,2}[A-Z]?)\b', s))
    return m.group(1) if m else None


def target(code):
    """Tâm toà (vĩ độ, kinh độ) theo bản đồ khuôn viên (ưu tiên toà của trường). Không có -> None."""
    if not code: return None
    try: p = json.loads(PLAN.read_text(encoding='utf-8'))
    except Exception: return None
    if code == 'SVD':   # sân vận động: tâm vùng sân trên bản đồ
        sv = next((g for g in p.get('san', []) if 'vận động' in str(g.get('n', '')).lower()), None)
        if not sv: return None
        t = {'k': 'SVD', 'c': [sum(q[0] for q in sv['p']) / len(sv['p']), sum(q[1] for q in sv['p']) / len(sv['p'])]}
    else:
        ts = [t for t in p.get('toa', []) if str(t.get('k', '')).upper() == code.upper()]
        if not ts: return None
        t = sorted(ts, key=lambda t: -(t.get('h') or 0))[0]
    x, y = t['c']
    return {'lat': round(N - y / p['h'] * (N - S), 6), 'lon': round(W_ + x / p['w'] * (E - W_), 6), 'r': RADIUS_M, 'toa': t['k']}


def _cid(c): return f"cls|{c.get('id')}|{str(c.get('start'))[:16]}"


def load():
    try: return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception: return {}


def spared(cid, st=None):
    """'moved' | 'arrived' | None."""
    return ((st if st is not None else load()).get(cid) or {}).get('spared')


def plan(events, now=None):
    """Điện thoại hỏi mỗi phút: đang trong 15 phút trước buổi trực tiếp nào? -> {'id', 'start', 'target', 'done'} hoặc {'id': None}."""
    now = now or dt.datetime.now(TZ)
    for c in offline_classes(events, now.date().isoformat()):
        s = dt.datetime.fromisoformat(c['start']).astimezone(TZ)
        left = (s - now).total_seconds() / 60
        if 0 < left <= PREP_MIN:
            cid = _cid(c)
            return {'id': cid, 'start': s.isoformat(timespec='minutes'), 'left': int(left + 0.999), 'target': target(building(c.get('location'))),
                    'done': bool(spared(cid))}
    return {'id': None}


def check(body, now=None):
    """Điện thoại báo kết quả 1 lần kiểm: {'id', 'moved': bool, 'at': bool, 'left': phút}. Chỉ lưu cờ, không có toạ độ."""
    now = now or dt.datetime.now(TZ)
    cid = str(body.get('id') or '')
    if not cid.startswith('cls|'): return {'ok': False}
    moved, at = bool(body.get('moved')), bool(body.get('at'))
    with _lock:
        st = load()
        for k in [k for k, v in st.items() if (v.get('day') or '') < (now - dt.timedelta(days=7)).date().isoformat()]: st.pop(k)   # giữ 7 ngày
        x = st.setdefault(cid, {'day': now.date().isoformat(), 'checks': [], 'spared': None})
        x['checks'].append({'phut': body.get('left'), 'khac_cho': moved, 'toi_toa': at, 'luc': now.strftime('%H:%M')})
        x['checks'] = x['checks'][-20:]
        if not x['spared'] and (at or moved): x['spared'] = 'arrived' if at else 'moved'
        STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True, 'spared': x['spared']}
