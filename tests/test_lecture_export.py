# -*- coding: utf-8 -*-
"""lecture_export.run: ghi chú bài giảng Notion -> Uni-Documents. Không gọi mạng / Notion thật (FakeN8n của conftest)."""
import sys, types

import academic
import lecture_export
import teams_files
from conftest import FakeN8n, page


def test_course_name_is_read_from_title_property(tmp_path, monkeypatch):
    """Cột Name của Courses là cột TIÊU ĐỀ (title). Trước v1.00.30 code đọc .get('rich_text') -> tên môn trong ghi chú xuất ra bị rỗng."""
    monkeypatch.setitem(sys.modules, 'copilot_app', types.SimpleNamespace(UNI=tmp_path, COURSE_FOLDERS={}))
    monkeypatch.setattr(teams_files, 'UNI', tmp_path)
    monkeypatch.setattr(teams_files, 'FOLDERS', tmp_path / 'uni_folders.json')
    monkeypatch.setattr(lecture_export, 'STATE', tmp_path / 'lecture_export.json')
    monkeypatch.setattr(lecture_export, '_blocks', lambda N, bid: [])   # nội dung ghi chú không liên quan tới lỗi này

    course = page('c1', Name=('title', 'Nhập môn lập trình'), Code=('rich_text', 'IT1110'))
    note = page('n1', Lecture=('title', 'Bài 1: Biến và kiểu dữ liệu'), Lecture_Date=('date', '2026-10-12'), Course=('relation', ['c1']))
    note['last_edited_time'] = note['created_time'] = '2026-10-12T10:00:00.000Z'
    fake = FakeN8n({academic.COURSES: [course], lecture_export.NOTES_DB: [note]})

    r = lecture_export.run(fake)

    assert r['ok'] and len(r['written']) == 1
    text = (tmp_path / r['written'][0]).read_text(encoding='utf-8')
    assert '- Môn: IT1110 Nhập môn lập trình' in text
