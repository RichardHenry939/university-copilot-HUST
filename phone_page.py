# -*- coding: utf-8 -*-
"""📱 University Copilot (điện thoại) — trang Notion RIÊNG, cấp cao nhất, dựng giống UC (Claude 2026-10-04).

Xem bằng app Notion kể cả khi laptop ngủ. Trang gồm các mục như UC:
  🔔 Thông báo (ô màu theo mức) · 📅 Hôm nay / Ngày mai (bảng tiết học + hạn trong ngày) · ⏰ Hạn sắp tới (bảng, màu theo loại)
  📡 Sự kiện bạn tham gia · 🎯 Ngoại khoá (minh chứng · đã đăng ký · học bổng · đang mở) · 🗓️ Tuần này · 🔗 Bảng đầy đủ
UC dựng danh sách khối rồi gửi cổng n8n "copilot-phone-page" — cổng CHỈ thay nội dung đúng trang này (PHONE_PAGE trong build.py).
Chỉ gửi khi nội dung đổi (không tính giờ chụp), hoặc 60 phút/lần để làm mới dòng "cập nhật lúc".
Chỉ ĐỌC trên điện thoại: Hoàn tất / Tắt nhắc vẫn làm trên UC ở máy."""
import uc_config as cfg
import datetime as dt, hashlib, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / 'school' / 'phone_page.json'
TZ = dt.timezone(dt.timedelta(hours=7))
PAGE = cfg.notion("phone_page")
DOW = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
DBS = [(cfg.notion("calendar_events"), 'Lịch học'), (cfg.notion("academic_work"), 'Hạn học tập'),
       (cfg.notion("extracurricular"), 'Ngoại khoá'), (cfg.notion("events_track"), 'Sự kiện theo dõi')]
KIND_COLOR = {'Môn học': 'red', 'Tự luyện cốt lõi': 'orange', 'Tự luyện': 'blue'}


# ------------------------------------------------------------------ khối Notion
def T(s, bold=False, color='default', italic=False):
    return {'type': 'text', 'text': {'content': str(s)[:1900]}, 'annotations': {'bold': bold, 'italic': italic, 'color': color}}
def H(level, s, color='default'): return {'object': 'block', 'type': f'heading_{level}', f'heading_{level}': {'rich_text': [T(s)], 'color': color}}
def P(*runs, color='default'): return {'object': 'block', 'type': 'paragraph', 'paragraph': {'rich_text': list(runs) or [T('')], 'color': color}}
def C(runs, emoji, color): return {'object': 'block', 'type': 'callout', 'callout': {'rich_text': runs, 'icon': {'type': 'emoji', 'emoji': emoji}, 'color': color}}
def DIV(): return {'object': 'block', 'type': 'divider', 'divider': {}}
def TOGGLE(title, children): return {'object': 'block', 'type': 'toggle', 'toggle': {'rich_text': [T(title, True)], 'children': children[:90]}}
def BUL(*runs): return {'object': 'block', 'type': 'bulleted_list_item', 'bulleted_list_item': {'rich_text': list(runs)}}
def TABLE(head, rows):
    def cell(v): return v if isinstance(v, list) else [T(v)]
    tr = lambda cells: {'object': 'block', 'type': 'table_row', 'table_row': {'cells': [cell(c) for c in cells]}}
    return {'object': 'block', 'type': 'table', 'table': {'table_width': len(head), 'has_column_header': True, 'has_row_header': False,
                                                         'children': [tr([[T(h, True)] for h in head])] + [tr(r) for r in rows[:60]]}}
def EMPTY(s): return P(T(s, italic=True, color='gray'))


def _hm(iso): return iso[11:16] if iso and len(iso) > 10 else ''
def _dm(iso):
    if not iso: return ''
    y = '' if iso[:4] == str(dt.date.today().year) else '/' + iso[:4]   # năm khác -> ghi kèm năm
    return f"{int(iso[8:10])}/{int(iso[5:7])}{y}"
def _days(d, today):
    k = (d - today).days
    return 'hôm nay' if k == 0 else 'mai' if k == 1 else 'quá hạn' if k < 0 else f'{k} ngày'


