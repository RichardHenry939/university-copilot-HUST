# -*- coding: utf-8 -*-
"""Hạn nộp — một nguồn duy nhất: 📋 Academic Work (Claude 2026-10-04).

Ba mức ("Loại hạn", theo định nghĩa của bạn):
  • Tự luyện          — luyện kỹ năng đã có (bài tập, quiz tự làm…): nhắc 72 / 48 / 36 / 24 giờ.
  • Tự luyện cốt lõi  — không ảnh hưởng trực tiếp đến điểm, nhưng không làm thì hậu quả nhãn tiền cho môn (ôn kiến thức cơ bản,
                        vá hổng trước kiểm tra…): như trên + 7h / 5h / 3h / 1h / 30 / 20 / 10 phút.
  • Môn học           — ảnh hưởng thật đến điểm (bài lấy điểm, BKT, quiz tính điểm, ôn thi giữa / cuối kỳ…):
                        như trên + 10h / 5h / 3h / 1h / 30 / 20 / 10 / 5 / 2 / 1 phút.
Dòng chưa có "Loại hạn" -> AGENT phân loại (Gemini qua cổng :8350, caller=deadline) theo định nghĩa trên, GHI vào Notion.
Bạn sửa tay trong Notion -> giữ nguyên ý bạn (agent không phân loại lại dòng đã có giá trị).
Hoàn tất (ô tích ở tab Hôm nay, có bước Xác nhận) -> Status = Submitted -> hạn biến mất, hết nhắc.
"Tắt nhắc" chỉ dừng thông báo; hạn vẫn nằm trong danh sách tới khi Hoàn tất.
Bài tập đọc từ Teams (mail_events bt-<môn>) được thêm vào Academic Work (Môn học) nếu chưa có — không ghi đè hạn đã có;
khác ngày thì đưa vào "Cần bạn xem"."""
import uc_config as cfg
import datetime as dt, json, re, threading, time, unicodedata
from pathlib import Path

WORK = cfg.notion("academic_work")
TZ = dt.timezone(dt.timedelta(hours=7))
DONE = ('Submitted', 'Graded')
HERE = Path(__file__).resolve().parent
REVIEW = HERE / 'school' / 'deadline_review.json'
KINDS_LOG = HERE / 'school' / 'deadline_kinds.json'   # agent đã phân loại dòng nào, vì sao
MARKS_ALL = (72 * 60, 48 * 60, 36 * 60, 24 * 60)
MARKS = {'Tự luyện': MARKS_ALL,
         'Tự luyện cốt lõi': MARKS_ALL + (420, 300, 180, 60, 30, 20, 10),
         'Môn học': MARKS_ALL + (600, 300, 180, 60, 30, 20, 10, 5, 2, 1)}
KINDS = tuple(MARKS)

_c = {'rows': None, 'at': 0, 'busy': False}


def norm(s):
    s = unicodedata.normalize('NFD', (s or '').lower())
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd'))).strip()


CLASSIFY = """Bạn phân loại các HẠN (deadline) trong kế hoạch học của một sinh viên ĐHBK Hà Nội vào đúng 1 trong 3 mức:
- "Môn học": ảnh hưởng TRỰC TIẾP đến điểm môn — bài/quiz/bài tập lấy điểm, bài kiểm tra (BKT), bài nộp cho giảng viên, đồ án, thí nghiệm có chấm,
  ôn tập cho kỳ thi giữa kỳ / cuối kỳ đã có lịch.
- "Tự luyện cốt lõi": KHÔNG tính điểm trực tiếp nhưng không làm sẽ gây hậu quả nhãn tiền cho môn (ảnh hưởng gián tiếp) — ôn / vá hổng kiến thức
  cơ bản đang học, chuẩn bị nền tảng cho buổi học hoặc bài kiểm tra sắp tới.
- "Tự luyện": rèn thêm kỹ năng đã có — làm thêm bài tập, quiz tự luyện, luyện nâng cao; bỏ qua thì không hậu quả rõ ràng cho môn.
Không chắc giữa hai mức thì chọn mức GẮT hơn (Môn học > Tự luyện cốt lõi > Tự luyện).

Các hạn:
{items}

Trả JSON: [{{"id": "<id>", "loai": "Môn học" | "Tự luyện cốt lõi" | "Tự luyện", "ly_do": "<ngắn>"}}]"""


