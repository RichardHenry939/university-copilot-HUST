# -*- coding: utf-8 -*-
"""(v1.00.57) Tab Fitness gọi /api/fitness nhưng bản công khai v1.00.52 sót đường này trong copilot_app.py -> tab không chạy."""
import importlib, io, pathlib, sys

import pytest


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


def get(app, path):
    h = app.H.__new__(app.H)
    h.path, h.headers, h.rfile = path, {}, io.BytesIO(b'')
    out = {}
    h._send = lambda code, obj=None, raw=None, ctype=None: out.update(code=code, obj=obj)
    h.do_GET()
    return out.get('code'), out.get('obj')


def test_api_fitness_tra_du_lieu(app):
    code, obj = get(app, '/api/fitness')
    assert code == 200 and isinstance(obj, dict) and 'today' in obj
