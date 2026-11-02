# -*- coding: utf-8 -*-
"""(v1.00.52, chủ 02/11 tối) Fitness = đi bộ 10000 bước (walk.py, giữ nguyên) + BÀI TẬP TẠI CHỖ do Gemini gợi ý.

Luật của chủ:
- Chỉ cần thảm / sàn nhà (+ một cái ghế, chủ cho phép 02/11 21:25), KHÔNG dụng cụ khác (tạ, dây, xà, tường, bàn...).
- Gọi ĐÚNG TÊN bài (tên tiếng Anh chuẩn để tra YouTube + tên tiếng Việt).
- Mỗi buổi tối đa 20 phút (khởi động + bài chính + giãn cơ).
- Tránh DOMS (đau cơ khởi phát muộn): người mới, khối lượng thấp, chừa 3 lần lặp (không tập tới kiệt sức),
  cùng nhóm cơ nghỉ >= 48 giờ, tăng dần theo tuần.
- Thể trạng: skinny fat (mỡ cao, cơ ít, sức bền / lực yếu) -> ưu tiên sức mạnh toàn thân + giữ thăng bằng, ít nhảy (khớp gối).
Dữ liệu cơ thể: school/fitness_profile.json (chỉ trên máy, thư mục school/ không lên GitHub). Chủ cho phép gửi Gemini khi lập bài
và đưa lên connector (connector cần deploy Firebase riêng — chưa làm). UC chỉ gợi ý tập luyện chung, KHÔNG phải tư vấn y tế.
"""
import datetime as dt, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE = HERE / 'school' / 'fitness_profile.json'
PLANS = HERE / 'school' / 'fitness_plans.json'   # {"YYYY-MM-DD": plan}
TZ = dt.timezone(dt.timedelta(hours=7))
MAX_MIN = 20
MODEL = 'gemini-3.5-flash'
# dụng cụ / chỗ dựa không được dùng (chủ: chỉ thảm + sàn). Bài nào nhắc tới thì loại.
NO_GEAR = re.compile(r'\b(dumbbells?|kettlebells?|barbells?|bands?|resistance|bench|tạ|dây|xà|bar|pull-?ups?|chin-?ups?|box|wall|tường|towel|khăn|bottles?|chai|balls?|bóng|rings?|trx|sofa|couch|bed|giường|table|desk)\b', re.I)
# (chủ 02/11 21:25) ĐƯỢC dùng ghế (nhà có ghế): chair dip, incline push-up lên ghế, step-up lên ghế... không bị loại.
# chỉ xét tên bài + cụm tra YouTube (câu hướng dẫn hay nói "bàn tay", "during"... dễ loại nhầm)


def _load(p, empty):
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return empty


def _save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(x, ensure_ascii=False, indent=1), encoding='utf-8')


def profile():
    return _load(PROFILE, None)


def set_profile(b):
    p = {}
    for k, lo, hi in (('weight_kg', 30, 200), ('height_cm', 120, 230), ('fat_pct', 3, 60), ('muscle_kg', 5, 80)):
        v = float(b.get(k)); assert lo <= v <= hi, f'{k} ngoài khoảng {lo}–{hi}'; p[k] = round(v, 1)
    p['type'] = str(b.get('type') or '')[:40]
    p['at'] = dt.datetime.now(TZ).isoformat(timespec='seconds')
    _save(PROFILE, p); return p


def derived(p):
    if not p: return {}
    h = p['height_cm'] / 100
    fat = p['weight_kg'] * p['fat_pct'] / 100
    return {'bmi': round(p['weight_kg'] / h / h, 1), 'fat_kg': round(fat, 1), 'lean_kg': round(p['weight_kg'] - fat, 1),
            'stride_m': round(0.415 * h, 2), 'steps_per_km': round(1000 / (0.415 * h))}   # bước chân ~41,5% chiều cao


def recent(today, days=7):
    pl = _load(PLANS, {})
    d0 = dt.date.fromisoformat(today)
    return {d: v for d, v in sorted(pl.items()) if 0 < (d0 - dt.date.fromisoformat(d)).days <= days}


