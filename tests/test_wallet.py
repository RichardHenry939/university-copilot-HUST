# -*- coding: utf-8 -*-
"""Ví thời gian (wallet.py, v1.00.42 W8): quy tắc cộng / trừ / thu hồi, chia khối 25 + 5. Không gọi mạng, không ghi file thật."""
import datetime as dt

import pytest

import wallet as W

T0 = dt.datetime(2026, 11, 2, 8, 0, tzinfo=W.TZ)
m = lambda k: dt.timedelta(minutes=k)


def new():
    return W.empty()


def test_chia_khoi_25_5():
    assert W.plan(60) == [('focus', 25), ('break', 5), ('focus', 25), ('break', 5)]
    assert W.plan(25) == [('focus', 25)]
    assert W.plan(40) == [('focus', 25), ('break', 5), ('focus', 10)]


def test_moi_khoi_25_phut_tron_cong_5_phut():
    st = new()
    W.start_focus(st, 60, 'MI1111', T0)
    r = W.end_focus(st, T0 + m(60))
    assert r['blocks'] == 2 and W.balance(st) == 10
    assert st['active'] is None and st['sessions'][0]['focus_min'] == 50


def test_ket_thuc_som_chi_tinh_khoi_da_tron():
    st = new()
    W.start_focus(st, 100, '', T0)
    r = W.end_focus(st, T0 + m(40))          # khối 1 trọn (25), khối 2 mới 10 phút
    assert r['blocks'] == 1 and W.balance(st) == 5
    assert st['sessions'][0]['focus_min'] == 35


def test_tam_dung_khong_tinh_thoi_gian():
    st = new()
    W.start_focus(st, 25, '', T0)
    W.pause(st, T0 + m(10))
    W.resume(st, T0 + m(40))                 # dừng 30 phút
    assert W.progress(st, T0 + m(50))['blocks_done'] == 0
    assert W.end_focus(st, T0 + m(55))['blocks'] == 1


def test_phien_het_gio_tu_ket_thuc_khi_xem():
    st = new()
    W.start_focus(st, 30, '', T0)
    v = W.view(st, T0 + m(31))
    assert v['active'] is None and v['balance'] == 5


def test_hoan_tat_han_cong_15_mot_lan_va_thu_hoi_dung_phan_da_cong():
    st = new()
    W.credit_deadline(st, 'dl-1', 'Quiz 08', T0)
    W.credit_deadline(st, 'dl-1', 'Quiz 08', T0)   # bấm lại không cộng thêm
    assert W.balance(st) == 15
    W.revoke_deadline(st, 'dl-1', T0 + m(5))
    assert W.balance(st) == 0
    W.revoke_deadline(st, 'dl-1', T0 + m(6))       # thu hồi lại không trừ thêm
    assert W.balance(st) == 0
    W.credit_deadline(st, 'dl-1', 'Quiz 08', T0 + m(7))   # hoàn tất lại sau khi bỏ: cộng lại
    assert W.balance(st) == 15


def test_giai_tri_tru_dung_so_phut_va_khong_vuot_so_du():
    st = new()
    W.credit_deadline(st, 'dl-1', 'x', T0)          # 15 phút
    W.start_fun(st, T0)
    W.end_fun(st, T0 + m(9) + dt.timedelta(seconds=10))   # 9 phút 10 giây -> làm tròn lên 10
    assert W.balance(st) == 5
    W.start_fun(st, T0 + m(20))
    v = W.view(st, T0 + m(40))                      # quá số dư -> tự dừng, chỉ trừ 5
    assert v['active'] is None and v['balance'] == 0


def test_khong_giai_tri_khi_vi_rong_va_khong_chay_hai_phien():
    st = new()
    with pytest.raises(ValueError):
        W.start_fun(st, T0)
    W.start_focus(st, 25, '', T0)
    with pytest.raises(ValueError):
        W.start_focus(st, 25, '', T0)


def test_thong_ke_ngay_tuan_thang():
    st = new()
    W.start_focus(st, 30, '', T0)
    W.end_focus(st, T0 + m(30))
    W.credit_deadline(st, 'dl-2', 'x', T0 + m(31))
    s = W.stats(st, T0 + m(60))
    assert s['ngay']['focus_min'] == 25 and s['ngay']['earned'] == 20
    assert s['tuan']['focus_min'] == 25 and s['thang']['blocks'] == 1
    assert W.stats(st, T0 + dt.timedelta(days=8))['tuan']['focus_min'] == 0


def test_tin_hieu_chi_ghi_khi_chu_da_dat_cau_hinh(tmp_path, monkeypatch):
    monkeypatch.setattr(W, 'SIGNAL_CFG', tmp_path / 'khong-co.json')
    st = new()
    W.start_focus(st, 25, '', T0)          # không có cấu hình -> không ghi gì, không lỗi
    target = tmp_path / 'sig.json'
    cfg = tmp_path / 'cfg.json'
    cfg.write_text('{"path": "%s"}' % str(target).replace('\\', '/'), encoding='utf-8')
    monkeypatch.setattr(W, 'SIGNAL_CFG', cfg)
    W.end_focus(st, T0 + m(25))
    assert '"focus": false' in target.read_text(encoding='utf-8')
