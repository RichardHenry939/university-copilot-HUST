# -*- coding: utf-8 -*-
"""(v1.00.52, chủ 02/11) Bản chép lời Teams thay recorder cho các lớp LÝ THUYẾT học online (IT2000, MI1111, MI1141) — CHỈ ĐỌC.

Khảo sát 02/11: bản ghi họp kênh nằm trong thư mục "Recordings" của kênh (SharePoint của nhóm, đọc bằng token Graph của trang Teams);
transcript lấy qua SharePoint `/_api/v2.1/drives/<d>/items/<i>/media/transcripts` (cookie phiên trình duyệt sẵn có) -> tải .vtt.
.vtt của trường KHÔNG có thẻ người nói (`<v Tên>`), nên phần lớn dòng chỉ có "[mm:ss] câu".

Đường đi (giống hệt recorder từ bước "đã chép lời xong"):
  .vtt -> đoạn {start, end, text, speaker} -> cổng chép lời POST /jobs/text (chỉ nén bằng LM Studio, không thu âm / chép lời)
  -> gọi lại n8n `lecture-transcript-ready` -> Lecture Analysis (Gemini) -> 📚 Lecture Notes -> lecture_export .txt
  trong "<môn>/Ghi chú Bài giảng"; sau đó UC chép .vtt gốc cạnh file .txt (cùng tên, đuôi .vtt).
Môn do n8n tự gán theo tiết học trùng giờ (như recorder). IT1108 (học trực tiếp) và nhóm MIL: không đụng, vẫn recorder.
Ngôn ngữ chép lời không phải tiếng Việt (vd 02/11 Giải tích đặt nhầm en-US) -> KHÔNG gửi, ghi "wrong-lang" để chủ biết.

Ra: school/teams/transcripts.json (trạng thái từng bản ghi), school/teams/transcripts/<captureId>.vtt + .txt ("[mm:ss] Người nói: câu").
  python teams_transcripts.py          -> chạy một lượt (tải + gửi + chép .vtt cạnh ghi chú)
Giới hạn (cố ý đi tắt): nếu chủ CŨNG bấm recorder cho cùng buổi thì sẽ có 2 ghi chú — chưa gộp; chỉ xét bản ghi trong 3 ngày gần nhất.
"""
import datetime as dt, json, re, shutil, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIR = HERE / 'school' / 'teams' / 'transcripts'
STATE = HERE / 'school' / 'teams' / 'transcripts.json'
TZ = dt.timezone(dt.timedelta(hours=7))
# nhóm Teams của lớp lý thuyết có bản ghi (IT2000 · MI1111 · MI1141 LT). IT1108 / Quân sự / lớp chiều thực hành: không có trong danh sách.
THEORY = re.compile(r'Nhập môn CNTT&TT - 171981|Giải tích 4-6|OMO-SángT2', re.I)
COURSE = [(re.compile(r'Nhập môn CNTT', re.I), 'IT2000'), (re.compile(r'Giải tích', re.I), 'MI1111'), (re.compile(r'OMO-SángT2', re.I), 'MI1141')]
# (chủ 02/11 tối) Môn CÒN lịch thi sắp tới = gấp: gửi nén ngay, kể cả khi đang chơi game (dịch vụ ưu tiên).
# Môn chưa có lịch thi (vd IT2000) = không gấp: dồn sang đêm 22:00–06:00 để máy đỡ nặng ban ngày.
MIN_SIZE = 20_000_000         # bỏ file "Meeting Recording.mp4" vài MB (đoạn ghi hỏng / bấm nhầm)
MAX_AGE_DAYS = 3
EVERY_MIN = 30
GATE = 'http://127.0.0.1:8340'
CALLBACK = 'http://127.0.0.1:5678/webhook/lecture-transcript-ready'
import uc_config as cfg
SESSIONS_DB = cfg.notion('lecture_sessions')   # 🎙️ Lecture Sessions (như recorder)

