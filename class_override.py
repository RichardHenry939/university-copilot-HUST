# -*- coding: utf-8 -*-
"""LUẬT (chủ, 14/10/2026): TKB KHÔNG thắng được thông báo đính chính của lớp trên Teams/mail (Claude 2026-10-14).

Thông báo đổi buổi học (nghỉ / chuyển online / đổi phòng / đổi giờ) được mail_events đọc thành chặng "buoi_hoc" của sự kiện
kind=lop trong school/events.json — trước đây chỉ nằm đó, dòng TKB trên 🗓️ Lịch vẫn y nguyên -> chat, tab Lịch báo học như TKB.
Giờ: áp chặng đó lên đúng dòng TKB (Kind=Class, Sync Key "<kỳ>|<mã môn>|<loại>|<ngày>|<giờ>", cùng mã môn + cùng ngày):
  • huỷ          -> tên "❌ NGHỈ (đính chính) · …"
  • online       -> tên/phòng sang Online (chỉ khi TKB đang ghi Offline)
  • đổi phòng    -> Location = phòng mới (chỉ khi chặng ghi rõ mã phòng kiểu D3-401)
  • đổi giờ      -> dời When, giữ thời lượng
Bản gốc TKB ghi một lần vào Notes ("TKB gốc: …"). tkb.run giữ nguyên dòng trùng Sync Key nên sửa không bị ghi đè;
dòng nào bị tạo lại (TKB đổi) thì lượt sau áp lại. Chỉ xét buổi từ hôm nay trở đi.
Giới hạn (cố ý đi tắt): thông báo bị rút lại (chặng hết huy) KHÔNG tự hoàn tác — sửa tay theo "TKB gốc" trong Notes.
Học bù sang ngày KHÔNG có buổi TKB thì không tạo dòng mới (vẫn nằm ở 📡 Sự kiện theo dõi).
  python class_override.py   -> {ok, patched, notes}"""
import uc_config as cfg
import datetime as dt, json, re
from pathlib import Path
from academic import Notion, P, TZ, rt, title

HERE = Path(__file__).resolve().parent
EVENTS_JSON = HERE / 'school' / 'events.json'
EVENTS_DB = cfg.notion("calendar_events")
ONLINE = re.compile(r'(?i)\bonline\b|trực tuyến')
ROOM = re.compile(r'\b([A-D]\d{1,2}[A-Z]?-\d{2,4}[A-Z]?)\b')
MARK = '❌ NGHỈ (đính chính) · '


def _src(e):
    m = (e.get('mails') or [])[-1:] or [{}]
    return f"{m[0].get('nguon') or 'Teams/mail'} {(m[0].get('at') or '')[8:10]}/{(m[0].get('at') or '')[5:7]}".strip()


def corrections(today=None):
    """{(mã môn, 'YYYY-MM-DD'): chặng} — chặng buổi học (từ hôm nay) của các sự kiện lớp đọc từ Teams/mail."""
    today = today or dt.datetime.now(TZ).date().isoformat()
    st = json.loads(EVENTS_JSON.read_text(encoding='utf-8'))
    out = {}
    for e in (st.get('events') or {}).values():
        if e.get('kind') != 'lop' or not e.get('course'): continue
        for s in (e.get('chang') or {}).values():
            if s.get('loai_chang') != 'buoi_hoc' or not s.get('ngay') or s['ngay'] < today: continue
            out[(e['course'], s['ngay'])] = dict(s, _src=_src(e))
    return out


def desired(r, s):
    """Thuộc tính cần ghi cho dòng TKB r theo chặng đính chính s (None nếu không đổi gì)."""
    ev, loc, notes = P(r, 'Event') or '', P(r, 'Location') or '', P(r, 'Notes') or ''
    base = ev[len(MARK):] if ev.startswith(MARK) else ev
    w = r['properties']['When']['date']
    txt = ' '.join(str(s.get(k) or '') for k in ('dia_diem', 'ghi_chu'))
    new_ev, new_loc, new_w, why = base, loc, None, []
    if s.get('huy'):
        new_ev = MARK + base; why.append('nghỉ' + (f": {s['ghi_chu']}" if s.get('ghi_chu') else ''))
    else:
        if ONLINE.search(txt) and 'Offline' in base:
            new_ev = base.replace('Offline', 'Online (đính chính)'); new_loc = 'Online (đính chính)'; why.append('chuyển online')
        else:
            m = ROOM.search(s.get('dia_diem') or '')
            if m and m.group(1) not in loc: new_loc = m.group(1); why.append(f'đổi phòng {loc} → {m.group(1)}')
        if s.get('gio') and re.fullmatch(r'\d{1,2}:\d{2}', s['gio']) and w.get('start') and w['start'][11:16] != s['gio'].zfill(5):
            st0 = dt.datetime.fromisoformat(w['start']); en0 = dt.datetime.fromisoformat(w['end']) if w.get('end') else None
            hh, mm = map(int, s['gio'].split(':')); st1 = st0.replace(hour=hh, minute=mm)
            new_w = {'start': st1.isoformat(timespec='minutes'), 'end': (st1 + (en0 - st0)).isoformat(timespec='minutes') if en0 else None}
            why.append(f"đổi giờ {w['start'][11:16]} → {s['gio']}")
    if new_ev == ev and new_loc == loc and not new_w: return None
    why = why or ['bỏ đính chính cũ (thông báo đã đổi)']
    props = {'Event': title(new_ev), 'Location': rt(new_loc)}
    if new_w: props['When'] = {'date': new_w}
    if 'TKB gốc:' not in notes:   # ghi bản gốc đúng 1 lần để còn sửa tay về được
        notes = (notes + ' · ' if notes else '') + f"TKB gốc: {ev} @ {loc} {(w.get('start') or '')[11:16]}"
    props['Notes'] = rt((f"ĐÍNH CHÍNH ({s['_src']}): {'; '.join(why)} · " + re.sub(r'^ĐÍNH CHÍNH \([^)]*\): [^·]*· ', '', notes))[:1900])
    return props, why


def apply(post):
    corr = corrections()
    if not corr: return {'ok': True, 'patched': 0, 'notes': []}
    nt = Notion(post)
    days = sorted({d for _, d in corr})
    rows = nt.query(EVENTS_DB, {'and': [{'property': 'Kind', 'select': {'equals': 'Class'}},
                                        {'property': 'When', 'date': {'on_or_after': (dt.date.fromisoformat(days[0]) - dt.timedelta(days=1)).isoformat()}},
                                        {'property': 'When', 'date': {'on_or_before': (dt.date.fromisoformat(days[-1]) + dt.timedelta(days=1)).isoformat()}}]})
    done, notes = 0, []
    for r in rows:
        k = (P(r, 'Sync Key') or '').split('|')
        if len(k) < 5 or (k[1], k[3]) not in corr: continue
        d = desired(r, corr[(k[1], k[3])])
        if not d: continue
        nt.patch(r['id'], d[0]); done += 1
        notes.append(f"{k[1]} {k[3][8:10]}/{k[3][5:7]} {k[4]}: " + '; '.join(d[1]))
    return {'ok': True, 'patched': done, 'notes': notes}


if __name__ == '__main__':
    import copilot_app
    print(json.dumps(apply(copilot_app._npost), ensure_ascii=False))
