# -*- coding: utf-8 -*-
"""Bộ quét trùng (Claude 2026-10-04): hạn học tập + lịch học.

Bắt:
  • 📋 Academic Work: 2 hạn còn mở, cùng giờ hết hạn (lệch ≤ 2 giờ) và tên giống nhau (hoặc cùng môn + gần như cùng tên)
    — vd nhập qua UC 2 lần, lần đầu ghi sai.
  • 🗓️ Lịch: 2 dòng cùng ngày, tên giống nhau (bỏ biểu tượng, mã môn, "Bài tập …"), vd dòng hạn do agent nhập hạn tạo và dòng do bộ đọc mail tạo;
    1 dòng sự kiện trùng buổi học (Class) cùng môn cùng ngày.
Không tự xoá gì: chỉ báo cặp nghi trùng (school/dups.json). Bạn chọn ở tab Hôm nay: "Giữ cả hai" hoặc "Bỏ bản …" (có bước Xác nhận
-> thùng rác Notion, khôi phục được 30 ngày; bỏ một hạn thì bỏ kèm dòng lịch + việc con chưa xong của nó)."""
import uc_config as cfg
import datetime as dt, json, re, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'dups.json'
WORK = cfg.notion("academic_work")
EVENTS = cfg.notion("calendar_events")
TASKS = cfg.notion("academic_tasks")
DAILY = cfg.notion("daily_plan")
TZ = dt.timezone(dt.timedelta(hours=7))
STOP = {'bai', 'tap', 'cac', 'va', 'cho', 'cua', 'the', 'hoc', 'ky', 'mon', 'nhap', 'trong', 'mot', 'nhung', 'deadline', 'han'}


