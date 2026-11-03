"""(03/11) ictsv_login.red_fast_due: quanh khung đỏ đọc app mỗi 3 phút, tới khi đã đọc được sau lúc hết khung."""
import datetime as dt
import ictsv_login as L

K = {'slot': {'start': '2026-11-03T18:26+07:00', 'end': '2026-11-03T18:46+07:00'}}


def t(h, m):
    return dt.datetime(2026, 11, 3, h, m, tzinfo=dt.timezone(dt.timedelta(hours=7))).timestamp()


def test_before_slot_not_fast():
    assert not L.red_fast_due(K, 0, t(18, 20))


def test_in_slot_every_3_min():
    assert L.red_fast_due(K, t(18, 30), t(18, 34))
    assert not L.red_fast_due(K, t(18, 33), t(18, 34))


def test_after_slot_until_read_after_end():
    assert L.red_fast_due(K, t(18, 40), t(18, 50))
    assert not L.red_fast_due(K, t(18, 47), t(18, 55))


def test_no_slot():
    assert not L.red_fast_due({'slot': {'start': None, 'end': None}}, 0, t(18, 30))
    assert not L.red_fast_due({}, 0, t(18, 30))
