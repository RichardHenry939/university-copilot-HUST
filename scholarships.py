# -*- coding: utf-8 -*-
"""🎓 Tab Học bổng (Claude 2026-10-05) — tách khỏi Ngoại khoá. CHỈ ĐỌC, không gọi AI.
Nguồn: CTSV HWScholarship/GetApprovedScholarship (qua ctsv_live.json / latest.json) + thư loại 'hoc_bong' (mail_kinds)."""
import datetime as dt, html, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TZ = dt.timezone(dt.timedelta(hours=7))
CTSV = 'https://ctsv.hust.edu.vn'


def _t(s):
    try: return dt.datetime.fromisoformat(str(s).replace(' ', 'T')).replace(tzinfo=TZ)
    except Exception: return None


def view():
    snap = {}
    for f in ('ctsv_live.json', 'latest.json'):
        try:
            d = json.loads((HERE / 'school' / f).read_text(encoding='utf-8')).get('ctsv') or {}
            if d.get('scholarships'): snap = d; break
        except Exception: pass
    now = dt.datetime.now(TZ); items = []
    for s in snap.get('scholarships', []):
        dl = _t(s.get('deadline'))
        items.append({'name': html.unescape(s.get('name') or ''), 'deadline': dl and dl.isoformat(), 'open': bool(dl and dl > now and str(s.get('expired')) != '1'),
                      'type': s.get('type'), 'quantity': s.get('quantity'), 'price': s.get('price'), 'applied': str(s.get('applied')) not in ('0', '', 'None'),
                      'desc': html.unescape(s.get('desc') or '')[:1200], 'more': html.unescape(s.get('more') or ''), 'contact': s.get('contact'),
                      'announced': _t(s.get('created')) and _t(s.get('created')).isoformat(), 'url': f"{CTSV}/hoc-bong/{s.get('id')}/chi-tiet", 'nguon': 'iCTSV'})
    try:
        import mail_kinds
        for m in mail_kinds.by_kind('hoc_bong', days=180):
            items.append({'name': m['subject'], 'deadline': None, 'open': True, 'type': 'Thông báo', 'desc': m.get('tom_tat') or '',
                          'announced': m.get('at'), 'url': (m.get('links') or [None])[0], 'links': m.get('links') or [],
                          'nguon': m['nguon'] + ' · ' + (m.get('from') or '')})
    except Exception: pass
    items.sort(key=lambda x: x.get('announced') or x.get('deadline') or '', reverse=True)
    return {'ok': True, 'open': [x for x in items if x['open']], 'closed': [x for x in items if not x['open']][:30],
            'list': f'{CTSV}/hoc-bong'}
