# -*- coding: utf-8 -*-
"""Luật học phí theo Tín chỉ học phí (tuition_rules.py): đọc quyết định, quy đổi TCHP, cập nhật mỗi năm học."""
import datetime as dt, json

import pytest

import tuition_rules as tr

# Chữ trích từ một quyết định học phí MẪU (số liệu giả, đúng bố cục Phụ lục I / II mà parse() đọc).
DECISION = """
PHỤ LỤC I. MỨC HỌC PHÍ
I. Các chương trình đào tạo đại học chính quy
1) Các chương trình đào tạo chuẩn
Chương trình Mức học phí
Khoa học máy tính, KT máy tính 690
Kỹ thuật điện 650
Toán - Tin 600
2) Các chương trình đào tạo tài năng
Chương trình tài năng 800
II. Các chương trình vừa làm vừa học
1) Các chương trình đào tạo chuẩn
Kỹ thuật máy tính 900
PHỤ LỤC II. QUY ĐỔI TÍN CHỈ HỌC TẬP SANG TÍN CHỈ HỌC PHÍ
I. Hệ đại học chính quy
Lý thuyết, bài tập: 15 tiết = 1 TCHP
Thí nghiệm, thực hành: 15 tiết = 0,5 TCHP
Giáo dục thể chất 1 TCHT = 1,5 TCHP
II. Hệ đào tạo thường xuyên
Lý thuyết: 15 tiết = 1,2 TCHP
"""
RULES = {'don_gia': 690_000, 'tchp_lt_bt_15_tiet': 1.0, 'tchp_tn_15_tiet': 0.5, 'tchp_gdtc_moi_tcht': 1.5}


# ----------------------------------------------------------------------------- năm học
@pytest.mark.parametrize('day, year', [
    (dt.date(2026, 10, 13), '2026-2027'),
    (dt.date(2026, 8, 1), '2026-2027'),     # tháng 8 đã là năm học mới
    (dt.date(2026, 7, 31), '2025-2026'),
    (dt.date(2027, 1, 15), '2026-2027'),
])
def test_school_year(day, year):
    assert tr.school_year(day) == year


# ----------------------------------------------------------------------------- đọc quyết định
def test_parse_reads_price_and_conversion_for_program():
    rules, err = tr.parse(DECISION, 'Kỹ thuật máy tính')
    assert err == []
    assert rules['don_gia'] == 690_000                       # "KT máy tính" được hiểu là "Kỹ thuật máy tính"
    assert 'máy tính' in rules['dong_bang']
    assert rules['tchp_lt_bt_15_tiet'] == 1.0
    assert rules['tchp_tn_15_tiet'] == 0.5                   # số thập phân kiểu Việt "0,5"
    assert rules['tchp_gdtc_moi_tcht'] == 1.5


def test_parse_uses_regular_program_table_not_part_time_one():
    # "Kỹ thuật máy tính" có trong cả bảng chính quy (690) và bảng vừa làm vừa học (900) -> phải lấy bảng chính quy
    rules, _ = tr.parse(DECISION, 'Kỹ thuật máy tính')
    assert rules['don_gia'] != 900_000


def test_parse_other_program():
    rules, err = tr.parse(DECISION, 'Kỹ thuật điện')
    assert err == [] and rules['don_gia'] == 650_000


def test_parse_normalises_backslashes_and_html_space():
    text = DECISION.replace('Kỹ thuật điện 650', 'Kỹ\\ thuật&#32;điện 650')
    rules, err = tr.parse(text, 'Kỹ thuật điện')
    assert err == [] and rules['don_gia'] == 650_000


def test_parse_unknown_program_reports_error():
    rules, err = tr.parse(DECISION, 'Ngôn ngữ Anh')
    assert 'don_gia' not in rules
    assert any('Ngôn ngữ Anh' in e for e in err)


def test_parse_missing_sections_reports_both():
    rules, err = tr.parse('văn bản không liên quan', 'Kỹ thuật máy tính')
    assert rules == {}
    assert len(err) == 2


def test_parse_flags_out_of_range_price():
    rules, err = tr.parse(DECISION.replace('KT máy tính 690', 'KT máy tính 150'), 'Kỹ thuật máy tính')
    assert rules['don_gia'] == 150_000
    assert any('đơn giá lạ' in e for e in err)


def test_parse_flags_out_of_range_conversion():
    rules, err = tr.parse(DECISION.replace('15 tiết = 0,5 TCHP', '15 tiết = 9 TCHP'), 'Kỹ thuật máy tính')
    assert any('tchp_tn_15_tiet lạ' in e for e in err)