LIST_JS = r"""async (pat) => {
  let tok = null;
  for (const k of Object.keys(localStorage)) { if (!/accesstoken/i.test(k)) continue;
    try { const o = JSON.parse(localStorage.getItem(k)); if (/graph\.microsoft\.com\/ChannelMessage\.Read\.All/i.test(o.target)) tok = o.secret; } catch (e) {} }
  if (!tok) return {ok: false, error: 'no graph token'};
  const g = async u => { try { const r = await fetch('https://graph.microsoft.com/v1.0' + u, {headers: {Authorization: 'Bearer ' + tok}, signal: AbortSignal.timeout(30000)});
      return r.ok ? r.json() : {error: r.status}; } catch (e) { return {error: 'timeout'}; } };
  const re = new RegExp(pat, 'i'), recs = [];
  for (const t of ((await g('/me/joinedTeams')).value || [])) {
    if (!re.test(t.displayName)) continue;
    for (const c of ((await g(`/teams/${t.id}/channels`)).value || [])) {
      const ff = await g(`/teams/${t.id}/channels/${c.id}/filesFolder`);
      if (!ff.parentReference) continue;
      const d = ff.parentReference.driveId;
      for (const k of ((await g(`/drives/${d}/items/${ff.id}/children?$top=200`)).value || [])) {
        if (!k.folder || !/^recordings$/i.test(k.name)) continue;
        for (const r of ((await g(`/drives/${d}/items/${k.id}/children?$top=200`)).value || []))
          if (r.file) recs.push({team: t.displayName, channel: c.displayName, name: r.name, size: r.size, created: r.createdDateTime, driveId: d, id: r.id, web: r.webUrl});
      }
    }
  }
  return {ok: true, recs};
}"""

VTT_JS = r"""async (rs) => {
  const out = [];
  for (const r of rs) {
    const base = `/_api/v2.1/drives/${r.driveId}/items/${r.id}`, one = {id: r.id};
    try {
      const a = await fetch(base + '/media/transcripts', {credentials: 'include', headers: {Accept: 'application/json'}});
      one.status = a.status;
      const v = a.ok ? ((await a.json()).value || []) : [];
      one.langs = v.map(x => x.languageTag);
      const tr = v.find(x => x.isDefault) || v[0];
      if (tr) {
        one.lang = tr.languageTag || '';
        const b = await fetch(base + `/media/transcripts/${tr.id}/streamContent?format=vtt`, {credentials: 'include'});
        if (b.ok) one.vtt = await b.text(); else one.status = b.status;
      }
    } catch (e) { one.error = String(e); }
    out.push(one);
  }
  return out;
}"""


# ----------------------------------------------------------------------------- .vtt -> chữ
def _sec(t):
    h, m, s = (['0'] + t.split(':'))[-3:]
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_vtt(text):
    """-> [{start, end, text, speaker}] (giây tính từ đầu bản ghi). Hiểu cả thẻ <v Tên>…</v> nếu có."""
    out = []
    for block in re.split(r'\r?\n\s*\r?\n', text.replace('﻿', '')):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        i = next((k for k, l in enumerate(lines) if '-->' in l), None)
        if i is None: continue
        m = re.match(r'\s*([\d:.]+)\s*-->\s*([\d:.]+)', lines[i])
        if not m: continue
        body = ' '.join(lines[i + 1:])
        sp = re.search(r'<v(?:\.[^ >]*)?\s+([^>]+)>', body)
        body = re.sub(r'<[^>]+>', '', body).strip()
        if body: out.append({'start': round(_sec(m.group(1)), 1), 'end': round(_sec(m.group(2)), 1), 'text': body,
                             'speaker': sp.group(1).strip() if sp else ''})
    return out


def merge(cues, gap=1.5, max_chars=400):
    """Gộp dòng liền nhau cùng người nói (cách nhau < gap giây, tổng < max_chars ký tự)."""
    out = []
    for c in cues:
        p = out[-1] if out else None
        if p and p['speaker'] == c['speaker'] and c['start'] - p['end'] < gap and len(p['text']) + len(c['text']) < max_chars:
            p['text'] += ' ' + c['text']; p['end'] = c['end']
        else:
            out.append(dict(c))
    return out


