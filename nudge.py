# -*- coding: utf-8 -*-
"""(v1.00.44) Thúc đi học bằng thông báo, theo yêu cầu của chủ 01/11.

Nhắc khi: việc hôm nay (Daily Task) còn chưa xong VÀ phút tập trung hôm nay (ví thời gian) chưa đạt tổng giờ dự kiến của các việc.
Không nhắc khi: đang trong giờ học trên lịch, đang tập trung / giải trí, ngày 💤 Rest, ngoài 08:00–21:30 (22:00 là khoá đêm).
Tối đa 1 lần / 60 phút. Nhắc KHÔNG khoá gì: khoá chỉ bật khi chủ bắt đầu phiên tập trung (wallet.py).
Trạng thái: school/nudge.json (lần nhắc cuối).
"""
import datetime as dt, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / 'school' / 'nudge.json'
TZ = dt.timezone(dt.timedelta(hours=7))
FROM, TO = dt.time(8, 0), dt.time(21, 30)
EVERY_MIN = 60


def in_class(classes, now):
    for e in classes or []:
        if e.get('kind') not in ('Class', 'Exam') or 'T' not in (e.get('start') or ''): continue
        try:
            a, b = dt.datetime.fromisoformat(e['start']), dt.datetime.fromisoformat(e.get('end') or e['start'])
        except ValueError: continue
        if a <= now <= b: return True
    return False


def _quiet(now, busy, in_cls, last):
    t = now.astimezone(TZ).time()
    if not (FROM <= t < TO) or busy or in_cls: return True
    return bool(last and (now - last).total_seconds() < EVERY_MIN * 60)


def decide(now, day, focus_min, busy, in_class, last):
    """-> {'title', 'text'} hoặc None. day = kết quả daymode.today_view (items, planHours, mode)."""
    if _quiet(now, busy, in_class, last) or not day or day.get('mode') == 'Rest': return None
    open_ = [x for x in day.get('items') or [] if x.get('status') != 'Done']
    target = int(round(float(day.get('planHours') or 0) * 60))
    if not open_ or focus_min >= target: return None
    first = open_[0].get('task') or ''
    return {'title': f'Còn {len(open_)} việc hôm nay · mới tập trung {focus_min}/{target} phút',
            'text': (f'Việc đầu: {first[:80]}. ' if first else '') + 'Mở UC, bật phiên tập trung để làm (bật là khoá mạng xã hội).'}


def _last():
    try: return dt.datetime.fromisoformat(json.loads(STATE.read_text(encoding='utf-8'))['last'])
    except Exception: return None


def run(post, classes, send, now=None):
    """Gọi mỗi phút từ vòng cảnh báo của UC. Kiểm điều kiện rẻ trước; chỉ đọc Notion khi tới lượt có thể nhắc."""
    now = now or dt.datetime.now(TZ)
    import wallet
    with wallet.lock:
        st = wallet.load(); v = wallet.view(st, now)
    busy, in_cls, last = v['active'] is not None, in_class(classes, now), _last()
    if _quiet(now, busy, in_cls, last): return None
    import daymode
    r = decide(now, daymode.today_view(post), v['stats']['ngay']['focus_min'], busy, in_cls, last)
    if r:
        send(r['title'], r['text'])
        STATE.write_text(json.dumps({'last': now.isoformat(timespec='seconds')}), encoding='utf-8')
    return r