def prompt(p, today, hist, walk_steps):
    d = derived(p)
    past = '\n'.join(f"- {k}: nhóm cơ {', '.join(v.get('focus') or [])}; bài {', '.join(x['name_en'] for x in v.get('main', []))}"
                     f"{' (ĐÃ TẬP, cảm nhận: ' + str(v.get('feedback')) + ')' if v.get('done') else ' (chưa tập)'}" for k, v in hist.items()) or '- (chưa có buổi nào: đây là tuần đầu)'
    return f"""Bạn là huấn luyện viên thể lực cho người MỚI BẮT ĐẦU. Lập MỘT buổi tập hôm nay ({today}) cho một sinh viên.
Số đo: {p['weight_kg']} kg, {p['height_cm']} cm, BMI {d['bmi']}, mỡ ~{p['fat_pct']}% (~{d['fat_kg']} kg), cơ ~{p['muscle_kg']} kg. Thể trạng: {p.get('type')}
(bên ngoài bình thường nhưng ít cơ, nhiều mỡ, lực và sức bền yếu). Hôm nay đã đi bộ ~{walk_steps} bước (đi bộ là phần riêng, không tính vào buổi này).
RÀNG BUỘC BẮT BUỘC:
1. CHỈ trọng lượng cơ thể, trên thảm hoặc sàn nhà, cùng lắm thêm MỘT CÁI GHẾ chắc chắn (được: chair dip, incline push-up lên ghế, step-up lên ghế).
   CẤM mọi dụng cụ / chỗ dựa khác: bàn, tường, giường, sofa, khăn, tạ, dây, xà, bóng.
2. Tổng thời gian <= {MAX_MIN} phút, gồm khởi động ~3 phút + bài chính + giãn cơ ~3 phút. Tính cả thời gian nghỉ.
3. Tránh DOMS: người mới -> 2 hiệp mỗi bài, dừng khi còn sức làm thêm ~3 lần (RIR 3), nhịp chậm có kiểm soát, KHÔNG tập tới kiệt sức,
   ít bật nhảy (bảo vệ gối). Nhóm cơ đã tập trong 48 giờ qua thì hôm nay để nghỉ (chọn nhóm khác). Tăng dần rất chậm theo tuần.
4. MỤC TIÊU: TĂNG CƠ là chính, giảm mỡ đi kèm (body recomposition cho skinny fat), KHÔNG phải chỉ giảm cân. Ưu tiên bài sức mạnh
   toàn thân + cơ lõi, tăng tiến dần (thêm lần lặp / phiên bản khó hơn theo tuần); chọn phiên bản dễ trước (vd knee push-up trước push-up).
5. Mỗi bài ghi TÊN TIẾNG ANH CHUẨN (để người dùng tra YouTube) và tên tiếng Việt; youtube_query là cụm tìm kiếm ngắn tiếng Anh (vd "knee push up form beginner").
Các buổi gần đây:
{past}
Trả về DUY NHẤT JSON: {{"focus": ["nhóm cơ chính"], "warmup": [bài], "main": [bài], "cooldown": [bài], "total_min": số, "note": "1–2 câu lưu ý an toàn"}}
mỗi bài = {{"name_en": "...", "name_vi": "...", "sets": số, "reps": "vd 8 lần hoặc 30 giây", "rest_sec": số, "minutes": số phút ước tính cả nghỉ, "cue": "1 câu kỹ thuật", "youtube_query": "..."}}"""


def clean(plan):
    """Gỡ bài cần dụng cụ, giữ tổng <= MAX_MIN phút (bỏ bớt bài chính cuối nếu thừa)."""
    out = {'focus': list(plan.get('focus') or [])[:4], 'note': str(plan.get('note') or '')[:300], 'dropped': []}
    for part in ('warmup', 'main', 'cooldown'):
        keep = []
        for x in plan.get(part) or []:
            txt = ' '.join(str(x.get(k, '')) for k in ('name_en', 'name_vi', 'youtube_query'))
            if NO_GEAR.search(txt): out['dropped'].append(x.get('name_en')); continue
            try: x['minutes'] = max(0.5, min(10.0, float(x.get('minutes') or 2)))
            except (TypeError, ValueError): x['minutes'] = 2.0
            keep.append({k: x.get(k) for k in ('name_en', 'name_vi', 'sets', 'reps', 'rest_sec', 'minutes', 'cue', 'youtube_query')})
        out[part] = keep
    tot = lambda: sum(x['minutes'] for p in ('warmup', 'main', 'cooldown') for x in out[p])
    while tot() > MAX_MIN and out['main']:
        out['dropped'].append(out['main'].pop()['name_en'])
    out['total_min'] = round(tot(), 1)
    return out


def plan(today=None, refresh=False, walk_steps=0, ask=None):
    """Buổi tập hôm nay (mỗi ngày gọi Gemini 1 lần, lưu lại; refresh=True mới hỏi lại)."""
    today = today or dt.datetime.now(TZ).date().isoformat()
    pl = _load(PLANS, {})
    if pl.get(today) and not refresh: return pl[today]
    p = profile()
    if not p: return {'error': 'Chưa nhập số đo cơ thể'}
    if ask is None:
        import mail_events; ask = lambda q: mail_events.gemini(q, model=MODEL, caller='fitness')
    x = clean(ask(prompt(p, today, recent(today), walk_steps)))
    if not x['main']: return {'error': 'Gemini không trả bài nào dùng được (đã loại bài cần dụng cụ). Thử lại.'}
    x.update(at=dt.datetime.now(TZ).isoformat(timespec='seconds'), done=False)
    pl[today] = x; _save(PLANS, pl); return x


def mark_done(today, feedback=''):
    pl = _load(PLANS, {})
    if today not in pl: raise ValueError('chưa có buổi tập ngày này')
    pl[today].update(done=True, feedback=str(feedback)[:200], doneAt=dt.datetime.now(TZ).isoformat(timespec='seconds'))
    _save(PLANS, pl); return pl[today]


def slot(now=None):
    """Khung 20 phút đầu tiên còn trống hôm nay, sau khung đi bộ (cùng luật xếp với đi bộ: không trùng học / thi)."""
    import walk
    now = (now or dt.datetime.now(TZ)).astimezone(TZ); today = now.date().isoformat()
    w = walk.view(now); ws = w.get('slot') or {}
    after = max(now, dt.datetime.fromisoformat(ws['end'])) if ws.get('end') else now
    return walk.slot(walk._events(), today, MAX_MIN, walk.cfg(), after=after)


def view(now=None):
    p = profile(); today = (now or dt.datetime.now(TZ)).date().isoformat()
    pl = _load(PLANS, {})
    try: sl = slot(now)
    except Exception as e: sl = {'error': str(e)[:200]}
    return {'profile': p, 'derived': derived(p), 'plan': pl.get(today), 'slot': sl, 'maxMin': MAX_MIN, 'today': today}
