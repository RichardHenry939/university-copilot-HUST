# -*- coding: utf-8 -*-
"""Hạn nộp (deadlines.py): mốc nhắc, đọc 📋 Academic Work qua n8n giả, phân loại bằng agent (giả), danh sách đang mở."""
import datetime as dt, json, sys, types

import pytest

import academic
import deadlines as d
from conftest import FakeN8n, page

TZ = d.TZ
NOW = dt.datetime(2026, 10, 13, 9, 0, tzinfo=TZ)


@pytest.fixture(autouse=True)
def fresh_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(d, '_c', {'rows': None, 'at': 0, 'busy': False})
    monkeypatch.setattr(d, 'REVIEW', tmp_path / 'deadline_review.json')
    monkeypatch.setattr(d, 'KINDS_LOG', tmp_path / 'deadline_kinds.json')


@pytest.fixture
def gemini(monkeypatch):
    """mail_events giả: chỉ có gemini(); ghi lại prompt, trả `answer`."""
    fake = types.SimpleNamespace(prompts=[], answer=[])

    def gem(prompt, caller=None):
        assert caller == 'deadline'
        fake.prompts.append(prompt)
        if isinstance(fake.answer, Exception): raise fake.answer
        return fake.answer
    fake.gemini = gem
    monkeypatch.setitem(sys.modules, 'mail_events', fake)
    return fake


# ----------------------------------------------------------------------------- hàm thuần
def test_norm_strips_accents_and_punctuation():
    assert d.norm('  Bài tập  Đại số — Tuần 3! ') == 'bai tap dai so tuan 3'
    assert d.norm(None) == ''


def test_marks_match_documented_schedule():
    # docstring: Tự luyện 72/48/36/24 giờ · cốt lõi + 7h/5h/3h/1h/30/20/10 phút · Môn học + 10h/5h/3h/1h/30/20/10/5/2/1 phút
    base = [72 * 60, 48 * 60, 36 * 60, 24 * 60]
    assert list(d.MARKS['Tự luyện']) == base
    assert list(d.MARKS['Tự luyện cốt lõi']) == base + [420, 300, 180, 60, 30, 20, 10]
    assert list(d.MARKS['Môn học']) == base + [600, 300, 180, 60, 30, 20, 10, 5, 2, 1]
    assert d.KINDS == ('Tự luyện', 'Tự luyện cốt lõi', 'Môn học')


@pytest.mark.parametrize('left, mark', [
    (60, 60), (55, 60), (50, 60),          # trong khoảng [mốc − 10, mốc]
    (49.9, None),                          # lỡ mốc 60 quá 10 phút -> không gửi bù
    (61, None),                            # chưa tới mốc
    (4320, 4320), (4315, 4320),            # 72 giờ
    (2, 2), (1, 1), (0.5, 1),
])
def test_mark_at_only_exact_marks(left, mark):
    assert d.mark_at(d.MARKS['Môn học'], left) == mark


def test_mark_at_custom_grace():
    assert d.mark_at((60,), 45, grace=15) == 60
    assert d.mark_at((60,), 44, grace=15) is None


def test_mark_due_per_kind():
    due = (NOW + dt.timedelta(minutes=300)).isoformat()
    assert d.mark_due({'due': due, 'kind': 'Môn học'}, NOW) == (300, 300)
    assert d.mark_due({'due': due, 'kind': 'Tự luyện cốt lõi'}, NOW)[0] == 300
    assert d.mark_due({'due': due, 'kind': 'Tự luyện'}, NOW)[0] is None          # tự luyện chỉ nhắc 72/48/36/24 giờ
    assert d.mark_due({'due': due, 'kind': 'Loại lạ'}, NOW)[0] == 300            # loại lạ -> coi như Môn học


def test_mark_due_past_deadline():
    m, left = d.mark_due({'due': (NOW - dt.timedelta(minutes=5)).isoformat(), 'kind': 'Môn học'}, NOW)
    assert m is None and left == -5


