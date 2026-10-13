# -*- coding: utf-8 -*-
"""Học phí kỳ này (tuition.py): số tín chỉ, đơn giá, tổng tự tính và đối chiếu với số của trường."""
import json

import pytest

import tuition
import tuition_rules

RULES = {'don_gia': 690_000, 'so_qd': '12006/QĐ-ĐHBK', 'nam_hoc': '2026-2027',
         'tchp_lt_bt_15_tiet': 1.0, 'tchp_tn_15_tiet': 0.5, 'tchp_gdtc_moi_tcht': 1.5}
TRANSCRIPT = {'rows': [
    ['Học kỳ 20261'],
    ['1', 'IT1108', 'Nhập môn lập trình', '2', '', ''],
    ['2', 'MI1111', 'Giải tích I', '4', '', ''],
    ['3', 'PE1014', 'Lý luận thể dục thể thao', '0', '', ''],
    ['4', 'MIL1210', 'Đường lối quốc phòng', '3', '', ''],
    ['Học kỳ 20252'],
    ['1', 'MI1141', 'Đại số', '4', '', ''],
]}
INFO = {'IT1108': {'creditInfo': '2(1-0-2-4)', 'credit': 2}, 'MI1111': {'creditInfo': '4(3-2-0-8)', 'credit': 4},
        'PE1014': {'creditInfo': '0(0-0-2-0)', 'credit': 0}, 'MIL1210': {'creditInfo': '3(0-0-0-0)', 'credit': 3}}


@pytest.fixture
def school(tmp_path, monkeypatch):
    """Thư mục school/ tạm: latest.json, tuition.json, tuition_rules.json."""
    monkeypatch.setattr(tuition, 'HERE', tmp_path)
    monkeypatch.setattr(tuition, 'CFG', tmp_path / 'school' / 'tuition.json')
    monkeypatch.setattr(tuition_rules, 'RULES', tmp_path / 'school' / 'tuition_rules.json')
    (tmp_path / 'school').mkdir()

    def write(name, obj):
        (tmp_path / 'school' / name).write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
    return write


# ----------------------------------------------------------------------------- hàm nhỏ
def test_credits_now_takes_only_first_semester_block():
    title, courses = tuition.credits_now({'transcript': TRANSCRIPT})
    assert title == 'Học kỳ 20261'
    assert [c['code'] for c in courses] == ['IT1108', 'MI1111', 'PE1014', 'MIL1210']
    assert sum(c['tc'] for c in courses) == 9


def test_credits_now_empty():
    assert tuition.credits_now({}) == (None, [])


@pytest.mark.parametrize('raw, value', [('3,500,000', 3_500_000), ('1 000', 1000), (700000, 700000), ('abc', None), (None, None)])
def test_num(raw, value):
    assert tuition._num(raw) == value


def test_invoice_fields_guesses_keys_case_insensitively():
    f = tuition._invoice_fields({'InvoiceCode': 'HD1', 'SemesterCode': '20261', 'TotalAmount': '6,210,000',
                                 'PaidAmount': '0', 'TypeName': 'Học phí', 'StatusName': 'Chưa nộp', 'Extra': 1})
    assert f == {'ma': 'HD1', 'hoc_ky': '20261', 'can_dong': 6_210_000, 'da_dong': 0, 'loai': 'Học phí',
                 'trang_thai': 'Chưa nộp', 'cap_nhat': None}


def test_invoice_fields_skips_empty_values():
    assert tuition._invoice_fields({'amount': '', 'total': '5'})['can_dong'] == 5


# ----------------------------------------------------------------------------- view()
def test_view_with_rules_sums_tchp_and_prices(school):
    school('latest.json', {'transcript': TRANSCRIPT, 'course_info': INFO, 'tkb': {'sem': '20261'}})
    school('tuition_rules.json', RULES)
    v = tuition.view()
    # IT1108 = 1 + 2×0,5 = 2 · MI1111 = 5 · PE1014 = 1,5 · MIL1210 = 3  -> 11,5 TCHP
    assert v['so_tin_chi'] == 9
    assert v['so_tchp'] == 11.5
    assert v['chua_ro'] == []
    assert v['don_gia'] == 690_000 and '12006/QĐ-ĐHBK' in v['don_gia_nguon']
    assert v['tong_tinh'] == 690_000 * 11.5
    assert v['doi_chieu'] is None          # trường chưa có số -> không đối chiếu


def test_view_user_override_beats_rules(school):
    school('latest.json', {'transcript': TRANSCRIPT, 'course_info': INFO})
    school('tuition_rules.json', RULES)
    school('tuition.json', {'don_gia': 700_000, 'nguon': 'bạn nhập', 'ghi_de': True})
    v = tuition.view()
    assert v['don_gia'] == 700_000 and v['don_gia_nguon'] == 'bạn nhập'
    assert v['tong_tinh'] == round(700_000 * 11.5)


