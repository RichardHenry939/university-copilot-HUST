# -*- coding: utf-8 -*-
"""(chủ 05/11) D-2, D-1 trước kỳ thi môn MI, PH, IT, EE, ET."""
import exam_focus as E


def ex(code, day, name='Giải tích I'):
    return {'kind': 'Exam', 'title': f'Thi GK: {name}', 'start': f'{day}T08:10:00+07:00', 'notes': f'{code} · GK'}


def test_d2_d1_co_khong_d0_d3_khong():
    evs = [ex('MI1111', '2026-11-08')]
    assert E.subject('2026-11-06', evs) == 'Ôn thi: Giải tích I (08/11)'
    assert E.subject('2026-11-07', evs)
    assert E.subject('2026-11-08', evs) is None
    assert E.subject('2026-11-05', evs) is None


def test_chi_khoa_trong_danh_sach():
    for code in ('MI1111', 'PH1110', 'IT2000', 'EE2000', 'ET2000', 'it1108'):
        assert E.subject('2026-11-07', [ex(code, '2026-11-08')]), code
    for code in ('MIL1210', 'FL1101', 'PE1010', 'SSH1111', 'ME2000', ''):
        assert E.subject('2026-11-07', [ex(code, '2026-11-08')]) is None, code


def test_hai_mon_cung_ngay_gop_ten_uu_tien_ngay_gan():
    evs = [ex('MI1111', '2026-11-08'), ex('MI1141', '2026-11-08', 'Đại số'), ex('PH1110', '2026-11-09', 'Vật lý')]
    assert E.subject('2026-11-07', evs) == 'Ôn thi: Giải tích I, Đại số (08/11)'
    assert E.subject('2026-11-08', evs) == 'Ôn thi: Vật lý (09/11)'
