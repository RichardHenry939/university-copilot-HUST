# -*- coding: utf-8 -*-
"""Trạng thái thi giữa kỳ từng môn (exam_status.py) — dữ liệu giả trong thư mục tạm, không gọi mạng."""
import datetime as dt
import json

import exam_status as X

TZ = dt.timezone(dt.timedelta(hours=7))
NOW = dt.datetime(2026, 10, 24, 22, 0, tzinfo=TZ)


def _school(tmp_path, monkeypatch, posts=(), mails=(), exams=(), rules=None):
    s = tmp_path / 'school'; (s / 'teams').mkdir(parents=True); (s / 'mail').mkdir()
    (s / 'teams' / 'posts.json').write_text(json.dumps({'posts': list(posts)}, ensure_ascii=False), encoding='utf-8')
    (s / 'mail' / 'inbox.json').write_text(json.dumps({'mails': list(mails)}, ensure_ascii=False), encoding='utf-8')
    (s / 'fami.json').write_text(json.dumps({'exams': list(exams)}, ensure_ascii=False), encoding='utf-8')
    rules = rules if rules is not None else {
        'MI1111': {'thanh_phan': [{'ten': 'Giữa kỳ'}]}, 'IT2000': {'thanh_phan': [{'ten': 'Thực hành'}]},
        'IT1108': {'thanh_phan': [{'ten': 'Giữa kỳ'}]}, 'IT3000': {'thanh_phan': []}, 'MIL1210': {}, 'PE1014': {}}
    (s / 'grade_rules.json').write_text(json.dumps(rules, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(X, 'SCHOOL', s)


def _by(rows):
    return {r['ma_hp']: r for r in rows}


def test_moi_mon_deu_co_dong_va_bo_qua_quoc_phong_the_duc(tmp_path, monkeypatch):
    _school(tmp_path, monkeypatch)
    rows = X.overview(NOW)
    assert sorted(r['ma_hp'] for r in rows) == ['IT1108', 'IT2000', 'IT3000', 'MI1111']


def test_fami_co_lich_dung_dau(tmp_path, monkeypatch):
    _school(tmp_path, monkeypatch, exams=[{'ma_hp': 'MI1111', 'ten_hp': 'Giải tích I', 'ngay': '2026-11-08', 'kip': '8h10-8h50', 'phong': 'D5-101'},
                                          {'ma_hp': 'MI1111', 'ngay': '2026-10-01'}])
    rows = X.overview(NOW)
    assert rows[0]['ma_hp'] == 'MI1111' and rows[0]['trang_thai'] == 'co_lich' and rows[0]['phong'] == 'D5-101'


def test_teams_bao_khong_thi(tmp_path, monkeypatch):
    _school(tmp_path, monkeypatch, posts=[{'Team': '2026.1 - Nhập môn CNTT&TT - 171981', 'ReceivedDateTime': '2026-10-08T01:00:00Z',
                                           'Body': 'Điểm quá trình 50%.\nKhông tổ chức thi giữa kỳ. Điểm giữa kỳ là điểm thực hành'}])
    r = _by(X.overview(NOW))['IT2000']
    assert r['trang_thai'] == 'khong_thi' and r['nguon'] == 'Teams' and r['luc'] == '2026-10-08'


def test_teams_du_kien_lay_cau_va_goi_y_ngay(tmp_path, monkeypatch):
    _school(tmp_path, monkeypatch, posts=[{'Team': 'Giải tích 4-6 Sáng thứ 2', 'ReceivedDateTime': '2026-10-04T01:00:00Z',
                                           'Body': 'Chào các bạn lịch thi dự kiến sẽ vào đầu tháng 11. Nội dung ôn tập chương 1'},
                                          {'Team': 'Giải tích 4-6 Sáng thứ 2', 'ReceivedDateTime': '2026-10-23T01:00:00Z',
                                           'Body': 'LCĐ tổ chức thi thử GK môn Giải tích'}])
    r = _by(X.overview(NOW))['MI1111']
    assert r['trang_thai'] == 'du_kien' and 'đầu tháng 11' in r['trich'] and r['ngay_goi_y'] == 'đầu tháng 11'


def test_co_giua_ky_trong_cach_tinh_diem_ma_chua_lich(tmp_path, monkeypatch):
    _school(tmp_path, monkeypatch)
    rows = _by(X.overview(NOW))
    assert rows['IT1108']['trang_thai'] == 'chua_lich' and rows['IT3000']['trang_thai'] == 'chua_co'


def test_mail_khong_lien_quan_mon_thi_bo_qua(tmp_path, monkeypatch):
    _school(tmp_path, monkeypatch, mails=[{'Subject': 'Olympic Vật lý', 'ReceivedDateTime': '2026-10-02T00:00:00Z', 'Body': 'Lịch thi vòng 2: 11/10'}])
    assert _by(X.overview(NOW))['IT3000']['trang_thai'] == 'chua_co'


def test_midterm_codes_chi_lay_mon_se_thi():
    rows = [{'ma_hp': 'A', 'trang_thai': 'co_lich'}, {'ma_hp': 'B', 'trang_thai': 'du_kien'}, {'ma_hp': 'C', 'trang_thai': 'chua_lich'},
            {'ma_hp': 'D', 'trang_thai': 'chua_co'}, {'ma_hp': 'E', 'trang_thai': 'khong_thi'}]
    assert X.midterm_codes(rows) == {'A', 'B', 'C'}
