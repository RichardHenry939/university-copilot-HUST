# -*- coding: utf-8 -*-
"""(v1.00.42 W8) Ví thời gian: phiên tập trung 25 + 5, cộng / trừ phút, thống kê.

Quy tắc (chủ chốt 26/10 và 31/10):
- Chủ chọn tổng thời gian; UC chia khối 25 phút tập trung + 5 phút nghỉ. Mỗi khối 25 phút TRỌN -> +5 phút ví.
- Kết thúc sớm được, nhưng chỉ tính khối đã trọn (câu "có cho kết thúc sớm không" chủ chưa chốt; đây là cách an toàn).
- Hoàn tất một hạn -> +15 phút, một lần cho mỗi hạn. Bỏ hoàn tất -> thu hồi đúng phần đã cộng.
- "Giải trí" trừ phút theo thời gian thật (làm tròn lên phút), không vượt số dư; hết số dư thì tự dừng.
Dữ liệu: school/wallet.json (sổ cái + phiên). Chỉ chạy trên máy này.
Tín hiệu tập trung cho phía chặn trang: CHỈ ghi khi chủ đã đặt school/secret/focus_signal.json {"path": "..."}.
UC không biết và không đụng phía chặn; không có cấu hình thì không ghi gì.
"""
import datetime as dt, json, math, threading, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILE = HERE / 'school' / 'wallet.json'
SIGNAL_CFG = HERE / 'school' / 'secret' / 'focus_signal.json'
TZ = dt.timezone(dt.timedelta(hours=7))
FOCUS, BREAK, BLOCK_REWARD, DEADLINE_REWARD = 25, 5, 5, 15
lock = threading.Lock()


def empty():
    return {'ledger': [], 'sessions': [], 'active': None}


def load(path=None):
    try: st = json.loads(Path(path or FILE).read_text(encoding='utf-8'))
    except Exception: return empty()
    for k, v in empty().items(): st.setdefault(k, v)
    return st


def save(st, path=None):
    p = Path(path or FILE); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp'); tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8'); tmp.replace(p)


def _iso(t): return t.astimezone(TZ).isoformat(timespec='seconds')
def _t(s): return dt.datetime.fromisoformat(s)


def balance(st):
    return sum(x['min'] for x in st['ledger'])


def _add(st, kind, minutes, now, ref='', note='', **extra):
    e = {'id': uuid.uuid4().hex[:10], 'at': _iso(now), 'kind': kind, 'min': int(minutes), 'ref': ref, 'note': note, **extra}
    st['ledger'].append(e)
    return e


def plan(total_min):
    """Chia tổng thời gian thành các pha: tập trung tối đa 25, nghỉ tối đa 5, xen kẽ."""
    out, rem = [], int(total_min)
    while rem > 0:
        f = min(FOCUS, rem); out.append(('focus', f)); rem -= f
        if rem <= 0: break
        b = min(BREAK, rem); out.append(('break', b)); rem -= b
    return out


def _elapsed_s(a, now):
    s = (now - _t(a['start'])).total_seconds() - a.get('paused_s', 0)
    if a.get('paused_at'): s -= (now - _t(a['paused_at'])).total_seconds()
    return max(0, s)


def progress(st, now):
    a = st['active']
    if not a or a['type'] != 'focus': return None
    el, acc, focus_s, blocks = _elapsed_s(a, now), 0, 0, 0
    phases = plan(a['total'])
    cur = None
    for i, (kind, mins) in enumerate(phases):
        length = mins * 60
        used = max(0, min(length, el - acc))
        if kind == 'focus':
            focus_s += used
            if mins == FOCUS and used >= length: blocks += 1
        if cur is None and el < acc + length: cur = {'phase': kind, 'index': i, 'left_s': int(acc + length - el), 'phase_min': mins}
        acc += length
    nfocus = sum(1 for k, _ in phases if k == 'focus')
    return {'blocks_done': blocks, 'blocks_total': sum(1 for k, mm in phases if k == 'focus' and mm == FOCUS), 'focus_count': nfocus,
            'focus_s': int(focus_s), 'elapsed_s': int(el), 'done': el >= acc, 'paused': bool(a.get('paused_at')),
            **(cur or {'phase': 'done', 'index': len(phases), 'left_s': 0, 'phase_min': 0})}


def _signal(focus, until=None, now=None):
    """Ghi tín hiệu cho phía chặn trang, chỉ khi chủ đã cấu hình đường dẫn. Lỗi ở đây không làm hỏng phiên."""
    try:
        target = json.loads(Path(SIGNAL_CFG).read_text(encoding='utf-8')).get('path')
        if not target: return
        Path(target).write_text(json.dumps({'focus': focus, 'until': until, 'at': _iso(now or dt.datetime.now(TZ))}), encoding='utf-8')
    except Exception: pass


