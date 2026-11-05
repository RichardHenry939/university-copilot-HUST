# -*- coding: utf-8 -*-
"""(chủ 05/11) Chống muộn: buổi trực tiếp, tím đi học, kế hoạch kiểm, tha khi khác chỗ / tới toà, không lưu toạ độ."""
import datetime as dt

import pytest

import late as L

D = '2026-11-05'
t = lambda h, m: dt.datetime(2026, 11, 5, h, m, tzinfo=L.TZ)
PE = {'kind': 'Class', 'id': 'pe', 'title': 'PE1014 · Lý luận TDTT · LT+BT · Offline', 'start': D + 'T06:45:00+07:00', 'end': D + 'T07:45:00+07:00', 'location': 'SVD'}
IT = {'kind': 'Class', 'id': 'it', 'title': 'IT1108 · Nhập môn lập trình · LT+BT · Offline', 'start': D + 'T09:20:00+07:00', 'location': 'D3-401'}
ON = {'kind': 'Class', 'id': 'on', 'title': 'IT2000 · Nhập môn CNTT · LT+BT · Online', 'start': D + 'T16:00:00+07:00', 'location': 'Phòng 103, tầng 1, toà nhà B1 và MS Teams'}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(L, 'STATE', tmp_path / 'late.json')


def test_buoi_truc_tiep_va_online():
    assert not L.online(PE) and L.online(ON)
    assert not L.online(dict(ON, attend='truc_tiep'))   # DS học trực tiếp đứng trên chữ "Online"
    assert [c['id'] for c in L.offline_classes([PE, IT, ON], D)] == ['pe', 'it']


def test_tim_di_hoc():
    sp = L.prep_spans([PE, IT, ON], D)
    assert sp[0][0][11:16] == '06:00' and sp[0][1][11:16] == '06:45'   # buổi đầu trước 8h: từ 06:00
    assert sp[1][0][11:16] == '09:05' and sp[1][1][11:16] == '09:20'
    assert len(sp) == 2   # buổi online không có


def test_ke_hoach_chi_trong_15_phut_va_co_toa():
    assert L.plan([IT], t(9, 0))['id'] is None
    p = L.plan([IT], t(9, 6))
    assert p['id'].startswith('cls|it|') and p['target']['toa'] == 'D3' and p['left'] == 14 and not p['done']


def test_tha_khi_khac_cho_hoac_toi_toa_khong_luu_toa_do():
    cid = L.plan([IT], t(9, 6))['id']
    assert L.check({'id': cid, 'moved': False, 'at': False, 'left': 14}, t(9, 6))['spared'] is None
    assert L.check({'id': cid, 'moved': True, 'at': False, 'lat': 21.0, 'lon': 105.8, 'left': 13}, t(9, 7))['spared'] == 'moved'
    assert L.plan([IT], t(9, 8))['done']
    raw = L.STATE.read_text(encoding='utf-8')
    assert '21.0' not in raw and '105.8' not in raw   # không có toạ độ của bạn trong dữ liệu UC
    cid2 = L.plan([PE], t(6, 40))['id']
    assert L.check({'id': cid2, 'at': True}, t(6, 41))['spared'] == 'arrived'


def test_ma_toa():
    assert L.building('Phòng 103, tầng 1, toà nhà B1 và MS Teams') == 'B1'
    assert L.building('D3-401') == 'D3' and L.building('TC-307') == 'TC' and L.building('SVD') == 'SVD'
