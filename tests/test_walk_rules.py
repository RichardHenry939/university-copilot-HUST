# -*- coding: utf-8 -*-
"""(chủ 07/11) Khung thể dục sáng lùi tối đa 3 lần, lần 4 sang 17h; đi đủ số phút của khung thì khung tự tắt."""
import datetime as dt

import walk as W

D = '2026-11-07'
TZ = W.TZ
at = lambda h, m: dt.datetime(2026, 11, 7, h, m, tzinfo=TZ)
P = lambda h, m: {'start': f'{D}T{h:02d}:{m:02d}+07:00', 'end': f'{D}T{h:02d}:{m + 20:02d}+07:00'}


def test_lui_sang_toi_da_3_lan():
    assert W.next_after([P(6, 0), P(6, 26), P(6, 48)], at(7, 10), D) == at(7, 10)   # lần lùi thứ 3: vẫn sáng


def test_lan_4_sang_17h():
    assert W.next_after([P(6, 0), P(6, 26), P(6, 48), P(7, 10)], at(7, 32), D) == at(17, 0)


def test_khung_chieu_khong_tinh_la_lui_sang():
    assert W.next_after([P(6, 0), P(17, 0)], at(17, 30), D) == at(17, 30)


def test_phut_di_bo():
    day = {'runs': [{'start': f'{D}T06:00:00+07:00', 'end': f'{D}T06:12:30+07:00'},
                    {'start': f'{D}T06:20:00+07:00', 'end': f'{D}T06:28:00+07:00'}]}
    assert W._walked_min(day) == (20, at(6, 28))
    assert W._walked_min(None) == (0, None)
