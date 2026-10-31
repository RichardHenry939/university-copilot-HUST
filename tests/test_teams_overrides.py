# -*- coding: utf-8 -*-
"""Lịch đè từ Teams (teams_overrides.py): dữ liệu giả, không gọi mạng."""
import copy
import datetime as dt

import teams_overrides as T

TZ = T.TZ
NOW = dt.datetime(2026, 10, 31, 20, 0, tzinfo=TZ)
EV = {'lop-IT2000': {
    'kind': 'lop', 'ten': 'Lịch lớp IT2000 Nhập môn CNTT và TT',
    'changes': [{'lines': ['Buổi học 7: ngày 29/10 → 1/11; giờ 16:00 → 09:00',
                           'Trước: Thời gian: 16:00 - 17:30 → Nay: Thời gian: 09:00 - 10:30']},
                {'lines': ['Buổi học 6 (22/10): phòng Online → Phòng 504']}],
    'chang': {
        'buoi hoc 7': {'ten': 'Buổi học 7', 'ngay': '2026-11-01', 'gio': '09:00', 'dia_diem': 'Phòng 103', 'ghi_chu': 'Lịch học bù', 'huy': False},
        'buoi hoc 6': {'ten': 'Buổi học 6', 'ngay': '2026-10-22', 'gio': '16:00', 'dia_diem': 'Phòng 504', 'ghi_chu': '', 'huy': False},
        'buoi cu': {'ten': 'Buổi cũ', 'ngay': '2026-09-01', 'gio': '16:00', 'dia_diem': 'x', 'huy': False},
        'da_huy': {'ten': 'Buổi 9', 'ngay': '2026-11-05', 'gio': '16:00', 'dia_diem': 'x', 'huy': True},
    }}}
CAL = [
    {'kind': 'Class', 'title': 'IT2000 · Nhập môn CNTT và TT · LT+BT · Online', 'start': '2026-10-29T16:00:00.000+07:00', 'end': '2026-10-29T17:30:00.000+07:00', 'location': 'Online', 'notes': ''},
    {'kind': 'Class', 'title': 'IT2000 · Nhập môn CNTT và TT · LT+BT · Online', 'start': '2026-10-22T16:00:00.000+07:00', 'end': '2026-10-22T17:30:00.000+07:00', 'location': 'Online', 'notes': ''},
    {'kind': 'Class', 'title': 'IT1108 · Nhập môn lập trình · LT+BT · Offline', 'start': '2026-10-29T09:20:00.000+07:00', 'end': '2026-10-29T11:45:00.000+07:00', 'location': 'D3-401', 'notes': ''},
    {'kind': 'Exam', 'title': 'Thi GK: Đại số', 'start': '2026-10-29T14:00:00+07:00', 'end': '2026-10-29T15:00:00+07:00', 'location': 'D6', 'notes': ''},
]


def test_buoi_doi_ngay_bo_buoi_cu_them_buoi_moi():
    out = T.apply(CAL, NOW, EV)
    titles = [(e['start'][:16], e['title']) for e in out]
    assert not any(s == '2026-10-29T16:00' and 'IT2000' in t for s, t in titles)   # buổi cũ đã bỏ
    new = [e for e in out if e['start'].startswith('2026-11-01T09:00')]
    assert len(new) == 1 and new[0]['end'].startswith('2026-11-01T10:30') and 'Teams đổi lịch' in new[0]['title']
    assert new[0]['source'] == 'teams' and new[0]['location'] == 'Phòng 103'


def test_doi_phong_cua_buoi_cung_gio_khong_nhan_doi():
    out = T.apply(CAL, NOW, EV)
    same = [e for e in out if e['start'].startswith('2026-10-22T16:00') and 'IT2000' in e['title']]
    assert len(same) == 1 and same[0]['location'] == 'Phòng 504'


def test_mon_khac_va_thi_khong_bi_dung_toi():
    out = T.apply(CAL, NOW, EV)
    assert any(e['title'].startswith('IT1108') for e in out)
    assert any(e['kind'] == 'Exam' for e in out)


def test_khong_sua_bo_dem_dung_chung():
    before = copy.deepcopy(CAL)
    T.apply(CAL, NOW, EV)
    assert CAL == before


def test_buoi_huy_va_qua_xa_bi_bo_qua():
    ovs = T.overrides(NOW, EV)
    labels = [o['label'] for o in ovs]
    assert 'Buổi 9' not in labels and 'Buổi cũ' not in labels   # đã huỷ / quá 14 ngày


def test_khong_co_su_kien_thi_thi_tra_nguyen_ban():
    assert T.apply(CAL, NOW, {}) == CAL
