# -*- coding: utf-8 -*-
"""v1.00.45: điểm rèn luyện + ảnh bìa CTSV.

- POST /api/drl: lưu lên CTSV chỉ khi có confirmed:true (bước Xác nhận trong UC); xem trước không lưu.
- ctsv_live._read_drl: đọc "Tổng SV: x - GV: y" trên trang; trang đổi chữ thì báo lỗi, không đoán.
- ctsv_live._save_images: chỉ tải ảnh hoạt động của bạn + hoạt động chưa kết thúc, bỏ qua ảnh đã có."""
import base64, sys, types

import pytest

from test_copilot_app_origin import app, post  # noqa: F401  (fixture dùng chung)

import ctsv_live


@pytest.fixture
def fake_ctsv(monkeypatch):
    calls = []
    mod = types.SimpleNamespace(rescore=lambda save=False: calls.append(save) or {'ok': True, 'saved_sv': 25, 'new': 31})
    monkeypatch.setitem(sys.modules, 'ctsv_live', mod)
    monkeypatch.setitem(sys.modules, 'extracurricular', types.SimpleNamespace(build=lambda: None))
    return calls


def test_drl_save_needs_confirm(app, fake_ctsv):
    code, obj = post(app, '/api/drl', {'action': 'save'})
    assert code == 200 and obj['ok'] is False and fake_ctsv == []
    code, obj = post(app, '/api/drl', {'action': 'save', 'confirmed': 'true'})   # chuỗi không tính là xác nhận
    assert obj['ok'] is False and fake_ctsv == []


def test_drl_preview_does_not_save(app, fake_ctsv):
    code, obj = post(app, '/api/drl', {'action': 'preview'})
    assert obj['ok'] is True and obj['new'] == 31 and fake_ctsv == [False]


def test_drl_save_confirmed(app, fake_ctsv):
    post(app, '/api/drl', {'action': 'save', 'confirmed': True})
    assert fake_ctsv == [True]


class Page:
    def __init__(self, text='', imgs=None):
        self.text, self.imgs, self.asked = text, imgs or {}, None

    def goto(self, *a, **k): pass

    def wait_for_timeout(self, ms): pass

    def inner_text(self, sel): return self.text

    def evaluate(self, js, todo):
        self.asked = todo
        return {i: self.imgs[i] for i, _ in todo if i in self.imgs}


def test_read_drl():
    assert ctsv_live._read_drl(Page('... Tổng SV: 25 - GV: 0 ...'))['sv'] == 25
    assert 'error' in ctsv_live._read_drl(Page('trang đổi giao diện'))


def test_save_images_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(ctsv_live, 'IMG', tmp_path)
    (tmp_path / '3.img').write_bytes(b'cu')
    b64 = base64.b64encode(b'anh').decode()
    ctsv = {'mine': [{'id': 1, 'avatar': 'a/1.png'}, {'id': 3, 'avatar': 'a/3.png'}, {'id': 4, 'avatar': ''}],
            'open': [{'id': 2, 'avatar': 'a/2.png', 'end': '2999-01-01T00:00:00'},
                     {'id': 5, 'avatar': 'a/5.png', 'end': '2000-01-01T00:00:00'},
                     {'id': '../x', 'avatar': 'a/x.png', 'end': '2999-01-01'}]}
    page = Page(imgs={'1': b64, '2': b64})
    r = ctsv_live._save_images(page, ctsv)
    assert sorted(i for i, _ in page.asked) == ['1', '2']   # 3 đã có, 4 không ảnh, 5 đã kết thúc, '../x' không phải số
    assert r == {'new': 2, 'tried': 2} and (tmp_path / '1.img').read_bytes() == b'anh'


def get(app, path):
    h = app.H.__new__(app.H)
    h.path, h.headers = path, {}
    out = {}
    h._send = lambda code, obj=None, raw=None, ctype=None: out.update(code=code, raw=raw, ctype=ctype)
    h.do_GET()
    return out


def test_hero_img_and_ctsv_img(app, monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'HERE', tmp_path)
    assert get(app, '/hero-img')['code'] == 404                      # chưa đặt ảnh -> trang dùng nền màu
    (tmp_path / 'ui' / 'assets').mkdir(parents=True)
    (tmp_path / 'ui' / 'assets' / 'hero.png').write_bytes(b'\x89PNG anh')
    r = get(app, '/hero-img'); assert r['code'] == 200 and r['ctype'] == 'image/png'
    (tmp_path / 'school' / 'ctsv_img').mkdir(parents=True)
    (tmp_path / 'school' / 'ctsv_img' / '7.img').write_bytes(b'\xff\xd8 jpg')
    r = get(app, '/ctsv-img/7'); assert r['code'] == 200 and r['ctype'] == 'image/jpeg'
    assert get(app, '/ctsv-img/8')['code'] == 404
    assert get(app, '/ctsv-img/..%2Fx').get('raw') is None             # chỉ nhận mã số
