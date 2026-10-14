# -*- coding: utf-8 -*-
"""Web app (copilot_app.py): yêu cầu POST từ trang web lạ (khác origin) phải bị chặn trước khi làm gì.

Một trang bất kỳ đang mở trong trình duyệt có thể gửi POST tới http://127.0.0.1:8320 (form / fetch no-cors);
trình duyệt luôn gắn header Origin của trang đó. UC chỉ nhận Origin của chính nó (hoặc không có Origin: n8n, curl)."""
import importlib, io, json, pathlib, sys, types

import pytest

ORIGIN_OK = 'http://127.0.0.1:8320'
EVIL = 'https://trang-la.example'


@pytest.fixture(scope='module')
def app():
    real = pathlib.Path.read_text

    def fake_read(self, *a, **k):   # khoá .copilot-secret của máy thật không có trong repo / CI
        return 'khoa-thu-nghiem' if self.name == '.copilot-secret' else real(self, *a, **k)
    pathlib.Path.read_text = fake_read
    try:
        sys.modules.pop('copilot_app', None)
        mod = importlib.import_module('copilot_app')
    finally:
        pathlib.Path.read_text = real
    yield mod
    sys.modules.pop('copilot_app', None)


def post(app, path, body, origin=None):
    """Gọi H.do_POST không qua socket; trả (mã, json)."""
    h = app.H.__new__(app.H)
    raw = json.dumps(body).encode('utf-8')
    h.path = path
    h.headers = {'Content-Length': str(len(raw)), **({'Origin': origin} if origin else {})}
    h.rfile = io.BytesIO(raw)
    out = {}
    h._send = lambda code, obj=None, raw=None, ctype=None: out.update(code=code, obj=obj)
    h.do_POST()
    return out['code'], out['obj']


@pytest.fixture
def spies(monkeypatch):
    """Thay các hành động thật (ghi file học phí, dịch PDF, gửi NotebookLM, ẩn buổi ghi) bằng bản ghi lại lời gọi."""
    calls = []
    fakes = {
        'tuition': types.SimpleNamespace(set_price=lambda v: calls.append(('tuition', v)) or {'ok': True}),
        'pdf_translate': types.SimpleNamespace(add=lambda f, l: calls.append(('translate', f)) or {'ok': True}),
        'nlm_bridge': types.SimpleNamespace(add=lambda f, n, t: calls.append(('nlm', f)) or {'ok': True}),
        'lecture_monitor': types.SimpleNamespace(dismiss=lambda c: calls.append(('dismiss', c)) or {'ok': True}),
    }
    for name, mod in fakes.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return calls


CASES = [
    ('/api/tuition/price', {'confirmed': True, 'don_gia': '1.000.000'}),
    ('/api/translate', {'confirmed': True, 'files': ['a.pdf'], 'lang': 'en'}),
    ('/api/nlm/add', {'confirmed': True, 'files': ['a.pdf']}),
    ('/api/lecture-monitor/dismiss', {'captureId': 'lecture-1'}),
]


@pytest.mark.parametrize('path, body', CASES)
def test_cross_origin_post_is_blocked(app, spies, path, body):
    code, obj = post(app, path, body, origin=EVIL)
    assert code == 403 and obj == {'error': 'cross-origin blocked'}
    assert spies == []                                   # không ghi / không chạy gì


@pytest.mark.parametrize('origin', [ORIGIN_OK, 'http://localhost:8320', None])
@pytest.mark.parametrize('path, body', CASES)
def test_same_origin_post_still_works(app, spies, path, body, origin):
    code, obj = post(app, path, body, origin=origin)
    assert code == 200 and obj == {'ok': True}
    assert len(spies) == 1


def test_key_protected_endpoint_still_reachable_without_origin(app):
    # n8n (trong Docker) gọi các công cụ có X-Copilot-Key, không gửi Origin: sai khoá -> 403 vì khoá, không phải vì origin
    code, obj = post(app, '/api/academic', {}, origin=None)
    assert code == 403 and obj == {'error': 'forbidden'}
