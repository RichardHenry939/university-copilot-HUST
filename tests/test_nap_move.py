# -*- coding: utf-8 -*-
"""(chủ 05/11) Ngủ trưa linh hoạt: buổi học / thi chen vào 13–15h thì DỜI cả khung 2 giờ, không cắt ngắn."""
import datetime as dt

import pytest

import nap as N

D = '2026-11-06'
at = lambda h, m: dt.datetime(2026, 11, 6, h, m, tzinfo=N.TZ)


def lop(a, b, title='Lớp', kind='Class'):
    return {'kind': kind, 'title': title, 'start': f'{D}T{a}:00+07:00', 'end': f'{D}T{b}:00+07:00'}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(N, 'WAKE', tmp_path / 'wake.json')
    monkeypatch.setattr(N, 'OUT', tmp_path / 'nap.json')
    monkeypatch.setattr(N, '_camp', lambda today: False)


def test_khong_co_lop_giu_13_15():
    assert N.window([], D) == ('13:00', '15:00', '')
    assert N.spans([], D) == ([['13:00', '15:00']], [])


def test_lop_ngoai_khung_khong_doi():
    ev = [lop('08:25', '11:45'), lop('15:00', '17:00')]
    assert N.spans(ev, D)[0] == [['13:00', '15:00']]


def test_it1108_12h30_17h30_doi_10_12():   # ví dụ chủ nêu
    ev = [lop('12:30', '17:30', 'IT1108')]
    free, why = N.spans(ev, D)
    assert free == [['10:00', '12:00']]
    assert why and 'IT1108' in why[0] and '10:00–12:00' in why[0]


def test_gio_hoc_lech_luoi_15_phut_van_doi_cat_phan_lan():   # thật ngày 06/11: MI1111 hết 10:05, IT1108 từ 12:30
    ev = [lop('06:45', '08:15', 'MI1141'), lop('08:25', '10:05', 'MI1111'), lop('12:30', '17:30', 'IT1108')]
    assert N.window(ev, D)[:2] == ('10:00', '12:00')
    free, why = N.spans(ev, D)
    assert free == [['10:05', '12:00']] and why[0].startswith('Dời ngủ trưa sang 10:00–12:00') and 'IT1108' in why[0]
    assert N.wake_min(ev, D) == '11:30'
    assert N.window([lop('08:25', '10:20'), lop('12:30', '17:30')], D)[:2] == ('13:00', '15:00')   # lấn đủ 1 bước (15 phút): không nới -> cách cũ


def test_lop_chen_mot_phan_doi_ca_khung_giu_2_gio():
    assert N.spans([lop('14:00', '16:00')], D)[0] == [['10:00', '12:00']]   # 10:00 và 16:00 cùng cách 3 giờ: chọn sớm hơn
    assert N.spans([lop('13:00', '14:00')], D)[0] == [['14:00', '16:00']]
    assert N.spans([lop('08:00', '11:00'), lop('13:30', '15:00')], D)[0] == [['15:00', '17:00']]


def test_lop_chiem_het_khung_nhung_con_cho_khac():
    assert N.spans([lop('13:00', '15:00')], D)[0] == [['15:00', '17:00']]   # cách 2 giờ, gần hơn 10:00 (cách 3 giờ)


def test_khong_con_cho_giu_cach_cu():
    ev = [lop('08:00', '11:30'), lop('13:30', '17:30')]
    free, why = N.spans(ev, D)
    assert free == [['13:00', '13:30']] and any('13:30–17:30' in w for w in why)
    assert N.spans([lop('08:00', '18:00')], D)[0] == []


def test_khong_chong_gio_an_trua_toi_camp():
    assert N.window([lop('10:00', '11:30'), lop('13:30', '15:00')], D, camp=False)[:2] == ('15:00', '17:00')
    ev = [lop('08:00', '15:45')]
    assert N.window(ev, D, camp=False)[:2] == ('15:45', '17:45')
    assert N.window(ev, D, camp=True)[:2] == ('13:00', '15:00')   # Camp ăn tối 17:30: không còn chỗ -> giữ cách cũ


def test_thi_cung_doi_nghi_khong_doi():
    assert N.spans([lop('13:00', '14:00', 'Thi', 'Exam')], D)[0] == [['14:00', '16:00']]
    assert N.spans([lop('13:00', '14:00', 'NGHỈ: Lớp')], D)[0] == [['13:00', '15:00']]


def test_yellow_giu_dem():
    assert N.spans([lop('12:30', '17:30')], D, N.YELLOW)[0] == [['00:00', '06:00'], ['10:00', '12:00'], ['22:00', '24:00']]


def test_tin_hieu_ghi_khung_moi(monkeypatch):
    monkeypatch.setattr(N, 'events', lambda post: [lop('12:30', '17:30', 'IT1108')])
    d = N.write(None, at(7, 30))
    assert d['nap'] and d['nap_spans'] == [['10:00', '12:00']] and d['spans'][1] == ['10:00', '12:00']
    assert d['why'].startswith('Dời ngủ trưa sang 10:00–12:00') and d['wake_min'] == '11:30'


def test_toi_da_day_theo_khung_doi(monkeypatch):
    monkeypatch.setattr(N, 'events', lambda post: [lop('12:30', '17:30')])
    assert not N.wake(None, at(11, 0))['ok']   # chưa đủ 90 phút
    assert not N.wake(None, at(12, 5))['ok']   # hết khung
    r = N.wake(None, at(11, 35))
    assert r['ok'] and r['signal']['nap_spans'] == [['10:00', '11:35']] and r['signal']['woke'] == '11:35'


def test_toi_da_day_khi_khong_doi_van_1430(monkeypatch):
    monkeypatch.setattr(N, 'events', lambda post: [])
    assert not N.wake(None, at(14, 29))['ok']
    assert N.wake(None, at(14, 30))['ok']
