# -*- coding: utf-8 -*-
"""v1.00.52: bản chép lời Teams (.vtt) thay recorder cho lớp lý thuyết; tải bù Drive."""
import datetime as dt

import teams_transcripts as T

VTT = """WEBVTT

c748/375-0
00:00:04.686 --> 00:00:07.286
Rồi đầu tiên tôi xin lỗi
hơi muộn một chút.

c748/383-0
00:00:08.036 --> 00:00:11.636
Giờ chúng ta sang bài mới.

c748/390-0
00:01:30.000 --> 00:01:32.500
<v Nguyễn Văn A>Em hỏi ạ</v>

c748/391-0
00:01:32.900 --> 00:01:34.000
<v Nguyễn Văn A>thầy ơi</v>
"""


def test_parse_vtt_times_text_speaker():
    c = T.parse_vtt(VTT)
    assert [x['start'] for x in c] == [4.7, 8.0, 90.0, 92.9]
    assert c[0]['text'] == 'Rồi đầu tiên tôi xin lỗi hơi muộn một chút.' and c[0]['speaker'] == ''
    assert c[2] == {'start': 90.0, 'end': 92.5, 'text': 'Em hỏi ạ', 'speaker': 'Nguyễn Văn A'}


def test_merge_same_speaker_and_text_format():
    k = T.merge(T.parse_vtt(VTT))
    assert len(k) == 2   # 2 dòng đầu liền nhau (cách 0.75 s) gộp; 2 dòng của A gộp
    assert T.to_text(k).splitlines() == [
        '[00:04] Rồi đầu tiên tôi xin lỗi hơi muộn một chút. Giờ chúng ta sang bài mới.',
        '[01:30] Nguyễn Văn A: Em hỏi ạ thầy ơi']


def test_started_at_from_teams_name():
    s = T.started_at('Meeting in General-20261102_083911-Meeting Recording 1.mp4', '2026-11-02T01:39:00Z')
    assert s == dt.datetime(2026, 11, 2, 8, 39, 11, tzinfo=T.TZ)
    s = T.started_at('x.mp4', '2026-11-02T01:39:00Z')
    assert s.hour == 8 and s.minute == 39


def test_theory_teams_only():
    assert T.THEORY.search('2026.1 - Nhập môn CNTT&TT - 171981')
    assert T.THEORY.search('Giải tích 4-6 Sáng thứ 2') and T.THEORY.search('OMO-SángT2-T1-3 171985 và 171992')
    for t in ('20261_NMLT_IT1108_171995', 'QUÂN SỰ_ĐẠI ĐỘI 3_ĐỢT 4_2026.1', 'BT_MI1141_20261'):
        assert not T.THEORY.search(t)


def test_due_window(monkeypatch, tmp_path):
    monkeypatch.setattr(T, 'STATE', tmp_path / 's.json')
    assert T.due(dt.datetime(2026, 11, 2, 10, 0, tzinfo=T.TZ))
    assert not T.due(dt.datetime(2026, 11, 2, 23, 30, tzinfo=T.TZ))   # giờ ngủ: không mở trình duyệt
    T.save({'items': {}, 'last_run': '2026-11-02T10:00:00+07:00'})
    assert not T.due(dt.datetime(2026, 11, 2, 10, 20, tzinfo=T.TZ))
    assert T.due(dt.datetime(2026, 11, 2, 10, 31, tzinfo=T.TZ))


# ---- 02/11 tối: thể dục trơ ra sau khi đi bộ (đọc app chỉ mỗi giờ; bảng theo ngày chỉ có số ước tính CTSV)
import walk, ictsv_login


def test_days_use_real_app_steps():
    ctsv = [{'DayRun': '2026-11-01 00:00:00', 'Distance': 421.0, 'km': 0.42, 'steps': 583}]
    app = {'2026-11-01': {'km': 1.47, 'steps': 2036}, '2026-11-02': {'km': 1.6, 'steps': 2210}}
    d = {r['DayRun'][:10]: r for r in walk.merge_days(ctsv, app)}
    assert d['2026-11-01']['steps'] == 583 and d['2026-11-01']['appSteps'] == 2036   # km giải tính giữ nguyên
    assert d['2026-11-02']['appSteps'] == 2210 and d['2026-11-02']['km'] == 0      # ngày chỉ có trong app vẫn hiện


