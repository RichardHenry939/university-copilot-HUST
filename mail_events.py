# -*- coding: utf-8 -*-
"""Mail trường -> sự kiện nhiều chặng + bản DIFF khi đính chính (Claude 2026-10-04).

Bài học gốc: hệ thống không thiếu dữ liệu — nó thiếu khả năng nói "cái bạn tưởng mình biết đã sai".
  • Gemini (cổng UC :8350, caller=mail) CHỈ trích dữ liệu: thư này nói tới những chặng nào (tên, ngày, giờ, địa điểm),
    thuộc sự kiện đang theo dõi nào. Không quyết định gì.
  • Code so từng chặng với dữ liệu đã có -> dòng "Trước → Nay" / "Thêm chặng". Đính chính = thay đổi, không phải sự kiện mới.
  • Mail xác nhận đăng ký mở "sự kiện đang theo dõi"; mail sau cùng luồng/chủ đề/người gửi tự gắn vào.
  • Lưu: school/events.json (gốc) + 📡 Sự kiện theo dõi (Notion) + mỗi chặng 1 dòng lịch (Kind=Event, Sync Key mail|…).
  python mail_events.py   (xử lý thư chưa xử lý trong school/mail/inbox.json)"""
import uc_config as cfg
import json, os, re, time, unicodedata, urllib.request, urllib.error, datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOX = HERE / 'school' / 'mail' / 'inbox.json'
STORE = HERE / 'school' / 'events.json'
GATE = 'http://127.0.0.1:8350/v1beta/models/{m}:generateContent?caller=mail'
TRACK_DB = cfg.notion("events_track")
EVENTS_DB = cfg.notion("calendar_events")
TZ = dt.timezone(dt.timedelta(hours=7))
SKIP_SENDERS = ('notion', 'microsoft teams', ' in teams', 'no-reply@', 'noreply@')
HINT = re.compile(r'thi\b|vòng|lịch|đăng k[ýí]|hội thảo|hội nghị|cuộc thi|olympic|seminar|workshop|buổi|phòng|hạn|deadline|nộp|'
                  r'xác nhận|thông báo|tập huấn|sinh hoạt|họp|khai mạc|bảo vệ|kiểm tra|thay đổi|đính chính|dời|hoãn|chuyển', re.I)


