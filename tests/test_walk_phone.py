# -*- coding: utf-8 -*-
"""(chủ 05/11) Lượt đi bộ iCTSV do app điện thoại gửi về: nhận, gộp theo ngày, không đếm trùng."""
import datetime as dt

import pytest

import walk_phone as P

ms = lambda h, m: int(dt.datetime(2026, 11, 5, h, m, tzinfo=P.TZ).timestamp() * 1000)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(P, 'OUT', tmp_path / 'wp.json')


def test_nhan_luot_gop_theo_ngay_khong_trung():
    run = {'id': '1', 'start': ms(17, 0), 'end': ms(17, 25), 'steps': 2400}
    assert P.receive({'runs': [run], 'at': ms(17, 26), 'active': None})['nhan'] == 1
    assert P.receive({'runs': [run], 'active': None})['nhan'] == 0   # gửi lại (mất mạng) không đếm 2 lần
    P.receive({'runs': [{'id': '2', 'start': ms(18, 0), 'end': ms(18, 10), 'steps': 900}]})
    d = P.days()['2026-11-05']
    assert d['steps'] == 3300 and len(d['runs']) == 2


def test_luot_dang_chay_va_du_lieu_hong():
    P.receive({'runs': [{'id': '3', 'start': ms(9, 0), 'end': ms(8, 0), 'steps': 5}], 'active': {'start': ms(19, 0)}})
    d = P.load()
    assert d['runs'] == {} and d['active']['start'].startswith('2026-11-05T19:00')


def test_luu_chang_duong_va_km():
    rt = [[21.0050, 105.8430, 1], [21.0059, 105.8430, 2]]   # ~100 m về phía bắc
    P.receive({'runs': [{'id': '5', 'start': ms(17, 53), 'end': ms(18, 15), 'steps': 2286, 'route': rt}]})
    r = P.load()['runs']['5']
    assert r['route'] == rt and 0.09 <= r['km'] <= 0.11


def test_khong_co_cam_bien_tinh_0_buoc():
    P.receive({'runs': [{'id': '4', 'start': ms(6, 0), 'end': ms(6, 20), 'steps': -1}]})
    r = P.load()['runs']['4']
    assert r['steps'] == 0 and r['sensor_ok'] is False