def test_probe_once_right_after_red_slot():
    t = lambda h, m: dt.datetime(2026, 11, 2, h, m, tzinfo=T.TZ).timestamp()
    sl = {'date': '2026-11-02', 'slot': {'start': '2026-11-02T17:44+07:00', 'end': '2026-11-02T18:04+07:00'}}
    assert not ictsv_login.after_slot_due(sl, t(17, 36), t(18, 3))    # chưa hết khung
    assert ictsv_login.after_slot_due(sl, t(17, 36), t(18, 7))        # hết khung 3 phút mà chưa đọc -> đọc ngay
    assert not ictsv_login.after_slot_due(sl, t(18, 7), t(18, 20))    # đã đọc sau khung -> thôi
    assert not ictsv_login.after_slot_due({}, t(17, 36), t(18, 7))


def test_zero_read_does_not_wipe_month():
    import walk_app
    old = {'month': '2026-11', 'month_total_steps': 2036, 'days': {'2026-11-01': {'steps': 2036}}}
    assert walk_app.looks_empty({'month': '2026-11', 'total_steps': 0, 'days': {}}, old)       # phiên hết hạn: không ghi đè
    assert walk_app.looks_empty({'month': None, 'total_steps': None, 'days': {}}, old)
    assert not walk_app.looks_empty({'month': '2026-11', 'total_steps': 4200, 'days': {'2026-11-02': {}}}, old)
    assert not walk_app.looks_empty({'month': '2026-12', 'total_steps': 0, 'days': {}}, {})       # đầu tháng mới, chưa đi: hợp lệ


def test_urgent_only_when_course_has_upcoming_exam():
    now = dt.datetime(2026, 11, 2, 19, 0, tzinfo=T.TZ)
    ex = [{'code': 'MI1111', 'start': '2026-11-08T08:10:00+07:00'}, {'code': 'MI1141', 'start': '2026-11-08T14:25:00+07:00'}]
    assert T.course_of('Giải tích 4-6 Sáng thứ 2') == 'MI1111' and T.course_of('OMO-SángT2-T1-3 171985 và 171992') == 'MI1141'
    assert T.course_of('2026.1 - Nhập môn CNTT&TT - 171981') == 'IT2000'
    assert T.urgent('MI1111', now, ex) and T.urgent('MI1141', now, ex)
    assert not T.urgent('IT2000', now, ex)                                       # chưa có lịch thi -> không gấp
    assert not T.urgent('MI1111', dt.datetime(2026, 11, 9, 8, 0, tzinfo=T.TZ), ex)   # thi xong rồi -> hết gấp
    assert T.night(dt.datetime(2026, 11, 2, 22, 0, tzinfo=T.TZ)) and T.night(dt.datetime(2026, 11, 3, 5, 59, tzinfo=T.TZ))
    assert not T.night(now)


# ---- Fitness (chủ 02/11 tối): thảm / sàn (+ ghế), <= 20 phút, tránh DOMS
import fitness as F


def test_fitness_clean_gear_and_time_cap():
    ex = lambda n, m: {'name_en': n, 'name_vi': '', 'sets': 2, 'reps': '8', 'rest_sec': 60, 'minutes': m, 'cue': 'keep core tight during the move', 'youtube_query': n}
    raw = {'focus': ['toàn thân'], 'warmup': [ex('March in place', 3)],
           'main': [ex('Knee push-up', 4), ex('Chair dip', 3), ex('Dumbbell row', 4), ex('Wall sit', 3), ex('Glute bridge', 4), ex('Bodyweight squat', 4), ex('Plank', 4)],
           'cooldown': [ex('Child pose', 3)]}
    c = F.clean(raw)
    names = [x['name_en'] for x in c['main']]
    assert 'Dumbbell row' not in names and 'Wall sit' not in names    # cần dụng cụ / tường
    assert 'Chair dip' in names                                        # ghế được (chủ 02/11 21:25)
    assert c['total_min'] <= F.MAX_MIN and 'Plank' in c['dropped']     # quá 20 phút -> bỏ bài chính cuối
    assert 'Knee push-up' in names                                     # câu "during" không bị nhầm là "ring"


def test_fitness_profile_derived():
    d = F.derived({'weight_kg': 80, 'height_cm': 180, 'fat_pct': 20, 'muscle_kg': 30})
    assert d['bmi'] == 24.7 and d['fat_kg'] == 16.0 and d['steps_per_km'] == 1339
