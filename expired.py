# -*- coding: utf-8 -*-
"""Việc của trường ĐÃ HẾT HẠN → ✅ Academic Tasks (Claude 2026-10-04, theo yêu cầu của bạn).

Bài đã hết hạn KHÔNG ghi thành hạn (📋 Academic Work — nơi đó chỉ cho hạn còn tới). Nếu ghi thì ghi vào Academic Tasks để UC
biết từng có việc đó: Status = Done (nhóm Complete → A4 không xếp lại, không nhắc quá hạn), "Kết quả hạn" = Đã làm / Bỏ lỡ / Không rõ,
"Nguồn hạn" = MOOC 8/10 · thẻ bài tập Teams …, Estimate = 0 (không làm lệch giờ trong đánh giá tuần).
Nguồn: MOOC (có điểm → biết làm hay chưa) + bài tập Teams (bt-MÃ; Teams không cho biết đã nộp → Không rõ, trừ khi MOOC có điểm).
Cùng môn + hạn lệch ≤ 2 giờ = một việc (Teams "Buổi học 4" = MOOC "Tuần 4") — MOOC thắng vì có điểm.
Khoá chống trùng: Breakdown Key "het-han|MÃ|YYYY-MM-DDTHH"."""
import uc_config as cfg
import datetime as dt, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = cfg.notion("academic_tasks")
TZ = dt.timezone(dt.timedelta(hours=7))


def _key(code, due):
    return f"het-han|{code}|{due.astimezone(TZ):%Y-%m-%dT%H}"


def collect(now=None):
    """-> {key: {name, code, due, ket_qua, nguon}} các việc của trường đã hết hạn."""
    import mail_events as me
    now = now or dt.datetime.now(TZ); out = {}
    # Teams (thẻ bài tập / thông báo bài tập)
    for eid, e in me.load()['events'].items():
        if e.get('kind') != 'bt': continue
        for s in e['chang'].values():
            w = me.when_of(s)
            if not w or w >= now or s.get('huy'): continue
            out[_key(e['course'], w)] = {'name': s['ten'], 'code': e['course'], 'due': w, 'ket_qua': 'Không rõ', 'nguon': 'Teams (thẻ / thông báo bài tập)'}
    # MOOC (có điểm) — thắng Teams khi trùng
    try: mo = json.loads((HERE / 'school' / 'mooc.json').read_text(encoding='utf-8'))
    except Exception: mo = {}
    for cid, c in mo.get('courses', {}).items():
        mc = re.search(r'\+([A-Z]{2,4}\d{4})\+', cid)
        if not mc: continue
        cstart = dt.datetime.fromisoformat(c['start'].replace('Z', '+00:00')) if c.get('start') else None
        for it in c['items']:
            if not it.get('due'): continue
            due = dt.datetime.fromisoformat(it['due'].replace('Z', '+00:00')).astimezone(TZ)
            if due >= now or (cstart and due < cstart): continue
            k = _key(mc.group(1), due)
            k2 = next((x for x in out if x.startswith(f"het-han|{mc.group(1)}|") and abs((out[x]['due'] - due).total_seconds()) <= 7200), k)
            done = (it.get('earned') or 0) > 0
            out.pop(k2, None)
            out[k] = {'name': it['name'], 'code': mc.group(1), 'due': due, 'ket_qua': 'Đã làm' if done else 'Bỏ lỡ',
                      'nguon': f"MOOC {it.get('earned', 0):g}/{it.get('possible', 0):g}"}
    # FAMI số hoá (thi theo chương các học phần MI): có điểm = Đã làm, không = Bỏ lỡ
    try:
        import fami
        for it in fami.items(now):
            if it['due'] >= now: continue
            sc = it.get('score') or {}
            pts = sc.get('diem') if isinstance(sc, dict) else None
            out[_key(it['code'], it['due'])] = {'name': it['name'], 'code': it['code'], 'due': it['due'],
                                                'ket_qua': 'Đã làm' if it['done'] else 'Bỏ lỡ',
                                                'nguon': 'FAMI số hoá' + (f' · {pts}/{it["max"]}' if pts is not None else '')}
    except Exception as e:
        print('expired fami:', e)
    return out


def record(post):
    from academic import Notion, P, title, rt
    nt = Notion(post)
    want = collect()
    have = {}
    for r in nt.query(TASKS, {'property': 'Breakdown Key', 'rich_text': {'starts_with': 'het-han|'}}):
        have[P(r, 'Breakdown Key')] = r
    courses = {c['code']: c['id'] for c in nt.courses()}
    made, upd = [], []
    for k, x in want.items():
        props = {'Task': title(x['name']), 'Status': {'status': {'name': 'Done'}}, 'Task Kind': {'select': {'name': 'Academic'}},
                 'Due': {'date': {'start': x['due'].isoformat()}}, 'Estimate (hrs)': {'number': 0}, 'Breakdown Key': rt(k),
                 'Kết quả hạn': {'select': {'name': x['ket_qua']}}, 'Nguồn hạn': rt(x['nguon'])}
        if courses.get(x['code']): props['Course'] = {'relation': [{'id': courses[x['code']]}]}
        r = have.get(k)
        if not r: nt.create(TASKS, props); made.append(f"{x['code']} {x['name']} · {x['ket_qua']}")
        elif P(r, 'Kết quả hạn') != x['ket_qua'] or P(r, 'Nguồn hạn') != x['nguon']:
            nt.patch(r['id'], {'Kết quả hạn': props['Kết quả hạn'], 'Nguồn hạn': props['Nguồn hạn'], 'Task': props['Task']}); upd.append(x['name'])
    return {'ok': True, 'created': made, 'updated': upd, 'total': len(want)}
