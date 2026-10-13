# -*- coding: utf-8 -*-
"""Hàm thuần của academic.py: thang điểm HUST, GPA, đọc thuộc tính Notion, khớp tên môn, lớp Notion qua n8n (giả)."""
import pytest

import academic as a
from conftest import FakeN8n, page


@pytest.mark.parametrize('score, want', [
    (10, ('A+', 4.0)), (9.5, ('A+', 4.0)), (9.4, ('A', 4.0)), (8.5, ('A', 4.0)), (8.0, ('B+', 3.5)), (7.0, ('B', 3.0)),
    (6.5, ('C+', 2.5)), (5.5, ('C', 2.0)), (5.0, ('D+', 1.5)), (4.0, ('D', 1.0)), (3.9, ('F', 0.0)), (0, ('F', 0.0)),
])
def test_letter_boundaries(score, want):
    assert a.letter(score) == want


@pytest.mark.parametrize('qt, ck, w, want', [(8, 6, 30, 6.6), (7.5, 8.5, 40, 8.1), (10, 0, 50, 5.0), (6.75, 6.75, 30, 6.8)])
def test_course_score_rounds_half_up(qt, ck, w, want):
    assert a.course_score(qt, ck, w) == want


def test_weighted_gpa_skips_zero_credit_and_missing():
    assert a.weighted_gpa([(3, 4.0), (2, 3.0), (0, 0.0), (4, None)]) == 3.6
    assert a.weighted_gpa([(0, 4.0)]) is None and a.weighted_gpa([]) is None


@pytest.mark.parametrize('x, rank', [(95, 'Xuất sắc'), (90, 'Xuất sắc'), (80, 'Tốt'), (65, 'Khá'), (50, 'Trung bình'), (35, 'Yếu'), (34, 'Kém')])
def test_conduct_rank(x, rank):
    assert a.conduct_rank(x) == rank


@pytest.mark.parametrize('x, v', [('7,5', 7.5), (' 8.25 ', 8.25), (9, 9.0), ('', None), (None, None), ('abc', None)])
def test_num(x, v):
    assert a.num(x) == v


def test_P_reads_every_supported_type():
    p = page('p', Name=('title', 'Bài 1'), Note=('rich_text', 'ghi chú'), Kind=('select', 'Quiz'), St=('status', 'Done'),
             N=('number', 3), C=('checkbox', True), R=('relation', ['x', 'y']), Due=('date', '2026-10-20'), U=('url', 'https://x'))
    p['properties']['M'] = {'type': 'multi_select', 'multi_select': [{'name': 'a'}, {'name': 'b'}]}
    p['properties']['F'] = {'type': 'formula', 'formula': {'type': 'number', 'number': 42}}
    p['properties']['X'] = {'type': 'people', 'people': []}
    got = {k: a.P(p, k) for k in ('Name', 'Note', 'Kind', 'St', 'N', 'C', 'R', 'Due', 'U', 'M', 'F', 'X', 'Missing')}
    assert got == {'Name': 'Bài 1', 'Note': 'ghi chú', 'Kind': 'Quiz', 'St': 'Done', 'N': 3, 'C': True, 'R': ['x', 'y'],
                   'Due': '2026-10-20', 'U': 'https://x', 'M': ['a', 'b'], 'F': 42, 'X': None, 'Missing': None}
    assert a.P(page('q', Kind=('select', None), Due=('date', None)), 'Kind') is None


COURSES = [
    page('1', Code=('rich_text', 'MI1111'), Name=('title', 'Giải tích I'), Semester=('select', 'S1'), Status=('status', 'Taking')),
    page('2', Code=('rich_text', 'MI1121'), Name=('title', 'Giải tích II'), Semester=('select', 'S2'), Status=('status', 'Planned')),
    page('3', Code=('rich_text', 'IT3011'), Name=('title', 'Cấu trúc dữ liệu và thuật toán'), Semester=('select', 'S3'), Status=('status', 'Planned')),
    page('4', Code=('rich_text', 'IT1108'), Name=('title', 'Nhập môn lập trình'), Semester=('select', 'S1'), Status=('status', 'Taking')),
    page('5', Code=('rich_text', 'CH1012'), Name=('title', 'Hoá học đại cương'), Semester=('select', 'S2'), Status=('status', 'Planned')),
    page('6', Code=('rich_text', 'SSH1111'), Name=('title', 'Triết học Mác - Lênin'), Semester=('select', 'S1'), Status=('status', 'Planned')),
]


@pytest.fixture
def nt():
    return a.Notion(FakeN8n({'db-courses': COURSES}))


@pytest.mark.parametrize('said, code', [
    ('MI1111', 'MI1111'), ('mi 1111', 'MI1111'),
    ('giải tích 2', 'MI1121'),                 # số 2 = II
    ('GT1', 'MI1111'),                         # viết tắt
    ('CTDL', 'IT3011'),
    ('nhap mon lap trinh', 'IT1108'),
    ('triet hoc', 'SSH1111'),
])
def test_find_course_matches(nt, said, code):
    c, ask = a.find_course(nt, said, 'S1')
    assert ask is None and c['code'] == code


def test_find_course_ambiguous_prefers_taking(nt):
    c, ask = a.find_course(nt, 'giải tích', 'S1')
    assert ask is None and c['code'] == 'MI1111'      # khớp 2 môn, chỉ 1 môn đang học -> chọn môn đó


def test_find_course_asks_back(nt):
    assert a.find_course(nt, '', 'S1') == (None, 'Bạn đang nói môn nào?')
    c, ask = a.find_course(nt, 'sinh học phân tử', 'S1')
    assert c is None and 'không tìm thấy' in ask
    c, ask = a.find_course(nt, 'hoa hoc', 'S1')       # "hoa hoc" khớp nguyên từ, không lẫn với "triết học"
    assert c['code'] == 'CH1012'


def test_notion_ops_raises_on_error():
    def post(path, body): return [{'res': [{'code': 200, 'body': {}}, {'code': 404, 'body': {'message': 'không thấy trang'}}]}]
    with pytest.raises(RuntimeError, match='không thấy trang'):
        a.Notion(post).ops([{}, {}])


def test_notion_query_follows_pagination():
    pages = iter([{'results': [1, 2], 'has_more': True, 'next_cursor': 'c2'}, {'results': [3], 'has_more': False}])
    bodies = []

    def post(path, body):
        bodies.append(body['ops'][0]['body'])
        return {'res': [{'code': 200, 'body': next(pages)}]}
    assert a.Notion(post).query('db', {'f': 1}) == [1, 2, 3]
    assert 'start_cursor' not in bodies[0] and bodies[1]['start_cursor'] == 'c2' and bodies[1]['filter'] == {'f': 1}


def test_current_sem(nt):
    n = a.Notion(FakeN8n({'db-semester_state': [page('s', State=('select', 'Old'), **{'Semester No.': ('select', '1')}),
                                                page('t', State=('select', 'Current'), **{'Semester No.': ('select', '3')})]}))
    assert a.current_sem(n) == 'S3'
    assert a.current_sem(a.Notion(FakeN8n())) == 'S1'