def norm(s):
    s = unicodedata.normalize('NFD', (s or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def subject_key(s):
    s = re.sub(r'^\s*((re|fw|fwd|tl|tr|trả lời|chuyển tiếp)\s*:\s*)+', '', s or '', flags=re.I)
    return norm(s)[:80]


def load():
    try: return json.loads(STORE.read_text(encoding='utf-8'))
    except Exception: return {'events': {}, 'processed': []}


def save(st):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')


def done_ids(st): return set(st['processed'])


def gemini(prompt, model='gemini-3.5-flash-lite', caller='mail'):
    body = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': 0.1, 'responseMimeType': 'application/json'}}
    key = os.environ.get('GEMINI_API_KEY')
    if not key:   # tiến trình mở trước khi đặt biến -> đọc thẳng biến User
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as k: key = winreg.QueryValueEx(k, 'GEMINI_API_KEY')[0]
    req = urllib.request.Request(GATE.format(m=model).replace('caller=mail', 'caller=' + caller), data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    for wait in (0, 65, 130):   # 429 thường là giới hạn theo phút -> chờ rồi thử lại; vẫn lỗi thì để lượt sau
        time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=180) as r: j = json.loads(r.read().decode('utf-8')); break
        except urllib.error.HTTPError as e:
            if e.code != 429 or wait == 130: raise
    time.sleep(4)   # giãn nhịp, không dồn quota
    text = ''.join(p.get('text', '') for p in j['candidates'][0]['content']['parts'])
    text = re.sub(r'^```(json)?|```$', '', text.strip()).strip()
    return json.loads(text)


def stage_key(name): return norm(name) or 'chang'


def when_of(sg):
    if not sg.get('ngay'): return None
    try:
        d = dt.date.fromisoformat(sg['ngay'])
        h, m = (int(x) for x in (sg.get('gio') or '23:59').split(':')[:2])
        return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)
    except Exception:
        return None


def fmt(sg):
    d = sg.get('ngay'); g = sg.get('gio')
    ds = f"{int(d[8:10])}/{int(d[5:7])}" if d else 'chưa rõ ngày'
    return ds + (f' {g}' if g else '') + (f", {sg['dia_diem']}" if sg.get('dia_diem') else '')


def diff_stages(old, new):
    """old/new: {stage_key: stage}. -> danh sách dòng thay đổi (chỉ chặng thư mới có nhắc)."""
    out = []
    for k, n in new.items():
        o = old.get(k)
        if not o:
            out.append(f"Thêm {n['ten']}: {fmt(n)}"); continue
        parts = []
        for f, label in (('ngay', 'ngày'), ('gio', 'giờ'), ('dia_diem', 'địa điểm')):
            if (n.get(f) or None) != (o.get(f) or None) and n.get(f) and o.get(f):   # trước chưa có -> chỉ là bổ sung, không phải thay đổi
                if f == 'dia_diem' and (norm(n[f]) in norm(o[f]) or norm(o[f]) in norm(n[f])): continue   # chỉ ghi gọn/chi tiết hơn
                if f == 'dia_diem' and rooms(n[f]) and rooms(n[f]) == rooms(o[f]): continue   # cùng các phòng, chỉ viết khác
                ov = o.get(f) or 'chưa có'
                if f == 'ngay':
                    ov = f"{int(o['ngay'][8:10])}/{int(o['ngay'][5:7])}" if o.get('ngay') else 'chưa có'
                    nv = f"{int(n['ngay'][8:10])}/{int(n['ngay'][5:7])}"
                else: nv = n[f]
                parts.append(f'{label} {ov} → {nv}')
        if n.get('huy') and not o.get('huy'): parts.append('ĐÃ HUỶ')
        if parts: out.append(f"{n['ten']}: " + '; '.join(parts))
    return out


def clean(body):
    keep = lambda u: u if re.search(r'teams\.microsoft|forms\.(office|gle)|zoom\.us|meet\.google', u) else ''
    t = re.sub(r'<(https?://[^>]*)>', lambda x: ' ' + keep(x.group(1)) + ' ', body or '')   # giữ link họp/biểu mẫu, bỏ link theo dõi
    t = re.sub(r'\[https?://[^\]]*\]', '', t)
    t = re.split(r'\n_{8,}\n|\nFrom: .*\nSent: |\nTừ: .*\nĐã gửi: ', t)[0]   # bỏ phần trích thư cũ khi trả lời
    return re.sub(r'\n\s*\n+', '\n', t).strip()


def text_diff(old, new):
    """Hai thư cùng chủ đề gần giống nhau -> các cặp dòng đã đổi (Trước/Nay). Thuần so chữ, không AI."""
    import difflib
    a, b = [l.strip() for l in old.splitlines() if l.strip()], [l.strip() for l in new.splitlines() if l.strip()]
    if not a or not b or difflib.SequenceMatcher(None, a, b).ratio() < 0.6: return []
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == 'equal': continue
        was, now = ' / '.join(a[i1:i2])[:200], ' / '.join(b[j1:j2])[:200]
        out.append(f'Trước: {was or "(không có)"} → Nay: {now or "(đã bỏ)"}')
    return out[:5]


PROMPT = """Bạn trích DỮ LIỆU từ một email gửi tới sinh viên Đại học Bách khoa Hà Nội. Không suy đoán, không bịa.
Email nhận lúc {received} (giờ VN). Năm hiện tại: {year}.

Các sự kiện đang theo dõi (id: tên — các chặng đã biết):
{tracked}
{hint}
EMAIL:
Người gửi: {sender}
Tiêu đề: {subject}
Nội dung:
{body}

Trả lời CHỈ một object JSON:
{{"lien_quan": true/false (email nói về một sự kiện/lịch/hạn mà sinh viên cần có mặt hoặc làm gì vào thời điểm cụ thể — cuộc thi, kỳ thi, hội thảo, buổi sinh hoạt, hạn đăng ký/nộp; false cho quảng cáo, tin chung, thông báo không có thời điểm),
 "loai": "xac_nhan_dang_ky" | "thong_bao_lich" | "dinh_chinh" | "nhac_nho" | "huy" | "ket_qua" | "khac",
 "nhom": "hoc_tap" (môn học, lớp, thi / kiểm tra môn, đăng ký học phần / kế hoạch học tập, học vụ) | "ngoai_khoa" (CLB, Đoàn / Hội, cuộc thi, tuyển thành viên / đội, thể thao, tình nguyện, hội thảo, khai giảng, sinh hoạt định hướng / công dân, học bổng),
 "doi_tuong": "ban_tham_gia" (CHỈ khi văn bản nêu RÕ người nhận đã đăng ký / được chọn / có tên trong danh sách / bắt buộc phải dự — vd thông báo lịch thi gửi cho thí sinh đã đăng ký, lịch lớp của môn đang học) | "moi_chung" (lời mời, tuyển thành viên, quảng bá, sự kiện mở cho ai muốn tham gia; KHÔNG CHẮC thì chọn moi_chung),
 "su_kien_id": "<id trong danh sách nếu email thuộc sự kiện đó, ngược lại null>",
 "ten_su_kien": "<tên ngắn, vd 'Olympic Vật lý ĐHBK 2026'>",
 "chang": [ {{"ten": "<tên chặng, vd 'Vòng 1', 'Hạn nộp bài', 'Buổi hội thảo'>", "loai_chang": "buoi_hoc" | "han_nop" | "su_kien", "ngay": "YYYY-MM-DD hoặc null", "gio": "HH:MM (giờ diễn ra ghi RÕ trong email; KHÔNG dùng giờ gửi email) hoặc null",
             "dia_diem": "<phòng/địa chỉ hoặc null>", "ghi_chu": "<thông tin quan trọng khác của chặng, ngắn, hoặc null>", "huy": true/false}} ],
 "tom_tat": "<1 câu tiếng Việt: email nói gì>"}}
Quy tắc: "chang" chỉ gồm các chặng email NÀY nhắc tới, với thông tin MỚI NHẤT theo email này. Dùng đúng tên chặng đã biết nếu là cùng chặng (kể cả khi email đổi ngày/giờ/phòng của nó). Tên chặng KHÔNG chứa ngày, giờ, phòng.
Nếu là một KHOẢNG thời gian ("từ ngày A đến hết ngày B"), "ngay" = ngày CUỐI B (hạn chót) và "ghi_chu" nêu "từ A".
Nếu email chia nhiều phòng theo danh sách, ghi "dia_diem" là các phòng và nêu cách chia trong "ghi_chu"."""


def tracked_text(st):
    rows = []
    for eid, e in st['events'].items():
        if e.get('status') != 'Đang theo dõi': continue
        ch = sorted(e['chang'].values(), key=lambda s: s.get('ngay') or '')[-8:]   # lớp học có nhiều buổi: chỉ đưa các chặng gần nhất
        rows.append(f"{eid}: {e['ten']} — " + '; '.join(f"{s['ten']} {fmt(s)}" for s in ch))
    return '\n'.join(rows) or '(chưa có)'


TEAMS_POSTS = HERE / 'school' / 'teams' / 'posts.json'
SKIP_CHANNEL = re.compile(r'trao đổi|thảo luận|discussion', re.I)
HINT_TEAMS = re.compile(r'quiz|due |bài tập|btvn|nộp|phòng|buổi|lịch|thi\b|kiểm tra|nghỉ|bù|online|offline|đổi|hạn', re.I)


def sources():
    """Thư trường + bài đăng Teams, theo thời gian. Bài Teams mang theo môn của lớp (nếu nhận ra)."""
    items = [dict(m, Source='mail') for m in json.loads(BOX.read_text(encoding='utf-8'))['items']]
    try:
        import teams_files
        tab = teams_files.course_table()
        for m in json.loads(TEAMS_POSTS.read_text(encoding='utf-8'))['items']:
            code, name = teams_files.course_of_team(m.get('Team') or '', tab)
            items.append(dict(m, CourseCode=code, CourseName=name))
    except FileNotFoundError: pass
    return sorted(items, key=lambda m: m['ReceivedDateTime'])


def must_of(x, m):
    """Bạn là NGƯỜI THAM GIA (leo thang đủ: toast + điện thoại) hay chỉ nhận lời mời chung (gợi ý trong UC)?
    Xác nhận đăng ký -> tham gia. Bài đăng trong nhóm Teams không phải lớp môn (vd K71) -> luôn là lời mời chung."""
    if x.get('loai') == 'xac_nhan_dang_ky': return True
    if m.get('Source') == 'teams' and not m.get('CourseCode'): return False
    return x.get('doi_tuong') == 'ban_tham_gia'


def course_events(st, code, name):
    """Mỗi môn có 2 sự kiện cố định: lịch lớp (buổi học, đổi phòng/giờ — không nhắc theo giờ) và bài tập (hạn nộp — có nhắc)."""
    for kind, eid, ten in (('lop', f'lop-{code}', f'Lịch lớp {code} {name}'), ('bt', f'bt-{code}', f'Bài tập {code} {name}')):
        st['events'].setdefault(eid, {'ten': ten, 'kind': kind, 'course': code, 'status': 'Đang theo dõi', 'chang': {}, 'conversations': [],
                                      'subject_keys': [], 'sender': '', 'mails': [], 'changes': [], 'ack': {},
                                      'created': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'notion_id': None})


def process(post=None, backfill=False):
    st = load(); items = sources()
    done = set(st['processed']); changes = []
    for m in items:
        if m['Id'] in done: continue
        teams = m.get('Source') == 'teams'
        sender = f"{m['FromName']} <{m['FromAddress']}>"
        text = (m['Subject'] + ' ' + m['Body'][:3000])
        if teams: skip = bool(SKIP_CHANNEL.search(m.get('Channel') or '')) or not (HINT.search(text) or HINT_TEAMS.search(text))
        else: skip = any(x in sender.lower() for x in SKIP_SENDERS) or not HINT.search(text)
        st['processed'].append(m['Id'])
        if skip: continue
        code = m.get('CourseCode')
        if code: course_events(st, code, m.get('CourseName') or '')
        # ghép chắc chắn trước (cùng luồng thư / cùng chủ đề / cùng bài Teams) rồi mới hỏi AI
        sk = subject_key(m['Subject'])
        likely = next((eid for eid, e in st['events'].items() if m.get('ConversationId') in e.get('conversations', [])
                       or (sk and sk in e.get('subject_keys', []))), None)
        hint = f"Gợi ý: email này cùng luồng/chủ đề với sự kiện {likely}.\n" if likely else ''
        if code:
            hint += (f"Bài đăng trong nhóm Teams của lớp môn {code} {m.get('CourseName')} (kênh {m.get('Channel')}). "
                     f"Thông báo buổi học / đổi phòng / đổi giờ / nghỉ / học bù của lớp -> su_kien_id = lop-{code}, mỗi buổi là 1 chặng tên 'Buổi N' (loai_chang buoi_hoc). "
                     f"Bài tập / quiz / hạn nộp -> su_kien_id = bt-{code}, mỗi bài là 1 chặng tên đúng tên bài (loai_chang han_nop, ngay/gio = hạn nộp).\n")
        # mốc để hiểu "ngày mai / tuần sau" = lúc ĐĂNG gốc (bài Teams sửa sau vẫn giữ lời lẽ của ngày đăng)
        recv = dt.datetime.fromisoformat((m.get('Created') or m['ReceivedDateTime']).replace('Z', '+00:00')).astimezone(TZ)
        try:
            x = gemini(PROMPT.format(received=recv.strftime('%H:%M %d/%m/%Y'), year=recv.year, tracked=tracked_text(st), hint=hint,
                                     sender=sender, subject=m['Subject'], body=clean(m['Body'])[:6000]))
        except Exception as e:
            st['processed'].pop(); print('gemini lỗi', m['Subject'][:60], e); break   # để lần sau thử lại, giữ thứ tự thư
        if isinstance(x, list): x = next((y for y in x if isinstance(y, dict)), {})   # đôi khi AI bọc trong mảng
        if not x.get('lien_quan') or not x.get('chang'): continue
        eid = x.get('su_kien_id') if x.get('su_kien_id') in st['events'] else likely
        for s in x['chang']:   # AI hay lấy nhầm giờ gửi thư làm giờ diễn ra
            if s.get('gio') == recv.strftime('%H:%M'): s['gio'] = None
        new = {stage_key(s['ten']): {k: s.get(k) for k in ('ten', 'ngay', 'gio', 'dia_diem', 'ghi_chu', 'huy', 'loai_chang')} for s in x['chang'] if s.get('ten')}
        now = dt.datetime.now(TZ).isoformat(timespec='minutes')
        src = {'subject': m['Subject'], 'from': m['FromName'], 'at': recv.isoformat(timespec='minutes'), 'loai': x.get('loai'),
               'tom_tat': x.get('tom_tat'), 'nguon': 'Teams · ' + (m.get('Team') or '')[:40] if teams else 'Mail'}
        if eid:
            e = st['events'][eid]
            lines = diff_stages(e['chang'], new)
            prev = next((p for p in reversed(items) if p['Id'] in done_ids(st) and p['Id'] != m['Id']
                         and (subject_key(p['Subject']) == sk or (teams and p.get('ConversationId') == m.get('ConversationId')))
                         and p['ReceivedDateTime'] < m['ReceivedDateTime']), None)
            if prev: lines += [l for l in text_diff(clean(prev['Body']), clean(m['Body'])) if l not in lines]
            if e.get('kind') in ('lop', 'bt'): lines = [l for l in lines if not l.startswith('Thêm ')]   # buổi / bài mới không phải "thay đổi"
            for k, s in new.items(): e['chang'][k] = {**e['chang'].get(k, {}), **{f: v for f, v in s.items() if v is not None}}
            if m.get('ConversationId') and m['ConversationId'] not in e['conversations']: e['conversations'].append(m['ConversationId'])
            if sk and sk not in e['subject_keys'] and e.get('kind') not in ('lop', 'bt'): e['subject_keys'].append(sk)
            e['mails'] = (e['mails'] + [src])[-30:]
            if must_of(x, m): e['must'] = True
            if x.get('nhom') in ('hoc_tap', 'ngoai_khoa') and not e.get('kind'): e['nhom'] = x['nhom']
            if lines:
                past = all((when_of(s) or dt.datetime.max.replace(tzinfo=TZ)) < dt.datetime.now(TZ) for s in new.values())
                ch = {'at': now, 'mail_at': src['at'], 'lines': lines, 'subject': m['Subject'], 'backfill': backfill or past, 'ack': None, 'nguon': src['nguon']}
                e['changes'].append(ch); changes.append((eid, ch))
            if x.get('loai') == 'huy' and not e.get('kind') and all(s.get('huy') for s in e['chang'].values()): e['status'] = 'Bỏ'
        else:
            eid = 'ev' + str(int(time.time() * 1000))[-9:]
            st['events'][eid] = {'ten': x.get('ten_su_kien') or m['Subject'][:60], 'status': 'Đang theo dõi', 'chang': new,
                                 'conversations': [m['ConversationId']] if m.get('ConversationId') else [], 'subject_keys': [sk] if sk else [],
                                 'sender': m['FromAddress'], 'mails': [src], 'changes': [], 'ack': {}, 'created': now, 'notion_id': None,
                                 'course': code, 'must': must_of(x, m), 'nhom': 'hoc_tap' if code else (x.get('nhom') or 'ngoai_khoa')}
        save(st)
        print('sự kiện', eid, st['events'][eid]['ten'], '|', x.get('loai'), '|', [fmt(s) for s in new.values()])
    save(st)
    if post: sync_notion(post, st)
    return {'changes': [(eid, ch['lines']) for eid, ch in changes], 'events': len(st['events'])}


def next_stage(e, now=None):
    now = now or dt.datetime.now(TZ)
    up = [(when_of(s), k, s) for k, s in e['chang'].items() if when_of(s) and not s.get('huy')]
    up = sorted([u for u in up if u[0] >= now - dt.timedelta(hours=3)])   # chặng đang diễn ra vẫn tính là "tới"
    return up[0] if up else (None, None, None)


def rooms(t):
    """Mã phòng chuẩn hoá: 'B1-103', 'b1 103', 'Phòng 103, tầng 1, toà nhà B1' -> {'b1-103'}."""
    s = norm(t or '')
    out = {f'{b}-{r}' for b, r in re.findall(r'\b([a-z]{1,2}\d{1,2})\s?(\d{3,4})\b', s)}
    for r, b in re.findall(r'\bphong (\d{3,4})\b.{0,40}?\b(?:toa nha|toa|nha)\s([a-z]{1,2}\d{1,2})\b', s):
        out.add(f'{b}-{r}')
    if not out: out = set(re.findall(r'\b\d{3,4}\b', s))   # chỉ có số phòng
    return out


def patch_classes(nt, eid, e):
    """Lịch lớp từ Teams -> sửa thẳng buổi học (Kind=Class) cùng môn, cùng ngày trong lịch Notion: phòng / giờ.
    Thông báo của giảng viên trên nhóm lớp là dữ liệu trường mới hơn TKB qldt; đồng bộ TKB giữ nguyên buổi đã có nên không bị đổi ngược."""
    from academic import rt, P
    done = e.setdefault('class_patched', {})
    for k, s in e['chang'].items():
        if not s.get('ngay') or (not s.get('dia_diem') and not s.get('gio')): continue
        sig = f"{s.get('ngay')}|{s.get('gio')}|{s.get('dia_diem')}"
        if done.get(k) == sig: continue
        rows = [r for r in nt.query(EVENTS_DB, {'and': [{'property': 'Kind', 'select': {'equals': 'Class'}},
                                                        {'property': 'When', 'date': {'equals': s['ngay']}}]})
                if (P(r, 'Event') or '').startswith(e['course'])]
        if not rows: done[k] = sig; continue
        r = rows[0]; loc = P(r, 'Location') or ''; when = r['properties']['When']['date']; notes = P(r, 'Notes') or ''
        props, lines = {}, []
        d = f"{int(s['ngay'][8:10])}/{int(s['ngay'][5:7])}"
        if s.get('dia_diem') and rooms(s['dia_diem']) and not rooms(s['dia_diem']) <= rooms(loc):
            props['Location'] = rt(s['dia_diem']); lines.append(f"{s['ten']} ({d}): phòng {loc or 'chưa có'} → {s['dia_diem']}")
        st0 = dt.datetime.fromisoformat(when['start'])
        if s.get('gio') and st0.strftime('%H:%M') != s['gio']:
            h, mi = map(int, s['gio'].split(':')); ns = st0.replace(hour=h, minute=mi)
            ne = (dt.datetime.fromisoformat(when['end']) + (ns - st0)).isoformat() if when.get('end') else None
            props['When'] = {'date': {'start': ns.isoformat(), **({'end': ne} if ne else {})}}
            lines.append(f"{s['ten']} ({d}): giờ {st0:%H:%M} → {s['gio']}")
        if props:
            props['Notes'] = rt((notes + ' · 📡 Teams: ' + '; '.join(lines))[:1900])
            nt.patch(r['id'], props)
            past = (when_of(s) or dt.datetime.now(TZ)) < dt.datetime.now(TZ)
            e['changes'].append({'at': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'lines': lines, 'subject': 'Lịch lớp (Teams)',
                                 'backfill': past, 'ack': None, 'nguon': 'Teams'})
        done[k] = sig


def sync_notion(post, st, only=None):
    """Đồng bộ events.json -> 📡 Sự kiện theo dõi + lịch. Chỉ gửi sự kiện có thay đổi (Notion qua n8n ~1 s/lần gọi)."""
    from academic import Notion, rt, title
    import hashlib
    nt = Notion(post)
    cal = None
    for eid, e in st['events'].items():
        if only and eid != only: continue
        if e.get('kind') == 'lop' and e.get('course'):
            try: patch_classes(nt, eid, e)
            except Exception as ex: print('patch_classes:', ex)
        w, k, s = next_stage(e)
        if not w and e['status'] == 'Đang theo dõi' and not e.get('kind') and any(when_of(x) for x in e['chang'].values()): e['status'] = 'Đã xong'   # mọi chặng đã qua
        sig = hashlib.sha1(json.dumps([e['ten'], e['status'], e['chang'], e['changes'][-1:], e.get('ack'), k, len(e['mails'])],
                                      ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if e.get('notion_id') and e.get('synced') == sig: continue
        if not e['chang'] and not e.get('notion_id'): continue   # sự kiện môn chưa có chặng nào
        last = e['changes'][-1] if e['changes'] else None
        props = {'Sự kiện': title(e['ten']), 'Trạng thái': {'select': {'name': e['status']}},
                 'Chặng tới': {'date': {'start': w.isoformat(timespec='minutes')}} if w else {'date': None},
                 'Chặng tới (mô tả)': rt(f"{s['ten']}: {fmt(s)}" if s else 'không còn chặng nào sắp tới'),
                 'Chặng (JSON)': rt(json.dumps(sorted(e['chang'].values(), key=lambda x: x.get('ngay') or '')[-12:], ensure_ascii=False)[:1900]),
                 'Thay đổi gần nhất': rt(' · '.join(last['lines'])[:1900] if last else ''),
                 'Lúc thay đổi': {'date': {'start': last['at']}} if last else {'date': None},
                 'Người gửi': rt(e.get('sender') or ''), 'Khoá chủ đề': rt(' | '.join(e['subject_keys'])[:1900]),
                 'Mail nguồn': rt(' | '.join(f"{x['at'][:16]} {x.get('nguon') or 'Mail'}: {x['subject']}" for x in e['mails'][-10:])[:1900])}
        conf = ((e.get('ack') or {}).get(k) or {}).get('choice') if k else None
        props['Xác nhận'] = {'select': {'name': conf}} if conf in ('Sẽ đi', 'Bỏ', 'Đã nộp') else {'select': None}
        if e.get('notion_id'): nt.patch(e['notion_id'], props)
        else: e['notion_id'] = nt.create(TRACK_DB, props)['id']
        if e.get('kind') not in ('lop', 'bt') and e.get('nhom') != 'ngoai_khoa':   # buổi học đã có (Class) · bài tập: Academic Work ghi lịch · ngoại khoá: 🎯 riêng
            if cal is None:
                cal = {}
                for r in nt.query(EVENTS_DB, {'property': 'Sync Key', 'rich_text': {'starts_with': 'mail|'}}):
                    cal[''.join(t.get('plain_text', '') for t in r['properties']['Sync Key']['rich_text'])] = r
            for sk_, sg in e['chang'].items():
                wd = when_of(sg); key = f'mail|{eid}|{sk_}'
                if not wd: continue
                dl = sg.get('loai_chang') == 'han_nop' or e.get('kind') == 'bt'
                cp = {'Event': title(f"{'📝' if dl else '📡'} {e['ten']} · {sg['ten']}" + (' (huỷ)' if sg.get('huy') else '')),
                      'Kind': {'select': {'name': 'Deadline' if dl else 'Event'}},
                      'When': {'date': {'start': wd.isoformat(timespec='minutes')}}, 'Location': rt(sg.get('dia_diem') or ''),
                      'Notes': rt((sg.get('ghi_chu') or '')[:1900]), 'Sync Key': rt(key)}
                if key in cal: nt.patch(cal[key]['id'], cp)
                else: cal[key] = nt.create(EVENTS_DB, cp)
        e['synced'] = sig
        save(st)
    save(st)


if __name__ == '__main__':
    import sys
    import copilot_app
    print(json.dumps(process(copilot_app._npost, backfill='--backfill' in sys.argv), ensure_ascii=False))