def to_text(kept):
    def mmss(s): s = int(s); return f'{s // 60:02d}:{s % 60:02d}'
    return '\n'.join(f"[{mmss(k['start'])}] " + (f"{k['speaker']}: " if k['speaker'] else '') + k['text'] for k in kept)


def started_at(name, created):
    """Giờ bắt đầu ghi: tên file Teams có '_YYYYMMDD_HHMMSS' (giờ máy ở VN); không có thì lấy giờ tạo file."""
    m = re.search(r'(\d{8})_(\d{6})', name)
    if m: return dt.datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S').replace(tzinfo=TZ)
    return dt.datetime.fromisoformat(created.replace('Z', '+00:00')).astimezone(TZ)


# ----------------------------------------------------------------------------- trạng thái
def load():
    try: return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception: return {'items': {}}


def save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')


def course_of(team):
    return next((c for rx, c in COURSE if rx.search(team or '')), '')


def urgent(code, now=None, exams=None):
    """Môn còn lịch thi (chưa tới giờ thi) -> gấp."""
    now = now or dt.datetime.now(TZ)
    if exams is None:
        import exam_watch; exams = exam_watch.exams(now)
        code_of = exam_watch._code
    else:
        code_of = lambda e: e.get('code')
    return bool(code) and any(code_of(e) == code and dt.datetime.fromisoformat(e['start']) >= now for e in exams)


def night(now=None):
    h = (now or dt.datetime.now(TZ)).hour
    return h >= 22 or h < 6


def due(now=None):
    now = now or dt.datetime.now(TZ)
    last = load().get('last_run')
    if not 7 <= now.hour < 23: return False
    return not last or (now - dt.datetime.fromisoformat(last)).total_seconds() >= EVERY_MIN * 60


