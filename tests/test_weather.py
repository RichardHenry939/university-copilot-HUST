# -*- coding: utf-8 -*-
"""Điểm "phù hợp để ra ngoài" (weather.score): dữ liệu giả, không gọi mạng."""
import datetime as dt

import weather as W

DAY = dt.datetime(2026, 11, 2, 16, 0, tzinfo=W.TZ)
NICE = {'feels': 25, 'rain': 0, 'rainProb': 0, 'code': 1, 'uv': 3, 'aqi': 40, 'wind': 10, 'day': True}


def test_troi_dep_ban_ngay_100():
    assert W.score(NICE, DAY) == (100, [])


def test_aqi_kem_tru_manh():
    s, why = W.score(dict(NICE, aqi=170), DAY)
    assert s == 40 and 'AQI 170' in why[0]


def test_nong_va_mua():
    s, _ = W.score(dict(NICE, feels=35, rain=1.2), DAY)
    assert s == 100 - 30 - 40


def test_gio_ngu_luon_0():
    assert W.score(NICE, dt.datetime(2026, 11, 2, 22, 30, tzinfo=W.TZ)) == (0, ['giờ ngủ (22:00–06:00)'])