def classify(rows):
    """[{id, name, course, type, weight, tasks}] -> {id: (loại, lý do)} bằng agent Gemini. Lỗi -> {} (lượt sau thử lại)."""
    if not rows: return {}
    import mail_events
    items = '\n'.join(f"- id={r['id']} | {r['name']} | môn {r.get('course') or '?'} | Type {r.get('type') or '-'} | Weight {r.get('weight') or '-'}"
                      + (f" | việc con: {r['tasks']}" if r.get('tasks') else '') for r in rows)
    try: out = mail_events.gemini(CLASSIFY.format(items=items), caller='deadline')
    except Exception as e:
        print('deadline classify:', e); return {}
    if isinstance(out, dict): out = out.get('items') or out.get('ket_qua') or [out]
    return {x['id']: (x['loai'], x.get('ly_do', '')) for x in out if isinstance(x, dict) and x.get('loai') in KINDS and x.get('id')}


def _fetch(post):
    from academic import Notion, P
    nt = Notion(post)
    rows = nt.query(WORK, {'and': [{'property': 'Entry Kind', 'select': {'equals': 'Deadline'}},
                                   {'property': 'Due', 'date': {'is_not_empty': True}}]})
    courses = {c['id']: c for c in nt.courses()}
    out = []
    for r in rows:
        due = r['properties']['Due']['date']['start']
        if len(due) == 10: due += 'T23:59:00+07:00'
        cid = (r['properties'].get('Course', {}).get('relation') or [{}])[0].get('id')
        c = courses.get(cid) or {}
        out.append({'id': r['id'], 'name': P(r, 'Name') or '', 'due': due, 'kind': P(r, 'Loại hạn'), 'status': P(r, 'Status') or 'Not started',
                    'course': c.get('code') or '', 'courseName': c.get('name') or '', 'type': P(r, 'Type') or '',
                    'weight': P(r, 'Weight %'), 'url': r.get('url')})
    todo = [x for x in out if not x['kind'] and x['status'] not in DONE]   # agent chỉ phân loại dòng đang mở, chưa có giá trị
    if todo:
        got = classify(todo)
        try: log = json.loads(KINDS_LOG.read_text(encoding='utf-8'))
        except Exception: log = {}
        for x in todo:
            if x['id'] not in got: continue
            k, why = got[x['id']]
            try:
                nt.patch(x['id'], {'Loại hạn': {'select': {'name': k}}}); x['kind'] = k
                log[x['id']] = {'name': x['name'], 'loai': k, 'ly_do': why, 'at': dt.datetime.now(TZ).isoformat(timespec='minutes')}
            except Exception as e: print('deadline kind write:', e)
        KINDS_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding='utf-8')
    for x in out:
        x['kind'] = x['kind'] or 'Môn học'   # agent chưa kịp phân loại -> tạm coi mức gắt nhất, không bỏ sót nhắc
    out.sort(key=lambda x: x['due'])
    return out


def refresh(post):
    if _c['busy']: return
    _c['busy'] = True
    try: _c.update(rows=_fetch(post), at=time.time())
    except Exception as e: print('deadlines:', e)
    finally: _c['busy'] = False


def all_rows(post, max_age=300):
    """Bản đệm (làm mới ngầm mỗi 5 phút). Lần đầu thì chờ lấy."""
    if _c['rows'] is None: refresh(post)
    elif time.time() - _c['at'] > max_age: threading.Thread(target=refresh, args=(post,), daemon=True).start()
    if _c['rows'] is None:   # chưa đọc được lần nào (Notion / n8n lỗi): BÁO LỖI, không coi là "không có hạn"
        raise RuntimeError('chưa đọc được 📋 Academic Work (Notion/n8n lỗi)')   # -> bộ hẹn ntfy không huỷ nhầm, trang 📱 không ghi thiếu
    return _c['rows']