def test_parse_missing_lab_conversion():
    text = DECISION.replace('Thí nghiệm, thực hành: 15 tiết = 0,5 TCHP\n', '')
    rules, err = tr.parse(text, 'Kỹ thuật máy tính')
    assert 'tchp_lt_bt_15_tiet' not in rules
    assert any('15 tiết' in e for e in err)


# ----------------------------------------------------------------------------- TCHP của một học phần
@pytest.mark.parametrize('credit_info, expected', [
    ('3(2-2-0-6)', 4.0),     # (2 + 2) giờ LT+BT / tuần × 15 tuần = 60 tiết = 4 TCHP
    ('2(1-0-2-4)', 2.0),     # 1 giờ LT = 1 TCHP + 2 giờ TN × 0,5 = 1 TCHP
    ('4(3-2-0-8)', 5.0),
    (' 3 ( 3 - 0 - 0 - 6 ) ', 3.0),
    ('2(0-0-4-4)', 2.0),
])
def test_tchp_regular_course(credit_info, expected):
    n, how = tr.tchp('IT1108', {'creditInfo': credit_info}, RULES)
    assert n == expected
    assert credit_info in how


def test_tchp_military_course_uses_study_credits():
    assert tr.tchp('MIL1210', {'credit': 3, 'creditInfo': '3(0-0-0-0)'}, RULES)[0] == 3.0


def test_tchp_military_course_without_credit_is_unknown():
    n, how = tr.tchp('MIL1220', {'credit': 0, 'creditInfo': '?'}, RULES)
    assert n is None and 'GDQP' in how


def test_tchp_physical_education_counts_one_credit_even_if_zero():
    assert tr.tchp('PE1014', {'credit': 0}, RULES)[0] == 1.5
    assert tr.tchp('PE1024', {'credit': 2}, RULES)[0] == 3.0


def test_tchp_missing_or_unreadable_info():
    assert tr.tchp('IT1108', None, RULES)[0] is None
    n, how = tr.tchp('IT1108', {'creditInfo': '3 tín chỉ'}, RULES)
    assert n is None and 'không đọc được' in how


# ----------------------------------------------------------------------------- tìm bài + PDF (mạng giả)
LIST_HTML = '''
<a href="/DisplayWeb/DisplayBaiViet?baiviet=111" class="x"><p class="title">Quy định đào tạo năm học 2026-2027</p></a>
<a href="/DisplayWeb/DisplayBaiViet?baiviet=222" class="x"><p class="title">Quyết định <b>mức học phí</b> năm học 2026-2027</p></a>
'''


def test_find_decision_picks_tuition_article(monkeypatch):
    monkeypatch.setattr(tr, '_get', lambda url, timeout=60: LIST_HTML.encode())
    d = tr.find_decision('2026-2027')
    assert d == {'title': 'Quyết định mức học phí năm học 2026-2027', 'url': tr.CTT + '/DisplayWeb/DisplayBaiViet?baiviet=222'}


def test_find_decision_none_after_three_pages(monkeypatch):
    seen = []
    monkeypatch.setattr(tr, '_get', lambda url, timeout=60: seen.append(url) or b'<html></html>')
    assert tr.find_decision('2030-2031') is None
    assert len(seen) == 3 and seen[1].endswith('&page=2')


def test_pdf_link_relative_is_quoted(monkeypatch):
    monkeypatch.setattr(tr, '_get', lambda url, timeout=60: '<a href="/Upload/Quyết định 12006_QĐ.pdf">tải</a>'.encode())
    u = tr._pdf_link('https://ctt.example/bai')
    assert u.startswith(tr.CTT + '/Upload/') and ' ' not in u and u.endswith('.pdf')


def test_pdf_link_absolute_and_missing(monkeypatch):
    monkeypatch.setattr(tr, '_get', lambda url, timeout=60: b'<a href="https://files.example/a.PDF">x</a>')
    assert tr._pdf_link('u') == 'https://files.example/a.PDF'
    monkeypatch.setattr(tr, '_get', lambda url, timeout=60: b'<p>none</p>')
    assert tr._pdf_link('u') is None


# ----------------------------------------------------------------------------- update / maybe_update
@pytest.fixture
def tmp_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, 'HERE', tmp_path)
    monkeypatch.setattr(tr, 'RULES', tmp_path / 'school' / 'tuition_rules.json')
    monkeypatch.setattr(tr, 'STATE', tmp_path / 'school' / 'tuition_rules_state.json')
    monkeypatch.setattr(tr, 'DOCS', tmp_path / 'school' / 'tuition_decisions')
    monkeypatch.setattr(tr, 'school_year', lambda today=None: '2026-2027')
    return tmp_path


