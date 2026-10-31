# -*- coding: utf-8 -*-
"""MOOC SoICT (soict.daotao.ai, Open edX) → UC (Claude 2026-10-04). CHỈ ĐỌC.

Đăng nhập: nút "Đăng nhập bằng HUST" → phiên Microsoft sẵn có của hồ sơ Chrome đồng bộ (bộ tự đăng nhập school_fetch).
Đọc: /api/enrollment/v1/enrollment (khoá đang học) + /api/course_home/v1/progress/<khoá> (từng phần bài: hạn, có tính điểm, điểm).
Áp (LUẬT TỐI CAO — MOOC là hệ thống của trường):
  • bài tính điểm còn hạn, Academic Work chưa có  → THÊM (Môn học)
  • đã có trong Academic Work mà hạn lệch          → SỬA theo MOOC (deadlines.fix_due: kèm lịch + việc con, báo "Thay đổi")
  • chỉ có điểm không chứng minh đã nộp; chỉ đóng hạn khi nguồn có submitted=true
  • quá hạn mà 0 điểm                              → báo bạn MỘT lần ("bỏ lỡ")
  • hạn trước ngày khoá học bắt đầu (khoá dùng lại của đợt trước, GV chưa cập nhật) → coi là cũ, bỏ qua
Ra: school/mooc.json"""
import datetime as dt, json, re, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'mooc.json'
BASE = 'https://soict.daotao.ai'
TZ = dt.timezone(dt.timedelta(hours=7))

JS = r"""async () => {
  const g = async u => { try { const r = await fetch(u, {credentials: 'include', signal: AbortSignal.timeout(30000)}); return r.ok ? await r.json() : {status: r.status}; }
                         catch (e) { return {error: String(e)}; } };
  const me = await g('/api/user/v1/me');
  if (!me.username) return {ok: false, error: 'chưa đăng nhập MOOC'};
  const en = await g('/api/enrollment/v1/enrollment');
  if (!Array.isArray(en)) return {ok:false, error:'MOOC enrollment không hợp lệ'};
  const out = {ok: true, courses: {}};
  for (const e of (Array.isArray(en) ? en : [])) {
    if (!e.is_active) continue;
    const c = e.course_details.course_id, pr = await g('/api/course_home/v1/progress/' + encodeURIComponent(c));
    if (!Array.isArray(pr.courseware_summary)) return {ok:false,error:'MOOC progress không hợp lệ; giữ dữ liệu cũ'};
    const items = [];
    for (const ch of (pr.courseware_summary || [])) for (const s of (ch.subsections || [])) {
      if (!s.graded) continue;
      const ps = s.problem_scores || [];
      items.push({chapter: ch.display_name, name: s.display_name, due: s.due, format: s.format, url: s.url,
                  earned: ps.reduce((a, x) => a + (x.earned || 0), 0), possible: ps.reduce((a, x) => a + (x.possible || 0), 0), percent: s.percent_graded});
    }
    out.courses[c] = {name: e.course_details.course_name, start: e.course_details.course_start, end: e.course_details.course_end, items};
  }
  return out;
}"""


