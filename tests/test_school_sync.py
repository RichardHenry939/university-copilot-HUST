# -*- coding: utf-8 -*-
"""Áp dữ liệu trường vào Notion (school_sync.py) — n8n / Notion giả."""
import pytest

import school_sync
from conftest import FakeN8n, page

COURSE = page('c-it', Code=('rich_text', 'IT1108'), Name=('title', 'Nhập môn lập trình'), Credits=('number', 2),
              Semester=('select', 'S1'), Status=('status', 'Completed'), Result=('select', 'Unknown'))


HEADS = ['STT', 'MÃ HỌC PHẦN', 'TÊN HỌC PHẦN', 'Phân loại Module/HP', 'Số TC', 'ECTS', 'Bắt buộc', 'Đã học', 'Điểm HP(Bậc)', 'Kết quả',
         'Xem chi tiết HP']   # đúng tiêu đề bảng CTĐT của qldt (10/2026)


def _program(grade, heads=HEADS, extra_col_at=None):
    # hàng khung CTĐT của qldt: STT · mã · tên · nhóm · TC · … · bắt buộc (X) · … · điểm chữ · kết quả
    row = ['1', 'IT1108', 'Nhập môn lập trình', 'Cơ sở ngành', '2', '', 'X', '', grade, 'Đạt']
    heads = list(heads)
    if extra_col_at is not None: heads.insert(extra_col_at, 'CỘT MỚI'); row.insert(extra_col_at, '???')
    return {'heads': heads, 'rows': [['Học kỳ 1 - Năm học 2026-2027'], row]}


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


def test_program_column_inserted_still_reads_by_header():
    # (v1.00.24, R-2) trường chèn thêm 1 cột: trước đây đọc cứng r[4] -> số tín sai / Credits = 0; nay dò cột theo tên tiêu đề
    n8n = FakeN8n({'db-courses': [COURSE]})
    changes, review = school_sync.apply(n8n, {'program': _program('B+', extra_col_at=3)})
    props = dict(n8n.patched)['c-it']
    assert props['Current GPA 4'] == {'number': 3.5}
    assert 'Credits' not in props            # số tín vẫn đọc đúng = 2 như Notion -> không ghi đè


def test_program_missing_column_skips_step_and_reports():
    # (v1.00.24, R-2) bảng mất cột "Số TC" -> bỏ cả bước CTĐT lượt đó, báo review, không ghi gì
    n8n = FakeN8n({'db-courses': [COURSE]})
    heads = [h for h in HEADS if h != 'Số TC']
    changes, review = school_sync.apply(n8n, {'program': _program('B+', heads=heads)})
    assert 'c-it' not in dict(n8n.patched)
    assert any('CTĐT' in r and 'số tc' in r for r in review)
