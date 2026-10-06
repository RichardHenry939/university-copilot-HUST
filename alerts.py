# -*- coding: utf-8 -*-
"""Cảnh báo sự kiện tự tìm đến bạn (Claude 2026-10-04) — đọc school/events.json (mail_events.py).

Leo thang theo thời gian, mỗi chặng chưa huỷ của sự kiện đang theo dõi:
  ≤72 giờ  -> VÀNG  (toast 1 lần; banner UC tới khi bấm "Đã biết")
  ≤24 giờ  -> ĐỎ    (toast khi vào mức + mỗi 6 giờ; banner tới khi "Đã biết" / "Sẽ đi" / "Bỏ")
  trong ngày -> ĐỎ GHIM: không tắt được bằng "Đã biết" — chỉ "Sẽ đi" hoặc "Bỏ" (toast mỗi giờ tới khi chọn)
Thư đính chính (Trước → Nay) -> ĐỎ "thay đổi": toast ngay, banner tới khi "Đã biết". Thư cũ nạp lần đầu (backfill) không toast.
Toast chỉ 06:00–23:00. Nội dung toast = chính sự việc (tên · chặng — ngày giờ, phòng — còn bao lâu), không phải "bạn có thông báo"."""
import json, base64, subprocess, datetime as dt
from pathlib import Path
import mail_events as me

HERE = Path(__file__).resolve().parent
STATE = HERE / 'school' / 'alerts.json'
TZ = me.TZ
UC = 'http://127.0.0.1:8320/'
APP_ID = r'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'


def _load():
    try: return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception: return {'sent': {}}


def _save(s): STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding='utf-8')


