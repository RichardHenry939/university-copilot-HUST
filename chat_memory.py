# -*- coding: utf-8 -*-
"""Trí nhớ hội thoại BỀN cho chat UC (Claude 2026-10-05).

Trí nhớ "Window Buffer" của n8n nằm trong RAM của n8n và không lưu ổn định -> sáng 5/10 chat quên bước "xem trước"
của doi_han nên bạn trả lời "23h tối thứ Hai" thì nó hỏi lại "bài nào?". Giờ web app tự giữ:
  • 10 lượt gần nhất của mỗi phiên (school/chat_history.json, bỏ lượt cũ hơn 12 giờ)
  • việc ĐANG CHỜ BẠN XÁC NHẬN (vd đề xuất dời hạn đã xem trước) — school/pending_actions.json
và gửi kèm mỗi tin nhắn mới. Không gọi AI nào."""
import datetime as dt, json, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
HIST = HERE / 'school' / 'chat_history.json'
PEND = HERE / 'school' / 'pending_actions.json'
TZ = dt.timezone(dt.timedelta(hours=7))
KEEP, MAX_AGE_H = 10, 12
_lk = threading.Lock()


def _load(p):
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return {}


def _save(p, d): p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')


def _fresh(items, hours):
    lim = (dt.datetime.now(TZ) - dt.timedelta(hours=hours)).isoformat()
    return [x for x in items if x.get('at', '') >= lim]


def wrap(session, text):
    """Tin nhắn gửi cho não = bối cảnh gần đây + việc đang chờ + tin nhắn mới."""
    with _lk:
        h = _fresh(_load(HIST).get(session, []), MAX_AGE_H)
        pend = [p for p in _fresh(_load(PEND).get('items', []), 24) if not p.get('done')]
    parts = []
    if pend:
        parts.append('VIỆC ĐANG CHỜ SINH VIÊN XÁC NHẬN (nếu tin nhắn mới là đồng ý / chỉnh giờ cho việc này thì gọi đúng công cụ ở bước ghi, không hỏi lại từ đầu):')
        for p in pend[-3:]:
            parts.append(f"- [{p['at'][11:16]}] {p['tool']}: {p['summary']} — gọi lại: {json.dumps(p['args'], ensure_ascii=False)} (đổi han_moi nếu sinh viên nêu giờ khác)")
    if h:
        parts.append('HỘI THOẠI GẦN ĐÂY (để hiểu câu trả lời ngắn):')
        for x in h[-KEEP:]:
            parts.append(('Bạn: ' if x['role'] == 'user' else 'UC: ') + x['text'][:700])
    if not parts: return text
    return '\n'.join(parts) + '\n---\nTIN NHẮN MỚI: ' + text


def remember(session, user_text, reply):
    with _lk:
        d = _load(HIST)
        now = dt.datetime.now(TZ).isoformat(timespec='seconds')
        h = _fresh(d.get(session, []), MAX_AGE_H) + [{'role': 'user', 'text': user_text[:2000], 'at': now},
                                                     {'role': 'uc', 'text': (reply or '')[:2000], 'at': now}]
        d[session] = h[-2 * KEEP:]
        _save(HIST, d)


def pending_add(tool, args, summary):
    with _lk:
        d = _load(PEND); items = _fresh(d.get('items', []), 24)
        items = [p for p in items if not (p['tool'] == tool and p['args'].get('work_ids') == args.get('work_ids'))]
        items.append({'tool': tool, 'args': args, 'summary': summary[:600], 'at': dt.datetime.now(TZ).isoformat(timespec='seconds')})
        d['items'] = items; _save(PEND, d)


def pending_done(tool, work_ids):
    with _lk:
        d = _load(PEND)
        for p in d.get('items', []):
            if p['tool'] == tool and set(str(p['args'].get('work_ids', '')).split(',')) & set(str(work_ids).split(',')): p['done'] = True
        _save(PEND, d)
