# -*- coding: utf-8 -*-
"""Ví thời gian (wallet.py, v1.00.42 W8): quy tắc cộng / trừ / thu hồi, chia khối 25 + 5. Không gọi mạng, không ghi file thật."""
import datetime as dt

import pytest

import wallet as W

T0 = dt.datetime(2026, 11, 2, 8, 0, tzinfo=W.TZ)


@pytest.fixture(autouse=True)
def no_real_signal(tmp_path, monkeypatch):
    # (01/11) test từng ghi vào tệp tín hiệu THẬT (máy đã bật tín hiệu) -> có thể bật chặn trang thật. Luôn trỏ ra chỗ tạm.
    monkeypatch.setattr(W, 'SIGNAL_CFG', tmp_path / 'chua-cau-hinh.json')
m = lambda k: dt.timedelta(minutes=k)


def new():
    return W.empty()


def test_chia_khoi_25_5():
    assert W.plan(60) == [('focus', 25), ('break', 5), ('focus', 25), ('break', 5)]
    assert W.plan(25) == [('focus', 25)]
    assert W.plan(40) == [('focus', 25), ('break', 5), ('focus', 10)]


def test_moi_khoi_25_phut_tron_cong_5_phut():
    st = new()
    W.start_focus(st, 60, 'MI1111', T0)
    r = W.end_focus(st, T0 + m(60))
    assert r['blocks'] == 2 and W.balance(st) == 10
    assert st['active'] is None and st['sessions'][0]['focus_min'] == 50


def test_da_bat_dau_thi_khong_huy_som():
    # (01/11) chủ chốt: vào phiên rồi thì không huỷ. Phiên chỉ kết thúc khi hết giờ.
    st = new()
    W.start_focus(st, 100, '', T0)
    with pytest.raises(ValueError):
        W.end_focus(st, T0 + m(40))
    assert st['active'] is not None and W.balance(st) == 0
    v = W.view(st, T0 + m(100))              # hết giờ -> tự kết thúc: 25+5+25+5+25+5+10 = 3 khối trọn
    assert v['active'] is None and v['balance'] == 15


def test_tam_dung_khong_tinh_thoi_gian():
    st = new()
    W.start_focus(st, 25, '', T0)
    W.pause(st, T0 + m(10))
    W.resume(st, T0 + m(40))                 # dừng 30 phút
    assert W.progress(st, T0 + m(50))['blocks_done'] == 0
    assert W.end_focus(st, T0 + m(55))['blocks'] == 1


def test_phien_het_gio_tu_ket_thuc_khi_xem():
    st = new()
    W.start_focus(st, 30, '', T0)
    v = W.view(st, T0 + m(31))
    assert v['active'] is None and v['balance'] == 5


def test_hoan_tat_han_cong_15_mot_lan_va_thu_hoi_dung_phan_da_cong():
    st = new()
    W.credit_deadline(st, 'dl-1', 'Quiz 08', T0)
    W.credit_deadline(st, 'dl-1', 'Quiz 08', T0)   # bấm lại không cộng thêm
    assert W.balance(st) == 15
    W.revoke_deadline(st, 'dl-1', T0 + m(5))
    assert W.balance(st) == 0
    W.revoke_deadline(st, 'dl-1', T0 + m(6))       # thu hồi lại không trừ thêm
    assert W.balance(st) == 0
    W.credit_deadline(st, 'dl-1', 'Quiz 08', T0 + m(7))   # hoàn tất lại sau khi bỏ: cộng lại
    assert W.balance(st) == 15


def test_giai_tri_tru_dung_so_phut_va_khong_vuot_so_du():
    st = new()
    W.credit_deadline(st, 'dl-1', 'x', T0)          # 15 phút
    W.start_fun(st, T0)
    W.end_fun(st, T0 + m(9) + dt.timedelta(seconds=10))   # 9 phút 10 giây -> làm tròn lên 10
    assert W.balance(st) == 5
    W.start_fun(st, T0 + m(20))
    v = W.view(st, T0 + m(40))                      # quá số dư -> tự dừng, chỉ trừ 5
    assert v['active'] is None and v['balance'] == 0


def test_khong_giai_tri_khi_vi_rong_va_khong_chay_hai_phien():
    st = new()
    with pytest.raises(ValueError):
        W.start_fun(st, T0)
    W.start_focus(st, 25, '', T0)
    with pytest.raises(ValueError):
        W.start_focus(st, 25, '', T0)


