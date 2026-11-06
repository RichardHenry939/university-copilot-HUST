# -*- coding: utf-8 -*-
"""(v1.00.49, chủ 02/11; v1.00.65 chủ 05/11: ngủ trưa linh hoạt) Ngủ trưa 2 giờ, mặc định 13:00–15:00.

Buổi học / thi chen vào 13:00–15:00 -> KHÔNG cắt ngắn nữa mà DỜI cả khung sang chỗ trống gần nhất (window()): không chồng buổi học / thi
(xanh biển), không chồng giờ ăn, trong 08:00–18:00, bước 15 phút, chọn |giờ bắt đầu − 13:00| nhỏ nhất (bằng nhau thì sớm hơn).
Không còn chỗ thì như cũ: buổi học / thi chiếm chỗ nào thì ngủ trưa mất đúng chỗ đó.
Đồng hồ 24 giờ là nguồn duy nhất: phần tô vàng = phần bị khoá.
UC ghi tín hiệu school/nap.json mỗi phút: {"date", "at", "spans": MỌI đoạn vàng hôm nay (đêm 00–06, ngủ trưa, đêm 22–24, đã trừ
buổi học / thi), "nap_spans": riêng phần ngủ trưa (cho đồng hồ), "why"}.
Khoá giờ ngủ (chạy riêng, chỉ ĐỌC file này) khoá đúng các đoạn đó.
An toàn: không có file / file cũ quá 10 phút (UC tắt) -> khoá đêm cố định 22–6h như cũ, không khoá trưa.
Lịch xét = lịch UC đang hiện: qldt/Notion + lịch thi + đổi lịch Teams (Teams đứng đầu).
"""
import datetime as dt, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'nap.json'
TZ = dt.timezone(dt.timedelta(hours=7))
NAP = ('13:00', '15:00')
NAP_LEN = 120
STEP = 15
RANGE = ('08:00', '18:00')   # khung ngủ trưa dời được trong khoảng này (khoá trưa cũng chỉ nhận trong khoảng này)
LUNCH = ('12:00', '13:00')
DINNER = ('19:00', '20:00')
DINNER_CAMP = ('17:30', '18:30')   # đi tắt: giờ ăn chép lại lần nữa (focus_rules.MEALS, ui); sửa lịch ăn thì sửa cả ba


def events(post):
    import timetable
    ev = list(timetable.get(post).get('events') or [])
    try:
        import fami; ev += fami.exam_events()
    except Exception as e: print('nap exams:', e)
    try:
        import teams_overrides; ev = teams_overrides.apply(ev)
    except Exception as e: print('nap teams:', e)
    return ev


NIGHT = (('00:00', '06:00'), ('22:00', '24:00'))
YELLOW = (NIGHT[0], NAP, NIGHT[1])   # mọi phần vàng của đồng hồ trong 1 ngày: đêm + ngủ trưa

# (chủ 05/11) "Tôi đã dậy": ngủ đủ 1 chu kỳ (~90 phút từ lúc vào khung) thì bấm xác nhận -> giờ ngủ trưa kết thúc tại giờ bấm.
# Chỉ nhận từ giờ bắt đầu khung + 90 phút và khi đang trong phần vàng ngủ trưa. Cắt ngay trong spans() nên mọi nơi đọc giờ ngủ trưa (khoá trưa máy tính,
# PhoneLock, đồng hồ, focus_rules, luật giờ trưa của agent qua nap.json) cùng thấy. Không đụng khoá đêm.
WAKE = HERE / 'school' / 'nap_wake.json'
WAKE_AFTER = 90


def _m(hm): return int(hm[:2]) * 60 + int(hm[3:5])


def _hm(m): return f'{m // 60:02d}:{m % 60:02d}'


def _blue(evs, today):
    """Các buổi học / thi hôm nay: [(bắt đầu, kết thúc, tên)]."""
    out = []
    for e in evs:
        st, en = str(e.get('start') or ''), str(e.get('end') or e.get('start') or '')
        if e.get('kind') not in ('Class', 'Exam') or 'T' not in st or st[:10] != today or 'NGHỈ' in str(e.get('title') or ''): continue
        out.append((st[11:16], en[11:16] if en[:10] == today else '24:00', e.get('title')))
    return out


def _camp(today):
    """⛺ Camp hôm nay? Chỉ đọc cache của focus_rules (nap.write làm mới mỗi phút, tối đa 30 phút đọc Notion 1 lần).
    Đi tắt: UC vừa bật, chưa có cache -> coi như ngày thường trong vài giây đầu."""
    try:
        import focus_rules
        return focus_rules._camp['day'] == today and bool(focus_rules._camp['v'])
    except Exception: return False


