# -*- coding: utf-8 -*-
"""(chủ 05/11) "Tôi đã dậy": chỉ từ 14:30, chỉ trong giờ ngủ trưa; cắt phần vàng ngủ trưa tại giờ dậy, đêm giữ nguyên."""
import datetime as dt

import pytest

import nap as N

D = '2026-11-05'
at = lambda h, m: dt.datetime(2026, 11, 5, h, m, tzinfo=N.TZ)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(N, 'WAKE', tmp_path / 'wake.json')
    monkeypatch.setattr(N, 'OUT', tmp_path / 'nap.json')
    monkeypatch.setattr(N, 'events', lambda post: [])


def test_truoc_1430_khong_nhan(env):
    r = N.wake(None, at(14, 10))
    assert not r['ok'] and N.woke(D) is None


def test_1435_cat_gio_ngu_trua_giu_dem(env):
    r = N.wake(None, at(14, 35))
    assert r['ok'] and r['at'] == '14:35'
    assert r['signal']['nap_spans'] == [['13:00', '14:35']]
    assert r['signal']['spans'] == [['00:00', '06:00'], ['13:00', '14:35'], ['22:00', '24:00']]
    assert r['signal']['woke'] == '14:35'
    assert not N.wake(None, at(14, 40))['ok']   # một lần mỗi ngày


def test_ngoai_gio_ngu_trua_khong_nhan(env):
    assert not N.wake(None, at(15, 5))['ok']


def test_buoi_hoc_chiem_nap(env, monkeypatch):
    ev = [{'kind': 'Class', 'title': 'Lớp', 'start': D + 'T14:00:00+07:00', 'end': D + 'T16:00:00+07:00'}]
    monkeypatch.setattr(N, 'events', lambda post: ev)
    assert not N.wake(None, at(14, 45))['ok']   # 14:00–15:00 là giờ học, không còn giờ ngủ để dậy


def test_tin_hieu_ngay_cu_khong_tinh(env):
    N.WAKE.write_text('{"date": "2026-11-04", "at": "14:31"}', encoding='utf-8')
    assert N.spans([], D)[0] == [['13:00', '15:00']]