def left(w, now):
    s = (w - now).total_seconds()
    if s <= 0: return 'đang diễn ra' if s > -3 * 3600 else 'đã qua'
    h = int(s // 3600); m = int(s % 3600 // 60)
    if h >= 48: return f'còn {h // 24} ngày {h % 24} giờ'
    return f'còn {h} giờ {m:02d} phút' if h else f'còn {m} phút'


CLASS_SLOTS = (30, 15)   # nhắc tiết học trước 30 và 15 phút
DL_MARKS = (72, 48, 36, 24)   # nhắc hạn nộp ở các mốc (giờ)


def class_alerts(classes, now, st=None):
    """Tiết học (Kind=Class trong lịch, đã gồm phòng đổi theo Teams) bắt đầu trong 30 phút tới -> nhắc giờ + phòng cụ thể.
    Kèm ghi chú buổi đó từ nhóm Teams của lớp (vd danh sách học offline) nếu có."""
    if not classes: return []
    st = st or me.load(); acked = _load().get('cls_ack', {})
    notes = {}
    for e in st['events'].values():
        if e.get('kind') == 'lop':
            for s in e['chang'].values():
                if s.get('ngay') and s.get('ghi_chu'): notes[(e['course'], s['ngay'])] = s['ghi_chu']
    out = []
    for c in classes:
        if c.get('kind') != 'Class': continue
        try: w = dt.datetime.fromisoformat(c['start']).astimezone(TZ)
        except Exception: continue
        mins = (w - now).total_seconds() / 60
        if not (0 < mins <= CLASS_SLOTS[0]): continue
        cid = f"cls|{c['id']}|{c['start'][:16]}"
        if cid in acked: continue
        end = dt.datetime.fromisoformat(c['end']).astimezone(TZ).strftime('%H:%M') if c.get('end') else ''
        name = ' · '.join(c['title'].split(' · ')[:2]); code = c['title'].split(' · ')[0]
        out.append({'id': cid, 'kind': 'class', 'level': 'blue', 'eid': cid, 'when': w.isoformat(), 'stage_level': 'class', 'mins': mins,
                    'title': f"Sắp vào học: {name}", 'text': f"{w:%H:%M}{'–' + end if end else ''} · {c.get('location') or 'chưa có phòng'} — còn {int(mins + 0.5)} phút",
                    'note': notes.get((code, w.date().isoformat()), ''), 'buttons': ['Đã biết']})
    return out


def deadline_alerts(dls, now):
    """Hạn trong 📋 Academic Work (deadlines.open_list) còn ≤72 giờ, chưa Hoàn tất, chưa Tắt nhắc."""
    import deadlines as D
    muted = _load().get('dl_mute', {})
    out = []
    for x in dls or []:
        if x['overdue'] or f"dl|{x['id']}" in muted: continue
        w = dt.datetime.fromisoformat(x['due']).astimezone(TZ); left = (w - now).total_seconds() / 60
        if left > 72 * 60: continue
        who = f"{x['name']}" + (f" · {x['course']}" if x['course'] else '')
        out.append({'id': f"dl|{x['id']}", 'kind': 'deadline', 'level': 'red' if left <= 24 * 60 else 'yellow', 'eid': f"dl|{x['id']}",
                    'when': w.isoformat(), 'stage_level': 'deadline', 'dl': x, 'mins': left,
                    'title': f"Hạn {x['kind'].lower()}: {who}", 'text': f"hạn {w:%H:%M} {w.day}/{w.month} — còn {D.say_left(left)}",
                    'note': '', 'buttons': ['Hoàn tất', 'Tắt nhắc']})
    return out


def extra_alerts(now):
    """🎯 Ngoại khoá: hoạt động đã đăng ký sắp diễn ra (≤24 giờ) · hạn nộp minh chứng còn ≤72 giờ. Nút: Tắt nhắc."""
    try:
        import extracurricular as X
        items = X.alert_items(X.load(), now)
    except Exception as e:
        print('extra alerts:', e); return []
    import deadlines as D
    muted = _load().get('dl_mute', {}); out = []
    for x in items:
        eid = f"ex|{x['key']}"
        if eid in muted: continue
        w = dt.datetime.fromisoformat(x['when']).astimezone(TZ); left = (w - now).total_seconds() / 60
        if left <= 0 or left > (72 * 60 if x['loai'] == 'Hạn nộp minh chứng' else 24 * 60): continue
        mc = x['loai'] == 'Hạn nộp minh chứng'
        out.append({'id': eid, 'kind': 'extra', 'level': 'red' if left <= 24 * 60 else 'yellow', 'eid': eid, 'when': w.isoformat(),
                    'stage_level': 'extra', 'mins': left, 'marks': x['marks'],
                    'title': ('Hạn nộp minh chứng: ' if mc else 'Ngoại khoá sắp diễn ra: ') + x['name'],
                    'text': (f"hạn {w:%H:%M} {w.day}/{w.month}" if mc else f"{w:%H:%M} {w.day}/{w.month}" + (f" · {x['place']}" if x.get('place') else '')) + f" — còn {D.say_left(left)}",
                    'note': x.get('note') or '', 'buttons': ['Tắt nhắc']})
    return out


def active(now=None, classes=None, dls=None):
    """Danh sách cảnh báo đang hiệu lực (cho banner UC và toast)."""
    now = now or dt.datetime.now(TZ)
    st = me.load(); out = class_alerts(classes, now, st) + deadline_alerts(dls, now) + extra_alerts(now)
    for eid, e in st['events'].items():
        if e.get('status') != 'Đang theo dõi': continue
        for ch in e.get('changes', []):
            if ch.get('ack') or ch.get('backfill'): continue
            out.append({'id': f"chg|{eid}|{ch['at']}", 'kind': 'change', 'level': 'red', 'eid': eid, 'change_at': ch['at'],
                        'title': f"Thay đổi: {e['ten']}" + (f" ({ch['nguon']})" if ch.get('nguon') else ''), 'text': ' · '.join(ch['lines']), 'buttons': ['Đã biết']})
        if e.get('kind') in ('lop', 'bt'): continue   # buổi học: chỉ báo khi ĐỔI · bài tập: nhắc qua 📋 Academic Work (deadlines.py), không nhắc trùng
        for k, s in e['chang'].items():
            w = me.when_of(s)
            if not w or s.get('huy'): continue
            ack = (e.get('ack') or {}).get(k) or {}
            if ack.get('choice') in ('Bỏ', 'Đã nộp'): continue
            dl = s.get('loai_chang') == 'han_nop' or e.get('kind') == 'bt'
            delta = (w - now).total_seconds()
            if delta < -3 * 3600: continue
            if w.date() == now.date() or delta <= 0: lvl = 'day'
            elif delta <= 24 * 3600: lvl = 'red'
            elif delta <= 72 * 3600: lvl = 'yellow'
            else: continue
            if ack.get('choice') == 'Sẽ đi' and lvl != 'day': continue        # đã hứa đi: chỉ nhắc lại trong ngày
            if ack.get('choice') == 'Đã biết' and ack.get('level') == lvl: continue   # "Đã biết" chỉ tắt đúng mức đó; lên mức là hiện lại
            going = ack.get('choice') == 'Sẽ đi'
            if not e.get('kind') and not e.get('must') and not going:   # lời mời chung, bạn chưa nói sẽ đi: chỉ gợi ý trong UC, không toast/điện thoại
                if (e.get('ack') or {}).get(k, {}).get('choice') == 'Đã biết': continue
                out.append({'id': f"opt|{eid}|{k}", 'kind': 'stage', 'level': 'yellow', 'pinned': False, 'eid': eid, 'stage': k, 'when': w.isoformat(),
                            'stage_level': 'optional', 'going': False, 'title': f"Có thể bạn quan tâm: {e['ten']} · {s['ten']}",
                            'text': f"{e['ten']} · {s['ten']} — {me.fmt(s)} — {left(w, now)}", 'note': s.get('ghi_chu') or '',
                            'buttons': ['Sẽ đi', 'Bỏ']})
                continue
            fact = f"{e['ten']} · {s['ten']} — {'hạn ' if dl else ''}{me.fmt(s)} — {left(w, now)}"
            out.append({'id': f"stg|{eid}|{k}|{lvl}", 'kind': 'stage', 'level': 'red' if lvl != 'yellow' else 'yellow', 'pinned': lvl == 'day' and not going,
                        'eid': eid, 'stage': k, 'when': w.isoformat(), 'stage_level': lvl, 'going': going, 'deadline': dl,
                        'title': ('Hôm nay: ' if lvl == 'day' else '') + f"{e['ten']} · {s['ten']}", 'text': fact,
                        'note': s.get('ghi_chu') or '',
                        'buttons': (['Đã nộp', 'Bỏ'] if lvl == 'day' else ['Đã nộp', 'Đã biết']) if dl else
                                   ['Sẽ đi', 'Bỏ'] if lvl == 'day' and not going else (['Đã biết'] if going else ['Sẽ đi', 'Bỏ', 'Đã biết'])})
    rank = {'class': 0, 'deadline': 1, 'extra': 2, 'day': 3, 'change': 4, 'red': 5, 'yellow': 6, 'optional': 7}
    return sorted(out, key=lambda a: (rank.get(a.get('stage_level') or a['kind'], 9), a.get('when') or ''))


def ack(eid, choice, stage=None, change_at=None, post=None):
    if eid.startswith('dl|') or eid.startswith('ex|'):   # hạn nộp / ngoại khoá: "Tắt nhắc" chỉ dừng thông báo — mục vẫn ở danh sách
        s = _load(); s.setdefault('dl_mute', {})[eid] = dt.datetime.now(TZ).isoformat(timespec='minutes'); _save(s)
        return {'ok': True}
    if eid.startswith('cls|'):   # tiết học: chỉ ẩn nhắc của buổi này
        s = _load(); s.setdefault('cls_ack', {})[eid] = dt.datetime.now(TZ).isoformat(timespec='minutes'); _save(s)
        return {'ok': True}
    st = me.load(); e = st['events'][eid]
    now = dt.datetime.now(TZ).isoformat(timespec='minutes')
    if change_at:
        for ch in e['changes']:
            if ch['at'] == change_at: ch['ack'] = now
    elif stage:
        lvl = next((a.get('stage_level') for a in active() if a.get('eid') == eid and a.get('stage') == stage), None)
        e.setdefault('ack', {})[stage] = {'choice': choice, 'level': lvl, 'at': now}
    me.save(st)
    if post and stage and choice in ('Sẽ đi', 'Bỏ', 'Đã nộp'):
        me.sync_notion(post, st, only=eid)   # ghi "Xác nhận" lên 📡 Sự kiện theo dõi
    return {'ok': True}


def toast(title, text, persistent=False):
    esc = lambda s: str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    xml = (f'<toast{" scenario=\"reminder\"" if persistent else ""} activationType="protocol" launch="{UC}">'
           f'<visual><binding template="ToastGeneric"><text>{esc(title)}</text><text>{esc(text)}</text></binding></visual>'
           f'<actions><action content="Mở UC" activationType="protocol" arguments="{UC}"/>'
           + ('<action content="Để sau" activationType="system" arguments="dismiss"/>' if persistent else '') +
           '</actions><audio src="ms-winsoundevent:Notification.Reminder"/></toast>')
    ps = ("[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
          "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null;"
          "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;$x.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
          + base64.b64encode(xml.encode('utf-8')).decode() + "')));"
          f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_ID}').Show([Windows.UI.Notifications.ToastNotification]::new($x))")
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(ps.encode('utf-16-le')).decode()],
                   capture_output=True, timeout=60, creationflags=0x08000000)