@pytest.mark.parametrize('mins, text', [
    (0.2, '1 phút'), (1, '1 phút'), (45, '45 phút'), (59.6, '1 giờ'),
    (60, '1 giờ'), (95, '1 giờ 35 phút'), (125, '2 giờ 05 phút'), (180, '3 giờ'),
    (600, '10 giờ'), (610, '10 giờ'),                       # ≥ 10 giờ: bỏ phút lẻ
    (1500, '25 giờ'), (2880, '2 ngày'), (3000, '2 ngày 2 giờ'), (4320, '3 ngày'),
])
def test_say_left(mins, text):
    assert d.say_left(mins) == text


# ----------------------------------------------------------------------------- phân loại bằng agent (giả)
ROW = {'id': 'w1', 'name': 'Quiz chương 2', 'course': 'MI1111', 'type': 'Quiz', 'weight': 10}


def test_classify_parses_valid_answers(gemini):
    gemini.answer = [{'id': 'w1', 'loai': 'Môn học', 'ly_do': 'tính điểm'},
                     {'id': 'w2', 'loai': 'Không có', 'ly_do': 'sai loại'},     # loại không hợp lệ -> bỏ
                     {'loai': 'Tự luyện'}, 'rác']                                 # thiếu id / không phải dict -> bỏ
    assert d.classify([ROW, {**ROW, 'id': 'w2'}]) == {'w1': ('Môn học', 'tính điểm')}
    assert 'id=w1 | Quiz chương 2 | môn MI1111 | Type Quiz | Weight 10' in gemini.prompts[0]


def test_classify_accepts_wrapped_dict(gemini):
    gemini.answer = {'items': [{'id': 'w1', 'loai': 'Tự luyện'}]}
    assert d.classify([ROW]) == {'w1': ('Tự luyện', '')}
    gemini.answer = {'id': 'w1', 'loai': 'Tự luyện cốt lõi'}                    # một object trơn
    assert d.classify([ROW]) == {'w1': ('Tự luyện cốt lõi', '')}


def test_classify_error_returns_empty(gemini):
    gemini.answer = TimeoutError('cổng Gemini bận')
    assert d.classify([ROW]) == {}


def test_classify_nothing_to_do(gemini):
    assert d.classify([]) == {} and gemini.prompts == []


# ----------------------------------------------------------------------------- đọc Academic Work (n8n giả)
def work_row(pid, name, due, kind=None, status='Not started', course='c-mi'):
    return page(pid, {'Name': ('title', name), 'Due': ('date', due), 'Loại hạn': ('select', kind), 'Status': ('status', status),
                      'Course': ('relation', [course] if course else []), 'Type': ('select', 'Assignment'), 'Weight %': ('number', 20)})


COURSES = [page('c-mi', Code=('rich_text', 'MI1111'), Name=('title', 'Giải tích I'))]


def fake_n8n(rows):
    return FakeN8n({'db-academic_work': rows, 'db-courses': COURSES})


def test_fetch_builds_rows_classifies_and_sorts(gemini):
    n8n = fake_n8n([work_row('w2', 'Bài 2', '2026-10-20', kind='Tự luyện'),
                    work_row('w1', 'Bài 1', '2026-10-15T08:00:00+07:00'),
                    work_row('w3', 'Bài 3', '2026-10-14', status='Submitted', course=None)])
    gemini.answer = [{'id': 'w1', 'loai': 'Tự luyện cốt lõi', 'ly_do': 'ôn nền'}]
    rows = d._fetch(n8n)
    assert [r['id'] for r in rows] == ['w3', 'w1', 'w2']
    w1, w2, w3 = rows[1], rows[2], rows[0]
    assert w1['kind'] == 'Tự luyện cốt lõi' and w1['course'] == 'MI1111' and w1['courseName'] == 'Giải tích I'
    assert w2['due'] == '2026-10-20T23:59:00+07:00'                      # ngày trơn -> 23:59 giờ VN
    assert w2['kind'] == 'Tự luyện' and w2['weight'] == 20
    assert w3['kind'] == 'Môn học' and w3['course'] == ''                # đã nộp: không phân loại, mặc định gắt nhất
    # chỉ dòng đang mở + chưa có loại được gửi cho agent, và kết quả được GHI vào Notion
    assert 'id=w1' in gemini.prompts[0] and 'id=w2' not in gemini.prompts[0] and 'id=w3' not in gemini.prompts[0]
    assert n8n.patched == [('w1', {'Loại hạn': {'select': {'name': 'Tự luyện cốt lõi'}}})]
    log = json.loads(d.KINDS_LOG.read_text(encoding='utf-8'))
    assert log['w1']['ly_do'] == 'ôn nền'
    db, flt = n8n.queries[0]
    assert db == 'db-academic_work' and {'property': 'Entry Kind', 'select': {'equals': 'Deadline'}} in flt['and']


