# -*- coding: utf-8 -*-
"""(chủ 05/11) Số bước theo ĐÚNG các lượt bạn bấm "bắt đầu" trong iCTSV, do app UC trên điện thoại thật gửi về
(android/.../WalkWatch.java: bắt lúc iCTSV bật / tắt dịch vụ đi bộ + hiệu số cảm biến bước chân).
Thay cho việc đọc màn hình iCTSV trong máy ảo (walk_app.py, giữ làm dự phòng). Lưu school/walk_phone.json."""
import datetime as dt, json, threading
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'school' / 'walk_phone.json'
TZ = dt.timezone(dt.timedelta(hours=7))
_lock = threading.Lock()


def load():
    try: return json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return {'runs': {}, 'at': None, 'active': None}


def _km(rt):
    import math
    R, s = 6371.0, 0.0
    for (a1, o1, *_), (a2, o2, *_) in zip(rt, rt[1:]):
        p1, p2 = math.radians(a1), math.radians(a2)
        h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(o2 - o1) / 2) ** 2
        s += 2 * R * math.asin(math.sqrt(h))
    return s


def _iso(ms): return dt.datetime.fromtimestamp(int(ms) / 1000, TZ).isoformat(timespec='seconds')


def receive(body, now=None):
    """body = {"runs": [{"id", "start", "end", "steps"} (ms)], "at": ms, "active": {"start": ms} | null}. -> {'ok', 'nhan'}."""
    now = now or dt.datetime.now(TZ)
    with _lock:
        d = load(); runs = d.setdefault('runs', {}); n = 0
        for r in body.get('runs') or []:
            try:
                rid, st, en, steps = str(r['id']), int(r['start']), int(r['end']), int(r.get('steps', -1))
            except Exception: continue
            if en < st or steps > 100000: continue   # dữ liệu hỏng
            if rid not in runs: n += 1
            runs[rid] = {'start': _iso(st), 'end': _iso(en), 'steps': max(steps, 0), 'sensor_ok': steps >= 0}
            # (chủ 05/11) chặng đường: [[vĩ độ, kinh độ, giây unix], ...] app ghi trong lượt; giữ tối đa 3000 điểm
            rt = [p[:3] for p in (r.get('route') or []) if isinstance(p, list) and len(p) >= 2][:3000]
            if rt: runs[rid]['route'] = rt; runs[rid]['km'] = round(_km(rt), 2)
        a = body.get('active')
        d['active'] = {'start': _iso(a['start'])} if isinstance(a, dict) and a.get('start') else None
        d['at'] = now.isoformat(timespec='seconds')   # nhịp "điện thoại còn báo về" (dùng như lần đọc app)
        d['sensor'] = bool(body.get('sensor'))
        OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True, 'nhan': n}


def days(d=None):
    """{ 'YYYY-MM-DD': {'steps', 'runs': [...]}} theo ngày bắt đầu lượt."""
    d = d or load(); out = {}
    for r in sorted((d.get('runs') or {}).values(), key=lambda r: r['start']):
        x = out.setdefault(r['start'][:10], {'steps': 0, 'runs': []})
        x['steps'] += r['steps']; x['runs'].append(r)
    return out
