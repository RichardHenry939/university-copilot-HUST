# -*- coding: utf-8 -*-
"""(v1.00.27) D-3 mất "Sẽ đi / Bỏ" khi bấm đúng lúc luồng mail chạy; D-4 dữ liệu Gemini lạ làm tắc hàng đợi thư."""
import re
import alerts
import mail_events as me
import uc_state


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(me, 'STORE', tmp_path / 'events.json')
    monkeypatch.setattr(alerts, 'STATE', tmp_path / 'alerts.json')
    monkeypatch.setattr(uc_state, 'ERRLOG', tmp_path / 'err.log')
    monkeypatch.setattr(alerts, 'active', lambda: [])
    uc_state.save_json(me.STORE, {'events': {'ev1': {'ten': 'Giao lưu', 'chang': {'s1': {'ten': 'Buổi 1', 'ngay': '2026-10-20'}},
                                                     'changes': [], 'ack': {}}}, 'processed': ['m1']})


def test_mail_loop_does_not_overwrite_choice(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    held = me.load()                                   # luồng mail đọc rồi chờ Gemini…
    alerts.ack('ev1', 'Sẽ đi', stage='s1')             # …bạn bấm "Sẽ đi"
    held['processed'].append('m2'); me.save(held)      # …luồng mail ghi bản đang giữ
    st = me.load()
    assert st['events']['ev1']['ack']['s1']['choice'] == 'Sẽ đi'
    assert st['processed'] == ['m1', 'm2']


def test_mute_survives_alerts_tick(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    uc_state.save_json(alerts.STATE, {'sent': {}})
    held = alerts._load()                              # tick đang gửi toast…
    alerts.ack('dl|abc', 'Tắt nhắc')                   # …bạn bấm "Tắt nhắc"
    held['sent']['x'] = 1; alerts._save(held)
    assert 'dl|abc' in alerts._load()['dl_mute']


def test_sane_cleans_odd_gemini_output():
    x = me._sane([{'lien_quan': True, 'chang': ['chuỗi lạ', {'ten': 'Vòng 1', 'ngay': 'null', 'gio': '20h00', 'huy': 'false'},
                                                 {'ten': 'Vòng 2', 'ngay': '2026-11-31', 'gio': '25:00'}]}])
    assert x['chang'] == [{'ten': 'Vòng 1', 'ngay': None, 'gio': '20:00', 'huy': False}, {'ten': 'Vòng 2', 'ngay': None, 'gio': None, 'huy': False}]
    assert me.fmt({'ten': 'x', 'ngay': 'null'}) == 'chưa rõ ngày'


def test_bad_message_skipped_after_three_tries(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    uc_state.save_json(me.STORE, {'events': {}, 'processed': []})
    mails = [{'Id': 'A', 'Subject': 'Hoạt động A', 'Body': 'x', 'FromName': 'a', 'FromAddress': 'a@hust.edu.vn', 'ReceivedDateTime': '2026-10-14T01:00:00Z'},
             {'Id': 'B', 'Subject': 'Hoạt động B', 'Body': 'x', 'FromName': 'b', 'FromAddress': 'b@hust.edu.vn', 'ReceivedDateTime': '2026-10-14T02:00:00Z'}]
    monkeypatch.setattr(me, 'sources', lambda: mails)
    monkeypatch.setattr(me, 'HINT', re.compile('.'))
    monkeypatch.setattr(me, 'SKIP_SENDERS', [])
    def fake(prompt, **k):
        if 'Hoạt động A' in prompt: raise ValueError('JSON hỏng')
        return {'lien_quan': True, 'ten_su_kien': 'B', 'chang': [{'ten': 'Hạn', 'ngay': '2026-10-21'}]}
    monkeypatch.setattr(me, 'gemini', fake)
    for _ in range(3): me.process()
    st = me.load()
    assert st['processed'] == ['A', 'B'] and [x['id'] for x in st['skipped']] == ['A']