def fetch():
    import school_fetch as f
    from school_mail import ChromeLock
    from playwright.sync_api import sync_playwright
    with ChromeLock(), sync_playwright() as p:
        ctx = f._launch(p, True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(BASE + '/dashboard', wait_until='commit', timeout=90000); page.wait_for_timeout(7000)
            if '/login' in page.url or 'Đăng nhập' in page.inner_text('body')[:300]:
                if '/login' not in page.url: page.goto(BASE + '/login', wait_until='commit', timeout=90000); page.wait_for_timeout(4000)
                page.get_by_text(re.compile('Đăng nhập bằng HUST', re.I)).first.click(); page.wait_for_timeout(4000)
                f._through_sso(page, 'soict.daotao.ai', deadline=120); page.wait_for_timeout(5000)
            r = page.evaluate(JS)
        finally:
            try: ctx.close()
            except Exception: pass
    return save_snapshot(r)


def save_snapshot(r):
    if not r.get('ok'): return r
    try: old = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: old = {}
    # (v1.00.27, R-3) nguồn trả RỖNG hợp lệ (đổi khoá JSON / 403) mà lần trước có dữ liệu -> KHÔNG ghi đè, giữ bản cũ, báo lỗi rõ
    if not r.get('courses') and old.get('courses'):
        import uc_state; uc_state._err('mooc.json: lượt mới 0 khoá (lần trước %d) -> giữ bản cũ' % len(old['courses']))
        return {'ok': False, 'error': 'MOOC trả 0 khoá — giữ dữ liệu lần trước'}
    for cid, course in r.get('courses', {}).items():
        if not course.get('items') and old.get('courses', {}).get(cid, {}).get('items'):
            return {'ok': False, 'error': 'MOOC trả 0 bài cho khoá đã có bài — giữ dữ liệu lần trước'}
    r['at'] = dt.datetime.now(TZ).isoformat(timespec='minutes'); r['missed_notified'] = old.get('missed_notified', [])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(OUT)
    return {'ok': True, 'courses': len(r['courses']), 'graded': sum(len(c['items']) for c in r['courses'].values())}


def _norm(s):
    s = unicodedata.normalize('NFD', (s or '').lower())
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd'))).strip()


def sync(post):
    """Áp dữ liệu MOOC vào 📋 Academic Work theo luật tối cao. -> tóm tắt."""
    import deadlines as D
    from academic import Notion, title
    try: m = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return {'ok': False, 'error': 'chưa đọc MOOC'}
    nt = Notion(post)
    rows = D._fetch(post)
    courses = {c['code']: c['id'] for c in nt.courses()}
    now = dt.datetime.now(TZ)
    out = {'added': [], 'fixed': [], 'done': [], 'missed': [], 'stale': 0}
    for cid, c in m['courses'].items():
        mc = re.search(r'\+([A-Z]{2,4}\d{4})\+', cid); code = mc.group(1) if mc else None
        if not code: continue   # khoá không phải học phần (vd Sinh hoạt công dân) -> tab Ngoại khoá lo
        cstart = dt.datetime.fromisoformat(c['start'].replace('Z', '+00:00')) if c.get('start') else None
        for it in c['items']:
            if not it.get('due'): continue
            due = dt.datetime.fromisoformat(it['due'].replace('Z', '+00:00')).astimezone(TZ)
            if cstart and due < cstart: out['stale'] += 1; continue   # hạn của đợt trước, GV chưa cập nhật
            done = it.get('submitted') is True  # a score alone cannot prove submission
            name = f"{it['name']} (MOOC)"
            # cùng môn + hạn lệch ≤ 2 giờ, hoặc tên giống -> cùng một bài (vd Teams "Buổi học 4" = MOOC "Tuần 4", cùng hạn 1/10 00:00)
            same = [x for x in rows if x['course'] == code and
                    _norm(x['name']).removesuffix(' mooc') == _norm(it['name'])]
            if same:
                x = same[0]
                if abs((dt.datetime.fromisoformat(x['due']) - due).total_seconds()) > 60 and _norm(it['name']) in _norm(x['name']):
                    D.fix_due(post, x['id'], x['name'], x['due'], due.isoformat(), 'MOOC SoICT'); out['fixed'].append(x['name'])
                if done and x['status'] not in D.DONE:
                    nt.patch(x['id'], {'Status': {'status': {'name': 'Submitted'}}}); out['done'].append(f"{x['name']} ({it['earned']:g}/{it['possible']:g})")
                continue
            if due < now:
                if not done and (it.get('possible') or 0) > 0: out['missed'].append((cid, it, due))
                continue
            props = {'Name': title(name), 'Entry Kind': {'select': {'name': 'Deadline'}}, 'Loại hạn': {'select': {'name': 'Môn học'}},
                     'Due': {'date': {'start': due.isoformat()}}, 'Status': {'status': {'name': 'Submitted' if done else 'Not started'}},
                     'Type': {'select': {'name': 'Lab' if (it.get('format') or '').lower() == 'lab' else 'Homework'}},
                     'Workload Status': {'select': {'name': 'Needs review'}}, 'Submission/Repo': {'url': work_url(it, cid)}}
            if courses.get(code): props['Course'] = {'relation': [{'id': courses[code]}]}
            nt.create(D.WORK, props); out['added'].append(name)
    # bỏ lỡ: báo MỘT lần (thông báo "Thay đổi" của sự kiện bài tập môn đó)
    import mail_events as me
    st = me.load(); notified = set(m.get('missed_notified', []))
    for cid, it, due in out['missed']:
        key = f"{cid}|{it['name']}"
        if key in notified: continue
        mc = re.search(r'\+([A-Z]{2,4}\d{4})\+', cid); code = mc.group(1)
        line = f"MOOC: “{it['name']}” hết hạn {due:%H:%M} {due.day}/{due.month} — điểm {it['earned']:g}/{it['possible']:g} (chưa có bằng chứng đã nộp)"
        ev = st['events'].get(f'bt-{code}')
        if ev is not None:
            ev['changes'].append({'at': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'lines': [line], 'subject': 'MOOC: bài đã quá hạn',
                                  'backfill': False, 'ack': None, 'nguon': 'MOOC'})
        notified.add(key)
    me.save(st)
    m['missed_notified'] = sorted(notified); OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding='utf-8')
    if out['added'] or out['fixed'] or out['done']: D.refresh(post)
    out['missed'] = [f"{it['name']} ({it['earned']:g}/{it['possible']:g})" for _, it, _ in out['missed']]
    return {'ok': True, **out}