def test_thong_ke_ngay_tuan_thang():
    st = new()
    W.start_focus(st, 30, '', T0)
    W.end_focus(st, T0 + m(30))
    W.credit_deadline(st, 'dl-2', 'x', T0 + m(31))
    s = W.stats(st, T0 + m(60))
    assert s['ngay']['focus_min'] == 25 and s['ngay']['earned'] == 20
    assert s['tuan']['focus_min'] == 25 and s['thang']['blocks'] == 1
    assert W.stats(st, T0 + dt.timedelta(days=8))['tuan']['focus_min'] == 0


def test_tin_hieu_chi_ghi_khi_chu_da_dat_cau_hinh(tmp_path, monkeypatch):
    monkeypatch.setattr(W, 'SIGNAL_CFG', tmp_path / 'khong-co.json')
    st = new()
    W.start_focus(st, 25, '', T0)          # không có cấu hình -> không ghi gì, không lỗi
    target = tmp_path / 'sig.json'
    cfg = tmp_path / 'cfg.json'
    cfg.write_text('{"path": "%s"}' % str(target).replace('\\', '/'), encoding='utf-8')
    monkeypatch.setattr(W, 'SIGNAL_CFG', cfg)
    W.end_focus(st, T0 + m(25))
    assert '"focus": false' in target.read_text(encoding='utf-8')


def test_khoang_tap_trung_hom_nay_bo_luc_tam_dung():
    st = new()
    W.start_focus(st, 60, 'x', T0)
    W.pause(st, T0 + m(20)); W.resume(st, T0 + m(30))
    assert W.spans_today(st, T0 + m(40)) == [[W._iso(T0), W._iso(T0 + m(20))], [W._iso(T0 + m(30)), W._iso(T0 + m(40))]]
    W.pause(st, T0 + m(45))   # đang tạm dừng: không tô phần sau 45'
    assert W.spans_today(st, T0 + m(50))[-1] == [W._iso(T0 + m(30)), W._iso(T0 + m(45))]


def _sig(tmp_path, monkeypatch):
    target, cfg = tmp_path / 'sig.json', tmp_path / 'cfg.json'
    cfg.write_text('{"path": "%s"}' % str(target).replace('\\', '/'), encoding='utf-8')
    monkeypatch.setattr(W, 'SIGNAL_CFG', cfg)
    import json
    return lambda: json.loads(target.read_text(encoding='utf-8'))


def test_uc_dung_go_chan_tiep_tuc_chan_lai(tmp_path, monkeypatch):
    # (chủ chốt 03/11 ~19:30) UC tự dừng (nút "Tiếp tục") -> gỡ chặn; tiếp tục -> chặn chạy lại, hạn lùi theo
    sig = _sig(tmp_path, monkeypatch); st = new()
    W.start_focus(st, 50, '', T0)
    W.pause(st, T0 + m(10), by='uc')
    assert sig()['focus'] is False and not W.by_user(st['active'])
    W.hold_signal(st, T0 + m(11))          # UC dừng: không được bật chặn lại
    assert sig()['focus'] is False
    W.resume(st, T0 + m(30))
    assert sig()['focus'] is True and W._t(sig()['until']) == T0 + m(30) + m(40) and 'paused_by' not in st['active']


def test_ban_tu_dung_giu_chan_va_gia_han(tmp_path, monkeypatch):
    # bạn tự bấm dừng (nút ▶) -> chặn giữ nguyên, tín hiệu không hết hạn giữa chừng
    sig = _sig(tmp_path, monkeypatch); st = new()
    W.start_focus(st, 50, '', T0); W.pause(st, T0 + m(10))
    assert W.by_user(st['active']) and sig()['focus'] is True
    W.hold_signal(st, T0 + m(90))
    assert sig()['focus'] is True and W._t(sig()['until']) > T0 + m(90)


def test_the_duc_de_len_luc_ban_dang_tu_dung(tmp_path, monkeypatch):
    sig = _sig(tmp_path, monkeypatch); st = new()
    W.start_focus(st, 50, '', T0)
    W.pause(st, T0 + m(5)); W.pause(st, T0 + m(8), forced='giờ thể dục', by='uc')
    a = st['active']
    assert sig()['focus'] is False and a['forced'] and not W.by_user(a) and a['paused_at'] == W._iso(T0 + m(5))


def test_phien_cu_khong_ghi_ai_dung_coi_la_uc_dung():
    a = {'type': 'focus', 'paused_at': W._iso(T0)}
    assert not W.by_user(a)