def build(post, now=None):
    import timetable, deadlines as D, alerts, extracurricular as X, mail_events as me
    now = now or dt.datetime.now(TZ); today = now.date()
    cls_all = timetable.get(post)['events']
    dls = D.open_list(post, days=21)   # Notion lỗi -> ném lỗi -> không ghi trang thiếu
    xs = X.load().get('items', [])
    ev = me.load()['events']
    notes = {(e['course'], s['ngay']): s['ghi_chu'] for e in ev.values() if e.get('kind') == 'lop' for s in e['chang'].values() if s.get('ngay') and s.get('ghi_chu')}
    B = []
    # đầu trang
    B.append(C([T('Bản chụp University Copilot', True), T(' · cập nhật '), T('{{AT}}', True),
                T('\nChỉ để xem. Hoàn tất / Tắt nhắc làm trên UC ở máy. Laptop ngủ thì nhắc vẫn tới qua ntfy; trang này cập nhật lại khi máy thức.')],
               '📱', 'gray_background'))
    # 🔔 thông báo
    B.append(H(2, '🔔 Thông báo'))
    al = alerts.active(now, cls_all, dls)
    main = [a for a in al if a.get('stage_level') != 'optional']; opt = [a for a in al if a.get('stage_level') == 'optional']
    for a in main:
        col = {'red': 'red_background', 'yellow': 'yellow_background', 'blue': 'blue_background'}.get(a['level'], 'gray_background')
        emo = {'class': '🔔', 'deadline': '⏰', 'extra': '🎯', 'change': '✏️'}.get(a.get('stage_level') or a['kind'], '📌')
        B.append(C([T(a['title'], True), T('\n' + a['text'].split(' — còn ')[0])] + ([T('\n' + a['note'], italic=True)] if a.get('note') else []), emo, col))
    if not main: B.append(EMPTY('Không có thông báo nào.'))
    if opt: B.append(TOGGLE(f'Có thể bạn quan tâm ({len(opt)})', [BUL(T(a['title'].replace('Có thể bạn quan tâm: ', ''), True), T(' — ' + a['text'].split(' — ', 2)[-2] if ' — ' in a['text'] else '')) for a in opt]))
    # 📅 hôm nay / ngày mai
    def day_blocks(d, label):
        out = [H(2, f"📅 {label} · {DOW[d.weekday()]} {d.day}/{d.month}")]
        rows = []
        for c in cls_all:
            if c.get('kind') != 'Class' or c['start'][:10] != d.isoformat(): continue
            parts = c['title'].split(' · '); code = parts[0]
            rows.append([f"{_hm(c['start'])}–{_hm(c.get('end'))}", [T(' · '.join(parts[:2]), True)] + ([T(' ' + parts[2], color='gray')] if len(parts) > 2 else []),
                         c.get('location') or '—', notes.get((code, d.isoformat()), '')])
        out.append(TABLE(['Giờ', 'Môn', 'Phòng', 'Ghi chú (Teams)'], rows) if rows else EMPTY('Không có tiết học.'))
        dd = [x for x in dls if x['due'][:10] == d.isoformat()]
        if dd:
            out.append(H(3, 'Hạn trong ngày'))
            out.append(TABLE(['Hạn', 'Việc', 'Loại'], [[_hm(x['due']), x['name'] + (f" · {x['course']}" if x['course'] else ''), [T(x['kind'], True, KIND_COLOR.get(x['kind'], 'default'))]] for x in dd]))
        ex = [x for x in xs if (x.get('start') or x.get('han') or '')[:10] == d.isoformat()
              and (x['loai'] in ('Đã đăng ký', 'Hạn nộp minh chứng') or (x['loai'] == 'Sự kiện (mail/Teams)' and x.get('must')))]
        if ex:
            out.append(H(3, 'Ngoại khoá trong ngày'))
            out.append(TABLE(['Giờ', 'Hoạt động', 'Địa điểm'], [[_hm(x.get('start') or x.get('han')), x['name'], x.get('place') or '—'] for x in ex]))
        return out
    B += day_blocks(today, 'Hôm nay')
    B += day_blocks(today + dt.timedelta(days=1), 'Ngày mai')
    # ⏰ hạn
    B.append(H(2, '⏰ Hạn sắp tới · 3 tuần'))
    if dls:
        B.append(TABLE(['Hạn', 'Việc', 'Môn', 'Loại', 'Còn'],
                       [[f"{_hm(x['due'])} {_dm(x['due'])}", x['name'], x['course'] or '—', [T(x['kind'], True, KIND_COLOR.get(x['kind'], 'default'))],
                         [T(_days(dt.date.fromisoformat(x['due'][:10]), today), x['minsLeft'] < 1440, 'red' if x['minsLeft'] < 1440 else 'default')]] for x in dls]))
        rv = [x for x in dls if x.get('review')]
        for x in rv: B.append(C([T(x['name'] + ': ', True), T(x['review'])], '⚠️', 'yellow_background'))
    else: B.append(EMPTY('Không có hạn nào trong 3 tuần tới.'))
    # 📡 sự kiện bạn tham gia
    B.append(H(2, '📡 Sự kiện bạn tham gia'))
    rows = []
    for e in ev.values():
        if e.get('status') != 'Đang theo dõi' or e.get('kind'): continue
        for k, s in e['chang'].items():
            w = me.when_of(s); ack = ((e.get('ack') or {}).get(k) or {}).get('choice')
            if w and w >= now and (e.get('must') or ack == 'Sẽ đi') and ack != 'Bỏ' and not s.get('huy'):
                rows.append((w, [f"{w:%H:%M} {w.day}/{w.month}", e['ten'], s['ten'], s.get('dia_diem') or '—']))
    B.append(TABLE(['Khi', 'Sự kiện', 'Chặng', 'Địa điểm'], [r for _, r in sorted(rows, key=lambda t: t[0])]) if rows else EMPTY('Không có sự kiện nào sắp tới.'))
    # 🎯 ngoại khoá
    B.append(H(2, '🎯 Ngoại khoá'))
    up = lambda x: (x.get('han') or x.get('end') or x.get('start') or '') >= now.isoformat()
    mc = [x for x in xs if x['loai'] == 'Hạn nộp minh chứng' and up(x)]
    B.append(H(3, 'Hạn nộp minh chứng (điểm rèn luyện)'))
    B.append(TABLE(['Hạn', 'Hoạt động', 'Trạng thái'], [[f"{_hm(x['han'])} {_dm(x['han'])}", x['name'], x['status']] for x in mc]) if mc else EMPTY('Không có.'))
    mine = sorted([x for x in xs if x['loai'] == 'Đã đăng ký'], key=lambda x: x.get('start') or '', reverse=True)
    B.append(H(3, 'Hoạt động bạn đã đăng ký'))
    B.append(TABLE(['Ngày', 'Hoạt động', 'Trạng thái'],
                   [[_dm(x.get('start')) + (f" → {_dm(x['end'])}" if x.get('end') and x['end'][:10] != (x.get('start') or '')[:10] else ''), x['name'],
                     [T(x['status'], True, 'green' if x['status'] == 'Đã xác nhận' else 'orange' if x['status'] == 'Chờ xác nhận' else 'red')]] for x in mine])
             if mine else EMPTY('Chưa đăng ký hoạt động nào trên CTSV.'))
    sch = [x for x in xs if x['loai'] == 'Học bổng' and up(x)]
    B.append(H(3, 'Học bổng còn hạn'))
    B.append(TABLE(['Hạn', 'Học bổng', 'Ghi chú'], [[f"{_hm(x['han'])} {_dm(x['han'])}", x['name'], x.get('note') or ''] for x in sch]) if sch else EMPTY('Không có.'))
    op = [x for x in xs if x['loai'] == 'Đang mở' and up(x)]
    B.append(H(3, 'Đang mở trên CTSV'))
    B.append(TABLE(['Tới', 'Hoạt động', 'Loại'], [[_dm(x.get('end')), x['name'], x.get('type') or ''] for x in op]) if op else EMPTY('Không có.'))
    # 🗓️ tuần này
    nxt = today.weekday() >= 5   # T7 / CN -> xem tuần tới
    mon = today - dt.timedelta(days=today.weekday()) + (dt.timedelta(days=7) if nxt else dt.timedelta())
    B.append(H(2, ('🗓️ Tuần tới' if nxt else '🗓️ Tuần này') + f' · {mon.day}/{mon.month} – {(mon + dt.timedelta(days=6)).day}/{(mon + dt.timedelta(days=6)).month}'))
    wrows = []
    for i in range(7):
        d = mon + dt.timedelta(days=i)
        cs = [f"{_hm(c['start'])} {c['title'].split(' · ')[1] if ' · ' in c['title'] else c['title']} ({c.get('location') or '?'})"
              for c in cls_all if c.get('kind') == 'Class' and c['start'][:10] == d.isoformat()]
        hs = [f"⏰ {x['name']}" for x in dls if x['due'][:10] == d.isoformat()]
        wrows.append([[T(f"{DOW[i]} {d.day}/{d.month}", True, 'blue' if d == today else 'default')], '\n'.join(cs) or '—', '\n'.join(hs) or ''])
    B.append(TABLE(['Ngày', 'Tiết học', 'Hạn'], wrows))
    # 🔗 bảng đầy đủ
    B.append(DIV()); B.append(H(3, '🔗 Mở bảng đầy đủ'))
    for dbid, _ in DBS: B.append({'object': 'block', 'type': 'link_to_page', 'link_to_page': {'type': 'database_id', 'database_id': dbid}})
    return B


def update(post, force=False):
    import copilot_app as app
    try: c = json.loads(CFG.read_text(encoding='utf-8'))
    except Exception: c = {}
    blocks = build(post)
    raw = json.dumps(blocks, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha1(raw.encode()).hexdigest()
    now = dt.datetime.now(TZ)
    if not force and c.get('hash2') == h and c.get('at2') and (now - dt.datetime.fromisoformat(c['at2'])).total_seconds() < 3600:
        return {'ok': True, 'changed': False}
    blocks = json.loads(raw.replace('{{AT}}', f"{now:%H:%M %d/%m}"))
    r = app.n8n('copilot-phone-page', {'blocks': blocks}, timeout=300)
    r = r[0] if isinstance(r, list) else r
    if not r.get('ok'): raise RuntimeError(f"trang điện thoại: {r}")
    c.update(hash2=h, at2=now.isoformat(timespec='minutes'), page=PAGE); CFG.write_text(json.dumps(c, ensure_ascii=False), encoding='utf-8')
    return {'ok': True, 'changed': True, 'blocks': len(blocks)}