def phone(title, text, priority=4, actions=None):
    """Đẩy lên điện thoại qua ntfy (kênh trong school/ntfy.json). Lỗi mạng không làm hỏng toast."""
    import urllib.request
    try: c = json.loads((HERE / 'school' / 'ntfy.json').read_text(encoding='utf-8'))
    except Exception: return False
    b = {'topic': c['topic'], 'title': title, 'message': text, 'priority': priority, 'tags': ['rotating_light' if priority >= 5 else 'warning']}
    if actions: b['actions'] = actions[:3]   # nút bấm ngay trên thông báo (phone_link: có chữ ký, luôn hỏi Xác nhận)
    body = json.dumps(b).encode('utf-8')
    try:
        urllib.request.urlopen(urllib.request.Request(c.get('server', 'https://ntfy.sh'), data=body, headers={'Content-Type': 'application/json'}), timeout=20).read()
        return True
    except Exception as e:
        print('ntfy:', e); return False


def notify(title, text, persistent=False, level='red', alert=None, phone_ok=True):
    """Máy tính (toast) + điện thoại (ntfy, chỉ mức đỏ / thay đổi / trong ngày).
    phone_ok=False: ntfy đã giữ hộ lần nhắc này (phone_sched, hẹn trước) -> chỉ toast, không đẩy trùng."""
    toast(title, text, persistent)
    if level != 'yellow' and phone_ok:
        try:
            import phone_link; acts = phone_link.actions_for(alert)
        except Exception as e: print('phone actions:', e); acts = None
        phone(title, text, 5 if persistent else 4, acts)


