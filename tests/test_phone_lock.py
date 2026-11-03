# -*- coding: utf-8 -*-
import datetime as dt, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import phone_lock as pl

TZ = pl.TZ


def at(h, m=0): return dt.datetime(2026, 11, 3, h, m, tzinfo=TZ)


def test_mode_night_core_always():
    assert pl.mode(at(22, 0), focus=False, nap=False) == 'night'
    assert pl.mode(at(5, 59), focus=False, nap=False) == 'night'
    assert pl.mode(at(6, 0), focus=False, nap=False) is None


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


def test_wanted_never_touches_protected_and_spares_youtube_in_focus():
    inst = {'com.facebook.katana', 'com.facebook.orca', 'com.bk.ctsv', 'uni.hust.ehust', 'com.android.chrome',
            'com.google.android.youtube', 'com.android.vending'}
    night = pl.wanted('night', inst)
    assert night == {'com.facebook.katana', 'com.android.chrome', 'com.google.android.youtube', 'com.android.vending'}
    assert 'com.google.android.youtube' not in pl.wanted('focus', inst)
    assert pl.wanted(None, inst) == set()


def test_tick_locks_then_unlocks_only_own(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, 'STATE', tmp_path / 'pl.json')
    calls = []
    inst = 'package:com.facebook.katana\npackage:com.bk.ctsv\npackage:com.android.chrome\n'
    def fake(*a, timeout=20):
        calls.append(a)
        if a[0] == 'get-state': return 0, 'device'
        if a[1:3] == ('pm', 'list'): return 0, inst
        if a[1:4] == ('cmd', 'package', 'suspend'): return 0, f"Package {a[-1]} new suspended state: true"
        return 0, ''
    monkeypatch.setattr(pl, 'adb', fake)
    r = pl.tick(at(23), m='night')
    assert r['locked'] == ['com.android.chrome', 'com.facebook.katana']
    assert not any('com.bk.ctsv' in c for c in calls)
    r = pl.tick(at(7), m=None)
    assert r['unlocked'] == ['com.android.chrome', 'com.facebook.katana']
    assert json.loads((tmp_path / 'pl.json').read_text())['locked'] == {}


def test_tick_falls_back_to_disable(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, 'STATE', tmp_path / 'pl.json')
    def fake(*a, timeout=20):
        if a[0] == 'get-state': return 0, 'device'
        if a[1:3] == ('pm', 'list'): return 0, 'package:com.facebook.katana\n'
        if a[1:4] == ('cmd', 'package', 'suspend'): return 255, 'Security exception'
        if a[1:3] == ('pm', 'disable-user'): return 0, 'Package com.facebook.katana new state: disabled-user'
        return 0, ''
    monkeypatch.setattr(pl, 'adb', fake)
    pl.tick(at(23), m='night')
    assert json.loads((tmp_path / 'pl.json').read_text())['locked'] == {'com.facebook.katana': 'disable'}


def test_tick_no_device(monkeypatch):
    monkeypatch.setattr(pl, 'adb', lambda *a, timeout=20: (1, 'error: device offline'))
    assert pl.tick(at(23)) == {'device': False}
