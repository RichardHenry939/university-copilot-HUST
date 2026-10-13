# -*- coding: utf-8 -*-
"""Hạ tầng chung cho bộ test: cấu hình giả, chặn mạng, n8n/Notion giả trong bộ nhớ.

- Không cần config.json thật: uc_config được nạp sẵn từ config.example.json, mỗi ID Notion thành "db-<tên logic>".
- Mọi lời gọi mạng (urllib) bị chặn: test nào cần thì tự monkeypatch đúng hàm của module.
- FakeN8n giả webhook copilot-notion mà academic.Notion dùng để đọc / ghi Notion.
"""
import json, sys, urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'addons' / 'low-end-priority'))

import uc_config  # noqa: E402

_cfg = json.loads((ROOT / 'config.example.json').read_text(encoding='utf-8'))
_cfg['notion'] = {k: f'db-{k}' for k in _cfg['notion']}
_cfg['n8n_workflows'] = {k: f'wf-{k}' for k in _cfg['n8n_workflows']}
uc_config._cfg = _cfg


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **k):
        raise AssertionError('test không được gọi mạng thật (urllib.request.urlopen)')
    monkeypatch.setattr(urllib.request, 'urlopen', blocked)


# ----------------------------------------------------------------------------- trang Notion giả
def prop(kind, value):
    """Thuộc tính Notion dạng API trả về, đủ cho academic.P đọc."""
    if kind in ('title', 'rich_text'): return {'type': kind, kind: [{'plain_text': value}] if value is not None else []}
    if kind in ('select', 'status'): return {'type': kind, kind: {'name': value} if value is not None else None}
    if kind in ('number', 'checkbox', 'url'): return {'type': kind, kind: value}
    if kind == 'date': return {'type': 'date', 'date': {'start': value} if value else None}
    if kind == 'relation': return {'type': 'relation', 'relation': [{'id': x} for x in value or []]}
    raise ValueError(kind)


def page(pid, props=None, url=None, **kw):
    """page('id', Name=('title', 'Bài 1'), Loại_hạn=('select', 'Môn học')) -> trang Notion giả ('_' trong tên khoá = dấu cách).
    Tên có ký tự đặc biệt ('Weight %') thì truyền qua dict `props`."""
    allp = {**{k.replace('_', ' '): v for k, v in kw.items()}, **(props or {})}
    return {'id': pid, 'url': url or f'https://notion.so/{pid}', 'properties': {k: prop(*v) for k, v in allp.items()}}


class FakeN8n:
    """Giả webhook n8n `copilot-notion`: truy vấn trả hết trang của database (bộ lọc do test tự chuẩn bị dữ liệu),
    tạo / sửa trang được ghi lại để test kiểm tra. Webhook khác: trả theo `hooks[path]` (hàm hoặc giá trị)."""

    def __init__(self, dbs=None, hooks=None):
        self.dbs = {k: list(v) for k, v in (dbs or {}).items()}
        self.hooks = hooks or {}
        self.created, self.patched, self.queries, self.calls = [], [], [], []

    def __call__(self, path, body):
        self.calls.append((path, body))
        if path != 'copilot-notion':
            h = self.hooks.get(path, {})
            return h(body) if callable(h) else h
        res = []
        for op in body['ops']:
            url, m = op['url'], op['method']
            if m == 'POST' and url.endswith('/query'):
                db = url.split('/databases/')[1].split('/')[0]
                self.queries.append((db, op['body'].get('filter')))
                res.append({'code': 200, 'body': {'results': self.dbs.get(db, []), 'has_more': False}})
            elif m == 'POST' and url.endswith('/pages'):
                self.created.append((op['body']['parent']['database_id'], op['body']['properties']))
                res.append({'code': 200, 'body': {'id': f'new-{len(self.created)}'}})
            elif m == 'PATCH':
                pid = url.rsplit('/', 1)[1]
                self.patched.append((pid, op['body']['properties']))
                res.append({'code': 200, 'body': {'id': pid}})
            else:
                res.append({'code': 400, 'body': {'message': f'không hỗ trợ {m} {url}'}})
        return {'res': res}


@pytest.fixture
def n8n():
    return FakeN8n()
