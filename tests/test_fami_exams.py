# -*- coding: utf-8 -*-
"""Lịch thi giữa kỳ FAMI (fami.exams_upcoming / gk_flags) — dữ liệu giả, không gọi mạng."""
import datetime as dt
import json

import fami

TZ = dt.timezone(dt.timedelta(hours=7))
NOW = dt.datetime(2026, 10, 24, 22, 0, tzinfo=TZ)


def test_exams_upcoming_chi_lay_lich_sap_toi_va_sap_xep(tmp_path, monkeypatch):
    f = tmp_path / 'fami.json'
    f.write_text(json.dumps({'exams': [
        {'ma_hp': 'MI1141', 'ngay': '2026-11-08', 'kip': '14h25-15h05'},
        {'ma_hp': 'MI1111', 'ngay': '2026-11-08', 'kip': '8h10-8h50'},
        {'ma_hp': 'MI1000', 'ngay': '2026-10-01', 'kip': '8h'},   # đã qua -> không hiện
    ]}), encoding='utf-8')
    monkeypatch.setattr(fami, 'OUT', f)
    got = [(e['ma_hp'], e['kip']) for e in fami.exams_upcoming(NOW)]
    assert got == [('MI1111', '8h10-8h50'), ('MI1141', '14h25-15h05')]


def test_exams_upcoming_khong_co_file_thi_tra_rong(tmp_path, monkeypatch):
    monkeypatch.setattr(fami, 'OUT', tmp_path / 'khong_co.json')
    assert fami.exams_upcoming(NOW) == []


def test_gk_flags_danh_dau_dung_mon_co_thi():
    exams = [{'ma_hp': 'MI1111'}, {'ma_hp': 'MI1141'}]
    rows = [{'course': 'MI1111', 'name': 'Giải tích I: Bài 10-35'}, {'course': 'IT1108', 'name': 'Quiz'}, {'course': '', 'name': 'không mã'}]
    out = fami.gk_flags(rows, exams)
    assert [x['gkExam'] for x in out] == [True, False, False]


def test_gk_flags_khong_co_lich_thi_thi_khong_hat_mon_nao():
    rows = [{'course': 'MI1111', 'name': 'x'}]
    assert fami.gk_flags(rows, [])[0]['gkExam'] is False


def test_exam_events_cho_tab_lich(tmp_path, monkeypatch):
    f = tmp_path / 'fami.json'
    f.write_text(json.dumps({'exams': [
        {'ma_hp': 'MI1111', 'ten_hp': 'Giải tích I', 'ngay': '2026-11-08', 'kip': '8h10-8h50', 'phong': 'D5-101', 'loai': 'GK'},
        {'ma_hp': 'MI1141', 'ten_hp': 'Đại số', 'ngay': '2026-11-08', 'kip': '', 'phong': ''},   # không có kíp -> cả ngày
        {'ma_hp': 'X', 'ngay': 'sai'},
    ]}, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(fami, 'OUT', f)
    ev = fami.exam_events()
    assert len(ev) == 2 and all(e['kind'] == 'Exam' for e in ev)
    assert ev[0]['title'] == 'Thi GK: Giải tích I' and ev[0]['start'] == '2026-11-08T08:10:00+07:00' and ev[0]['end'] == '2026-11-08T08:50:00+07:00'
    assert ev[0]['location'] == 'D5-101' and ev[1]['start'] == '2026-11-08'
