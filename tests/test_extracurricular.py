# -*- coding: utf-8 -*-
"""🎯 Ngoại khoá (extracurricular.py): dựng danh sách từ CTSV / MOOC / mail — mọi nguồn ngoài đều giả."""
import datetime as dt, json, sys, types

import pytest

import extracurricular as X
import mail_events_stub

NOW = dt.datetime(2026, 10, 13, 9, 0, tzinfo=X.TZ)


@pytest.fixture
def school(tmp_path, monkeypatch):
    monkeypatch.setattr(X, 'HERE', tmp_path)
    monkeypatch.setattr(X, 'OUT', tmp_path / 'school' / 'extracurricular.json')
    monkeypatch.setitem(sys.modules, 'mail_events', mail_events_stub.make({}))
    monkeypatch.setitem(sys.modules, 'mail_kinds', types.SimpleNamespace(by_kind=lambda *a, **k: []))
    (tmp_path / 'school').mkdir()

    def write(name, obj):
        (tmp_path / 'school' / name).write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
    return write


def test_mooc_course_start_is_utc_converted_to_vietnam_time(school):
    # Open edX trả course_start theo UTC ("…Z"): 01:00 UTC = 08:00 giờ Việt Nam (mooc.py, expired.py, course_detail.py đều đọc là UTC)
    school('mooc.json', {'courses': {'course-v1:SoICT+SHCD+2026': {
        'name': 'Sinh hoạt công dân', 'start': '2026-10-20T01:00:00Z', 'items': [{'name': 'Bài 1', 'earned': 0}]}}})
    items = X.build(NOW)['items']
    mooc = next(i for i in items if i['key'].startswith('mooc|'))
    assert dt.datetime.fromisoformat(mooc['start']) == dt.datetime(2026, 10, 20, 8, 0, tzinfo=X.TZ)
    assert mooc['start'] == '2026-10-20T08:00:00+07:00'
    assert mooc['note'] == 'Chưa làm: Bài 1'


def test_mooc_course_without_start(school):
    school('mooc.json', {'courses': {'course-v1:SoICT+SHCD+2026': {'name': 'Sinh hoạt công dân', 'items': []}}})
    mooc = next(i for i in X.build(NOW)['items'] if i['key'].startswith('mooc|'))
    assert mooc['start'] is None and mooc['note'] == 'Đã làm đủ bài tính điểm'


def test_mooc_course_with_subject_code_is_not_extracurricular(school):
    school('mooc.json', {'courses': {'course-v1:SoICT+IT1108+2026_1': {'name': 'Nhập môn lập trình', 'start': '2026-09-01T00:00:00Z', 'items': []}}})
    assert not [i for i in X.build(NOW)['items'] if i['key'].startswith('mooc|')]


def test_ctsv_local_times_stay_vietnam_time(school):
    # thời gian của iCTSV không kèm múi giờ = giờ Việt Nam: giữ nguyên, chỉ gắn +07:00
    school('latest.json', {'ctsv': {'ok': True, 'mine': [{'id': 7, 'name': 'Hiến máu', 'start': '2026-10-15 08:00:00',
                                                         'end': '2026-10-15 11:00:00', 'deadline': None, 'ua': '2'}], 'open': []}})
    it = next(i for i in X.build(NOW)['items'] if i['key'] == 'ctsv|mine|7')
    assert it['start'] == '2026-10-15T08:00:00+07:00' and it['status'] == 'Đã xác nhận'
