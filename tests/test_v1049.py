# -*- coding: utf-8 -*-
"""v1.00.49: thông báo từng việc (tiêu đề tên + giờ, nhắc trước giờ ngủ), lịch thi -> ôn thi hằng ngày (trừ TDTT / QP-AN),
đối chiếu eHUST (Teams > eHUST > qldt), số bước theo app iCTSV."""
import datetime as dt, sys, types

sys.modules.setdefault('keyring', types.SimpleNamespace(get_password=lambda *a: None, set_password=lambda *a: None, delete_password=lambda *a: None))

import alerts, deadlines as D, exam_watch, ehust_check, walk_app

TZ = dt.timezone(dt.timedelta(hours=7))


def test_head_has_name_and_time():
    w = dt.datetime(2026, 11, 2, 23, 0, tzinfo=TZ)
    assert alerts.head('Bài 10-35 · MI1111', w) == 'Bài 10-35 · MI1111 — hạn 23:00 2/11'


def test_night_slots_before_sleep():
    w = dt.datetime(2026, 11, 2, 23, 0, tzinfo=TZ)
    ts = [t.strftime('%H:%M') for t in alerts.night_slots(w, D.MARKS['Môn học'])]
    assert ts and ts[-1] == '21:30' and all(t < '22:00' for t in ts)
    assert alerts.night_slots(dt.datetime(2026, 11, 2, 15, 0, tzinfo=TZ)) == []
    early = alerts.night_slots(dt.datetime(2026, 11, 3, 2, 0, tzinfo=TZ))   # hạn 02:00 -> nhắc trong ngày thức hôm trước
    assert {t.date() for t in early} == {dt.date(2026, 11, 2)}


def test_exam_exempt_rules():
    ex = lambda t, n: {'title': t, 'notes': n, 'start': '2026-12-20T08:00:00+07:00'}
    assert not exam_watch.exempt(ex('Thi: Giải tích III', 'MI1131 · CK'))
    assert exam_watch.exempt(ex('Thi: Lý luận TDTT', 'PE1014 · CK'))
    assert exam_watch.exempt(ex('Thi: Đường lối quốc phòng', 'MIL1110 · CK'))
    assert exam_watch.exempt(ex('Thi: Giáo dục thể chất A', ' · CK'))


def test_review_daily_until_exam(monkeypatch):
    evs = [{'kind': 'Exam', 'title': 'Thi GK: Giải tích I', 'notes': 'MI1111 · GK', 'start': '2026-11-08T08:10:00+07:00', 'location': 'D5-101'},
           {'kind': 'Exam', 'title': 'Thi: Lý luận TDTT', 'notes': 'PE1014 · CK', 'start': '2026-11-09T07:00:00+07:00', 'location': ''}]
    import fami
    monkeypatch.setattr(fami, 'exam_events', lambda: evs)
    r = exam_watch.review(today='2026-11-02')
    assert [x['title'] for x in r] == ['Ôn thi định kỳ hằng ngày môn Giải tích I (MI1111)'] and r[0]['locked']
    assert exam_watch.review(today='2026-11-09') == []   # qua ngày thi thì hết


def test_exam_alarm_once_per_exam(monkeypatch, tmp_path):
    import fami
    monkeypatch.setattr(fami, 'exam_events', lambda: [{'kind': 'Exam', 'title': 'Thi GK: Đại số', 'notes': 'MI1141 · GK', 'start': '2026-11-08T14:25:00+07:00', 'location': 'D6-208'}])
    monkeypatch.setattr(exam_watch, 'SEEN', tmp_path / 'seen.json')
    got = []
    exam_watch.tick(lambda t, x: got.append(t)); exam_watch.tick(lambda t, x: got.append(t))
    assert len(got) == 1 and 'Đại số' in got[0] and '14:25' in got[0]


def test_ehust_parse_and_teams_wins():
    s = ehust_check.parse_slot('06:45\n09:10\n171992 - Đại số\nMã học phần: MI1141\nOnline\nSáng Thứ 2, Tiết 1 - 3\nTuần 10\nGiảng viên: A')
    assert s['code'] == 'MI1141' and s['room'] == 'Online' and s['start'] == '06:45'
    eh = {'2026-10-31': [{'start': '08:25', 'end': '10:05', 'code': 'IT2000', 'room': 'B1-103'}], '2026-11-01': []}
    uc = {'2026-10-31': [], '2026-11-01': [{'start': '09:00', 'end': '10:30', 'code': 'IT2000', 'room': 'B1', 'teams': True}]}
    d = ehust_check.compare(eh, uc, sorted(eh), {('2026-10-29', 'IT2000')})
    assert len(d) == 2 and all(x['theo_teams'] for x in d)   # Teams dời buổi -> không báo lệch
    d2 = ehust_check.compare({'2026-11-05': []}, {'2026-11-05': [{'start': '16:00', 'end': '17:30', 'code': 'IT2000', 'room': 'Online', 'teams': False}]}, ['2026-11-05'])
    assert len(d2) == 1 and not d2[0]['theo_teams']


def test_walk_app_parse_runs():
    screen = ['Tổng quan 11-2026', 'Tổng bước chân', 'Tốc độ TB (/km)', '2,036', '14:02',
              'Ngày 1 Tháng 11 2026\n1.47 km - Tổng thời gian: 20:39',
              '0.42 km\n528 bước\n19:09\nT.gian: 00:04:35\nTốc độ: 10:53 /km',
              '1.02 km\n1,472 bước\n18:54\nT.gian: 00:15:36\nTốc độ: 15:13 /km',
              '0.03 km\n36 bước\n18:53\nT.gian: 00:00:28\nTốc độ: 18:16 /km']
    r = walk_app.parse([screen, screen])   # cuộn trùng màn -> không đếm đôi
    d = r['days']['2026-11-01']
    assert r['month'] == '2026-11' and r['total_steps'] == 2036 and d['steps'] == 2036 and len(d['runs']) == 3
    assert [x['at'] for x in d['runs']] == ['18:53', '18:54', '19:09']


def test_nap_yellow_only_blue_overrides():
    import nap
    ev = lambda s, e, k='Class': {'kind': k, 'title': 'X', 'start': f'2026-11-06T{s}:00+07:00', 'end': f'2026-11-06T{e}:00+07:00'}
    assert nap.spans([ev('12:30', '17:30')], '2026-11-06')[0] == []                      # lab cả chiều: không ngủ trưa
    assert nap.spans([ev('14:00', '16:00')], '2026-11-06')[0] == [['13:00', '14:00']]
    assert nap.spans([ev('13:30', '14:15', 'Exam')], '2026-11-06')[0] == [['13:00', '13:30'], ['14:15', '15:00']]
    full, _ = nap.spans([ev('21:00', '22:30')], '2026-11-06', nap.YELLOW)
    assert full == [['00:00', '06:00'], ['13:00', '15:00'], ['22:30', '24:00']]
