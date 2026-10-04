# -*- coding: utf-8 -*-
"""Điện thoại ⇄ UC qua ntfy, hai chiều (Claude 2026-10-04). Chỉ chạy khi máy (UC) đang mở.

Chiều UC -> điện thoại: kênh thông báo (school/ntfy.json "topic"), kèm NÚT trên thông báo.
Chiều điện thoại -> UC: kênh lệnh riêng ("cmd_topic"); UC giữ 1 kết nối nghe liên tục (ntfy stream).
  • Nút GHI (Sẽ đi / Bỏ / Đã biết — KHÔNG có Hoàn tất / Tắt nhắc trên điện thoại, theo yêu cầu của bạn) = lệnh có CHỮ KÝ HMAC (khoá .copilot-secret), hết hạn 48 giờ, mỗi lệnh dùng 1 lần.
    Bấm nút -> UC hỏi lại "Xác nhận …?" kèm nút Xác nhận (cũng có chữ ký) -> lúc đó mới ghi. Không bao giờ ghi ngầm.
  • Lệnh XEM gõ tay hoặc bấm nút menu: "hôm nay" · "mai" · "hạn" · "menu" — chỉ đọc, không cần chữ ký.
  • Tin không có chữ ký hợp lệ thì chỉ được xem, không bao giờ làm thay đổi gì."""
import base64, datetime as dt, hashlib, hmac, json, secrets, threading, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / 'school' / 'ntfy.json'
STATE = HERE / 'school' / 'ntfy_cmd_state.json'
TZ = dt.timezone(dt.timedelta(hours=7))
SECRET = (HERE / '.copilot-secret').read_text().strip().encode()
TTL = 48 * 3600


def cfg():
    c = json.loads(CFG.read_text(encoding='utf-8'))
    if not c.get('cmd_topic'):
        c['cmd_topic'] = 'uc-cmd-' + secrets.token_urlsafe(18).replace('_', 'x').replace('-', 'y').lower()
        CFG.write_text(json.dumps(c, ensure_ascii=False), encoding='utf-8')
    return c


def _load():
    try: return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception: return {'last_id': None, 'used': {}}


def _save(s):
    now = time.time(); s['used'] = {k: v for k, v in s['used'].items() if v > now - TTL - 3600}   # nhớ lệnh đã dùng tới khi hết hạn
    STATE.write_text(json.dumps(s, ensure_ascii=False), encoding='utf-8')


# ------------------------------------------------------------------ lệnh có chữ ký
def make(op, step='ask', **arg):
    body = json.dumps({'op': op, 'step': step, 'arg': arg, 'exp': int(time.time()) + TTL, 'n': secrets.token_hex(4)},
                      ensure_ascii=False, separators=(',', ':')).encode()
    b = base64.urlsafe_b64encode(body).decode().rstrip('=')
    return f"uc1.{b}.{hmac.new(SECRET, b.encode(), hashlib.sha256).hexdigest()[:24]}"


def verify(text):
    try:
        tag, b, sig = text.strip().split('.')
        if tag != 'uc1' or not hmac.compare_digest(sig, hmac.new(SECRET, b.encode(), hashlib.sha256).hexdigest()[:24]): return None
        d = json.loads(base64.urlsafe_b64decode(b + '=' * (-len(b) % 4)))
        return d if d.get('exp', 0) > time.time() else None
    except Exception:
        return None


def btn(label, body, clear=True):
    return {'action': 'http', 'label': label, 'url': f"https://ntfy.sh/{cfg()['cmd_topic']}", 'method': 'POST', 'body': body, 'clear': clear}


def menu_buttons():
    return [btn('Hôm nay', 'hôm nay', False), btn('Ngày mai', 'mai', False), btn('Hạn', 'hạn', False)]


def actions_for(a):
    """Nút cho một cảnh báo (alerts.active) -> tối đa 3 nút ntfy."""
    if not a: return []
    k = a.get('kind')
    if k == 'deadline':   # theo yêu cầu của bạn (4/10): KHÔNG có Hoàn tất / Tắt nhắc trên điện thoại — làm ở UC trên máy
        return []
    if k == 'change':
        return [btn('Đã biết', make('ack', eid=a['eid'], change_at=a['change_at'], choice='Đã biết', name=a['title']))]
    if k == 'stage':
        return [btn(c, make('ack', eid=a['eid'], stage=a['stage'], choice=c, name=a['title'])) for c in a.get('buttons', [])][:3]
    return []


def push(title, text, actions=None, priority=3, tags=None):
    c = cfg()
    body = {'topic': c['topic'], 'title': title, 'message': text, 'priority': priority, 'tags': tags or ['iphone']}
    if actions: body['actions'] = actions[:3]
    urllib.request.urlopen(urllib.request.Request(c.get('server', 'https://ntfy.sh'), data=json.dumps(body).encode('utf-8'),
                                                  headers={'Content-Type': 'application/json'}), timeout=20).read()