def start_focus(st, total_min, subject, now):
    if st['active']: raise ValueError('Đang có một phiên chạy.')
    total = int(total_min)
    if not 5 <= total <= 480: raise ValueError('Tổng thời gian từ 5 đến 480 phút.')
    st['active'] = {'type': 'focus', 'id': uuid.uuid4().hex[:10], 'start': _iso(now), 'total': total, 'subject': str(subject or '')[:120],
                    'paused_at': None, 'paused_s': 0}
    _signal(True, _iso(now + dt.timedelta(minutes=total)), now)
    return st['active']


def pause(st, now):
    a = st['active']
    if a and a['type'] == 'focus' and not a.get('paused_at'): a['paused_at'] = _iso(now)


def resume(st, now):
    a = st['active']
    if a and a.get('paused_at'):
        a['paused_s'] = a.get('paused_s', 0) + (now - _t(a['paused_at'])).total_seconds(); a['paused_at'] = None


def end_focus(st, now):
    a = st['active']
    if not a or a['type'] != 'focus': raise ValueError('Không có phiên tập trung nào.')
    p = progress(st, now)
    blocks, reward = p['blocks_done'], p['blocks_done'] * BLOCK_REWARD
    st['sessions'].append({'id': a['id'], 'start': a['start'], 'end': _iso(now), 'total': a['total'], 'subject': a['subject'],
                           'focus_min': p['focus_s'] // 60, 'blocks': blocks})
    if reward: _add(st, 'focus', reward, now, ref=a['id'], note=f'{blocks} khối 25 phút' + (f' · {a["subject"]}' if a['subject'] else ''))
    st['active'] = None
    _signal(False, None, now)
    return {'blocks': blocks, 'reward': reward}


def start_fun(st, now):
    if st['active']: raise ValueError('Đang có một phiên chạy.')
    cap = balance(st)
    if cap <= 0: raise ValueError('Ví đang hết phút. Tập trung đủ khối hoặc hoàn tất hạn để có thêm.')
    st['active'] = {'type': 'fun', 'id': uuid.uuid4().hex[:10], 'start': _iso(now), 'cap': cap}
    return st['active']


def end_fun(st, now):
    a = st['active']
    if not a or a['type'] != 'fun': raise ValueError('Không có phiên giải trí nào.')
    spent = min(a['cap'], math.ceil((now - _t(a['start'])).total_seconds() / 60))
    if spent: _add(st, 'fun', -spent, now, ref=a['id'], note='giải trí')
    st['active'] = None
    return {'spent': spent}


def _credited(st, dl_id):
    return [x for x in st['ledger'] if x['kind'] == 'deadline' and x['ref'] == dl_id and not x.get('revoked')]


def credit_deadline(st, dl_id, name, now):
    if not dl_id or _credited(st, dl_id): return None
    return _add(st, 'deadline', DEADLINE_REWARD, now, ref=dl_id, note=str(name or '')[:120])


def revoke_deadline(st, dl_id, now):
    out = []
    for x in _credited(st, dl_id):
        x['revoked'] = True
        out.append(_add(st, 'revoke', -x['min'], now, ref=dl_id, note='bỏ hoàn tất: ' + x.get('note', '')))
    return out


def stats(st, now):
    now = now.astimezone(TZ); day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    starts = {'ngay': day0, 'tuan': day0 - dt.timedelta(days=day0.weekday()), 'thang': day0.replace(day=1)}
    out = {}
    for k, s in starts.items():
        ses = [x for x in st['sessions'] if _t(x['start']) >= s]
        led = [x for x in st['ledger'] if _t(x['at']) >= s]
        out[k] = {'focus_min': sum(x['focus_min'] for x in ses), 'blocks': sum(x['blocks'] for x in ses), 'sessions': len(ses),
                  'earned': sum(x['min'] for x in led if x['min'] > 0 and x['kind'] != 'revoke'),
                  'spent': -sum(x['min'] for x in led if x['kind'] == 'fun')}
    return out


def view(st, now):
    """Trạng thái cho giao diện. Phiên đã hết giờ (hoặc giải trí hết số dư) thì tự kết thúc ở đây."""
    a = st['active']
    if a and a['type'] == 'focus' and progress(st, now)['done']: end_focus(st, now)
    elif a and a['type'] == 'fun' and (now - _t(a['start'])).total_seconds() >= a['cap'] * 60: end_fun(st, now)
    a = st['active']
    act = None
    if a and a['type'] == 'focus': act = {**a, **progress(st, now)}
    elif a: act = {**a, 'left_s': max(0, int(a['cap'] * 60 - (now - _t(a['start'])).total_seconds()))}
    return {'balance': balance(st), 'active': act, 'stats': stats(st, now), 'recent': st['ledger'][-12:][::-1],
            'rules': {'focus': FOCUS, 'break': BREAK, 'block_reward': BLOCK_REWARD, 'deadline_reward': DEADLINE_REWARD}}