EVERY = {'yellow': None, 'red': 6 * 3600, 'day': 3600, 'change': None, 'optional': None}   # None = chỉ 1 lần


def tick(now=None, send=notify, classes=None, dls=None):
    """Gọi mỗi phút: toast + điện thoại cho những cảnh báo tới lúc nhắc. -> danh sách đã gửi."""
    now = now or dt.datetime.now(TZ)
    quiet = not (6 <= now.hour < 23)
    s = _load(); sent = []
    try:
        import phone_sched; sched = phone_sched.scheduled_keys()
    except Exception: sched = set()
    for a in active(now, classes, dls):
        key = a['id']; lvl = a.get('stage_level') or a['kind']
        if lvl == 'deadline':   # mốc theo loại hạn; đêm vẫn nhắc các mốc ≤1 giờ (hạn 23:59 cần nhắc 30/20/10/5/2/1 phút)
            import deadlines as D
            mark, left = D.mark_due(a['dl'], now)
            k2 = f"{key}|{mark}"
            if mark is None or s['sent'].get(k2): continue   # LUẬT (06/10): kệ giờ, phải đúng mốc — thông báo không tự mất đi
            x = a['dl']
            send(f"Còn {D.say_left(mark)}: {x['name']}" + (f" · {x['course']}" if x['course'] else ''),
                 f"{x['kind']} — {a['text'].split(' — ')[0]}", persistent=mark <= 60, level='red', alert=a, phone_ok=k2 not in sched)
            s['sent'][k2] = now.isoformat(timespec='seconds'); sent.append(k2); continue
        if lvl == 'extra':   # ngoại khoá: đúng các mốc của mục (sự kiện 24h/2h · hạn MC như tự luyện cốt lõi)
            import deadlines as D
            mark = D.mark_at(a['marks'], a['mins'])
            k2 = f"{key}|{mark}"
            if mark is None or s['sent'].get(k2): continue   # LUẬT (06/10): kệ giờ, phải đúng mốc — thông báo không tự mất đi
            send(f"Còn {D.say_left(mark)}: " + a['title'], a['text'] + (f"\n{a['note']}" if a.get('note') else ''), level='red', alert=a, phone_ok=k2 not in sched)
            s['sent'][k2] = now.isoformat(timespec='seconds'); sent.append(k2); continue
        if lvl == 'class':   # tiết học: đúng 2 lần, trước 30 và 15 phút
            import deadlines as D
            slot = D.mark_at(CLASS_SLOTS, a['mins'], 3)   # đúng mốc 30 / 15 phút, lỡ thì bỏ
            k2 = f'{key}|{slot}'
            if slot is None or s['sent'].get(k2): continue
            send(f"Còn {slot} phút: " + a['title'].split(': ', 1)[1], a['text'].rsplit(' — ', 1)[0] + (f"\n{a['note']}" if a.get('note') else ''), level='red', phone_ok=k2 not in sched)
            s['sent'][k2] = now.isoformat(timespec='seconds'); sent.append(k2); continue
        if a.get('deadline') and lvl in ('yellow', 'red'):   # hạn nộp: nhắc đúng các mốc 72 / 48 / 36 / 24 giờ
            hours = (dt.datetime.fromisoformat(a['when']) - now).total_seconds() / 3600
            import deadlines as D
            mark = next((m for m in DL_MARKS if m - D.GRACE / 60 <= hours <= m), None)   # đúng mốc, lỡ thì bỏ qua
            k2 = f"dl|{a['eid']}|{a['stage']}|{mark}"
            if mark is None or s['sent'].get(k2): continue
            send(f"Còn {mark} giờ: " + a["title"], a['text'] + (f"\n{a['note']}" if a.get('note') else ''), level='red', alert=a)
            s['sent'][k2] = now.isoformat(timespec='seconds'); sent.append(k2); continue
        if quiet: continue
        if lvl == 'optional': continue   # gợi ý: chỉ banner trong UC
        last = s['sent'].get(key)
        every = EVERY[lvl]
        if a.get('going') and lvl == 'day':   # đã chọn "Sẽ đi": chỉ nhắc 2 giờ và 30 phút trước
            w = dt.datetime.fromisoformat(a['when']); mins = (w - now).total_seconds() / 60
            slot = '120' if 100 < mins <= 120 else '30' if 15 < mins <= 30 else None
            if not slot or s['sent'].get(key + '|' + slot): continue
            key, every = key + '|' + slot, None
            last = None
        if last and (every is None or (now - dt.datetime.fromisoformat(last)).total_seconds() < every): continue
        ev_sched = a.get('kind') == 'stage' and any(k.startswith(f"ev|{a['eid']}|{a.get('stage')}|") for k in sched)
        send(a['title'], a['text'] + (f"\n{a['note']}" if a.get('note') else ''), persistent=a.get('pinned', False), level=a['level'], alert=a,
             phone_ok=not ev_sched or lvl == 'day')   # 24h / 2h / 30 phút đã hẹn trên ntfy; nhắc ghim trong ngày vẫn đẩy
        s['sent'][key] = now.isoformat(timespec='seconds'); sent.append(a['id'])
    _save(s)
    return sent


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['test']:   # toast thử, không đụng dữ liệu
        print('phone', phone('UC · thử cảnh báo', 'Tin thử từ University Copilot. Cảnh báo thật sẽ ghi chính sự việc: tên · chặng — ngày giờ, phòng — còn bao lâu.', 4))
    else:
        print(json.dumps(active(), ensure_ascii=False, indent=1))
