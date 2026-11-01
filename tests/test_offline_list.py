# -*- coding: utf-8 -*-
"""Đối chiếu MSSV với danh sách học offline (offline_list.py, v1.00.42 W3): dữ liệu giả, MSSV giả, không gọi mạng."""
import offline_list as O

ROWS = [['DANH SÁCH BUỔI HỌC OFFLINE (tiêu đề lớn)', '', ''],
        ['MSSV', 'Họ tên', 'Buổi học offline'],
        ['299999991', 'A', 'B1: 10/09/2026, B7: 29/10/2026'],
        ['299999992', 'B', 'B2: 17/09/2026']]
ROWS = ROWS[1:]   # hàng tiêu đề thật là hàng đầu của bảng CSV


def test_tim_dung_buoi_cua_minh_va_tat_ca_buoi():
    r = O.match(ROWS, '299999991')
    assert r['ok'] and r['found'] and r['mine'] == {1: '2026-09-10', 7: '2026-10-29'}
    assert r['all'] == {1: '2026-09-10', 7: '2026-10-29', 2: '2026-09-17'}


def test_khong_co_ten_thi_moi_buoi_la_online():
    r = O.match(ROWS, '299999999')
    assert r['ok'] and not r['found'] and r['mine'] == {}


def test_bang_khong_co_cot_buoi_thi_bao_loi_khong_doan():
    assert not O.match([['MSSV', 'Họ tên']], '299999991')['ok']


def test_buoi_doi_ngay_nhan_qua_nhan_buoi_hoc():
    st = {'ok': True, 'all': {'1': '2026-09-10', '7': '2026-10-29'}, 'mine': {'7': '2026-10-29'}}
    moved = {'kind': 'Class', 'title': 'IT2000 · Nhập môn CNTT và TT · Teams đổi lịch', 'start': '2026-11-01T09:00:00+07:00', 'label': 'Buổi học 7'}
    other = {'kind': 'Class', 'title': 'IT2000 · Nhập môn CNTT và TT · LT+BT · Online', 'start': '2026-09-10T16:00:00+07:00'}
    lab = {'kind': 'Class', 'title': 'IT2000 · Nhập môn CNTT và TT · Thực nghiệm', 'start': '2026-09-10T12:30:00+07:00'}
    assert O.verdict(moved, st) == ('truc_tiep', 7)
    assert O.verdict(other, st) == ('online', 1)
    assert O.verdict(lab, st) is None
    out = O.annotate([moved], st)
    assert out[0]['attend'] == 'truc_tiep' and 'TRỰC TIẾP' in out[0]['notes']
