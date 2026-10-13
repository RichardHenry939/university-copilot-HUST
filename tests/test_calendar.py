# -*- coding: utf-8 -*-
"""Phân tích lịch: chu kỳ học kỳ (semester.py), sinh buổi học từ TKB (tkb.py), lọc thông báo cũ (stale_filter.py)."""
import datetime as dt

import pytest

import semester
import stale_filter as sf
import tkb
from conftest import FakeN8n, page

CAL = {'first_year': 2026, 'odd_start': '08-24', 'tet_start': '01-19', 'even_start': '02-16', 'summer_start': '07-19',
       'overrides': {'2028': {'tet_start': '01-24', 'even_start': '02-21'}}, 'week1': {'2026': '2026-08-31'}}
D = dt.date


# ============================================================================= semester.expected
@pytest.mark.parametrize('day, want', [
    (D(2026, 10, 13), ('Semester', 1)),
    (D(2026, 8, 24), ('Semester', 1)),         # đúng ngày khai kỳ lẻ
    (D(2027, 1, 18), ('Semester', 1)),         # năm mới dương lịch nhưng chưa tới Tết
    (D(2027, 1, 19), ('Tết', 1)),
    (D(2027, 2, 16), ('Semester', 2)),
    (D(2027, 7, 18), ('Semester', 2)),
    (D(2027, 7, 19), ('Hè', 2)),
    (D(2027, 8, 24), ('Semester', 3)),
    (D(2028, 1, 20), ('Semester', 3)),         # năm 2028 Tết dời sang 24/01 (overrides)
    (D(2028, 1, 24), ('Tết', 3)),
    (D(2028, 2, 18), ('Tết', 3)),              # kỳ chẵn 2028 dời sang 21/02
    (D(2028, 2, 21), ('Semester', 4)),
    (D(2030, 7, 20), ('Hè', 8)),
    (D(2030, 8, 24), ('Done', 8)),             # sau S8 thì dừng
    (D(2031, 7, 20), ('Done', 8)),
    (D(2026, 3, 1), ('Semester', 1)),          # trước khi nhập học -> không ra số kỳ âm
])
def test_expected_period(day, want):
    assert semester.expected(day, CAL) == want


def test_d_applies_year_override_only_for_that_year():
    assert semester._d(2028, CAL['tet_start'], CAL, 'tet_start') == D(2028, 1, 24)
    assert semester._d(2029, CAL['tet_start'], CAL, 'tet_start') == D(2029, 1, 19)


def test_repo_calendar_file_is_consistent():
    c = semester.cal()                                   # semester_calendar.json trong repo
    for k in ('odd_start', 'tet_start', 'even_start', 'summer_start'):
        m, d = map(int, c[k].split('-')); D(2027, m, d)
    assert semester.expected(D(2026, 10, 13), c) == ('Semester', 1)


# ============================================================================= tkb: hàm nhỏ
@pytest.mark.parametrize('raw, out', [('6:45', '06:45'), ('13h30', '13:30'), ('15.00', '15:00'), ('9', '09:00'), (' 7H5 ', '07:05')])
def test_hhmm(raw, out):
    assert tkb._hhmm(raw) == out


@pytest.mark.parametrize('bad', ['25:00', '10:60', '', 'sáng'])
def test_hhmm_rejects(bad):
    with pytest.raises(ValueError):
        tkb._hhmm(bad)


def test_load_accepts_json_text_or_list():
    assert tkb._load('[{"mon": "MI1111"}]') == [{'mon': 'MI1111'}]
    assert tkb._load([1]) == [1] and tkb._load('') == [] and tkb._load(None) == []


@pytest.fixture
def cal(monkeypatch):
    monkeypatch.setattr(semester, 'cal', lambda: CAL)


def test_week1_from_calendar_and_fallback(cal, monkeypatch):
    assert tkb.week1(D(2026, 12, 1)) == D(2026, 8, 31)
    assert tkb.week1(D(2027, 3, 1)) == D(2026, 8, 31)             # kỳ chẵn vẫn thuộc năm học 2026
    # năm học chưa ghi week1: = thứ Hai của tuần sau ngày khai kỳ lẻ (24/08/2027 là thứ Ba -> 30/08/2027)
    assert tkb.week1(D(2027, 9, 15)) == D(2027, 8, 30)