def norm(s):
    s = unicodedata.normalize('NFD', (s or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def toks(s):
    s = re.sub(r'\b[a-z]{2,4}\d{4}\b', ' ', norm(s))   # bỏ mã môn
    return {w for w in s.split() if w not in STOP and len(w) > 1}


def sim(a, b):
    A, B = toks(a), toks(b)
    if not A or not B: return 0.0
    return len(A & B) / min(len(A), len(B))   # trùng phần lớn của tên ngắn hơn


def vn(t):
    return dt.datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(TZ).strftime('%H:%M %d/%m')


def _when(r, prop):
    d = (r['properties'].get(prop) or {}).get('date') or {}
    s = d.get('start')
    if not s: return None
    if len(s) == 10: s += 'T23:59:00+07:00'
    return dt.datetime.fromisoformat(s)


def scan(post):
    from academic import Notion, P
    nt = Notion(post)
    try: old = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: old = {}
    kept = set(old.get('kept', []))
    courses = {c['id']: c['code'] for c in nt.courses()}
    pairs = []
    # 1) hạn học tập
    work = [r for r in nt.query(WORK, {'property': 'Entry Kind', 'select': {'equals': 'Deadline'}})
            if (P(r, 'Status') or '') not in ('Submitted', 'Graded') and _when(r, 'Due')]
    for i, a in enumerate(work):
        for b in work[i + 1:]:
            wa, wb = _when(a, 'Due'), _when(b, 'Due')
            if abs((wa - wb).total_seconds()) > 2 * 3600: continue
            s = sim(P(a, 'Name'), P(b, 'Name'))
            ca = [courses.get(x['id']) for x in a['properties']['Course']['relation']]
            cb = [courses.get(x['id']) for x in b['properties']['Course']['relation']]
            if set(filter(None, ca)) and set(filter(None, cb)) and not (set(filter(None, ca)) & set(filter(None, cb))):
                continue   # gắn 2 môn khác nhau -> 2 hạn thật (vd "Vá hổng Chương I" của Giải tích I và của Đại số), không phải trùng
            if s >= 0.6 or (s >= 0.4 and ca == cb):
                pairs.append({'kind': 'han', 'score': round(s, 2), 'why': f"cùng hạn {wa:%H:%M %d/%m}" + (f", tên giống {int(s * 100)}%"),
                              'a': {'id': a['id'], 'name': P(a, 'Name'), 'course': ', '.join(filter(None, ca)), 'created': vn(a['created_time']),
                                    'tasks': len(a['properties']['Tasks']['relation']), 'url': a.get('url')},
                              'b': {'id': b['id'], 'name': P(b, 'Name'), 'course': ', '.join(filter(None, cb)), 'created': vn(b['created_time']),
                                    'tasks': len(b['properties']['Tasks']['relation']), 'url': b.get('url')}})
    # 2) lịch: từ hôm qua tới 60 ngày tới
    today = dt.datetime.now(TZ).date()
    ev = nt.query(EVENTS, {'and': [{'property': 'When', 'date': {'on_or_after': (today - dt.timedelta(days=1)).isoformat()}},
                                   {'property': 'When', 'date': {'on_or_before': (today + dt.timedelta(days=60)).isoformat()}}]})
    by_day = {}
    for r in ev: by_day.setdefault(((r['properties']['When']['date'] or {}).get('start') or '')[:10], []).append(r)
    for day, rs in by_day.items():
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                ka, kb = P(a, 'Kind'), P(b, 'Kind')
                if ka == kb == 'Class': continue   # 2 buổi học cùng ngày là bình thường
                if (P(a, 'Sync Key') or '').startswith('deadline|') and (P(b, 'Sync Key') or '').startswith('deadline|'): continue   # dòng lịch của 2 hạn: đã báo ở cặp hạn
                ta, tb = P(a, 'Event') or '', P(b, 'Event') or ''
                s = sim(ta, tb)
                ca = {courses.get(x['id']) for x in a['properties']['Course']['relation']} | set(re.findall(r'[A-Z]{2,4}\d{4}', ta))
                cb = {courses.get(x['id']) for x in b['properties']['Course']['relation']} | set(re.findall(r'[A-Z]{2,4}\d{4}', tb))
                same_course = bool((ca & cb) - {None})
                class_dup = 'Class' in (ka, kb) and same_course and abs((_when(a, 'When') - _when(b, 'When')).total_seconds()) <= 3 * 3600 and s >= 0.3
                diff_course = bool(ca - {None}) and bool(cb - {None}) and not same_course   # 2 môn khác nhau -> không trùng
                if (s >= 0.7 and not diff_course) or class_dup:
                    pairs.append({'kind': 'lich', 'score': round(s, 2), 'why': f"cùng ngày {day[8:10]}/{day[5:7]}" + (', trùng buổi học' if class_dup else f", tên giống {int(s * 100)}%"),
                                  'a': {'id': a['id'], 'name': ta, 'kindrow': ka, 'key': P(a, 'Sync Key') or '', 'created': vn(a['created_time']), 'url': a.get('url')},
                                  'b': {'id': b['id'], 'name': tb, 'kindrow': kb, 'key': P(b, 'Sync Key') or '', 'created': vn(b['created_time']), 'url': b.get('url')}})
    for p in pairs: p['pid'] = '|'.join(sorted([p['a']['id'], p['b']['id']]))
    pairs = [p for p in pairs if p['pid'] not in kept]
    data = {'at': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'pairs': pairs, 'kept': sorted(kept)}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return data


def load():
    try: return json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return {'pairs': [], 'kept': []}


def keep_both(pid):
    d = load(); d['kept'] = sorted(set(d.get('kept', [])) | {pid}); d['pairs'] = [p for p in d['pairs'] if p['pid'] != pid]
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True}


def plan_drop(post, pid, drop_id):
    """Những gì sẽ vào thùng rác nếu bỏ drop_id (để hiện ở bước Xác nhận)."""
    from academic import Notion, P
    p = next((x for x in load()['pairs'] if x['pid'] == pid), None)
    if not p or drop_id not in (p['a']['id'], p['b']['id']): return None
    row = p['a'] if p['a']['id'] == drop_id else p['b']
    ids, what = [drop_id], [f"{'hạn' if p['kind'] == 'han' else 'dòng lịch'} “{row['name']}”"]
    if p['kind'] == 'han':
        nt = Notion(post)
        cal = [r for r in nt.query(EVENTS, {'property': 'Sync Key', 'rich_text': {'equals': f'deadline|{drop_id}'}})]
        ids += [r['id'] for r in cal]
        tasks = [t for t in nt.query(TASKS, {'property': 'Academic Work', 'relation': {'contains': drop_id}}) if P(t, 'Status') != 'Done']
        ids += [t['id'] for t in tasks]
        daily = []
        for t in tasks: daily += nt.query(DAILY, {'property': 'Source Task', 'relation': {'contains': t['id']}})
        ids += [d['id'] for d in daily]
        what += [f"{len(cal)} dòng lịch của hạn này", f"{len(tasks)} việc con chưa xong", f"{len(daily)} việc trong kế hoạch ngày"]
    return {'ids': ids, 'what': what, 'row': row, 'pair': p}


def drop(post, pid, drop_id):
    import subprocess, sys
    pl = plan_drop(post, pid, drop_id)
    if not pl: return {'ok': False, 'loi': 'Cặp trùng không còn (đã quét lại?)'}
    r = subprocess.run([sys.executable, str(HERE / 'notion_archive.py'), *pl['ids']], cwd=str(HERE), capture_output=True, timeout=300,
                       creationflags=0x08000000, env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'})
    if r.returncode: return {'ok': False, 'loi': (r.stderr or b'').decode('utf-8', 'ignore')[-300:]}
    d = load(); d['pairs'] = [p for p in d['pairs'] if p['pid'] != pid]
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    try:
        import deadlines; deadlines.refresh(post)
    except Exception: pass
    return {'ok': True, 'trashed': len(pl['ids'])}
