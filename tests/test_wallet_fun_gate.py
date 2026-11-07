# -*- coding: utf-8 -*-
"""(chủ 07/11) Lần giải trí đầu ngày dùng ngay (tối đa 20 phút); từ lần 2 phải tích luỹ thêm >= 1/2 số phút lần trước."""
import datetime as dt

import pytest

import wallet as W

at = lambda h, m: dt.datetime(2026, 11, 7, h, m, tzinfo=W.TZ)


def _st(bal=100):
    st = W.empty(); W._add(st, 'focus', bal, at(6, 0), note='nạp thử')
    return st


def test_lan_dau_dung_ngay_toi_da_20p():
    st = _st(); f = W.start_fun(st, at(9, 0))
    assert f['cap'] == 20
    assert W.end_fun(st, at(9, 30))['spent'] == 20


def test_lan_2_can_tich_luy_nua_lan_truoc():
    st = _st(); W.start_fun(st, at(9, 0)); W.end_fun(st, at(9, 20))   # dùng 20 phút -> cần 10
    with pytest.raises(ValueError): W.start_fun(st, at(9, 30))
    W._add(st, 'focus', 5, at(9, 55))
    assert W.fun_gate(st, at(9, 56)) == (False, 5)
    W._add(st, 'focus', 5, at(10, 25))
    assert W.fun_gate(st, at(10, 26)) == (True, 0)
    W.start_fun(st, at(10, 30)); W.end_fun(st, at(10, 36))   # lần 2 dùng 6 phút -> lần 3 cần 3
    assert W.fun_gate(st, at(10, 40)) == (False, 3)


def test_ngay_moi_tinh_lai_tu_dau():
    st = _st(); W.start_fun(st, at(21, 0)); W.end_fun(st, at(21, 20))
    assert W.fun_gate(st, dt.datetime(2026, 11, 8, 7, 0, tzinfo=W.TZ)) == (True, 0)


def test_cong_ngay_moi_khoi_25p_khong_cong_lai_khi_het_phien():   # (chủ 07/11)
    st = W.empty(); t0 = at(8, 0)
    W.start_focus(st, 85, 'x', t0)                     # 3 khối
    W.view(st, t0 + dt.timedelta(minutes=26)); assert W.balance(st) == 5
    W.view(st, t0 + dt.timedelta(minutes=27)); assert W.balance(st) == 5   # không cộng lặp
    W.view(st, t0 + dt.timedelta(minutes=56)); assert W.balance(st) == 10
    W.view(st, t0 + dt.timedelta(minutes=90)); assert st['active'] is None and W.balance(st) == 15