def test_view_unknown_course_is_listed_and_explains_gap(school):
    info = dict(INFO, MIL1210={'credit': 0, 'creditInfo': '?'})
    school('latest.json', {'transcript': TRANSCRIPT, 'course_info': info, 'tkb': {'sem': '20261'},
                           'tuition': {'ok': True, 'items': [{'amount': 8_000_000, 'semester': '20261', 'typename': 'Học phí'}]}})
    school('tuition_rules.json', RULES)
    v = tuition.view()
    assert v['chua_ro'] == ['MIL1210']
    assert v['so_tchp'] == 8.5
    chk = v['doi_chieu']
    assert chk['khop'] is False and chk['chenh'] == 8_000_000 - 690_000 * 8.5
    assert 'MIL1210' in chk['giai_thich']


def test_view_matches_school_invoice_within_1000(school):
    school('latest.json', {'transcript': TRANSCRIPT, 'course_info': INFO, 'tkb': {'sem': '20261'},
                           'tuition': {'ok': True, 'items': [
                               {'amount': 7_935_500, 'semester': '20261', 'typename': 'Học phí'},
                               {'amount': 99_000, 'semester': '20261', 'typename': 'Bảo hiểm y tế'},     # không phải học phí
                               {'amount': 5_000_000, 'semester': '20252', 'typename': 'Học phí'}]}})   # kỳ khác
    school('tuition_rules.json', RULES)
    v = tuition.view()
    assert v['truong']['tong_can_dong'] == 7_935_500
    assert v['doi_chieu']['khop'] is True and v['doi_chieu']['giai_thich'] is None
    assert len(v['truong']['hoa_don']) == 3 and 'raw' not in v['truong']['hoa_don'][0]


def test_view_sis_numbers_are_authoritative(school):
    school('latest.json', {'transcript': TRANSCRIPT, 'course_info': INFO, 'tkb': {'sem': '20261'},
                           'sis_tuition': {'ok': True, 'tong_hoc_phi': 9_000_000, 'con_phai_dong': 9_000_000, 'hoc_ky': '20261',
                                           'hoc_phan': [
                                               {'code': 'IT1108', 'name': 'Nhập môn lập trình', 'tchp': 2.0, 'tien': 1_380_000, 'he_so': 1},
                                               {'code': 'MI1111', 'name': 'Giải tích I', 'tchp': 6.0, 'tien': 4_140_000, 'he_so': 1},
                                               {'code': 'EM1010', 'name': 'Quản trị học', 'tchp': 2.0, 'tien': 1_380_000, 'he_so': 1}]}})
    school('tuition_rules.json', RULES)
    v = tuition.view()
    by = {c['code']: c for c in v['hoc_phan']}
    assert by['IT1108']['lech'] is False and by['IT1108']['tchp_truong'] == 2.0
    assert by['MI1111']['lech'] is True                 # UC tính 5, trường tính 6
    assert by['EM1010']['cach_tinh'] == 'chỉ có trên trang học phí của trường' and by['EM1010']['tc'] is None
    assert v['mon_lech'] == ['MI1111']
    assert v['truong']['tong_can_dong'] == 9_000_000    # số của SIS thay cho hoá đơn qldt
    assert v['sis']['doc_duoc'] is True and v['sis']['con_phai_dong'] == 9_000_000


def test_view_infers_price_from_first_invoice_without_rules(school, tmp_path):
    school('latest.json', {'transcript': TRANSCRIPT, 'tkb': {'sem': '20261'},
                           'tuition': {'ok': True, 'items': [{'amount': 6_300_000, 'semester': '20261'}]}})
    v = tuition.view()
    assert v['don_gia'] == 700_000                     # 6 300 000 ÷ 9 tín chỉ
    assert v['tong_tinh'] == 6_300_000
    assert v['doi_chieu']['khop'] is True
    saved = json.loads((tmp_path / 'school' / 'tuition.json').read_text(encoding='utf-8'))
    assert saved['don_gia'] == 700_000 and saved['tu_ky'] == '20261'
    assert '6.300.000 đ' in saved['nguon']


def test_view_without_any_data(school):
    v = tuition.view()
    assert v['ok'] and v['don_gia'] is None and v['tong_tinh'] is None and v['doi_chieu'] is None
    assert v['luat'] is None and v['nop_tai'] == tuition.PAY_URL


# ----------------------------------------------------------------------------- set_price
def test_set_price_accepts_vietnamese_format(school, tmp_path):
    school('latest.json', {'transcript': TRANSCRIPT})
    v = tuition.set_price('700.000')
    assert v['don_gia'] == 700_000
    assert json.loads((tmp_path / 'school' / 'tuition.json').read_text(encoding='utf-8'))['ghi_de'] is True


@pytest.mark.parametrize('bad', ['10.000', '20.000.000', 'abc'])
def test_set_price_rejects_unreasonable(school, bad):
    with pytest.raises(ValueError):
        tuition.set_price(bad)
