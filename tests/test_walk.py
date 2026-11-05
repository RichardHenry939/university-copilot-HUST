# -*- coding: utf-8 -*-
"""Thể dục (walk.py): luật tăng mục tiêu, tuần thi, khung giờ đi bộ, khoảng học quân sự. Dữ liệu giả, không gọi mạng."""
import datetime as dt

import walk as K

C = dict(K.DEFAULT)
D = dt.date


def week(mon, steps):   # 7 ngày bắt đầu từ thứ Hai `mon`, mỗi ngày `steps` (list)
    return {(mon + dt.timedelta(days=i)).isoformat(): s for i, s in enumerate(steps)}


def test_tuan_dat_7_7_tang_10_phan_tram():
    assert K.target_for(D(2026, 11, 9), week(D(2026, 11, 2), [3000] * 7), set(), C) == 2420


def test_tuan_dat_4_7_giu_nguyen():
    assert K.target_for(D(2026, 11, 9), week(D(2026, 11, 2), [3000] * 4 + [0] * 3), set(), C) == 2200


def test_khong_vuot_10000():
    hist = {}
    for w in range(40): hist.update(week(D(2026, 1, 5) + dt.timedelta(weeks=w), [20000] * 7))
    assert K.target_for(D(2026, 11, 9), hist, set(), C) == 10000


def test_tuan_thi_dung_muc_tuan_thi_va_khong_anh_huong_tuan_sau():
    hist = week(D(2026, 11, 2), [3000] * 7)
    assert K.target_for(D(2026, 11, 3), hist, {'2026-11-08'}, C) == 1200
    assert K.target_for(D(2026, 11, 9), hist, {'2026-11-08'}, C) == 2200   # tuần thi không tính vào luật tăng


def test_khung_gio_tranh_buoi_hoc_va_khong_sau_19h():
    ev = [{'kind': 'Class', 'start': '2026-11-02T06:10:00+07:00', 'end': '2026-11-02T09:10:00+07:00'},
          {'kind': 'Class', 'start': '2026-11-02T16:00:00+07:00', 'end': '2026-11-02T17:45:00+07:00'}]
    s = K.slot(ev, '2026-11-02', 20, C)
    assert s['start'] == '2026-11-02T17:45+07:00' and not s['indoor']
    busy = [{'kind': 'Class', 'start': '2026-11-03T06:00:00+07:00', 'end': '2026-11-03T08:00:00+07:00'},
            {'kind': 'Class', 'start': '2026-11-03T17:00:00+07:00', 'end': '2026-11-03T19:00:00+07:00'}]
    assert K.slot(busy, '2026-11-03', 20, C)['indoor'] is True


def test_hoc_quan_su_gom_dai_lien_nhau():
    ev = [{'title': 'MIL1240 · x', 'start': d + 'T06:45:00+07:00'} for d in ('2026-11-09', '2026-11-12', '2026-11-13', '2026-11-16', '2026-11-19', '2026-11-20', '2026-11-23', '2026-11-26', '2026-11-27')]
    assert K.military(ev, '2026-11-15') == {'active': True, 'from': '2026-11-09', 'to': '2026-11-27'}
    assert K.military(ev, '2026-11-02')['active'] is False


def test_hom_nay_khong_xep_vao_khung_da_qua():
    now = dt.datetime(2026, 11, 2, 9, 0, tzinfo=K.TZ)
    assert K.slot([], '2026-11-02', 20, C, after=now)['start'] == '2026-11-02T17:00+07:00'
    late = dt.datetime(2026, 11, 2, 20, 0, tzinfo=K.TZ)
    assert K.slot([], '2026-11-02', 20, C, after=late)['indoor'] is True


# (v1.00.56, chủ 03/11) chưa đọc được app sau khung thì KHÔNG dời khung (trước đây máy ảo chết -> 0 bước -> khung trượt mãi)
def _tz(h, m): return dt.datetime(2026, 11, 3, h, m, tzinfo=K.TZ)
SL = {'start': '2026-11-03T17:00+07:00', 'end': '2026-11-03T17:20+07:00'}


def test_chua_co_khung_thi_xep_moi():
    assert K.need_new_slot(None, _tz(15, 0), None)


def test_khung_chua_het_thi_giu():
    assert not K.need_new_slot(SL, _tz(17, 10), '2026-11-03T17:15:00')


def test_het_khung_ma_chua_doc_app_sau_khung_thi_giu():
    assert not K.need_new_slot(SL, _tz(17, 45), '2026-11-02T21:32:43')
    assert not K.need_new_slot(SL, _tz(17, 45), None)


def test_doc_app_hong_qua_90_phut_van_doi_khung():   # (chủ 05/11) khung 6h kẹt cả ngày vì không đọc được app
    assert K.need_new_slot(SL, _tz(18, 50), '2026-11-02T21:32:43')
    assert K.need_new_slot(SL, _tz(18, 50), None)


def test_het_khung_da_doc_app_sau_khung_thi_xep_lai():
    assert K.need_new_slot(SL, _tz(17, 45), '2026-11-03T17:23:00')