# ============================================================================= tkb.plan / run
COURSES = [
    page('c-mi', Code=('rich_text', 'MI1111'), Name=('title', 'Giải tích I'), Semester=('select', 'S1'), Status=('status', 'Planned')),
    page('c-it', Code=('rich_text', 'IT1108'), Name=('title', 'Nhập môn lập trình'), Semester=('select', 'S1'), Status=('status', 'Taking')),
    page('c-ph', Code=('rich_text', 'PH1110'), Name=('title', 'Vật lý đại cương I'), Semester=('select', 'S1'), Status=('status', 'Taking')),
]
ARGS = {'bat_dau': '2026-08-31', 'ket_thuc': '2027-01-10', 'ky': 'S1',
        'lop': [{'mon': 'MI1111', 'loai': 'LT', 'thu': '2', 'bat_dau': '6:45', 'ket_thuc': '9:10', 'phong': 'D3-101',
                 'giang_vien': 'GV A', 'tuan_chan_le': 'le'},
                {'mon': 'nhập môn lập trình', 'loai': 'TH', 'thu': 'Thứ 5', 'bat_dau': '13h30', 'ket_thuc': '15.00',
                 'phong': 'Online Teams', 'tuan': [2, 3]}],
        'nghi': [{'tu': '2026-09-14', 'den': '2026-09-20', 'ly_do': 'Đợt QP-AN'},
                 {'tu': '2026-10-12', 'mon': 'MI1111', 'ly_do': 'GV đi công tác'}]}


def nt_with(courses=COURSES, **dbs):
    from academic import Notion
    return Notion(FakeN8n({'db-courses': courses, **dbs}))


def test_plan_generates_sessions(cal):
    events, courses, probs, (start, end, sem, code_sem, offs) = tkb.plan(nt_with(), ARGS)
    assert probs == [] and sem == 'S1' and code_sem == '20261' and set(courses) == {'MI1111', 'IT1108'}
    mi = [e for e in events if e['code'] == 'MI1111']
    # thứ Hai tuần lẻ từ 31/08 (tuần 1) tới 04/01 (tuần 19) = 10 buổi, trừ tuần 3 (đợt QP-AN) và 12/10 = tuần 7 (nghỉ riêng MI1111)
    assert [e['date'] for e in mi][:3] == [D(2026, 8, 31), D(2026, 9, 28), D(2026, 10, 26)]
    assert len(mi) == 8
    assert mi[0]['start'] == '2026-08-31T06:45:00+07:00' and mi[0]['end'] == '2026-08-31T09:10:00+07:00'
    assert mi[0]['title'] == 'MI1111 · Giải tích I · LT · Offline' and mi[0]['room'] == 'D3-101' and mi[0]['notes'] == 'GV GV A'
    assert mi[0]['key'] == '20261|MI1111|LT|2026-08-31|06:45'
    it = [e for e in events if e['code'] == 'IT1108']
    assert [e['date'] for e in it] == [D(2026, 9, 10)]                  # tuần 2; tuần 3 rơi vào đợt nghỉ
    assert it[0]['title'].endswith('· TH · Online')                      # phòng "Online…" -> hình thức Online
    off = [e for e in events if not e['code']]
    assert len(off) == 1 and off[0]['title'] == '⛔ Đợt QP-AN (14/09 → 20/09)' and off[0]['end'] == '2026-09-20'


def test_plan_reports_problems_per_class(cal):
    a = dict(ARGS, lop=[{'mon': 'Hoá học', 'thu': '2', 'bat_dau': '7:00', 'ket_thuc': '9:00'},
                        {'mon': 'MI1111', 'thu': '2', 'bat_dau': 'sáng', 'ket_thuc': '9:00'},
                        {'mon': 'IT1108', 'thu': '9', 'bat_dau': '7:00', 'ket_thuc': '9:00'}],
             nghi=[{'ly_do': 'không có ngày'}])
    events, _, probs, _ = tkb.plan(nt_with(), a)
    assert events == []
    assert len(probs) == 4
    assert 'Đợt nghỉ không rõ ngày' in probs[0]
    assert probs[1].startswith('Lớp 1 (Hoá học)')
    assert 'giờ học không rõ' in probs[2] and 'không rõ thứ mấy' in probs[3]


@pytest.mark.parametrize('patch, msg', [
    ({'bat_dau': None}, 'Thiếu ngày'),
    ({'ket_thuc': '2026-09-05'}, 'không giống một kỳ học'),
    ({'lop': '[]'}, 'Chưa có lớp'),
    ({'lop': '{hỏng'}, 'không đọc được'),
])
def test_plan_rejects_bad_input(cal, patch, msg):
    r = tkb.plan(nt_with(), dict(ARGS, **patch))
    assert len(r) == 3 and msg in r[2][0]


