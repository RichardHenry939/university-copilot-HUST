# -*- coding: utf-8 -*-
"""(v1.00.45 tiếp, 01/11 tối) Thể dục thể thao: đi bộ hằng ngày gắn giải "10000 bước chân" của CTSV. CHỈ ĐỌC dữ liệu trường.

Đặc tả: bản đặc tả module Đi bộ của chủ (plans/spec-walk-module.md, chỉ có ở máy chủ). Phần đã làm trong bản này:
- Số bước = km CTSV × bước/km (walk_ctsv.STEPS_PER_KM), như cách trường quy đổi.
- Mục tiêu ngày: bắt đầu 2200 bước; hết mỗi tuần (từ thứ Hai) đạt >= 5/7 ngày -> tuần sau +10%, không vượt 10000.
  Tuần có thi -> mục tiêu tuần thi 1200, tuần đó không tính vào luật tăng. Trần ngày = mục tiêu × 1,3.
- Giờ đi: chỉ trong 6–8h và 17–19h, ưu tiên nửa đầu (6–7h, 17–18h, tránh cao điểm), không chen giờ học/thi;
  hết chỗ -> gợi ý đi trong nhà. Không bao giờ sau 19h.
- Học quân sự (các buổi MIL liền nhau trên thời khoá biểu): KHÔNG nhắc đi hằng ngày, vẫn hiện số bước.
CHƯA làm (đi tắt, ghi rõ): check-in đau chân buổi sáng (luật giữ/giảm khi đau), luật nắng nóng/AQI (chưa chọn nguồn),
nạp đơn vị ví khi đạt mục tiêu (chủ chưa chốt 1 đơn vị = bao nhiêu phút). Làm lại khi chủ chốt các mục đó.
"""
import datetime as dt, json, math
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG_FILE = HERE / 'school' / 'walk_config.json'   # tuỳ chọn: ghi đè các số dưới đây
TZ = dt.timezone(dt.timedelta(hours=7))
DEFAULT = {'start_target_steps': 2200, 'weekly_increase': 0.10, 'daily_cap_ratio': 1.3, 'final_target_steps': 10000,
           'exam_week_target_steps': 1200, 'days_to_increase': 5, 'steps_per_min': 110,
           'windows': [[6, 8], [17, 19]]}   # khung đi bộ ưa thích của chủ; không bao giờ sau 19h


MANUAL = HERE / 'school' / 'walk_manual.json'   # {'YYYY-MM-DD': số bước cả ngày theo app iCTSV, chủ tự nhập}


def manual():
    try: return {k: int(v) for k, v in json.loads(MANUAL.read_text(encoding='utf-8')).items()}
    except Exception: return {}


def set_manual(day, n):
    dt.date.fromisoformat(day); n = int(n)
    if not 0 <= n <= 100000: raise ValueError('Số bước từ 0 đến 100000.')
    m = manual(); m[day] = n
    MANUAL.parent.mkdir(parents=True, exist_ok=True); MANUAL.write_text(json.dumps(m), encoding='utf-8')
    return m


OVERRIDE = HERE / 'school' / 'walk_override.json'   # (v1.00.49) {'YYYY-MM-DD': {'ly_do', 'at', 'by'}}: ngày được xoá khung đỏ


def overrides():
    """Khung thể dục (ĐỎ trên đồng hồ) KHÔNG sửa được trong UC. Cách duy nhất: AI gọi công cụ MCP uc_xoa_the_duc với lý do
    chính đáng (vd đau chân), lệnh về máy qua uc_mcp/push.py -> file này. Luật dùng ghi trong skill uc-assistant."""
    try: return json.loads(OVERRIDE.read_text(encoding='utf-8'))
    except Exception: return {}


def set_override(day, ly_do, at, by='mcp'):
    o = overrides()
    if day in o: return o
    o[day] = {'ly_do': str(ly_do)[:300], 'at': at, 'by': by}
    OVERRIDE.parent.mkdir(parents=True, exist_ok=True); OVERRIDE.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding='utf-8')
    return o


def cfg():
    c = dict(DEFAULT)
    try: c.update(json.loads(CFG_FILE.read_text(encoding='utf-8')))
    except Exception: pass
    return c


def _events():
    try: return json.loads((HERE / 'timetable_cache.json').read_text(encoding='utf-8')).get('events') or []
    except Exception: return []