# ----------------------------------------------------------------------------- trình duyệt (chỉ đọc)
def _browse(pick_new):
    import school_fetch as f
    from school_mail import ChromeLock
    from playwright.sync_api import sync_playwright
    with ChromeLock(), sync_playwright() as p:
        ctx = f._launch(p, True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto('https://teams.cloud.microsoft/', wait_until='commit', timeout=90000)
            for _ in range(30):
                page.wait_for_timeout(3000)
                if any(h in page.url for h in ('login.microsoftonline', 'adfs', 'sso.hust', 'asso.hust')):
                    f._through_sso(page, 'teams.cloud.microsoft', deadline=120); continue
                try: has = page.evaluate("() => Object.keys(localStorage).some(k => /accesstoken/i.test(k) && /ChannelMessage\\.Read/.test(localStorage.getItem(k) || ''))")
                except Exception: has = False
                if has: break
            lst = page.evaluate(LIST_JS, THEORY.pattern)
            if not lst.get('ok'): return lst, []
            new = pick_new(lst['recs'])
            if not new: return lst, []
            page.goto(new[0]['web'], wait_until='commit', timeout=90000)   # sang SharePoint: API v2.1 dùng cookie cùng nguồn
            for _ in range(40):
                page.wait_for_timeout(3000)
                if any(h in page.url for h in ('login.microsoftonline', 'adfs', 'sso.hust', 'asso.hust')):
                    f._through_sso(page, 'sharepoint.com', deadline=120); continue
                if 'sharepoint.com' in page.url: break
            page.wait_for_timeout(3000)
            return lst, page.evaluate(VTT_JS, new)
        finally:
            try: ctx.close()
            except Exception: pass


# ----------------------------------------------------------------------------- một lượt
def _gate_text(cap, start, end, kept):
    q = urllib.parse.urlencode({'captureId': cap, 'startedAt': start.isoformat(), 'endedAt': end.isoformat(),
                                'callback': CALLBACK, 'source': 'teams-vtt'})
    body = json.dumps({'kept': kept}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(f'{GATE}/jobs/text?{q}', data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read())


def _session(nt, cap, start, end, rec):
    """Dòng 🎙️ Lecture Sessions như recorder tạo, ở trạng thái Processing (vòng 'Uploaded' của n8n không nhặt: không có audio)."""
    rt = lambda s: {'rich_text': [{'text': {'content': s[:1900]}}]}
    return nt.create(SESSIONS_DB, {
        'Session': {'title': [{'text': {'content': f'Lecture {cap}'}}]}, 'State': {'select': {'name': 'Processing'}},
        'Capture ID': rt(cap), 'Analysis Key': rt(cap + ':lecture-v2'),
        'Started At': {'date': {'start': start.isoformat()}}, 'Ended At': {'date': {'start': end.isoformat()}},
        'Audio URL': {'url': rec.get('web')},
        'Processing Notes': rt(f"Bản chép lời Teams ({rec['team']}) — không thu âm; .vtt -> nén trên máy -> Gemini.")})


def _send(nt, x, kept):
    """Tạo dòng Lecture Sessions + gửi chữ vào cổng nén. -> bản ghi trạng thái mới."""
    start = dt.datetime.fromisoformat(x['startedAt']); end = start + dt.timedelta(seconds=kept[-1]['end'])
    try:
        _session(nt, x['captureId'], start, end, {'team': x.get('team', ''), 'web': x.get('web')})
        j = _gate_text(x['captureId'], start, end, kept)
        return {**x, 'status': 'sent', 'job': j.get('jobId'), 'sentAt': dt.datetime.now(TZ).isoformat(timespec='seconds')}
    except Exception as e:
        return {**x, 'status': 'error', 'error': f'{type(e).__name__}: {e}'[:300]}


def _gate_retry(jid):
    req = urllib.request.Request(f'{GATE}/jobs/{jid}/retry', data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())


def dispatch_deferred(post, st=None, now=None):
    """Đêm (22:00–06:00): gửi các buổi không gấp đã dồn lại. Không cần trình duyệt (dùng .vtt đã lưu). -> số buổi đã gửi"""
    now = now or dt.datetime.now(TZ)
    if not night(now): return 0
    own = st is None
    st = load() if own else st
    import academic
    nt, n = academic.Notion(post), 0
    for iid, x in st.get('items', {}).items():
        if x.get('status') != 'deferred': continue
        if x.get('job'):   # job đã có trong cổng (hoãn giữa chừng): chạy lại từ bước nén, không chép lời lại
            try: _gate_retry(x['job']); x.update(status='sent', sentAt=now.isoformat(timespec='seconds')); n += 1
            except Exception as e: x.update(status='error', error=f'retry: {type(e).__name__}: {e}'[:300])
            continue
        src = DIR / f"{x['captureId']}.vtt"
        if not src.exists(): x.update(status='error', error='mất file .vtt'); continue
        st['items'][iid] = _send(nt, x, merge(parse_vtt(src.read_text(encoding='utf-8'))))
        n += st['items'][iid]['status'] == 'sent'
    if own: save(st)
    return n


def place_vtt(post, st):
    """Ghi chú đã xuất ra .txt -> chép .vtt gốc cạnh nó. -> số file đã chép"""
    import academic, copilot_app as app
    try: exp = json.loads((HERE / 'school' / 'lecture_export.json').read_text(encoding='utf-8'))
    except Exception: return 0
    nt, n = academic.Notion(post), 0
    for iid, x in st['items'].items():
        if x.get('status') != 'sent' or x.get('vttRel'): continue
        rows = nt.query(SESSIONS_DB, {'property': 'Capture ID', 'rich_text': {'equals': x['captureId']}})
        url = ((rows[0]['properties'].get('Processed Note') or {}).get('url') or '') if rows else ''
        m = re.search(r'([0-9a-f]{32})$', url.replace('-', ''))
        if not m: continue
        h = m.group(1); nid = f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'
        rel = (exp.get(nid) or {}).get('rel')
        src = DIR / f"{x['captureId']}.vtt"
        if not rel or not src.exists(): continue
        vrel = str(Path(rel).with_suffix('.vtt'))
        shutil.copy2(src, app.UNI / vrel)
        x.update(vttRel=vrel, status='done', note=url); n += 1
    return n


def run(post):
    import academic
    st = load(); items = st.setdefault('items', {})
    now = dt.datetime.now(TZ)
    st['last_run'] = now.isoformat(timespec='seconds'); save(st)
    if not items: st['since'] = (now - dt.timedelta(days=MAX_AGE_DAYS)).isoformat(timespec='seconds')
    since = dt.datetime.fromisoformat(st.get('since') or (now - dt.timedelta(days=MAX_AGE_DAYS)).isoformat())

    def pick_new(recs):
        out = []
        for r in recs:
            if r['id'] in items or r['size'] < MIN_SIZE or not r['name'].lower().endswith('.mp4'): continue
            c = dt.datetime.fromisoformat(r['created'].replace('Z', '+00:00'))
            if c < since or c < now - dt.timedelta(days=MAX_AGE_DAYS): continue
            out.append(r)
        return out[:6]

    lst, got = _browse(pick_new)
    res = {'ok': bool(lst.get('ok')), 'error': lst.get('error'), 'recordings': len(lst.get('recs') or []), 'sent': [], 'skipped': []}
    recs = {r['id']: r for r in (lst.get('recs') or [])}
    nt = academic.Notion(post)
    DIR.mkdir(parents=True, exist_ok=True)
    for g in got:
        r = recs[g['id']]; start = started_at(r['name'], r['created'])
        cap = 'teams-' + start.strftime('%Y%m%d-%H%M%S') + '-' + re.sub(r'\W', '', g['id'])[-6:]
        x = {'captureId': cap, 'team': r['team'], 'name': r['name'], 'startedAt': start.isoformat(), 'lang': g.get('lang'), 'at': now.isoformat(timespec='seconds')}
        if not g.get('vtt'):   # chưa có transcript (Teams xử lý chậm) -> lượt sau thử lại, không ghi vào items
            res['skipped'].append(f"{r['name']}: chưa có bản chép lời ({g.get('status')})"); continue
        (DIR / f'{cap}.vtt').write_text(g['vtt'], encoding='utf-8')
        kept = merge(parse_vtt(g['vtt']))
        (DIR / f'{cap}.txt').write_text(to_text(kept), encoding='utf-8')
        if not (g.get('lang') or '').lower().startswith('vi'):
            items[g['id']] = {**x, 'status': 'wrong-lang'}; save(st)
            res['skipped'].append(f"{r['name']}: Teams chép lời bằng {g.get('lang')} (không phải tiếng Việt) — không gửi"); continue
        if not kept:
            items[g['id']] = {**x, 'status': 'empty'}; save(st); continue
        x.update(course=course_of(r['team']), web=r.get('web'), segments=len(kept))
        if not urgent(x['course'], now) and not night(now):
            items[g['id']] = {**x, 'status': 'deferred'}; save(st)
            res['skipped'].append(f"{r['name']}: {x['course'] or 'môn ?'} chưa có lịch thi -> nén đêm nay (22:00–06:00)"); continue
        items[g['id']] = _send(nt, x, kept)
        if items[g['id']]['status'] == 'sent': res['sent'].append(r['name'])
        save(st)
    try: res['deferred_sent'] = dispatch_deferred(post, st, now)
    except Exception as e: res['deferred_sent'] = f'{type(e).__name__}: {e}'[:200]
    try: res['vtt_placed'] = place_vtt(post, st)
    except Exception as e: res['vtt_placed'] = f'{type(e).__name__}: {e}'[:200]
    save(st)
    return res


def skip_rels():
    """.vtt UC đã chép cạnh ghi chú: không nạp ngược lên Drive / Notion (như .txt của lecture_export)."""
    return {x['vttRel'].lower() for x in load().get('items', {}).values() if x.get('vttRel')}


if __name__ == '__main__':
    import copilot_app as C
    print(json.dumps(run(C._npost), ensure_ascii=False, indent=1))
