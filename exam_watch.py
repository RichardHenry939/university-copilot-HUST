# -*- coding: utf-8 -*-
"""(v1.00.49, chủ yêu cầu 02/11) Lịch thi -> báo động ngay + việc "Ôn thi định kỳ hằng ngày môn X" mỗi ngày tới ngày thi.

- exams(): lịch thi (fami.exam_events: PDF lịch thi + FAMI), BỎ môn thể dục thể thao (mã PE...) và quốc phòng an ninh
  (mã MIL..., tên có Quốc phòng / GDQP / An ninh / Giáo dục thể chất).
  Đi tắt: nhận diện miễn bằng LUẬT mã / tên môn, chưa gọi Gemini / AI local. Gặp môn tên lạ bị lọt / bị bỏ nhầm thì
  thêm từ khoá vào EXEMPT_NAME; khi nguồn lịch thi có môn không mã, không tên rõ mới cần tới AI.
- review(today): mỗi môn thi chưa tới ngày thi -> 1 việc hôm nay, KHÔNG tắt được (UI không có nút bỏ / hoàn tất).
  Ngoại lệ chủ tự cho: bình thường UC không tạo nhiệm vụ học tập; đây chỉ là lời nhắc ôn, không dạy, không làm bài.
- tick(send): lịch thi mới (chưa từng thấy) -> mỗi môn 1 tin riêng (tiêu đề = tên môn + giờ thi), lưu school/exam_seen.json.
"""
import datetime as dt, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEN = HERE / 'school' / 'exam_seen.json'
TZ = dt.timezone(dt.timedelta(hours=7))
EXEMPT_CODE = re.compile(r'^(PE|MIL)\d', re.I)
EXEMPT_NAME = re.compile(r'quốc phòng|gdqp|an ninh|thể dục|thể chất|tdtt', re.I)


def _code(e): return (str(e.get('notes') or '').split(' · ')[0] or '').strip()


def _name(e): return re.sub(r'^Thi( GK)?:\s*', '', str(e.get('title') or '')).strip()


def exempt(e): return bool(EXEMPT_CODE.match(_code(e)) or EXEMPT_NAME.search(_name(e)))


def exams(now=None):
    import fami
    now = now or dt.datetime.now(TZ)
    out = [e for e in fami.exam_events() if not exempt(e)]
    return sorted(out, key=lambda e: e['start'])


def review(today=None, now=None):
    """Việc ôn thi của hôm nay: mỗi môn có lịch thi từ hôm nay trở đi (gộp nhiều lịch thi cùng môn, lấy buổi gần nhất)."""
    today = today or dt.datetime.now(TZ).date().isoformat()
    first = {}
    for e in exams(now):
        if e['start'][:10] < today: continue
        k = _code(e) or _name(e)
        if k not in first: first[k] = e
    return [{'kind': 'Review', 'title': f"Ôn thi định kỳ hằng ngày môn {_name(e)}" + (f" ({_code(e)})" if _code(e) else ''),
             'start': today, 'exam': e['start'], 'examLocation': e.get('location') or '', 'course': _code(e), 'locked': True}
            for e in sorted(first.values(), key=lambda e: e['start'])]


def tick(send, now=None):
    """Lịch thi chưa từng thấy -> báo động, mỗi môn 1 tin. Lần chạy đầu (chưa có file) cũng báo: chủ muốn biết ngay."""
    import alerts
    try: seen = set(json.loads(SEEN.read_text(encoding='utf-8')))
    except Exception: seen = set()
    sent = []
    for e in exams(now):
        key = f"{_code(e) or _name(e)}|{e['start']}"
        if key in seen: continue
        w = dt.datetime.fromisoformat(e['start']) if 'T' in e['start'] else None
        title = 'Lịch thi: ' + (alerts.head(_name(e) + (f" · {_code(e)}" if _code(e) else ''), w, 'thi') if w else f"{_name(e)} — ngày {e['start']}")
        send(title, (f"Phòng {e['location']}" if e.get('location') else 'Chưa rõ phòng') + ' · từ hôm nay UC thêm việc "Ôn thi định kỳ hằng ngày" tới ngày thi.')
        seen.add(key); sent.append(key)
    if sent:
        SEEN.parent.mkdir(parents=True, exist_ok=True); SEEN.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding='utf-8')
    return sent
