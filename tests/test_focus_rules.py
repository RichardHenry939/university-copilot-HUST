# -*- coding: utf-8 -*-
"""focus_rules.tick (chủ 03/11): khung thể dục = dừng bắt buộc + gỡ chặn; giải trí dừng sạch; pause tay giữ chặn."""
import datetime as dt

import pytest

import focus_rules as F
import wallet as W


@pytest.fixture(autouse=True)
def _no_exam_off(tmp_path, monkeypatch):   # (06/11) không đọc file tắt tập trung thật
    monkeypatch.setattr(F, 'EXAM_OFF', tmp_path / 'off.json')

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


@pytest.fixture
def exam(env, monkeypatch):
    import exam_focus
    monkeypatch.setattr(exam_focus, 'subject', lambda today: 'Ôn thi: Giải tích I (08/11)' if today in ('2026-11-06', '2026-11-07') else None)
    return env


D1 = dt.datetime(2026, 11, 6, 9, 0, tzinfo=W.TZ)


def test_ngay_truoc_thi_tu_bat_khong_mssv(exam):
    color, notify, sent = exam
    r = F.tick(None, notify, D1)
    assert r == ('auto_start', 'Ôn thi: Giải tích I (08/11)') and len(sent) == 1
    a = W.load()['active']
    assert a['type'] == 'focus' and a['total'] == 175 and a['subject'].startswith('Ôn thi')
    assert F.tick(None, notify, D1 + m(1)) is None and len(sent) == 1   # không bật chồng


def test_ca_ngay_tu_6h_den_truoc_22h(exam):
    _, notify, _ = exam
    assert F.tick(None, notify, D1.replace(hour=5, minute=59)) is None
    assert F.tick(None, notify, D1.replace(hour=22, minute=0)) is None
    assert F.tick(None, notify, D1.replace(hour=6, minute=0))[0] == 'auto_start'


def test_ngay_thuong_khong_tu_bat(exam):
    _, notify, _ = exam
    assert F.tick(None, notify, dt.datetime(2026, 11, 5, 9, 0, tzinfo=W.TZ)) is None
    assert W.load().get('active') is None


def test_gio_hoc_van_bat_mau_khac_cho(exam):
    color, notify, _ = exam
    for c in ('purple', 'red', 'yellow'):
        color['v'] = (c, 'x')
        assert F.tick(None, notify, D1) is None
    color['v'] = ('blue', 'giờ học')
    assert F.tick(None, notify, D1)[0] == 'auto_start'


def test_phien_giai_tri_khong_dung_toi(exam):
    _, notify, _ = exam
    st = W.empty(); W._add(st, 'focus', 30, D1); W.start_fun(st, D1); W.save(st)
    assert F.tick(None, notify, D1 + m(1)) is None and W.load()['active']['type'] == 'fun'


def test_phien_het_gio_tu_bat_lai(exam):
    _, notify, _ = exam
    F.tick(None, notify, D1)
    assert F.tick(None, notify, D1 + m(176))[0] == 'auto_start'
    st = W.load()
    assert len(st['sessions']) == 1 and st['active']['start'] == W._iso(D1 + m(176))


def test_vang_ket_thuc_roi_het_vang_tu_bat_lai(exam):
    color, notify, _ = exam
    F.tick(None, notify, D1)
    color['v'] = ('yellow', 'giờ ngủ trưa (10:00–12:00)')
    assert F.tick(None, notify, D1 + m(60))[0] == 'end'
    assert F.tick(None, notify, D1 + m(61)) is None   # còn vàng: chờ
    color['v'] = ('white', '')
    assert F.tick(None, notify, D1 + m(180))[0] == 'auto_start'


def test_tim_tu_dung_roi_tu_tiep_voi_phien_tu_bat(exam):
    color, notify, _ = exam
    F.tick(None, notify, D1)
    color['v'] = ('purple', 'giờ ăn trưa (12:00–13:00)')
    assert F.tick(None, notify, D1 + m(10))[0] == 'pause'
    color['v'] = ('white', '')
    assert F.tick(None, notify, D1 + m(70)) == ('resume', 'purple')


def test_gio_an_khi_ban_tu_dung_van_giu_nguyen(env):
    color, notify, sent = env
    st = W.empty(); W.start_focus(st, 50, '', T0); W.pause(st, T0 + m(5)); W.save(st)
    color['v'] = ('purple', 'giờ ăn tối (19:00–20:00)')
    F.tick(None, notify, T0 + m(10))
    assert W.by_user(W.load()['active']) and not sent


def test_doi_pha_nghi_go_chan_va_bao(monkeypatch):   # (chủ 07/11)
    sig = []
    monkeypatch.setattr(W, '_signal', lambda f, u=None, n=None: sig.append(f))
    monkeypatch.setattr(W, 'save', lambda st, path=None: None)
    st = W.empty(); t0 = dt.datetime(2026, 11, 7, 8, 0, tzinfo=W.TZ)
    W.start_focus(st, 55, 'x', t0)                                    # 25 tập trung + 5 nghỉ + 25 tập trung
    assert F._phase_sync(st, t0 + dt.timedelta(minutes=1)) is None    # đầu phiên: không báo thêm
    m = F._phase_sync(st, t0 + dt.timedelta(minutes=26))
    assert m[0] == 'UC · Đã bắt đầu nghỉ' and sig[-1] is False
    assert F._phase_sync(st, t0 + dt.timedelta(minutes=27)) is None   # cùng pha: không báo lặp
    m = F._phase_sync(st, t0 + dt.timedelta(minutes=31))
    assert m[0] == 'UC · Đã bắt đầu tập trung' and sig[-1] is True
