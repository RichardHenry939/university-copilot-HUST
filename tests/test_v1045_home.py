# -*- coding: utf-8 -*-
"""v1.00.45 (tiếp): trang chủ kiểu Cổng CTSV.

- POST /api/hero (nút "Đổi ảnh nền"): chỉ nhận JPG/PNG/WebP theo byte đầu, <= 8 MB, chặn trang web lạ (Origin), giữ một ảnh duy nhất.
- GET /api/owner: đọc khoá "owner" trong config.json; thiếu khoá / giá trị giữ chỗ "<...>" -> {} và không lỗi.
- GET /assets/<tên>.svg|png: chỉ phục vụ file trong ui/assets, đúng kiểu ảnh.
"""
import io

import pytest

from test_copilot_app_origin import app  # noqa: F401  (fixture dùng chung)
from test_v1045_ctsv import get

import uc_config

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 32
WEBP = b'RIFF\x24\x00\x00\x00WEBPVP8 ' + b'\x00' * 24


def post_raw(app, path, data, origin=None, length=None):
    h = app.H.__new__(app.H)
    h.path = path
    h.headers = {'Content-Length': str(len(data) if length is None else length), **({'Origin': origin} if origin else {})}
    h.rfile = io.BytesIO(data)
    out = {}
    h._send = lambda code, obj=None, raw=None, ctype=None: out.update(code=code, obj=obj)
    h.do_POST()
    return out['code'], out['obj']


@pytest.fixture
def home(app, monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'HERE', tmp_path)
    return tmp_path / 'ui' / 'assets'


def test_hero_accepts_small_png_and_serves_it(app, home):
    code, obj = post_raw(app, '/api/hero', PNG, origin='http://127.0.0.1:8320')
    assert code == 200 and obj == {'ok': True, 'kind': 'png', 'bytes': len(PNG)}
    assert (home / 'hero.png').read_bytes() == PNG
    r = get(app, '/hero-img'); assert r['code'] == 200 and r['ctype'] == 'image/png'


def test_hero_keeps_only_one_image(app, home):
    post_raw(app, '/api/hero', PNG)
    code, obj = post_raw(app, '/api/hero', JPG)
    assert code == 200 and obj['kind'] == 'jpg'
    assert sorted(p.name for p in home.iterdir()) == ['hero.jpg']   # ảnh png cũ đã bị thay, không còn file tạm
    assert post_raw(app, '/api/hero', WEBP)[1]['kind'] == 'webp'


@pytest.mark.parametrize('data', [b'<svg onload=alert(1)>', b'GIF89a' + b'\x00' * 10, b'%PDF-1.7', b'just text'])
def test_hero_rejects_non_images(app, home, data):
    code, obj = post_raw(app, '/api/hero', data)
    assert code == 415 and obj['ok'] is False
    assert not home.exists() or not any(home.iterdir())


def test_hero_rejects_empty_and_too_big(app, home):
    assert post_raw(app, '/api/hero', b'')[0] == 400
    code, obj = post_raw(app, '/api/hero', PNG, length=app.HERO_MAX + 1)   # chặn theo Content-Length, không đọc thân
    assert code == 413 and obj['ok'] is False
    assert not home.exists() or not any(home.iterdir())


def test_hero_blocks_foreign_origin(app, home):
    code, _ = post_raw(app, '/api/hero', PNG, origin='https://trang-la.example')
    assert code == 403 and not home.exists()


def test_owner_missing_config_is_empty(app, monkeypatch):
    monkeypatch.setitem(uc_config._cfg, 'owner', None)
    assert get_json(app, '/api/owner') == {}
    monkeypatch.delitem(uc_config._cfg, 'owner')
    assert get_json(app, '/api/owner') == {}


def test_owner_placeholders_dropped_and_values_passed(app, monkeypatch):
    monkeypatch.setitem(uc_config._cfg, 'owner', {'name': 'Nguyen Van A', 'email': '<email liên hệ>', 'phone': '', 'x': 'bo'})
    assert get_json(app, '/api/owner') == {'name': 'Nguyen Van A'}


def test_owner_without_config_file(monkeypatch, tmp_path):
    monkeypatch.setattr(uc_config, '_cfg', None)
    monkeypatch.setattr(uc_config, '_FILE', tmp_path / 'khong-co.json')
    assert uc_config.owner() == {}


def test_assets_route(app, home):
    home.mkdir(parents=True)
    (home / 'map.svg').write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    (home / 'school-logo.png').write_bytes(PNG)
    r = get(app, '/assets/map.svg'); assert r['code'] == 200 and r['ctype'] == 'image/svg+xml'
    r = get(app, '/assets/school-logo.png'); assert r['code'] == 200 and r['ctype'] == 'image/png'
    assert get(app, '/assets/khong-co.svg')['code'] == 404
    for bad in ('/assets/../copilot_app.py', '/assets/Map.SVG', '/assets/hero.jpg', '/assets/%2e%2e%2fx.svg'):
        assert get(app, bad).get('raw') is None, bad


def test_public_map_is_committed_asset():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    assert (root / 'ui' / 'assets' / 'map.svg').read_bytes()[:200].lstrip().startswith((b'<svg', b'<?xml'))


def get_json(app, path):
    h = app.H.__new__(app.H)
    h.path, h.headers = path, {}
    out = {}
    h._send = lambda code, obj=None, raw=None, ctype=None: out.update(code=code, obj=obj)
    h.do_GET()
    assert out['code'] == 200
    return out['obj']