def window(evs, today, camp=None):
    """Khung ngủ trưa hôm nay -> (bắt đầu, kết thúc, lý do dời). Không dời được thì trả NAP (spans() cắt phần bị chiếm như cũ)."""
    blue = _blue(evs, today)
    hit = [b for b in blue if b[0] < NAP[1] and b[1] > NAP[0]]
    if not hit: return NAP[0], NAP[1], ''
    busy = [(a, b) for a, b, _ in blue] + [LUNCH, DINNER_CAMP if (_camp(today) if camp is None else camp) else DINNER]
    grid = range(_m(RANGE[0]), _m(RANGE[1]) - NAP_LEN + 1, STEP)
    cand = [s for s in grid if not any(_hm(s) < b and _hm(s + NAP_LEN) > a for a, b in busy)]
    if not cand:   # (06/11) giờ học không tròn lưới 15 phút (MI1111 hết 10:05, ví dụ của chủ: ngủ 10:00–12:00): nới cho buổi học lấn < 1 bước; spans() cắt phần lấn
        meals_ = busy[len(blue):]
        lap = lambda s, a, b: max(0, min(s + NAP_LEN, _m(b)) - max(s, _m(a))) if b != '24:00' else max(0, s + NAP_LEN - max(s, _m(a)))
        cand = [s for s in grid if not any(_hm(s) < b and _hm(s + NAP_LEN) > a for a, b in meals_) and all(lap(s, a, b) < STEP for a, b, _ in blue)]
    if not cand: return NAP[0], NAP[1], ''
    s = min(cand, key=lambda s: (abs(s - _m(NAP[0])), s))
    return _hm(s), _hm(s + NAP_LEN), 'Dời ngủ trưa sang ' + f'{_hm(s)}–{_hm(s + NAP_LEN)} vì ' + '; '.join(f'{t} {a}–{b}' for a, b, t in hit)


def woke(today):
    """Giờ bạn xác nhận đã dậy hôm nay ('HH:MM') hoặc None."""
    try:
        d = json.loads(WAKE.read_text(encoding='utf-8'))
        return d['at'] if d.get('date') == today else None
    except Exception: return None


def wake_min(evs, today):
    """Mốc sớm nhất được bấm "Tôi đã dậy": giờ bắt đầu khung ngủ trưa hôm nay + 90 phút."""
    return _hm(_m(window(evs, today)[0]) + WAKE_AFTER)


def can_wake(nap_free, hm, earliest=None):
    """Đang trong phần vàng ngủ trưa và đã tới mốc sớm nhất?"""
    return hm >= (earliest or _hm(_m(NAP[0]) + WAKE_AFTER)) and any(a <= hm < b for a, b in nap_free)


def wake(post, now=None):
    """Ghi 'đã dậy' (bạn tự bấm + Xác nhận trong UC). -> dict trạng thái."""
    now = now or dt.datetime.now(TZ); today, hm = now.date().isoformat(), now.strftime('%H:%M')
    ev = events(post); free, _ = spans(ev, today); earliest = wake_min(ev, today)
    if woke(today): return {'ok': False, 'loi': f'Hôm nay đã xác nhận dậy lúc {woke(today)}.'}
    if not any(a <= hm < b for a, b in free): return {'ok': False, 'loi': 'Không đang trong giờ ngủ trưa.'}
    if not can_wake(free, hm, earliest): return {'ok': False, 'loi': f'Chưa tới {earliest}: ngủ ít nhất 1 chu kỳ đã.'}
    WAKE.parent.mkdir(parents=True, exist_ok=True)
    WAKE.write_text(json.dumps({'date': today, 'at': hm}), encoding='utf-8')
    return {'ok': True, 'at': hm, 'signal': write(post, now)}


def spans(evs, today, base=(NAP,)):
    """(chủ 02/11) đồng hồ 24 giờ không có chỗ cho 2 lịch chồng nhau; chỉ xanh biển (học / thi) đè được vàng.
    (chủ 05/11) khung ngủ trưa dời theo window(); còn chồng (không dời được, đêm) thì phần vàng mất đúng chỗ đó.
    -> (các đoạn vàng còn lại [["13:00","14:00"], ...], lý do: khung đã dời / các buổi đã chiếm chỗ). base = các khung vàng gốc (mặc định chỉ ngủ trưa)."""
    wa, wb, moved = window(evs, today)
    free, took = [[wa, wb] if tuple(b) == NAP else list(b) for b in base], [moved] if moved else []
    for s, t, title in _blue(evs, today):
        if not any(s < b and t > a for a, b in free): continue
        took.append(f"{title} {s}–{t}")
        free = [p for a, b in free for p in ([[a, min(b, s)]] if a < s else []) + ([[max(a, t), b]] if t < b else []) if p[0] < p[1]]
    w = woke(today)
    if w:   # đã dậy: phần vàng trong khung ngủ trưa dừng tại giờ dậy (đêm giữ nguyên)
        free = [[a, min(b, w)] if wa <= a < wb else [a, b] for a, b in free if not (wa <= a < wb and a >= w)]
        free = [p for p in free if p[0] < p[1]]
    return free, took


def decide(evs, today):
    """-> (còn ngủ trưa không, lý do). Giữ cho chỗ gọi cũ."""
    free, took = spans(evs, today)
    return bool(free), '; '.join(took)


def write(post, now=None):
    now = now or dt.datetime.now(TZ); today = now.date().isoformat()
    ev = events(post)
    if post and _blue(ev, today):   # làm mới cache Camp cho window() (chỉ cần khi có buổi học / thi có thể làm dời khung)
        try: __import__('focus_rules').camp_today(post, today)
        except Exception as e: print('nap camp:', e)
    free, took = spans(ev, today, YELLOW)   # SleepLock (chủ 02/11): khoá đúng MỌI phần vàng UC tô, không theo giờ cố định
    nap_free, _ = spans(ev, today)
    # 'at' đổi mỗi lần ghi = nhịp sống: khoá thấy tín hiệu cũ quá 10 phút (UC tắt) thì quay về khoá đêm cố định 22–6h
    d = {'date': today, 'at': now.isoformat(timespec='seconds'), 'spans': free, 'nap': bool(nap_free), 'nap_spans': nap_free, 'why': '; '.join(took),
         'woke': woke(today), 'wake_min': wake_min(ev, today)}   # (05/11) 'woke' = giờ bạn xác nhận đã dậy (nap_spans đã cắt tại đó); None = chưa
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    return d
