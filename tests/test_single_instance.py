# -*- coding: utf-8 -*-
"""(v1.00.59) single_instance: bản thứ hai không được chạy khi bản đầu còn giữ mutex."""
import subprocess, sys, uuid

import pytest

import single_instance as S


@pytest.mark.skipif(sys.platform != 'win32', reason='mutex có tên chỉ có trên Windows')
def test_ban_thu_hai_bi_tu_choi_khi_ban_dau_con_chay():
    name = 'Local\\UCTest-' + uuid.uuid4().hex
    assert S.acquire(name, wait=0)
    code = f"import sys; sys.path.insert(0, r'{S.__file__.rsplit(chr(92), 1)[0]}'); import single_instance as S; print(S.acquire(r'{name}', wait=1, step=0.5))"
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30).stdout.strip()
    assert out == 'False'


def test_ngoai_windows_luon_cho_chay(monkeypatch):
    monkeypatch.setattr(S.sys, 'platform', 'linux')
    assert S.acquire('x', wait=0)
