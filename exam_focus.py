# -*- coding: utf-8 -*-
"""(v1.00.65, chủ 05/11) Hai ngày cuối trước thi (D-2, D-1): UC tự bật tập trung cả ngày (focus_rules.tick).

Chỉ các kỳ thi môn MI (Toán – Tin), PH (Vật lý), IT (SoICT), EE / ET (SEEE). Không tính MIL, FL, PE và khoa khác.
Nguồn lịch thi: exam_watch.exams() (PDF lịch thi + FAMI, đã bỏ TDTT / QP-AN). Đi tắt: nhận khoa theo TIỀN TỐ mã môn; môn không có
mã trong lịch thi thì không tính (không đoán theo tên).
"""
import datetime as dt, re

DEPTS = re.compile(r'^(MI|PH|IT|EE|ET)\d', re.I)
DAYS_BEFORE = (1, 2)


def _exams(evs=None):
    if evs is None:
        import exam_watch
        evs = exam_watch.exams()
    return [e for e in evs if DEPTS.match(str(e.get('notes') or '').split(' · ')[0].strip())]


def upcoming(today, evs=None):
    """Các kỳ thi thuộc danh sách, gần nhất, nếu hôm nay là D-1 / D-2 của chúng; không phải thì []."""
    d0, near, out = dt.date.fromisoformat(today), None, []
    for e in sorted(_exams(evs), key=lambda e: str(e['start'])):
        day = dt.date.fromisoformat(str(e['start'])[:10])
        if (day - d0).days not in DAYS_BEFORE: continue
        if near is None: near = day
        if day == near: out.append(e)
    return out


def subject(today, evs=None):
    """'Ôn thi: <môn> (<ngày thi>)' nếu hôm nay là ngày trước thi; không phải thì None."""
    ex = upcoming(today, evs)
    if not ex: return None
    names = [re.sub(r'^Thi( GK)?:\s*', '', str(e.get('title') or '')).strip() for e in ex]
    return f"Ôn thi: {', '.join(dict.fromkeys(names))} ({str(ex[0]['start'])[8:10]}/{str(ex[0]['start'])[5:7]})"