def open_list(post, days=21):
    now = dt.datetime.now(TZ)
    try: review = json.loads(REVIEW.read_text(encoding='utf-8'))
    except Exception: review = {}
    out = []
    for x in all_rows(post):
        if x['status'] in DONE: continue
        w = dt.datetime.fromisoformat(x['due'])
        if w > now + dt.timedelta(days=days): continue
        rv = review.get(x['id'])
        out.append({**x, 'overdue': w < now, 'minsLeft': int((w - now).total_seconds() // 60),
                    'review': f"Teams ghi hạn {rv['teams']}, Notion ghi {rv['notion'][:10]} — sửa ngày trong Notion nếu Notion sai" if rv and rv['notion'][:10] == x['due'][:10] else ''})
    return out


def complete(post, row_id):
    from academic import Notion
    Notion(post).patch(row_id, {'Status': {'status': {'name': 'Submitted'}}})
    for x in _c['rows'] or []:
        if x['id'] == row_id: x['status'] = 'Submitted'
    threading.Thread(target=refresh, args=(post,), daemon=True).start()
    return {'ok': True}


def upsert_teams(post, st):
    """Bài tập Teams (sự kiện bt-<môn>) còn hạn -> Academic Work (Môn học) nếu chưa có. Không ghi đè hạn đã có."""
    from academic import Notion, title
    nt = Notion(post)
    rows = _fetch(post)
    have = {norm(x['name']): x for x in rows}
    courses = {c['code']: c['id'] for c in nt.courses()}
    try: review = json.loads(REVIEW.read_text(encoding='utf-8'))
    except Exception: review = {}
    now, made, fixed = dt.datetime.now(TZ), [], []
    for eid, e in st['events'].items():
        if e.get('kind') != 'bt': continue
        for s in e['chang'].values():
            if not s.get('ngay') or s.get('huy'): continue
            due = dt.datetime.fromisoformat(f"{s['ngay']}T{s.get('gio') or '23:59'}:00+07:00")
            n = norm(s['ten'])
            x = have.get(n) or next((v for k, v in have.items() if n and (n in k or k in n)), None)
            if x:
                # LUẬT TỐI CAO (thiếu / tranh chấp -> theo trường; thừa -> giữ): Teams là dữ liệu trường -> hạn tranh chấp ghi theo Teams
                old_due = x['due']
                if old_due[:10] != s['ngay'] or (s.get('gio') and old_due[11:16] != s['gio']):
                    hhmm = s.get('gio') or old_due[11:16] or '23:59'   # thẻ Teams chỉ có ngày -> giữ giờ đang có
                    new_due = dt.datetime.fromisoformat(f"{s['ngay']}T{hhmm}:00+07:00").isoformat()
                    fix_due(post, x['id'], x['name'], old_due, new_due, f"Teams · {e['ten']}", eid)
                    review.pop(x['id'], None); fixed.append(x['name'])
                continue
            if due < now: continue   # THIẾU nhưng đã qua hạn: không tạo hạn mới (chỉ tranh chấp mới sửa cả hạn đã qua)
            props = {'Name': title(s['ten']), 'Entry Kind': {'select': {'name': 'Deadline'}}, 'Loại hạn': {'select': {'name': 'Môn học'}},
                     'Due': {'date': {'start': due.isoformat()}}, 'Status': {'status': {'name': 'Not started'}},
                     'Workload Status': {'select': {'name': 'Needs review'}}}
            if re.search(r'quiz', s['ten'], re.I): props['Type'] = {'select': {'name': 'Quiz'}}
            if courses.get(e.get('course')): props['Course'] = {'relation': [{'id': courses[e['course']]}]}
            nt.create(WORK, props); made.append(s['ten']); have[n] = {'name': s['ten'], 'due': due.isoformat()}
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding='utf-8')
    if made or fixed: refresh(post)
    return {'created': made, 'fixed': fixed, 'review': list(review.values())}


