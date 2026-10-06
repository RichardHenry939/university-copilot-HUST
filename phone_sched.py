# -*- coding: utf-8 -*-
"""Nhắc vẫn đến điện thoại khi laptop ngủ (Claude 2026-10-04).

Máy còn thức -> UC hẹn sẵn trên máy chủ ntfy (tối đa 3 ngày, ở đây 70 giờ) mọi lần nhắc sắp tới:
  • tiết học: 30 và 15 phút trước (giờ + phòng, đã gồm đổi phòng theo Teams)
  • hạn học tập (📋 Academic Work): đúng các mốc theo "Loại hạn" (Tự luyện / Tự luyện cốt lõi / Môn học)
  • ngoại khoá đã đăng ký (24h + 2h trước) · hạn nộp minh chứng (mốc như tự luyện cốt lõi)
  • sự kiện bạn tham gia (thi, phỏng vấn…): 24 giờ, 2 giờ, 30 phút trước
Mỗi lần nhắc có mã cố định (sequence id) -> có thay đổi thì SỬA tin đã hẹn, hết cần (Hoàn tất / Tắt nhắc / Bỏ / qua giờ…) thì HUỶ.
Giờ yên lặng 23:00–06:00: mốc > 1 giờ dời về 06:00 (như nhắc trên máy); mốc ≤ 1 giờ vẫn gửi.
Những lần nhắc này KHÔNG gửi lại từ vòng cảnh báo trên máy (tránh trùng) — trên máy chỉ còn toast."""
import datetime as dt, hashlib, json, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / 'school' / 'ntfy_sched.json'
TZ = dt.timezone(dt.timedelta(hours=7))
HORIZON = dt.timedelta(hours=70)


def _cfg(): return json.loads((HERE / 'school' / 'ntfy.json').read_text(encoding='utf-8'))
def _load():
    try: return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception: return {'items': {}}
def _save(s): STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding='utf-8')
def seq(key): return 'uc' + hashlib.sha1(key.encode()).hexdigest()[:30]


def _quiet_shift(t, mark_min, due):
    """(06/10) Không dời mốc sang 06:00 nữa (từng sinh "còn 41 giờ"): mọi mốc gửi đúng giờ, đúng số."""
    return t   # (06/10) mốc đêm vẫn gửi ĐÚNG giờ nhưng im lặng (priority 2, xem cuối plan) — không bỏ, không dời


def plan(post, now=None):
    """-> {key: {at, title, text, priority, actions}} cho 70 giờ tới."""
    import timetable, deadlines as D, alerts, extracurricular as X, mail_events as me
    now = now or dt.datetime.now(TZ); end = now + HORIZON
    st_al = alerts._load(); muted = st_al.get('dl_mute', {}); cls_ack = st_al.get('cls_ack', {})
    out = {}
    # tiết học
    notes = {}
    for e in me.load()['events'].values():
        if e.get('kind') == 'lop':
            for s in e['chang'].values():
                if s.get('ngay') and s.get('ghi_chu'): notes[(e['course'], s['ngay'])] = s['ghi_chu']
    for c in timetable.get(post)['events']:
        if c.get('kind') != 'Class': continue
        w = dt.datetime.fromisoformat(c['start']).astimezone(TZ)
        if not (now < w <= end): continue
        if f"cls|{c['id']}|{c['start'][:16]}" in cls_ack: continue
        en = dt.datetime.fromisoformat(c['end']).astimezone(TZ).strftime('%H:%M') if c.get('end') else ''
        name = ' · '.join(c['title'].split(' · ')[:2]); code = c['title'].split(' · ')[0]
        for m in (30, 15):
            t = w - dt.timedelta(minutes=m)
            if t <= now or not (6 <= t.hour < 23): continue
            note = notes.get((code, w.date().isoformat()), '')
            out[f"cls|{c['id']}|{c['start'][:16]}|{m}"] = {'at': t, 'title': f"Còn {m} phút: {name}", 'priority': 4,
                'text': f"{w:%H:%M}{'–' + en if en else ''} · {c.get('location') or 'chưa có phòng'}" + (f"\n{note}" if note else '')}
    # hạn học tập
    for x in D.open_list(post, days=4):
        if x['overdue'] or f"dl|{x['id']}" in muted: continue
        due = dt.datetime.fromisoformat(x['due']).astimezone(TZ)
        for m in D.MARKS.get(x['kind'], D.MARKS['Môn học']):
            t = _quiet_shift(due - dt.timedelta(minutes=m), m, due)
            if not t or t <= now or t > end: continue
            left = (due - t).total_seconds() / 60
            out[f"dl|{x['id']}|{m}"] = {'at': t, 'title': f"Còn {D.say_left(left)}: {x['name']}" + (f" · {x['course']}" if x['course'] else ''),
                                        'text': f"{x['kind']} — hạn {due:%H:%M} {due.day}/{due.month}", 'priority': 5 if m <= 60 else 4}
    # ngoại khoá
    for x in X.alert_items(X.load(), now):
        if f"ex|{x['key']}" in muted: continue
        w = dt.datetime.fromisoformat(x['when']).astimezone(TZ)
        mc = x['loai'] == 'Hạn nộp minh chứng'
        for m in x['marks']:
            t = _quiet_shift(w - dt.timedelta(minutes=m), m, w)
            if not t or t <= now or t > end: continue
            left = (w - t).total_seconds() / 60
            out[f"ex|{x['key']}|{m}"] = {'at': t, 'title': f"Còn {D.say_left(left)}: " + ('Hạn nộp minh chứng: ' if mc else 'Ngoại khoá: ') + x['name'],
                                         'text': (f"hạn {w:%H:%M} {w.day}/{w.month}" if mc else f"{w:%H:%M} {w.day}/{w.month}" + (f" · {x['place']}" if x.get('place') else '')),
                                         'priority': 4}
    # sự kiện bạn tham gia (mail / Teams), không phải lịch lớp / bài tập
    for eid, e in me.load()['events'].items():
        if e.get('status') != 'Đang theo dõi' or e.get('kind'): continue
        for k, s in e['chang'].items():
            ack = ((e.get('ack') or {}).get(k) or {}).get('choice')
            if not (e.get('must') or ack == 'Sẽ đi') or ack in ('Bỏ', 'Đã nộp') or s.get('huy'): continue
            w = me.when_of(s)
            if not w or not (now < w <= end + dt.timedelta(days=1)): continue
            for m in (24 * 60, 120, 30):
                t = _quiet_shift(w - dt.timedelta(minutes=m), m, w)
                if not t or t <= now or t > end: continue
                left = (w - t).total_seconds() / 60
                out[f"ev|{eid}|{k}|{m}"] = {'at': t, 'title': f"Còn {D.say_left(left)}: {e['ten']} · {s['ten']}",
                                            'text': me.fmt(s) + (f"\n{s['ghi_chu']}" if s.get('ghi_chu') else ''), 'priority': 5 if m <= 120 else 4}
    for k, b in out.items():   # giờ yên lặng 23:00–06:00: mốc > 60 phút vẫn tới đúng giờ nhưng không chuông / rung
        if not (6 <= b['at'].hour < 23) and int(k.rsplit('|', 1)[1]) > 60: b['priority'] = 2
    return out