def _d(s): return str(s or '')[:10]


def military(events, today):
    """Khoảng học quân sự: các ngày có buổi MIL, gom thành dải liền nhau (cho phép hở <= 3 ngày, vd cuối tuần)."""
    days = sorted({_d(e.get('start')) for e in events if str(e.get('title', '')).startswith('MIL')})
    runs, cur = [], None
    for d in days:
        if cur and (dt.date.fromisoformat(d) - dt.date.fromisoformat(cur[1])).days <= 3: cur[1] = d
        else:
            cur = [d, d]; runs.append(cur)
    hit = next((r for r in runs if r[0] <= today <= r[1]), None)
    nxt = next((r for r in runs if r[0] > today), None)
    return {'active': bool(hit), 'from': (hit or nxt or [None, None])[0], 'to': (hit or nxt or [None, None])[1]}


def _monday(d): return d - dt.timedelta(days=d.weekday())


def target_for(day, steps_by_day, exam_days, c=None):
    """Mục tiêu bước của ngày `day` (date). steps_by_day: {'YYYY-MM-DD': số bước}. exam_days: tập ngày có thi."""
    c = c or cfg()
    wk = _monday(day)
    if any(_d(x) and wk <= dt.date.fromisoformat(x) < wk + dt.timedelta(days=7) for x in exam_days):
        return c['exam_week_target_steps']
    known = sorted(steps_by_day)
    if not known: return c['start_target_steps']
    t, w = c['start_target_steps'], _monday(dt.date.fromisoformat(known[0]))
    while w < wk:   # đi qua từng tuần đã hết, áp luật tăng
        days = [w + dt.timedelta(days=i) for i in range(7)]
        exam = any(d.isoformat() in exam_days for d in days)
        if not exam:
            met = sum(1 for d in days if steps_by_day.get(d.isoformat(), 0) >= t)
            if met >= c['days_to_increase']: t = min(c['final_target_steps'], round(t * (1 + c['weekly_increase'])))
        w += dt.timedelta(days=7)
    return max(c['exam_week_target_steps'], min(c['final_target_steps'], t))


def slot(events, today, minutes, c=None, after=None):
    """Khung đi bộ hôm nay: khoảng đầu tiên (theo thứ tự ưu tiên) đủ `minutes` phút không trùng buổi học / thi."""
    c = c or cfg()
    busy = []
    for e in events:
        if _d(e.get('start')) != today or e.get('kind') not in ('Class', 'Exam') or 'T' not in str(e.get('start')): continue
        try: busy.append((dt.datetime.fromisoformat(e['start']), dt.datetime.fromisoformat(e.get('end') or e['start'])))
        except Exception: pass
    d0 = dt.datetime.fromisoformat(today + 'T00:00:00+07:00')
    best = []
    for h0, h1 in c['windows']:   # khung liền (6–8h, 17–19h); đi được vắt qua giữa khung
        w0, w1 = d0 + dt.timedelta(hours=h0), d0 + dt.timedelta(hours=h1)
        t = max(w0, after) if after else w0   # hôm nay: chỉ xếp vào phần khung còn ở phía trước
        for b0, b1 in sorted(busy):
            if b1 <= t or b0 >= w1: continue
            if (b0 - t).total_seconds() >= minutes * 60: break
            t = max(t, b1)
        if (w1 - t).total_seconds() >= minutes * 60:
            best.append((0 if t < w0 + (w1 - w0) / 2 else 1, t))   # luật A: bắt đầu ở nửa đầu (trước cao điểm) được ưu tiên
    if best:
        _, t = min(best, key=lambda x: (x[0], x[1].hour >= 12, x[1]))
        return {'start': t.isoformat(timespec='minutes'), 'end': (t + dt.timedelta(minutes=minutes)).isoformat(timespec='minutes'),
                'indoor': False, 'rush': t.hour in (7, 18)}
    return {'start': None, 'end': None, 'indoor': True, 'rush': False}


def merge_days(ctsv_days, app_days):
    """(v1.00.52, chủ 02/11) Bảng theo ngày: giữ km/bước GIẢI TÍNH của CTSV (ước tính km × 1385) và thêm số THẬT của app
    (appSteps / appKm); ngày chỉ có trong app (vd sau khi đợt giải đóng) vẫn có dòng, km giải tính = 0."""
    rows = {_d(r.get('DayRun')): dict(r) for r in (ctsv_days or [])}
    for d, a in (app_days or {}).items():
        r = rows.setdefault(d, {'DayRun': d + ' 00:00:00', 'Distance': 0, 'km': 0, 'steps': 0})
        r['appSteps'], r['appKm'] = a.get('steps', 0), a.get('km', 0)
    return [rows[d] for d in sorted(rows)]