def work_url(item, cid):
    from urllib.parse import urljoin, urlsplit
    url = urljoin(BASE, item.get('url') or ('/courses/' + cid + '/course/'))
    return url if urlsplit(url).netloc == urlsplit(BASE).netloc and urlsplit(url).scheme == 'https' else BASE + '/courses/' + cid + '/course/'


def collect_api(request):
    """Read enrolled assignments using an existing browser's cookie jar; GET only."""
    from urllib.parse import quote
    def get(path):
        response = request.get(BASE + path, timeout=30000)
        if not response.ok:
            raise ValueError('MOOC API HTTP ' + str(response.status))
        return response.json()
    try:
        enrollments = get('/api/enrollment/v1/enrollment')
        if not isinstance(enrollments, list): raise ValueError('enrollment không hợp lệ')
        courses = {}
        for e in enrollments:
            if not e.get('is_active'): continue
            c = e['course_details']; cid = c['course_id']
            progress = get('/api/course_home/v1/progress/' + quote(cid, safe=''))
            if not isinstance(progress.get('courseware_summary'), list):
                raise ValueError('progress không hợp lệ; giữ dữ liệu cũ')
            items = []
            for chapter in progress['courseware_summary']:
                for sub in chapter.get('subsections', []):
                    if not sub.get('graded'): continue
                    scores = sub.get('problem_scores') or []
                    items.append(dict(chapter=chapter.get('display_name'), name=sub['display_name'],
                        due=sub.get('due'), format=sub.get('format'), url=sub.get('url'),
                        earned=sum(x.get('earned') or 0 for x in scores),
                        possible=sum(x.get('possible') or 0 for x in scores),
                        percent=sub.get('percent_graded')))
            courses[cid] = dict(name=c.get('course_name'), start=c.get('course_start'), end=c.get('course_end'), items=items)
        return dict(ok=True, courses=courses)
    except Exception as e:
        return dict(ok=False, error=f'{type(e).__name__}: {e}'[:200])

if __name__ == '__main__':
    print(json.dumps(fetch(), ensure_ascii=False))