def _fake_site(monkeypatch, pdf_url='https://ctt.example/Upload/12006_QD-DHBK.pdf', text=DECISION):
    monkeypatch.setattr(tr, 'find_decision', lambda year: {'title': f'Quyết định mức học phí {year}', 'url': 'https://ctt.example/bai'})
    monkeypatch.setattr(tr, '_pdf_link', lambda u: pdf_url)
    monkeypatch.setattr(tr, '_get', lambda url, timeout=60: b'%PDF-fake')
    monkeypatch.setattr(tr, '_tika', lambda data: text)


def test_update_writes_rules(tmp_rules, monkeypatch):
    _fake_site(monkeypatch)
    res = tr.update()
    assert res['ok']
    saved = json.loads(tr.RULES.read_text(encoding='utf-8'))
    assert saved['don_gia'] == 690_000 and saved['nam_hoc'] == '2026-2027'
    assert saved['so_qd'] == '12006/QĐ-ĐHBK'
    assert saved['chuong_trinh'] == 'Kỹ thuật máy tính'
    assert (tr.DOCS / '2026-2027.pdf').read_bytes() == b'%PDF-fake'


def test_update_uses_program_from_user_config(tmp_rules, monkeypatch):
    _fake_site(monkeypatch)
    (tmp_rules / 'school').mkdir(parents=True, exist_ok=True)
    (tmp_rules / 'school' / 'tuition.json').write_text(json.dumps({'chuong_trinh': 'Kỹ thuật điện'}), encoding='utf-8')
    assert tr.update()['rules']['don_gia'] == 650_000


def test_update_skips_when_year_already_loaded(tmp_rules, monkeypatch):
    tr._save(tr.RULES, {'nam_hoc': '2026-2027', 'don_gia': 1})
    monkeypatch.setattr(tr, 'find_decision', lambda y: pytest.fail('không được tải lại'))
    res = tr.update()
    assert res['ok'] and 'skip' in res


def test_update_does_not_overwrite_on_parse_error(tmp_rules, monkeypatch):
    tr._save(tr.RULES, {'nam_hoc': '2025-2026', 'don_gia': 600_000})
    _fake_site(monkeypatch, text='văn bản hỏng')
    res = tr.update()
    assert not res['ok']
    assert json.loads(tr.RULES.read_text(encoding='utf-8'))['don_gia'] == 600_000


def test_update_reports_missing_decision_and_pdf(tmp_rules, monkeypatch):
    monkeypatch.setattr(tr, 'find_decision', lambda y: None)
    assert not tr.update()['ok']
    _fake_site(monkeypatch, pdf_url=None)
    assert 'PDF' in tr.update()['error']


def test_maybe_update_only_in_aug_to_nov(tmp_rules, monkeypatch):
    monkeypatch.setattr(tr, 'update', lambda: pytest.fail('ngoài mùa không được chạy'))
    assert tr.maybe_update(dt.datetime(2027, 3, 1, 9)) is None


def test_maybe_update_once_per_day(tmp_rules, monkeypatch):
    calls = []
    monkeypatch.setattr(tr, 'update', lambda: calls.append(1) or {'ok': False, 'error': 'chưa có'})
    now = dt.datetime(2026, 10, 13, 9)
    assert tr.maybe_update(now) == {'ok': False, 'error': 'chưa có'}
    assert tr.maybe_update(now.replace(hour=15)) is None
    assert tr.maybe_update(now + dt.timedelta(days=1)) is not None
    assert len(calls) == 2
    assert json.loads(tr.STATE.read_text(encoding='utf-8'))['last_try'] == '2026-10-14'


def test_maybe_update_stops_when_rules_exist(tmp_rules, monkeypatch):
    tr._save(tr.RULES, {'nam_hoc': '2026-2027'})
    monkeypatch.setattr(tr, 'update', lambda: pytest.fail('đã có luật năm học'))
    assert tr.maybe_update(dt.datetime(2026, 10, 13, 9)) is None


def test_maybe_update_records_exception(tmp_rules, monkeypatch):
    def boom(): raise ConnectionError('mất mạng')
    monkeypatch.setattr(tr, 'update', boom)
    res = tr.maybe_update(dt.datetime(2026, 9, 2, 9))
    assert res['ok'] is False and 'ConnectionError' in res['error']
    assert 'mất mạng' in json.loads(tr.STATE.read_text(encoding='utf-8'))['last']['error']