def view(now=None):
    import walk_ctsv
    now = (now or dt.datetime.now(TZ)).astimezone(TZ); today = now.date().isoformat()
    c, ev, w = cfg(), _events(), walk_ctsv.view()
    # (01/11 tối) CTSV chỉ trả quãng đường GIẢI ghi nhận (có vẻ bỏ lượt chậm hơn ~15 phút/km), không phải tổng cả ngày như app.
    # Tổng cả ngày = max(số chủ nhập theo app, số quy từ CTSV). Số giải ghi nhận vẫn trả riêng (contest).
    contest = {_d(r.get('DayRun')): r.get('steps', 0) for r in (w.get('days') or [])}
    man = manual()
    # (v1.00.49) số THẬT từ app iCTSV (đủ mọi lượt, kể cả lượt chậm giải không tính) — walk_app.py
    import walk_app
    wa = walk_app.load(); app = wa.get('days') or {}
    steps = {d: max(contest.get(d, 0), man.get(d, 0), (app.get(d) or {}).get('steps', 0)) for d in set(contest) | set(man) | set(app)}
    exam_days = {_d(e.get('start')) for e in ev if e.get('kind') == 'Exam'}
    tgt = target_for(now.date(), steps, exam_days, c)
    mil = military(ev, today)
    # (02/11, chủ) chốt khung đi bộ của hôm nay một lần (trước đây tính lại mỗi lần đọc với mốc "bây giờ" -> giờ cứ trượt theo phút).
    # Chỉ tính lại khi chưa có khung hôm nay hoặc khung đã chốt đã qua hẳn.
    sl_file = HERE / 'school' / 'walk_slot.json'
    try: kept = json.loads(sl_file.read_text(encoding='utf-8'))
    except Exception: kept = {}
    sl = kept.get('slot') if kept.get('date') == today else None
    if not sl or (sl.get('end') and dt.datetime.fromisoformat(sl['end']) < now):
        sl = slot(ev, today, max(10, math.ceil(tgt / c['steps_per_min'])), c, after=now)
        try: sl_file.parent.mkdir(parents=True, exist_ok=True); sl_file.write_text(json.dumps({'date': today, 'slot': sl}), encoding='utf-8')
        except Exception: pass
    done = steps.get(today, 0)
    ov = overrides().get(today)
    # (v1.00.49, chủ 02/11) khung đi bộ = ĐỎ trên đồng hồ: chỉ khi có nhắc (không học quân sự), đi ngoài trời, chưa bị AI xoá với lý do chính đáng
    red = bool(mil and not mil['active'] and sl.get('start') and not sl.get('indoor') and not ov)
    extra = {'red': red, 'redCleared': ov, 'contestSteps': contest.get(today, 0), 'manualSteps': man.get(today),
             'appSteps': (app.get(today) or {}).get('steps'), 'app': app, 'appAt': wa.get('at')}
    month = today[:7]; prev = (now.date().replace(day=1) - dt.timedelta(days=1)).isoformat()[:7]
    return {'ok': bool(w.get('ok')), 'at': w.get('at'), 'error': w.get('error'), 'competition': w.get('competition'),
            'myRank': w.get('myRank'), 'top100Km': w.get('top100Km'), 'stepsPerKm': w.get('stepsPerKm'),
            'board': w.get('board') or [],
            'days': merge_days(w.get('days'), app), 'today': today, 'target': tgt, 'cap': round(tgt * c['daily_cap_ratio']),
            'steps': done, 'met': done >= tgt, 'capped': done >= round(tgt * c['daily_cap_ratio']),
            'examWeek': tgt == c['exam_week_target_steps'] and any(_monday(now.date()) <= dt.date.fromisoformat(x) < _monday(now.date()) + dt.timedelta(days=7) for x in exam_days if x),
            'slot': sl, 'military': mil, 'remind': not mil['active'],
            'monthSteps': sum(v for k, v in steps.items() if k.startswith(month)),
            'prevMonthSteps': sum(v for k, v in steps.items() if k.startswith(prev)), **extra}