def test_fetch_unclassified_defaults_to_strictest(gemini):
    gemini.answer = []
    rows = d._fetch(fake_n8n([work_row('w1', 'Bài 1', '2026-10-15')]))
    assert rows[0]['kind'] == 'Môn học'


def test_all_rows_raises_when_never_loaded(monkeypatch):
    monkeypatch.setattr(d, '_fetch', lambda post: (_ for _ in ()).throw(RuntimeError('n8n tắt')))
    with pytest.raises(RuntimeError, match='chưa đọc được'):
        d.all_rows(lambda *a: None)


def test_all_rows_returns_cache_and_refreshes_in_background(monkeypatch):
    rows = [{'id': 'x'}]
    d._c.update(rows=rows, at=0)
    started = []
    monkeypatch.setattr(d.threading, 'Thread', lambda target, args, daemon: types.SimpleNamespace(start=lambda: started.append(target)))
    assert d.all_rows('post') is rows
    assert started == [d.refresh]                                          # cũ hơn 5 phút -> làm mới ngầm


def test_refresh_skips_when_busy(monkeypatch):
    d._c['busy'] = True
    monkeypatch.setattr(d, '_fetch', lambda post: pytest.fail('đang bận thì không đọc lại'))
    d.refresh('post')


def test_open_list_filters_done_and_far_and_marks_overdue(monkeypatch):
    now = dt.datetime.now(TZ)
    iso = lambda **k: (now + dt.timedelta(**k)).isoformat()
    d._c.update(rows=[
        {'id': 'a', 'name': 'Quá hạn', 'due': iso(hours=-2), 'status': 'Not started', 'kind': 'Môn học'},
        {'id': 'b', 'name': 'Sắp tới', 'due': iso(days=2), 'status': 'In progress', 'kind': 'Môn học'},
        {'id': 'c', 'name': 'Đã nộp', 'due': iso(days=1), 'status': 'Submitted', 'kind': 'Môn học'},
        {'id': 'e', 'name': 'Đã chấm', 'due': iso(days=1), 'status': 'Graded', 'kind': 'Môn học'},
        {'id': 'f', 'name': 'Xa quá', 'due': iso(days=30), 'status': 'Not started', 'kind': 'Tự luyện'}], at=1e18)
    d.REVIEW.write_text(json.dumps({'b': {'teams': '2026-10-16', 'notion': iso(days=2)}}), encoding='utf-8')
    out = d.open_list('post')
    assert [x['id'] for x in out] == ['a', 'b']
    assert out[0]['overdue'] is True and out[0]['minsLeft'] < 0
    assert out[1]['overdue'] is False and 2 * 1440 - 2 <= out[1]['minsLeft'] <= 2 * 1440
    assert 'Teams ghi hạn 2026-10-16' in out[1]['review']
    assert [x['id'] for x in d.open_list('post', days=60)] == ['a', 'b', 'f']


def test_complete_marks_submitted(monkeypatch):
    n8n = FakeN8n()
    d._c.update(rows=[{'id': 'w1', 'status': 'Not started'}], at=1e18)
    monkeypatch.setattr(d.threading, 'Thread', lambda **k: types.SimpleNamespace(start=lambda: None))
    assert d.complete(n8n, 'w1') == {'ok': True}
    assert n8n.patched == [('w1', {'Status': {'status': {'name': 'Submitted'}}})]
    assert d._c['rows'][0]['status'] == 'Submitted'
