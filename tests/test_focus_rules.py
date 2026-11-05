# -*- coding: utf-8 -*-
"""focus_rules.tick (chủ 03/11): khung thể dục = dừng bắt buộc + gỡ chặn; giải trí dừng sạch; pause tay giữ chặn."""
import datetime as dt

import pytest

import focus_rules as F
import wallet as W

T0 = dt.datetime(2026, 11, 3, 17, 0, tzinfo=W.TZ)
m = lambda k: dt.timedelta(minutes=k)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(W, 'FILE', tmp_path / 'wallet.json')
    monkeypatch.setattr(W, 'SIGNAL_CFG', tmp_path / 'chua-cau-hinh.json')
    monkeypatch.setattr(F, 'STATE', tmp_path / 'fr.json')
    color = {'v': ('white', '')}
    monkeypatch.setattr(F, 'color_now', lambda post, now: color['v'])
    sent = []
    return color, (lambda t, b: sent.append(t)), sent


def test_the_duc_dung_bat_buoc_ca_khi_dang_pause_tay(env):
    color, notify, sent = env
    st = W.empty(); W.start_focus(st, 50, '', T0); W.pause(st, T0 + m(5)); W.save(st)
    color['v'] = ('red', 'giờ thể dục (17:10–17:40)')
    assert F.tick(None, notify, T0 + m(10)) == ('pause', 'giờ thể dục (17:10–17:40)')
    assert W.load()['active']['forced']
    assert F.tick(None, notify, T0 + m(11)) is None and len(sent) == 1   # không báo lại mỗi phút


def test_the_duc_ket_thuc_giai_tri_chi_tru_phut_da_dung(env):
    color, notify, _ = env
    st = W.empty(); W._add(st, 'focus', 30, T0); W.start_fun(st, T0); W.save(st)
    color['v'] = ('red', 'giờ thể dục')
    assert F.tick(None, notify, T0 + m(7))[0] == 'fun_end'
    st = W.load()
    assert st['active'] is None and W.balance(st) == 23


def test_gio_hoc_tap_trung_chay_tiep(env):   # (chủ 05/11) xanh biển + tập trung = xanh nõn chuối, không dừng
    color, notify, sent = env
    st = W.empty(); W.start_focus(st, 50, '', T0); W.save(st)
    color['v'] = ('blue', 'giờ học')
    assert F.tick(None, notify, T0 + m(3)) is None and not sent
    assert not W.load()['active'].get('paused_at')


def test_gio_ngu_ket_thuc_phien(env):   # (chủ 05/11) vàng: kết thúc luôn phiên
    color, notify, _ = env
    st = W.empty(); W.start_focus(st, 50, '', T0); W.save(st)
    color['v'] = ('yellow', 'giờ ngủ trưa (13:00–15:00)')
    assert F.tick(None, notify, T0 + m(30))[0] == 'end'
    st = W.load()
    assert st['active'] is None and st['sessions'][-1]['cut'] == 'giờ ngủ' and W.balance(st) == 5   # 1 khối 25 phút


def test_gio_an_tu_dung_roi_tu_tiep(env):   # (chủ 05/11) tím: tự dừng, hết tím tự tiếp tục
    color, notify, sent = env
    st = W.empty(); W.start_focus(st, 50, '', T0); W.save(st)
    color['v'] = ('purple', 'giờ ăn tối (19:00–20:00)')
    assert F.tick(None, notify, T0 + m(3))[0] == 'pause'
    assert F.tick(None, notify, T0 + m(4)) is None   # không dừng / báo lại
    a = W.load()['active']; assert a['paused_at'] and a['auto'] == 'purple'
    color['v'] = ('white', '')
    assert F.tick(None, notify, T0 + m(10)) == ('resume', 'purple')
    a = W.load()['active']; assert not a['paused_at'] and 'auto' not in a and len(sent) == 2


def test_the_duc_het_khung_tu_tiep(env):
    color, notify, _ = env
    st = W.empty(); W.start_focus(st, 50, '', T0); W.save(st)
    color['v'] = ('red', 'giờ thể dục'); F.tick(None, notify, T0 + m(2))
    color['v'] = ('white', '')
    assert F.tick(None, notify, T0 + m(25)) == ('resume', 'red')


def test_gio_an_khi_ban_tu_dung_van_giu_nguyen(env):
    color, notify, sent = env
    st = W.empty(); W.start_focus(st, 50, '', T0); W.pause(st, T0 + m(5)); W.save(st)
    color['v'] = ('purple', 'giờ ăn tối (19:00–20:00)')
    F.tick(None, notify, T0 + m(10))
    assert W.by_user(W.load()['active']) and not sent
