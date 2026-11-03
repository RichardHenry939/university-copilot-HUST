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


def test_moi_viec_mot_thong_bao_rieng_va_tap_trung_rieng():
    # (03/11, chủ) không gộp: 2 việc chưa xong -> 2 tin, mỗi tin 1 việc + "còn X giờ"; phút tập trung là tin thứ 3
    r = d(focus_min=35)
    assert r and len(r) == 3
    a, b, f = r
    assert 'Ôn Giải tích' in a['title'] and 'Bài Đại số' not in a['title'] + a['text']
    assert 'Bài Đại số' in b['title'] and 'Ôn Giải tích' not in b['title'] + b['text']
    assert 'Dự kiến 2 giờ' in a['text'] and 'còn 8 giờ 00 phút' in a['text']   # 14:00 -> 22:00
    assert '35/240 phút' in f['title'] and 'Ôn Giải tích' not in f['title'] + f['text']


def test_viec_khong_uoc_luong_gio_thi_khong_ghi_du_kien():
    day = dict(DAY, items=[{'task': 'Nộp đơn', 'status': 'Not started', 'est': 0}], planHours=1)
    r = d(day=day)
    assert len(r) == 2 and 'Dự kiến' not in r[0]['text'] and 'Nộp đơn' in r[0]['title']


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