def _send(topic, sid, body, at):
    req = urllib.request.Request(f"https://ntfy.sh/{topic}/{sid}", data=body['text'].encode('utf-8'), method='PUT',
                                 headers={'Title': '=?UTF-8?B?' + __import__('base64').b64encode(body['title'].encode('utf-8')).decode() + '?=',   # RFC 2047
                                          'At': str(int(at.timestamp())),
                                          'Priority': str(body['priority']), 'Tags': 'alarm_clock'})
    urllib.request.urlopen(req, timeout=20).read()


def _cancel(topic, sid):
    urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}/{sid}", method='DELETE'), timeout=20).read()


def reconcile(post, now=None, dry=False):
    """Đưa danh sách hẹn trên ntfy về đúng kế hoạch: hẹn mới · sửa tin đổi nội dung / giờ · huỷ tin không còn cần."""
    now = now or dt.datetime.now(TZ)
    want = plan(post, now)
    s = _load(); have = s['items']; topic = _cfg()['topic']
    added = changed = cancelled = 0; errors = []
    for key, b in want.items():
        sig = hashlib.sha1(json.dumps([b['title'], b['text'], int(b['at'].timestamp())], ensure_ascii=False).encode()).hexdigest()[:16]
        cur = have.get(key)
        if cur and cur['sig'] == sig: continue
        if (b['at'] - now).total_seconds() < 15: continue   # ntfy cần hẹn ≥10 giây; sát giờ thì để vòng trên máy lo
        if not dry:
            try: _send(topic, seq(key), b, b['at'])
            except Exception as e: errors.append(f'{key}: {e}'); continue
        have[key] = {'sig': sig, 'at': b['at'].isoformat(timespec='minutes'), 'title': b['title']}
        added += 0 if cur else 1; changed += 1 if cur else 0
    for key in list(have):
        if key in want: continue
        at = dt.datetime.fromisoformat(have[key]['at'])
        if at > now + dt.timedelta(seconds=20) and not dry:   # chưa gửi -> huỷ trên ntfy
            try: _cancel(topic, seq(key)); cancelled += 1
            except Exception as e: errors.append(f'cancel {key}: {e}'); continue
        del have[key]   # đã qua giờ (ntfy đã gửi) hoặc vừa huỷ
    if not dry: _save(s)
    return {'planned': len(want), 'added': added, 'changed': changed, 'cancelled': cancelled, 'errors': errors[:5]}


def scheduled_keys():
    """Các lần nhắc đang được ntfy giữ hộ -> vòng cảnh báo trên máy không gửi điện thoại trùng."""
    return set(_load()['items'])
