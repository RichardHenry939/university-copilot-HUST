# -*- coding: utf-8 -*-
"""(v1.00.42) MSSV của chủ, lưu mã hoá DPAPI theo tài khoản Windows (school/secret/mssv.dpapi).

Giá trị đi qua stdin của PowerShell (không nằm trên dòng lệnh, không vào log). /api/mssv/status chỉ trả {"saved": true|false};
số chỉ hiện lại qua /api/mssv/reveal cho trang UC trong trình duyệt localhost. Agent không gọi load() / reveal (xem AGENTS.md).
Cùng định dạng với mssv_set.ps1 (bản dự phòng): ConvertFrom-SecureString không khoá -> chỉ tài khoản Windows này giải được.
"""
import re, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILE = HERE / 'school' / 'secret' / 'mssv.dpapi'
# K71 trong danh sách lớp có 9 chữ số (2026xxxxx); khoá cũ có 8 -> nhận cả hai.
PATTERN = re.compile(r'2\d{7,8}')
_PS = ['powershell', '-NoProfile', '-NonInteractive', '-Command']
_FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def valid(v):
    return bool(PATTERN.fullmatch(str(v or '').strip()))


def status():
    return {'saved': FILE.exists() and FILE.stat().st_size > 0}


def save(v):
    v = str(v or '').strip()
    if not valid(v): return {'ok': False, 'loi': 'MSSV phải là 8 hoặc 9 chữ số, bắt đầu bằng 2.'}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    cmd = ("$v = [Console]::In.ReadLine(); "
           "ConvertTo-SecureString $v -AsPlainText -Force | ConvertFrom-SecureString | "
           f"Set-Content -LiteralPath '{FILE}' -Encoding ascii")
    r = subprocess.run(_PS + [cmd], input=v + '\n', capture_output=True, text=True, timeout=30, creationflags=_FLAGS)
    if r.returncode != 0 or not status()['saved']: return {'ok': False, 'loi': 'Không lưu được (PowerShell báo lỗi).'}
    return {'ok': True, **status()}


def delete():
    try: FILE.unlink()
    except FileNotFoundError: pass
    return {'ok': True, **status()}


def load():
    """MSSV dạng rõ, CHỈ dùng trong bộ nhớ (đối chiếu danh sách). Không ghi ra đâu. -> str hoặc None."""
    if not status()['saved']: return None
    cmd = (f"$s = Get-Content -LiteralPath '{FILE}' | ConvertTo-SecureString; "
           "[Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))")
    try: r = subprocess.run(_PS + [cmd], capture_output=True, text=True, timeout=30, creationflags=_FLAGS)
    except Exception: return None
    v = (r.stdout or '').strip()
    return v if r.returncode == 0 and valid(v) else None
