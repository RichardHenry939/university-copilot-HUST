# -*- coding: utf-8 -*-
"""(v1.00.56) Canh máy ảo cho lượt đọc iCTSV (ictsv_login.EmuWatch + plog). Không gọi adb, không mở máy ảo thật."""
import ictsv_login as L

H = 3600


def run(w, seq, hour=17, off=False):
    """seq: [(giây, máy ảo có lên không)] -> danh sách (giây, việc)."""
    out = []
    for t, up in seq:
        for a in w.step(up, t, hour, off): out.append((t, a))
    return out


def test_may_ao_chay_thi_khong_lam_gi():
    assert run(L.EmuWatch(), [(0, True), (60, True)]) == []


def test_mat_may_ao_qua_2_phut_thi_bao_va_bat_lai():
    assert run(L.EmuWatch(), [(0, False), (60, False), (120, False)]) == [(120, 'down'), (120, 'start')]


def test_chop_tat_duoi_2_phut_khong_bao():
    assert run(L.EmuWatch(), [(0, False), (60, False), (90, True)]) == []


def test_bat_lai_cach_nhau_10_phut_toi_da_3_lan_roi_bo_cuoc():
    seq = [(t, False) for t in range(0, 40 * 60, 30)]
    acts = [a for _, a in run(L.EmuWatch(), seq)]
    assert acts.count('start') == 3 and acts.count('down') == 1 and acts.count('giveup') == 1
    starts = [t for t, a in run(L.EmuWatch(), seq) if a == 'start']
    assert starts[1] - starts[0] >= 600 and starts[2] - starts[1] >= 600


def test_len_lai_thi_bao_da_chay_lai():
    w = L.EmuWatch()
    run(w, [(0, False), (120, False)])
    assert run(w, [(200, True)]) == [(200, 'back')]


def test_ngoai_gio_06_22_khong_bat_khong_bao():
    assert run(L.EmuWatch(), [(0, False), (300, False)], hour=23) == []


def test_tat_tu_bat_thi_chi_bao():
    assert run(L.EmuWatch(), [(0, False), (300, False)], off=True) == [(300, 'down')]


def test_qua_ngay_moi_dem_lai_so_lan_bat():
    w = L.EmuWatch()
    run(w, [(t, False) for t in range(0, 40 * 60, 30)])
    w.new_day()
    assert 'start' in [a for _, a in run(w, [(30 * H, True), (30 * H + 10, False), (30 * H + 200, False)])]


def test_plog_ghi_dong_co_gio(tmp_path, monkeypatch):
    f = tmp_path / 'ictsv_probe.log'
    monkeypatch.setattr(L, 'PROBE_LOG', f)
    L.plog('probe: ok')
    line = f.read_text(encoding='utf-8').strip()
    assert line.endswith('probe: ok') and line[:4].isdigit()


def test_plog_cat_bot_khi_qua_lon(tmp_path, monkeypatch):
    f = tmp_path / 'ictsv_probe.log'
    monkeypatch.setattr(L, 'PROBE_LOG', f)
    f.write_text('x' * 300_000, encoding='utf-8')
    L.plog('moi')
    assert f.stat().st_size < 200_000 and f.read_text(encoding='utf-8').strip().endswith('moi')