# ------------------------------------------------------------------ trả lời lệnh xem
def _classes(post, day):
    import timetable
    out = []
    for e in timetable.get(post)['events']:
        if e['kind'] != 'Class' or e['start'][:10] != day.isoformat(): continue
        s = dt.datetime.fromisoformat(e['start']).astimezone(TZ); en = dt.datetime.fromisoformat(e['end']).astimezone(TZ) if e.get('end') else None
        out.append(f"{s:%H:%M}{'–' + format(en, '%H:%M') if en else ''} {' · '.join(e['title'].split(' · ')[:2])} — {e.get('location') or '?'}")
    return out


def _deadlines(post, days=7):
    import deadlines as D
    out = []
    for x in D.open_list(post, days=days):
        w = dt.datetime.fromisoformat(x['due']).astimezone(TZ)
        left = 'QUÁ HẠN' if x['overdue'] else 'còn ' + D.say_left(x['minsLeft'])
        out.append(f"{x['name']}{' · ' + x['course'] if x['course'] else ''} [{x['kind']}] — {w:%H:%M %d/%m}, {left}")
    return out


def reply_view(post, text):
    t = text.strip().lower()
    now = dt.datetime.now(TZ)
    if t in ('hôm nay', 'hom nay', 'today', 'hn'):
        cl = _classes(post, now.date()); dl = _deadlines(post, 3)
        return (f"Hôm nay {now:%d/%m}", ('Lịch học:\n' + '\n'.join(cl) if cl else 'Hôm nay không có tiết học.') +
                ('\n\nHạn 3 ngày tới:\n' + '\n'.join(dl) if dl else '\n\nKhông có hạn nào trong 3 ngày tới.'))
    if t in ('mai', 'ngày mai', 'ngay mai', 'lịch mai', 'lich mai', 'tomorrow'):
        d = now.date() + dt.timedelta(days=1); cl = _classes(post, d)
        return (f"Ngày mai {d:%d/%m}", '\n'.join(cl) if cl else 'Ngày mai không có tiết học.')
    if t in ('hạn', 'han', 'deadline', 'deadlines'):
        dl = _deadlines(post, 21)
        return ('Hạn 3 tuần tới', '\n'.join(dl) if dl else 'Không có hạn nào đang mở.')
    return ('UC · lệnh', 'Gõ hoặc bấm: "hôm nay" · "mai" · "hạn". Nút Sẽ đi / Bỏ / Đã biết trên cảnh báo sự kiện luôn hỏi Xác nhận trước khi ghi. Hoàn tất / Tắt nhắc hạn: làm trên UC ở máy.')


# ------------------------------------------------------------------ thực hiện lệnh có chữ ký
def run_signed(post, d):
    import alerts
    op, a, name = d['op'], d['arg'], d['arg'].get('name', '')
    if op != 'ack': return ('UC · từ chối', 'Hoàn tất / Tắt nhắc hạn chỉ làm trên UC ở máy.', None)   # yêu cầu của bạn 4/10
    label = a.get('choice', '')
    if d['step'] == 'ask':   # bước 1: hỏi lại
        return (f"Xác nhận “{label}”?", f"{name}\nGhi lựa chọn này (Notion nếu cần) và cập nhật cảnh báo.",
                [btn('Xác nhận', make(op, 'do', **a)), btn('Huỷ', 'huỷ')])
    if op == 'ack': alerts.ack(a['eid'], a['choice'], stage=a.get('stage'), change_at=a.get('change_at'), post=post)
    else: return ('UC · lệnh lạ', op, None)
    return (f"Đã {label.lower()}", name, None)


def handle(post, text):
    text = (text or '').strip()
    if not text or text.lower() in ('huỷ', 'hủy', 'huy'): return None
    if text.startswith('uc1.'):
        d = verify(text)
        if not d: return ('UC · từ chối', 'Lệnh hết hạn hoặc chữ ký sai — không làm gì.', None)
        s = _load(); key = text.rsplit('.', 1)[1]
        if key in s['used']: return None   # lệnh đã dùng (bấm 2 lần / gửi lại)
        s['used'][key] = time.time(); _save(s)
        try: return run_signed(post, d)
        except Exception as e: return ('UC · lỗi', f'{type(e).__name__}: {e}'[:300], None)
    title, body = reply_view(post, text)
    return (title, body, menu_buttons())


def listen(post):
    """Nghe kênh lệnh liên tục (ntfy stream), tự nối lại. Chỉ xử lý tin mới (không chạy lại tin cũ khi khởi động)."""
    s = _load()
    since = s.get('last_id') or str(int(time.time()))
    while True:
        try:
            url = f"https://ntfy.sh/{cfg()['cmd_topic']}/json?since={since}"
            with urllib.request.urlopen(url, timeout=120) as r:
                for line in r:
                    m = json.loads(line.decode('utf-8'))
                    if m.get('event') != 'message': continue
                    since = m['id']; s = _load(); s['last_id'] = since; _save(s)
                    if time.time() - m.get('time', 0) > 900: continue   # tin cũ hơn 15 phút: bỏ
                    out = handle(post, m.get('message', ''))
                    if out:
                        try: push(out[0], out[1], out[2], priority=3)
                        except Exception as e: print('phone push:', e)
        except Exception as e:
            print('phone listen:', e); time.sleep(10)