def fix_due(post, work_id, name, old_due, new_due, source, eid=None):
    """Sửa hạn theo dữ liệu trường: 📋 Academic Work + dòng lịch của hạn (deadline|id) + việc con có cùng hạn cũ.
    Ghi nhật ký 🏫 Đồng bộ trường và báo bạn một thông báo "Thay đổi" (🔔 + điện thoại)."""
    from academic import Notion, P
    nt = Notion(post)
    nt.patch(work_id, {'Due': {'date': {'start': new_due}}})
    n_cal = n_task = 0
    for r in nt.query(cfg.notion("calendar_events"), {'property': 'Sync Key', 'rich_text': {'equals': f'deadline|{work_id}'}}):
        nt.patch(r['id'], {'When': {'date': {'start': new_due}}}); n_cal += 1
    for t in nt.query(cfg.notion("academic_tasks"), {'property': 'Academic Work', 'relation': {'contains': work_id}}):
        td = ((t['properties'].get('Due') or {}).get('date') or {}).get('start') or ''
        if P(t, 'Status') != 'Done' and td[:16] == old_due[:16]:
            nt.patch(t['id'], {'Due': {'date': {'start': new_due}}}); n_task += 1
    o, n_ = dt.datetime.fromisoformat(old_due), dt.datetime.fromisoformat(new_due)
    line = f"{name}: hạn {o:%H:%M} {o.day}/{o.month} → {n_:%H:%M} {n_.day}/{n_.month} (theo {source}; sửa kèm {n_cal} dòng lịch, {n_task} việc con)"
    try:
        import school_sync; school_sync._log(post, 'Đã đồng bộ', [line], [])
    except Exception as ex: print('fix_due log:', ex)
    if eid:   # báo như một thư đính chính
        import mail_events as me
        st = me.load(); ev = st['events'].get(eid)
        if ev is not None:
            ev['changes'].append({'at': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'lines': [line], 'subject': 'Luật tối cao: hạn theo trường',
                                  'backfill': False, 'ack': None, 'nguon': 'Teams'})
            me.save(st)
    return line


GRACE = 10   # phút: vòng cảnh báo chạy mỗi phút; trễ hơn thế = đã lỡ mốc -> KHÔNG gửi bù (06/10, người dùng)


def mark_at(marks, left, grace=GRACE):
    """Mốc vừa tới (left nằm trong [mốc − grace, mốc]) hoặc None. Lỡ mốc (hạn mới phát hiện, giờ yên lặng) thì bỏ qua,
    chờ mốc kế tiếp — không bao giờ nhắc "còn 38 giờ" hay "còn 41 giờ" (README: chỉ đúng các mốc)."""
    return next((m for m in sorted(marks) if m - grace <= left <= m), None)


def mark_due(x, now):
    """Mốc nhắc hiện tại (phút) của một hạn, hoặc None."""
    left = (dt.datetime.fromisoformat(x['due']) - now).total_seconds() / 60
    if left <= 0: return None, left
    return mark_at(MARKS.get(x['kind'], MARKS['Môn học']), left), left


def say_left(mins):
    mins = int(mins + 0.5)
    if mins >= 2880: return f'{mins // 1440} ngày' + (f' {mins % 1440 // 60} giờ' if mins % 1440 >= 60 else '')
    if mins >= 120: return f'{mins // 60} giờ' + (f' {mins % 60:02d} phút' if mins < 600 and mins % 60 else '')
    if mins >= 60: return f'{mins // 60} giờ' + (f' {mins % 60:02d} phút' if mins % 60 else '')
    return f'{max(mins, 1)} phút'
