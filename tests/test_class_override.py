# -*- coding: utf-8 -*-
"""Luật "TKB không thắng đính chính Teams/mail" (class_override.py): chặng buổi học áp lên dòng TKB — dữ liệu giả."""
import json

import class_override as CO


def row(ev, loc, start, end, notes='', key='20261|IT1108|LT+BT|2026-10-15|09:20'):
    t = lambda s: [{'plain_text': s, 'text': {'content': s}}]
    return {'id': 'p1', 'properties': {
        'Event': {'type': 'title', 'title': t(ev)}, 'Location': {'type': 'rich_text', 'rich_text': t(loc)},
        'Notes': {'type': 'rich_text', 'rich_text': t(notes)}, 'Sync Key': {'type': 'rich_text', 'rich_text': t(key)},
        'When': {'type': 'date', 'date': {'start': start, 'end': end}}}}


def text(p, k):
    v = p[k]; arr = v.get('title') or v.get('rich_text') or []
    return ''.join(x['text']['content'] for x in arr)


R = lambda: row('IT1108 · Nhập môn lập trình · LT+BT · Offline', 'D3-401', '2026-10-15T09:20:00.000+07:00', '2026-10-15T11:45:00.000+07:00', 'Mã lớp 171995')
S = lambda **k: dict({'ngay': '2026-10-15', 'loai_chang': 'buoi_hoc', '_src': 'Teams 12/10'}, **k)


def test_huy_danh_dau_nghi_va_giu_ban_goc():
    props, why = CO.desired(R(), S(huy=True, ghi_chu='Nghỉ dịp 70 năm'))
    assert text(props, 'Event').startswith(CO.MARK)
    assert 'TKB gốc: IT1108 · Nhập môn lập trình · LT+BT · Offline @ D3-401 09:20' in text(props, 'Notes')
    assert text(props, 'Notes').startswith('ĐÍNH CHÍNH (Teams 12/10): nghỉ')


def test_chuyen_online_chi_khi_tkb_offline():
    props, why = CO.desired(R(), S(dia_diem='online'))
    assert 'Online (đính chính)' in text(props, 'Event') and text(props, 'Location') == 'Online (đính chính)'
    on = row('IT2000 · Nhập môn CNTT và TT · LT+BT · Online', 'Online', '2026-10-15T16:00:00+07:00', '2026-10-15T17:30:00+07:00')
    assert CO.desired(on, S(ghi_chu='học online qua MS Teams')) is None   # TKB đã Online -> không đụng


def test_doi_phong_va_doi_gio_giu_thoi_luong():
    props, why = CO.desired(R(), S(dia_diem='Phòng D9-201', gio='13:00'))
    assert text(props, 'Location') == 'D9-201'
    assert props['When']['date']['start'].startswith('2026-10-15T13:00') and props['When']['date']['end'].startswith('2026-10-15T15:25')


def test_ap_lan_hai_khong_ghi_lai():
    props, _ = CO.desired(R(), S(huy=True))
    after = row(text(props, 'Event'), text(props, 'Location'), '2026-10-15T09:20:00+07:00', '2026-10-15T11:45:00+07:00', text(props, 'Notes'))
    assert CO.desired(after, S(huy=True)) is None


def test_corrections_chi_lay_buoi_hoc_tu_hom_nay(tmp_path, monkeypatch):
    f = tmp_path / 'events.json'
    f.write_text(json.dumps({'events': {
        'lop-IT2000': {'kind': 'lop', 'course': 'IT2000', 'mails': [{'nguon': 'Teams', 'at': '2026-10-12T10:00'}], 'chang': {
            'b5': {'ngay': '2026-10-15', 'loai_chang': 'buoi_hoc', 'huy': True},
            'b1': {'ngay': '2026-09-10', 'loai_chang': 'buoi_hoc'},
            'tn': {'ngay': '2026-10-20', 'loai_chang': 'thi_nghiem'}}},
        'x': {'kind': None, 'course': None, 'chang': {}}}}), encoding='utf-8')
    monkeypatch.setattr(CO, 'EVENTS_JSON', f)
    c = CO.corrections('2026-10-14')
    assert list(c) == [('IT2000', '2026-10-15')] and c[('IT2000', '2026-10-15')]['_src'] == 'Teams 12/10'
