# -*- coding: utf-8 -*-
import datetime as dt, json, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import phone_lock as pl

TZ = pl.TZ
EMU, PHONE = 'emulator-5554', 'R5CX123'


def at(h, m=0): return dt.datetime(2026, 11, 3, h, m, tzinfo=TZ)


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, 'STATE', tmp_path / 'pl.json')
    monkeypatch.setattr(pl, 'APPS', tmp_path / 'apps.json')
    monkeypatch.setattr(pl, 'LOG', tmp_path / 'pl.log')



@pytest.fixture(autouse=True)
def _khong_co_khoa_tam(tmp_path, monkeypatch):   # (05/11) cờ khoá đêm tạm / khoá giờ học thật trên máy không được lọt vào test
    monkeypatch.setattr(pl, 'FORCE', tmp_path / 'force.json'); monkeypatch.setattr(pl, 'CLASS', tmp_path / 'class.json')


def test_khoa_gio_hoc_cao_nhat_ban_ngay(tmp_path):
    pl.CLASS.write_text('{"until": "2026-11-05T17:30:00+07:00"}', encoding='utf-8')
    t = lambda h, m: dt.datetime(2026, 11, 5, h, m, tzinfo=pl.TZ)
    assert pl.mode(t(16, 0), focus=True, nap=True) == 'class'
    assert pl.mode(t(17, 30), focus=False, nap=False) == 'default'

def test_mode_night_core_always():
    assert pl.mode(at(22, 0), focus=False, nap=False) == 'night'
    assert pl.mode(at(5, 59), focus=False, nap=False) == 'night'
    assert pl.mode(at(6, 0), focus=False, nap=False) == 'default'


def test_mode_nap_and_focus():
    assert pl.mode(at(13, 30), focus=True, nap=True) == 'nap'
    assert pl.mode(at(10, 0), focus=True, nap=False) == 'focus'


def test_nap_signal_stale_or_other_day(tmp_path, monkeypatch):
    f = tmp_path / 'nap.json'; monkeypatch.setattr(pl, 'NAP', f)
    f.write_text(json.dumps({'date': '2026-11-03', 'at': at(13, 0).isoformat(), 'nap_spans': [['13:00', '15:00']]}))
    assert pl._nap_on(at(13, 5)) is True
    assert pl._nap_on(at(13, 20)) is False          # tín hiệu cũ > 10 phút
    f.write_text(json.dumps({'date': '2026-11-02', 'at': at(13, 0).isoformat(), 'nap_spans': [['13:00', '15:00']]}))
    assert pl._nap_on(at(13, 5)) is False


INST = {'com.facebook.katana', 'com.facebook.orca', 'com.bk.ctsv', 'uni.hust.ehust', 'com.android.chrome',
        'com.google.android.youtube', 'com.android.vending', 'com.linkedin.android', 'com.game.x', 'com.bank.y'}


def test_luat_4_che_do_cua_chu():
    # (chủ 04/11, 05/11) mặc định: chỉ MXH; tập trung: + YouTube, store, game; trưa: như tập trung, chừa Messenger;
    # đêm: tất, kể cả Messenger. Luôn chừa LinkedIn, iCTSV, eHUST, ngân hàng.
    g = ('com.game.x',)
    assert pl.wanted('default', INST, g) == {'com.facebook.katana', 'com.google.android.youtube'}   # (04/11) app YouTube gốc khoá, chừa ReVanced
    rv = 'app.revanced.android.youtube'   # (chủ 05/11) ReVanced: chừa ở mặc định, khoá từ tập trung trở lên
    assert rv not in pl.wanted('default', INST | {rv}, g) and rv in pl.wanted('focus', INST | {rv}, g)
    # (04/11) trình duyệt thường không tạm dừng (chặn tên miền qua laptop); Tor mới khoá cứng
    assert pl.wanted('focus', INST, g) == {'com.facebook.katana', 'com.google.android.youtube', 'com.android.vending', 'com.game.x'}
    assert 'org.torproject.torbrowser' in pl.wanted('focus', INST | {'org.torproject.torbrowser'}, g)
    assert 'org.torproject.torbrowser' not in pl.wanted('default', INST | {'org.torproject.torbrowser'}, g)
    assert pl.wanted('nap', INST | {'app.revanced.android.youtube'}, g) == pl.wanted('focus', INST, g) | {'app.revanced.android.youtube'}
    assert pl.wanted('night', INST, g) == pl.wanted('nap', INST, g) | {'com.facebook.orca'}
    for m in ('default', 'focus', 'nap', 'night'):
        assert not pl.wanted(m, INST, g) & {'com.linkedin.android', 'com.bk.ctsv', 'uni.hust.ehust', 'com.bank.y'}


def fake_adb(devs, inst, calls, suspend_ok=True):
    def f(serial, *a, timeout=20):
        calls.append((serial, *a))
        if a[0] == 'devices': return 0, 'List of devices attached\n' + ''.join(f'{d}\tdevice\n' for d in devs)
        if a[1:3] == ('pm', 'list'): return 0, ''.join(f'package:{p}\n' for p in inst)
        if a[1:4] == ('cmd', 'package', 'suspend'):
            return (0, f'Package {a[-1]} new suspended state: true') if suspend_ok else (255, 'Security exception')
        if a[1:3] == ('pm', 'disable-user'): return 0, f'Package {a[-1]} new state: disabled-user'
        return 0, ''
    return f


def test_tick_locks_then_unlocks_only_own(monkeypatch):
    calls = []
    monkeypatch.setattr(pl, 'adb', fake_adb([EMU], ['com.facebook.katana', 'com.bk.ctsv', 'com.android.chrome'], calls))
    r = pl.tick(at(23), m='night')
    assert r['locked'] == [f'{EMU}:com.facebook.katana']        # Chrome không bị tạm dừng nữa
    assert not any('com.bk.ctsv' in c for c in calls)
    r = pl.tick(at(7), m='default')
    assert r['unlocked'] == []                                   # MXH vẫn khoá ở mặc định
    assert json.loads(pl.STATE.read_text())['devices'][EMU]['locked'] == {'com.facebook.katana': 'suspend'}


def test_dien_thoai_chua_duyet_thi_khong_dung(monkeypatch):
    calls = []
    monkeypatch.setattr(pl, 'adb', fake_adb([EMU, PHONE], ['com.facebook.katana'], calls))
    pl.tick(at(23), m='night')
    assert not any(c[0] == PHONE for c in calls)
    pl.APPS.write_text(json.dumps({'devices': [PHONE]}))
    r = pl.tick(at(23, 1), m='night')
    assert r['locked'] == [f'{PHONE}:com.facebook.katana']


def test_tick_falls_back_to_disable(monkeypatch):
    monkeypatch.setattr(pl, 'adb', fake_adb([EMU], ['com.facebook.katana'], [], suspend_ok=False))
    pl.tick(at(23), m='night')
    assert json.loads(pl.STATE.read_text())['devices'][EMU]['locked'] == {'com.facebook.katana': 'disable'}


def test_doc_trang_thai_dang_cu():
    pl.STATE.write_text(json.dumps({'locked': {'com.android.chrome': 'suspend'}, 'mode': 'focus'}))
    assert pl._load()['devices'][EMU]['locked'] == {'com.android.chrome': 'suspend'}


def test_tick_no_device(monkeypatch):
    monkeypatch.setattr(pl, 'adb', lambda serial, *a, timeout=20: (0, 'List of devices attached\n'))
    assert pl.tick(at(23)) == {'device': False}
