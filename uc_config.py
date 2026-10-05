# -*- coding: utf-8 -*-
"""Cấu hình riêng của từng người dùng — đọc từ config.json (không đưa lên Git).

Mọi ID database Notion, ID credential n8n và đường dẫn trên máy nằm ở đây thay vì viết thẳng trong code.
Bắt đầu: sao chép config.example.json -> config.json rồi điền giá trị của bạn.
Bí mật (API key, mật khẩu) KHÔNG nằm trong file này: chúng ở biến môi trường / Windows Credential Manager.
"""
import json
from pathlib import Path

_FILE = Path(__file__).resolve().parent / 'config.json'
_cfg = None


def _load():
    global _cfg
    if _cfg is None:
        if not _FILE.exists():
            raise FileNotFoundError('Thiếu config.json — sao chép config.example.json thành config.json và điền giá trị.')
        _cfg = json.loads(_FILE.read_text(encoding='utf-8'))
    return _cfg


def notion(key):
    """ID database / trang Notion theo tên logic (vd 'academic_work')."""
    return _load()['notion'][key]


def path(key):
    return _load()['paths'][key]


def n8n_cred(kind, name):
    """Tham chiếu credential trong n8n (chỉ là ID, không chứa bí mật)."""
    return {'id': _load()['n8n_credentials'][kind], 'name': name}


def n8n_workflow(key):
    """ID workflow n8n trên máy (copilot | lecture_capture | lecture_analysis)."""
    return _load()["n8n_workflows"][key]