def test_run_preview_and_write(cal):
    old = [page('old-keep', {'Sync Key': ('rich_text', '20261|MI1111|LT|2026-08-31|06:45')}),
           page('old-drop', {'Sync Key': ('rich_text', '20261|MI1111|LT|2026-09-01|06:45')})]
    n8n = FakeN8n({'db-courses': COURSES, 'db-calendar_events': old}, hooks={'copilot-tkb-archive': [{'ok': True}]})
    prev = tkb.run(n8n, ARGS)
    assert prev['ok'] and prev['xem_truoc']['so_buoi'] == 9
    assert prev['xem_truoc']['mon_du_kien_khong_co_trong_tkb'] == ['PH1110 Vật lý đại cương I']
    assert n8n.created == [] and n8n.patched == []

    res = tkb.run(n8n, dict(ARGS, buoc='ghi'))
    assert res['ok']
    assert ('copilot-tkb-archive', {'ids': ['old-drop']}) in n8n.calls
    created_keys = [p['Sync Key']['rich_text'][0]['text']['content'] for _, p in n8n.created]
    assert '20261|MI1111|LT|2026-08-31|06:45' not in created_keys          # buổi trùng Sync Key được giữ, không tạo lại
    assert len(n8n.created) == 9                                          # 8 + 1 buổi học + 1 dải nghỉ − 1 buổi đã có
    patched = dict(n8n.patched)
    assert patched['c-mi'] == {'Status': {'status': {'name': 'Taking'}}}
    assert patched['c-ph']['Status'] == {'status': {'name': 'Planned'}}   # môn đang học nhưng không có trong TKB
    assert 'c-it' not in patched                                          # đã Taking, đúng kỳ -> không ghi


def test_run_stops_if_archive_refuses(cal):
    old = [page('old-drop', {'Sync Key': ('rich_text', 'khác')})]
    n8n = FakeN8n({'db-courses': COURSES, 'db-calendar_events': old}, hooks={'copilot-tkb-archive': {'bo_qua': ['old-drop']}})
    res = tkb.run(n8n, dict(ARGS, buoc='ghi'))
    assert res['ok'] is False and 'từ chối 1 trang' in res['loi'] and n8n.created == []


# ============================================================================= stale_filter
NOW = dt.datetime(2026, 10, 13, 9, 0)


@pytest.mark.parametrize('at, text, kept', [
    ('2026-10-01', 'Hạn nộp hồ sơ 20/10/2026', True),
    ('2026-10-01', 'Hạn nộp hồ sơ 20-09-2026', False),                  # mọi ngày đã qua
    ('2026-09-01', 'Đăng ký từ 01/09/2026 đến 15/10/2026', True),        # còn một ngày chưa qua
    ('2026-10-01', 'Lịch thi 2026-11-02', True),
    ('2026-10-01', 'Học bổng tháng 9/2026', False),                      # tháng 9 -> ngày cuối tháng 30/09
    ('2026-10-01', 'Học bổng tháng 10 năm 2026', True),
    ('2026-10-01T08:00:00Z', 'Nộp trước 24/10', True),                   # ngày không ghi năm -> năm của thông báo
    ('2026-10-01', 'Nộp trước 24/09', False),
    ('2026-09-20', 'Thông báo chung không ghi ngày', True),
    ('2026-05-01', 'Thông báo chung không ghi ngày', False),             # cũ hơn 90 ngày
    ('2025-12-01', 'Thông báo năm trước', False),
    (None, 'Không rõ ngày gửi', True),
])
def test_keep(at, text, kept):
    assert sf.keep(at, text, now=NOW) is kept


def test_keep_handles_impossible_dates():
    assert sf.keep('2026-10-01', '31/02/2026 và 30/10/2026', now=NOW) is True
    assert sf._dates('tháng 12/2026') == [D(2026, 12, 31)]


def test_split_counts_hidden():
    items = [{'at': '2026-10-01', 't': 'hạn 20/10/2026'}, {'at': '2025-01-01', 't': 'cũ'}, {'at': '2026-10-10', 't': None}]
    kept, hidden = sf.split(items, 'at', ['t'], now=NOW)
    assert [i['at'] for i in kept] == ['2026-10-01', '2026-10-10'] and hidden == 1
