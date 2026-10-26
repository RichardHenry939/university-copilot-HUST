# -*- coding: utf-8 -*-
"""v1.00.37: nhắc ngoại khoá bớt dày, tắt được cả loại; vòng sau của cuộc thi không tự coi là bắt buộc."""
import datetime as dt

import alerts
import extracurricular as X
import mail_events as me

TZ = dt.timezone(dt.timedelta(hours=7))
NOW = dt.datetime(2026, 10, 26, 10, 0, tzinfo=TZ)


def test_vong_sau_chi_nhac_khi_ban_bam_se_di():
    e = {'must': True}
    assert me.must_remind(e, {'ten': 'Vòng 1'}) is True
    assert me.must_remind(e, {'ten': 'Vòng 2'}) is False
    assert me.must_remind(e, {'ten': 'Chung kết'}) is False
    assert me.must_remind(e, {'ten': 'Bán kết khu vực'}) is False
    assert me.must_remind(e, {'ten': 'Vòng 2'}, 'Sẽ đi') is True
    assert me.must_remind({'must': False}, {'ten': 'Họp lớp'}) is False
    assert me.must_remind({'must': True}, {'ten': 'Hạn đăng ký'}) is True


def test_han_minh_chung_chi_nhac_2_lan():
    data = {'items': [{'key': 'ctsv|mc|1', 'name': 'Sóng', 'loai': 'Hạn nộp minh chứng', 'han': '2026-10-27T00:00:00+07:00', 'status': 'Chờ xác nhận'}]}
    out = X.alert_items(data, NOW)
    assert out[0]['marks'] == (24 * 60, 180)


def test_tat_moi_nhac_ngoai_khoa(monkeypatch):
    st = {}
    monkeypatch.setattr(alerts, '_load', lambda: dict(st))
    monkeypatch.setattr(alerts, '_save', lambda s: (st.clear(), st.update(s)))
    item = {'key': 'ctsv|mc|1', 'name': 'Sóng', 'loai': 'Hạn nộp minh chứng', 'han': (NOW + dt.timedelta(hours=5)).isoformat(),
            'when': (NOW + dt.timedelta(hours=5)).isoformat(), 'marks': (1440, 180), 'status': 'Chờ xác nhận'}
    monkeypatch.setattr(X, 'load', lambda: {'items': []})
    monkeypatch.setattr(X, 'alert_items', lambda data, now: [item])
    assert len(alerts.extra_alerts(NOW)) == 1
    alerts.set_extra_off(True)
    assert st.get('extra_off') and alerts.extra_alerts(NOW) == []
    alerts.set_extra_off(False)
    assert 'extra_off' not in st and len(alerts.extra_alerts(NOW)) == 1
