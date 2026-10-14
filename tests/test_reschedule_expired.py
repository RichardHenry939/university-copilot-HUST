# -*- coding: utf-8 -*-
"""Dời hạn tự đặt (reschedule.py) và gom việc đã hết hạn (expired.py) — Notion / mail / MOOC / FAMI đều giả."""
import datetime as dt, json, sys, types

import pytest

import expired
import reschedule as rs
from conftest import FakeN8n, page

TZ = rs.TZ


# ============================================================================= reschedule
@pytest.mark.parametrize('raw, iso', [
    ('2026-10-05T19:00', '2026-10-05T19:00:00+07:00'),
    ('2026-10-05 19:00', '2026-10-05T19:00:00+07:00'),
    ('2026-10-05', '2026-10-05T23:59:00+07:00'),                 # ngày trơn = 23:59
    (' 2026-10-05T19:00+00:00 ', '2026-10-05T19:00:00+00:00'),   # có múi giờ -> giữ nguyên
])
def test_when(raw, iso):
    assert rs._when(raw).isoformat() == iso


@pytest.mark.parametrize('bad', ['', None, 'mai', '05/10/2026'])
def test_when_rejects(bad):
    with pytest.raises(ValueError):
        rs._when(bad)


def test_fmt():
    assert rs._fmt(dt.datetime(2026, 10, 5, 7, 3, tzinfo=TZ)) == '07:03 5/10'


def _work(pid, name, kind, due, url=None):
    props = {'Name': ('title', name), 'Loại hạn': ('select', kind), 'Due': ('date', due)}
    if url is not None: props['Submission/Repo'] = ('url', url)
    return page(pid, props)


