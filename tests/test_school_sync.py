# -*- coding: utf-8 -*-
"""Áp dữ liệu trường vào Notion (school_sync.py) — n8n / Notion giả."""
import pytest

import school_sync
from conftest import FakeN8n, page

COURSE = page('c-it', Code=('rich_text', 'IT1108'), Name=('title', 'Nhập môn lập trình'), Credits=('number', 2),
              Semester=('select', 'S1'), Status=('status', 'Completed'), Result=('select', 'Unknown'))


def _program(grade):
    # hàng khung CTĐT của qldt: STT · mã · tên · nhóm · TC · … · bắt buộc (X) · … · điểm chữ · kết quả
    return {'rows': [['Học kỳ 1 - Năm học 2026-2027'],
                     ['1', 'IT1108', 'Nhập môn lập trình', 'Cơ sở ngành', '2', '', 'X', '', grade, 'Đạt']]}


@pytest.mark.parametrize('grade, gpa4, result', [
    ('A+', 4.0, 'Pass'), ('A', 4.0, 'Pass'), ('B+', 3.5, 'Pass'), ('B', 3.0, 'Pass'),
    ('C+', 2.5, 'Pass'), ('C', 2.0, 'Pass'), ('D+', 1.5, 'Pass'), ('D', 1.0, 'Pass'), ('F', 0.0, 'Fail'),
    ('8.2 B+', 3.5, 'Pass'),
])
def test_apply_reads_letter_grade_with_plus(grade, gpa4, result):
    n8n = FakeN8n({'db-courses': [COURSE]})
    changes, review = school_sync.apply(n8n, {'program': _program(grade)})
    props = dict(n8n.patched)['c-it']
    assert props['Current GPA 4'] == {'number': gpa4}       # B+ phải là 3.5, không phải 3.0 của B
    assert props['Result'] == {'select': {'name': result}}
    assert any(f'điểm HP {grade.split()[-1]} ' in c for c in changes)


def test_apply_skips_row_without_letter_grade():
    n8n = FakeN8n({'db-courses': [COURSE]})
    school_sync.apply(n8n, {'program': _program('')})
    assert 'Current GPA 4' not in dict(n8n.patched).get('c-it', {})
