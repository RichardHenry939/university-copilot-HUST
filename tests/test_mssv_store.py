# -*- coding: utf-8 -*-
"""MSSV (mssv_store.py, v1.00.42 W2): chỉ kiểm định dạng; không gọi PowerShell, không ghi file."""
import mssv_store as M


def test_dinh_dang_mssv():
    assert M.valid('20260000') and M.valid('202600000') and M.valid(' 202600000 ')
    assert not M.valid('') and not M.valid('12345678') and not M.valid('2026000') and not M.valid('2026000000') and not M.valid('2026abcd')


def test_luu_so_sai_dinh_dang_bi_tu_choi_truoc_khi_goi_powershell(monkeypatch):
    called = []
    monkeypatch.setattr(M.subprocess, 'run', lambda *a, **k: called.append(1))
    assert not M.save('abc')['ok'] and not called