@pytest.fixture
def future():
    base = (dt.datetime.now(TZ) + dt.timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
    return base


def _setup(future):
    old = (future - dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:00+07:00')
    work = [_work('aaaa-1111', 'Ôn chương 1', 'Tự luyện', old),
            _work('bbbb-2222', 'Bài tập lớn', 'Môn học', old),
            _work('cccc-3333', 'Luyện đề', 'Tự luyện cốt lõi', old, url='https://teams.microsoft.com/l/x'),
            _work('dddd-4444', 'Quiz 3 (MOOC)', 'Tự luyện', old),
            _work('eeee-5555', 'Chưa có ngày', 'Tự luyện', None)]
    kids = [page('t-open', Status=('status', 'To do'), Due=('date', old)),
            page('t-done', Status=('status', 'Done'), Due=('date', old)),
            page('t-later', Status=('status', 'To do'), Due=('date', (future + dt.timedelta(days=5)).isoformat()))]
    return FakeN8n({'db-academic_work': work, 'db-academic_tasks': kids, 'db-calendar_events': [page('cal-1')]})


def test_run_preview_writes_nothing(future):
    n8n = _setup(future)
    out = rs.run(n8n, {'work_ids': 'aaaa1111, bbbb-2222 cccc-3333;dddd-4444 eeee-5555 zzzz', 'han_moi': future.strftime('%Y-%m-%dT%H:%M')})
    assert out['ok'] and out['buoc'] == 'xem_truoc' and 'nhac' in out
    assert len(out['se_doi']) == 1 and out['se_doi'][0].startswith('Ôn chương 1 (Tự luyện)')
    assert 'kèm 1 việc con, 1 dòng lịch' in out['se_doi'][0]           # việc con đã Done / có hạn sau hạn mới -> không kéo theo
    refused = ' | '.join(out['tu_choi'])
    for name in ('Bài tập lớn', 'Luyện đề', 'Quiz 3 (MOOC)'):          # Môn học, URL của trường, tên nguồn trường
        assert name in refused
    assert 'hạn chưa có ngày' in refused and 'zzzz' in refused
    assert n8n.patched == []


def test_run_write_updates_work_tasks_calendar_and_kicks_a4(future):
    n8n = _setup(future)
    kicked = []
    out = rs.run(n8n, {'work_ids': 'aaaa-1111', 'han_moi': future.strftime('%Y-%m-%d %H:%M'), 'buoc': 'ghi'}, kick_a4=lambda: kicked.append(1))
    iso = future.isoformat(timespec='minutes')
    assert n8n.patched == [('aaaa-1111', {'Due': {'date': {'start': iso}}}),
                           ('cal-1', {'When': {'date': {'start': iso}}}),
                           ('t-open', {'Due': {'date': {'start': iso}}})]
    assert out['tong'].startswith('Đã dời 1 hạn, 1 việc con, 1 dòng lịch') and kicked == [1]
    assert 'da_doi' in out and out['a4'].startswith('đã chạy lại A4')


def test_run_write_reports_a4_failure(future):
    def boom(): raise ConnectionError
    out = rs.run(_setup(future), {'work_ids': 'aaaa-1111', 'han_moi': future.isoformat(), 'buoc': 'ghi'}, kick_a4=boom)
    assert 'ConnectionError' in out['a4']


@pytest.mark.parametrize('args, key', [
    ({'han_moi': '2030-01-01'}, 'thieu'),
    ({'work_ids': 'x', 'han_moi': 'không rõ'}, 'thieu'),
    ({'work_ids': 'x', 'han_moi': '2020-01-01T08:00'}, 'tu_choi'),
])
def test_run_validates_input(args, key):
    out = rs.run(FakeN8n(), args)
    assert out['ok'] is False and key in out


# ============================================================================= expired
NOW = dt.datetime(2026, 10, 13, 12, 0, tzinfo=TZ)


@pytest.fixture
def sources(tmp_path, monkeypatch):
    """mail_events + fami giả, MOOC đọc từ thư mục tạm."""
    import mail_events_stub
    me = mail_events_stub.make({})
    fami = types.SimpleNamespace(items=lambda now: [])
    monkeypatch.setitem(sys.modules, 'mail_events', me)
    monkeypatch.setitem(sys.modules, 'fami', fami)
    monkeypatch.setattr(expired, 'HERE', tmp_path)
    (tmp_path / 'school').mkdir()
    return types.SimpleNamespace(me=me, fami=fami, mooc=lambda obj: (tmp_path / 'school' / 'mooc.json').write_text(json.dumps(obj), encoding='utf-8'))


def test_key_is_hour_in_vietnam_time():
    assert expired._key('MI1111', dt.datetime(2026, 10, 1, 16, 30, tzinfo=dt.timezone.utc)) == 'het-han|MI1111|2026-10-01T23'


def test_collect_teams_only_past_and_not_cancelled(sources):
    sources.me.state['events'] = {
        'bt-MI1111': {'kind': 'bt', 'course': 'MI1111', 'chang': {
            '1': {'ten': 'Bài 1', 'ngay': '2026-10-10', 'gio': '23:59'},
            '2': {'ten': 'Bài 2', 'ngay': '2026-10-20'},                  # chưa tới hạn
            '3': {'ten': 'Bài 3', 'ngay': '2026-10-09', 'huy': True},     # bị huỷ
            '4': {'ten': 'Bài 4'}}},                                      # không có ngày
        'tb-x': {'kind': 'tb', 'chang': {'1': {'ten': 'Thông báo', 'ngay': '2026-10-01'}}}}
    out = expired.collect(NOW)
    assert list(out) == ['het-han|MI1111|2026-10-10T23']
    assert out['het-han|MI1111|2026-10-10T23']['ket_qua'] == 'Không rõ'


def test_collect_mooc_wins_over_teams_within_two_hours(sources):
    sources.me.state['events'] = {'bt-IT1108': {'kind': 'bt', 'course': 'IT1108', 'chang': {
        '1': {'ten': 'Buổi học 4', 'ngay': '2026-10-10', 'gio': '22:00'}}}}
    sources.mooc({'courses': {'course-v1:SoICT+IT1108+2026_1': {'start': '2026-09-01T00:00:00Z', 'items': [
        {'name': 'Tuần 4', 'due': '2026-10-10T16:59:00Z', 'earned': 8, 'possible': 10},     # 23:59 VN, lệch 1h59 với Teams
        {'name': 'Tuần 5', 'due': '2026-10-12T16:59:00Z', 'earned': 0, 'possible': 10},
        {'name': 'Tuần 9', 'due': '2026-11-01T16:59:00Z'},                                  # chưa tới hạn
        {'name': 'Trước khoá', 'due': '2026-08-01T00:00:00Z'},                              # trước ngày bắt đầu khoá
        {'name': 'Không hạn'}]},
        'course-v1:Khac+ABC+2026': {'items': [{'name': 'x', 'due': '2026-10-01T00:00:00Z'}]}}})   # không có mã môn
    out = expired.collect(NOW)
    assert set(out) == {'het-han|IT1108|2026-10-10T23', 'het-han|IT1108|2026-10-12T23'}
    w4 = out['het-han|IT1108|2026-10-10T23']
    assert (w4['name'], w4['ket_qua'], w4['nguon']) == ('Tuần 4', 'Đã làm', 'MOOC 8/10')
    assert out['het-han|IT1108|2026-10-12T23']['ket_qua'] == 'Bỏ lỡ'


def test_collect_fami_and_its_failure(sources, monkeypatch):
    due = dt.datetime(2026, 10, 11, 9, 0, tzinfo=TZ)
    sources.fami.items = lambda now: [
        {'code': 'MI1141', 'name': 'Chương 1', 'due': due, 'done': True, 'score': {'diem': 9}, 'max': 10},
        {'code': 'MI1141', 'name': 'Chương 2', 'due': due + dt.timedelta(days=1), 'done': False, 'score': None, 'max': 10},
        {'code': 'MI1141', 'name': 'Chương 5', 'due': NOW + dt.timedelta(days=3), 'done': False}]
    out = expired.collect(NOW)
    assert out['het-han|MI1141|2026-10-11T09']['nguon'] == 'FAMI số hoá · 9/10'
    assert out['het-han|MI1141|2026-10-12T09'] ['ket_qua'] == 'Bỏ lỡ'
    assert len(out) == 2

    def broken(now): raise RuntimeError('FAMI hết phiên')
    sources.fami.items = broken
    assert expired.collect(NOW) == {}                                     # FAMI lỗi không làm hỏng cả lượt


def test_record_creates_new_and_updates_changed(monkeypatch):
    due = dt.datetime(2026, 10, 10, 23, 59, tzinfo=TZ)
    want = {'het-han|MI1111|2026-10-10T23': {'name': 'Bài 1', 'code': 'MI1111', 'due': due, 'ket_qua': 'Đã làm', 'nguon': 'MOOC 8/10'},
            'het-han|MI1111|2026-10-11T23': {'name': 'Bài 2', 'code': 'MI1111', 'due': due, 'ket_qua': 'Bỏ lỡ', 'nguon': 'MOOC 0/10'},
            'het-han|XX0000|2026-10-11T23': {'name': 'Bài 3', 'code': 'XX0000', 'due': due, 'ket_qua': 'Không rõ', 'nguon': 'Teams'}}
    monkeypatch.setattr(expired, 'collect', lambda: want)
    have = [page('t1', {'Breakdown Key': ('rich_text', 'het-han|MI1111|2026-10-10T23'), 'Kết quả hạn': ('select', 'Không rõ'),
                        'Nguồn hạn': ('rich_text', 'Teams')}),
            page('t2', {'Breakdown Key': ('rich_text', 'het-han|MI1111|2026-10-11T23'), 'Kết quả hạn': ('select', 'Bỏ lỡ'),
                        'Nguồn hạn': ('rich_text', 'MOOC 0/10')})]
    n8n = FakeN8n({'db-academic_tasks': have, 'db-courses': [page('c-mi', Code=('rich_text', 'MI1111'), Name=('title', 'GT1'))]})
    res = expired.record(n8n)
    assert res == {'ok': True, 'created': ['XX0000 Bài 3 · Không rõ'], 'updated': ['Bài 1'], 'total': 3}
    (db, props), = n8n.created
    assert db == 'db-academic_tasks' and props['Status'] == {'status': {'name': 'Done'}} and props['Estimate (hrs)'] == {'number': 0}
    assert 'Course' not in props                                          # môn không có trong Courses -> không gắn quan hệ
    assert n8n.patched[0][0] == 't1' and n8n.patched[0][1]['Kết quả hạn'] == {'select': {'name': 'Đã làm'}}


@pytest.mark.parametrize('sg', [{'ngay': '2026-10-10'}, {'ngay': '2026-10-10', 'gio': '7:05'}, {'ngay': 'x'}, {}, {'ngay': '2026-02-30'}])
def test_stub_when_of_matches_real_mail_events(sg):
    import importlib
    import mail_events_stub
    real = importlib.import_module('mail_events')        # module thật: nạp không gọi mạng
    assert real.when_of(sg) == mail_events_stub.when_of(sg)
