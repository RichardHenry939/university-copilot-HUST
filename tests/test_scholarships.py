# -*- coding: utf-8 -*-
"""Học bổng (scholarships.view): giữ nội dung chi tiết (content) cho thẻ, tách Đang mở / Hết hạn đúng theo hạn và cờ Expired."""
import json, sys, types

import scholarships


def test_view_open_closed_and_content(monkeypatch, tmp_path):
    (tmp_path / 'school').mkdir()
    sch = [{'id': 1, 'name': 'HB &amp; A', 'deadline': '2999-01-01 23:55:00', 'expired': '0', 'price': '10.000.000 đồng/suất',
            'quantity': '10', 'applied': '0', 'desc': 'Học bổng', 'content': 'Điều kiện: GPA &gt;= 3.2', 'created': '2026-10-23 09:00:00'},
           {'id': 2, 'name': 'HB cũ', 'deadline': '2999-01-01 23:55:00', 'expired': '1', 'applied': '1', 'created': '2026-01-01 09:00:00'},
           {'id': 3, 'name': 'HB qua hạn', 'deadline': '2000-01-01 00:00:00', 'expired': '0', 'created': '2026-01-02 09:00:00'}]
    (tmp_path / 'school' / 'ctsv_live.json').write_text(json.dumps({'ctsv': {'scholarships': sch}}), encoding='utf-8')
    monkeypatch.setattr(scholarships, 'HERE', tmp_path)
    monkeypatch.setitem(sys.modules, 'mail_kinds', types.SimpleNamespace(by_kind=lambda *a, **k: []))
    d = scholarships.view()
    assert [x['name'] for x in d['open']] == ['HB & A']
    assert d['open'][0]['content'] == 'Điều kiện: GPA >= 3.2' and d['open'][0]['url'].endswith('/hoc-bong/1/chi-tiet')
    assert sorted(x['name'] for x in d['closed']) == ['HB cũ', 'HB qua hạn']
    assert next(x for x in d['closed'] if x['name'] == 'HB cũ')['applied'] is True
