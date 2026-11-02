# -*- coding: utf-8 -*-
"""(v1.00.49, chủ 02/11) Ngủ trưa 13:00–15:00 CHỈ khi hôm đó không có buổi học / thi chen vào khung đó.

Đồng hồ 24 giờ là nguồn duy nhất: phần tô vàng = phần bị khoá. Buổi học / thi chiếm chỗ nào thì ngủ trưa mất đúng chỗ đó.
UC ghi tín hiệu school/nap.json mỗi phút: {"date", "at", "spans": MỌI đoạn vàng hôm nay (đêm 00–06, trưa 13–15, đêm 22–24, đã trừ
buổi học / thi), "nap_spans": riêng phần ngủ trưa (cho đồng hồ), "why"}.
SleepLock (hệ thống khoá giờ ngủ, chạy riêng, chỉ ĐỌC file này) khoá đúng các đoạn spans (chỉ trong 22–6h và 13–15h).
An toàn: không có file / file cũ quá 10 phút (UC tắt) -> khoá đêm cố định 22–6h như cũ, không khoá trưa.
Lịch xét = lịch UC đang hiện: qldt/Notion + lịch thi + đổi lịch Teams (Teams đứng đầu).
"""
import datetime as dt, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'nap.json'
TZ = dt.timezone(dt.timedelta(hours=7))
NAP = ('13:00', '15:00')


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


YELLOW = (('00:00', '06:00'), NAP, ('22:00', '24:00'))   # mọi phần vàng của đồng hồ trong 1 ngày: đêm + ngủ trưa


def spans(evs, today, base=(NAP,)):
    """(chủ 02/11) đồng hồ 24 giờ không có chỗ cho 2 lịch chồng nhau; chỉ xanh biển (học / thi) đè được vàng:
    buổi học / thi chiếm chỗ nào thì phần vàng mất đúng chỗ đó.
    -> (các đoạn vàng còn lại [["13:00","14:00"], ...], các buổi đã chiếm chỗ). base = các khung vàng gốc (mặc định chỉ ngủ trưa)."""
    free, took = [list(b) for b in base], []
    for e in evs:
        st, en = str(e.get('start') or ''), str(e.get('end') or e.get('start') or '')
        if e.get('kind') not in ('Class', 'Exam') or 'T' not in st or st[:10] != today or 'NGHỈ' in str(e.get('title') or ''): continue
        s, t = st[11:16], en[11:16] if en[:10] == today else '24:00'
        if not any(s < b and t > a for a, b in free): continue
        took.append(f"{e.get('title')} {s}–{t}")
        free = [p for a, b in free for p in ([[a, min(b, s)]] if a < s else []) + ([[max(a, t), b]] if t < b else []) if p[0] < p[1]]
    return free, took


def decide(evs, today):
    """-> (còn ngủ trưa không, lý do). Giữ cho chỗ gọi cũ."""
    free, took = spans(evs, today)
    return bool(free), '; '.join(took)


def write(post, now=None):
    now = now or dt.datetime.now(TZ); today = now.date().isoformat()
    ev = events(post)
    free, took = spans(ev, today, YELLOW)   # SleepLock (chủ 02/11): khoá đúng MỌI phần vàng UC tô, không theo giờ cố định
    nap_free, _ = spans(ev, today)
    # 'at' đổi mỗi lần ghi = nhịp sống: khoá thấy tín hiệu cũ quá 10 phút (UC tắt) thì quay về khoá đêm cố định 22–6h
    d = {'date': today, 'at': now.isoformat(timespec='seconds'), 'spans': free, 'nap': bool(nap_free), 'nap_spans': nap_free, 'why': '; '.join(took)}
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    return d
