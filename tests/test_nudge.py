# -*- coding: utf-8 -*-
"""Thúc đi học (nudge.py, v1.00.44): chỉ quyết định có nhắc hay không và nội dung; không gửi thật, không gọi Notion."""
import datetime as dt

import nudge as N

TZ = N.TZ
NOW = dt.datetime(2026, 11, 2, 14, 0, tzinfo=TZ)
DAY = {'mode': 'Bình thường', 'planHours': 4, 'items': [
    {'task': 'Ôn Giải tích', 'status': 'Not started', 'est': 2},
    {'task': 'Bài Đại số', 'status': 'Not started', 'est': 2},
    {'task': 'Đọc slide', 'status': 'Done', 'est': 0}]}


def d(**k):
    base = dict(now=NOW, day=DAY, focus_min=0, busy=False, in_class=False, last=None)
    base.update(k)
    return N.decide(**base)


def test_con_viec_va_chua_tap_trung_du_thi_nhac():
    r = d()
    assert r and '2 việc' in r['title'] and '0/240 phút' in r['title'] and 'Ôn Giải tích' in r['text']


def test_tap_trung_du_tong_du_kien_thi_thoi():
    assert d(focus_min=240) is None


def test_xong_het_viec_thi_thoi():
    day = dict(DAY, items=[dict(x, status='Done') for x in DAY['items']])
    assert d(day=day) is None


def test_khong_nhac_khi_dang_hoc_dang_tap_trung_hay_ngay_nghi():
    assert d(in_class=True) is None
    assert d(busy=True) is None
    assert d(day=dict(DAY, mode='Rest')) is None


def test_ngoai_khung_gio_va_moi_nhac_xong_thi_im():
    assert d(now=NOW.replace(hour=7, minute=30)) is None
    assert d(now=NOW.replace(hour=21, minute=45)) is None
    assert d(last=NOW - dt.timedelta(minutes=30)) is None
    assert d(last=NOW - dt.timedelta(minutes=61)) is not None


def test_dang_trong_gio_hoc_theo_lich():
    cls = [{'kind': 'Class', 'start': '2026-11-02T13:30:00+07:00', 'end': '2026-11-02T15:00:00+07:00', 'title': 'x'}]
    assert N.in_class(cls, NOW) and not N.in_class(cls, NOW.replace(hour=16))
