# -*- coding: utf-8 -*-
"""Chi tiết một môn trong kỳ: các LỚP thành phần + ĐIỂM thành phần + cách tính (Claude 2026-10-05).

Ghép nhiều trang (người dùng 5/10: "cái này đòi hỏi liên trang web"):
  • CÁCH TÍNH  : bài của giảng viên trên Teams / mail (vd IT2000 "Điểm học phần = TN×40% + MOOC×10% + CK×50%")
                 -> Gemini đọc MỘT lần mỗi môn, chỉ khi có bài mới nói về cách tính -> school/grade_rules.json
  • ĐIỂM       : qldt "Điểm thành phần" (vd "TN/TH: 10")  — LUẬT TỐI CAO: điểm của trường thắng
                 MOOC SoICT (bài tập hằng tuần: điểm / tối đa; bỏ bài cũ của khoá trước)
                 điểm bạn báo qua chat (✅ Grades, academic.py)
  • LỚP        : thời khoá biểu (LT+BT / BT / TN …: GV, phòng, số buổi đã học)
Không gọi AI khi xem (chỉ đọc file); AI chỉ chạy trong vòng cập nhật khi có bài mới về cách tính."""
import datetime as dt, hashlib, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES = HERE / 'school' / 'grade_rules.json'
TZ = dt.timezone(dt.timedelta(hours=7))
GRADING = re.compile(r'cách tính điểm|điểm quá trình|điểm học phần|trọng số|chuyên cần|điểm thành phần|điểm giữa kỳ|điểm cuối kỳ|thang điểm', re.I)
LETTERS = [('A+', 9.5), ('A', 8.5), ('B+', 8.0), ('B', 7.0), ('C+', 6.5), ('C', 5.5), ('D+', 5.0), ('D', 4.0)]


def _load(p, d=None):
    try: return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception: return d if d is not None else {}


PROMPT = """Dưới đây là các bài, trang thông báo và file mà giảng viên / khoa đưa cho lớp môn {code} {name}. Có thể một tài liệu nói chung cho nhiều môn (vd "các học phần Toán cao cấp") — chỉ lấy phần áp dụng cho môn {code}. Hãy rút ra CÁCH TÍNH ĐIỂM HỌC PHẦN, không bịa.
Trả lời CHỈ JSON: {{"cong_thuc": "<1 dòng tiếng Việt, đúng như bài đăng>",
 "thanh_phan": [{{"ten": "<tên thành phần>", "trong_so": <% trên ĐIỂM HỌC PHẦN, số>,
   "nguon": "qldt" (điểm thành phần trường nhập: thực hành / thí nghiệm / giữa kỳ / quá trình) | "mooc_bt" (bài tập hằng tuần trên MOOC SoICT / daotao.ai) | "fami" (bài thi / đánh giá theo chương trên FAMI số hoá — các môn Toán MI) | "chuyen_can" | "cuoi_ky" | "khac",
   "nhan_qldt": "<nhãn có thể xuất hiện trên qldt, vd 'TN/TH', 'GK', 'QT' — hoặc null>", "ghi_chu": "<ngắn hoặc null>"}}],
 "ghi_chu": "<luật cộng / trừ điểm quan trọng khác, ngắn, hoặc null>"}}
Nếu một thành phần gộp nhiều thứ (vd 'tham dự lớp và bài tập hằng tuần trên MOOC 10%') thì giữ là MỘT thành phần với nguon chính.
Tổng trong_so phải = 100 nếu bài đăng nói đủ. Bài sau ĐÍNH CHÍNH bài trước thì theo bài mới nhất của giảng viên / trợ giảng; bỏ qua câu trả lời của sinh viên và các con số không phải trọng số (phổ điểm, số thứ tự, tỉ lệ vắng, % trong một thành phần con).

BÀI ĐĂNG:
{posts}"""


GRADING_POST = re.compile(r'đánh giá (các )?học phần|đánh giá các hp|cách tính điểm|thang điểm|trọng số|điểm quá trình|điểm học phần|điểm cuối kỳ|điểm giữa kỳ|chuyên cần|điểm thưởng|điểm cộng', re.I)
GRADING_DOC = re.compile(r'đánh giá|danh gia|cách tính|cach tinh|đề cương|de cuong|syllabus|thang điểm|grading|quy định điểm|điểm học phần', re.I)
DOC_EXT = ('.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.txt')
URL_RX = re.compile(r'https?://[^\s"<>)\]]+')


def _tika(path, limit=12000):
    """Trích chữ từ file trên máy bằng Tika (Docker :9998) — không gọi AI."""
    import urllib.request
    try:
        req = urllib.request.Request('http://127.0.0.1:9998/tika', data=Path(path).read_bytes(), method='PUT',
                                     headers={'Accept': 'text/plain; charset=utf-8'})
        with urllib.request.urlopen(req, timeout=120) as r: return re.sub(r'\n\s*\n+', '\n', r.read().decode('utf-8', 'ignore'))[:limit]
    except Exception as e:
        return f'(không đọc được file: {type(e).__name__})'


def _page(url, limit=8000):
    """Đọc trang thông báo mà bài đăng dẫn tới (vd fami.hust.edu.vn/thong-bao-sinh-vien/...) — chỉ trang công khai."""
    import html as H, urllib.request
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (UC; doc cach tinh diem)'})
        with urllib.request.urlopen(req, timeout=30) as r:
            if 'text/html' not in (r.headers.get('Content-Type') or ''): return ''
            t = r.read().decode('utf-8', 'ignore')
        t = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', t)
        t = H.unescape(re.sub(r'<[^>]+>', ' ', t))
        return re.sub(r'\s+', ' ', t).strip()[:limit]
    except Exception as e:
        return f'(không mở được trang: {type(e).__name__})'


DOCS_CACHE = HERE / 'school' / 'grade_docs_cache.json'
STRICT_WEIGHT = re.compile(r'\d{1,3}\s?%[\s\S]{0,400}?\d{1,3}\s?%|0[.,]\d\s*[*x×]', re.I)   # ít nhất 2 trọng số / một công thức
HAS_WEIGHT = re.compile(r'\d{1,3}\s?%|trọng số|hệ số\s*0[.,]\d|0[.,]\d\s*\*', re.I)


def _grading_excerpt(text, width=1400):
    """Đoạn trong tài liệu nói về đánh giá / cách tính điểm (có trọng số) — vd slide 16 "Đánh giá học phần: 50% GIỮA KỲ…" của IT1108."""
    out, last = [], -10**9
    for m in GRADING_POST.finditer(text or ''):
        if m.start() < last + width: continue
        win = text[max(0, m.start() - 300): m.start() + width]
        if HAS_WEIGHT.search(win): out.append(win.strip()); last = m.start()
        if len(out) >= 3: break
    return '\n…\n'.join(out)


def _doc_hits(code_files):
    """MỌI tài liệu của môn (slide, đề cương, file trong kênh / Shared Documents) -> đọc NỘI DUNG bằng Tika, giữ đoạn nói về cách tính.
    Cache theo file + ngày sửa: mỗi file chỉ đọc một lần (Tika, không AI)."""
    cache = _load(DOCS_CACHE)
    hits = {}
    for code, docs in code_files.items():
        for d in docs:
            sig = f"{d['path']}|{d.get('modified')}"
            c = cache.get(d['path'])
            if not c or c.get('sig') != sig:
                if not Path(d['path']).exists(): continue
                c = {'sig': sig, 'hit': _grading_excerpt(_tika(d['path'], 400000))}
                cache[d['path']] = c
            if c['hit'] or GRADING_DOC.search(d['name']):
                hits.setdefault(code, []).append({**d, 'excerpt': c['hit']})
    DOCS_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding='utf-8')
    return hits


def refresh_rules(gemini=None):
    """Gọi trong vòng cập nhật, cho MỌI nhóm Teams / môn: gom (1) bài nói về đánh giá / cách tính điểm, (2) trang mà bài đó dẫn tới,
    (3) file đánh giá / đề cương trong Files của nhóm (đọc bằng Tika) -> chỉ khi bộ nguồn đổi mới gọi AI (1 lần / môn)."""
    import mail_events as me
    gemini = gemini or me.gemini
    rules = _load(RULES)
    by = {}
    for m in me.sources():
        code = m.get('CourseCode')
        text = (m.get('Subject') or '') + ' ' + (m.get('Body') or '')
        if code and (GRADING_POST.search(text) or (GRADING.search(text) and re.search(r'\d{1,3}\s?%', text))):
            by.setdefault(code, {'name': m.get('CourseName') or '', 'posts': [], 'docs': [], 'links': []})['posts'].append(m)
    try:   # (6/10) trả lời trong luồng + Class Notebook của mọi nhóm lớp
        import teams_files
        tab = teams_files.course_table()
        T = HERE / 'school' / 'teams'
        for y in _load(T / 'replies.json', {}).get('items') or []:
            code, name = teams_files.course_of_team(y.get('team') or '', tab)
            if code and GRADING_POST.search(y.get('body') or '') and STRICT_WEIGHT.search(y.get('body') or ''):   # SV hay nhắc "trọng số" bâng quơ
                by.setdefault(code, {'name': name or '', 'posts': [], 'docs': [], 'links': []})['posts'].append(
                    {'Id': 'reply:' + y['id'] + '@' + (y.get('modified') or ''), 'Subject': '↳ trả lời: ' + (y.get('parentSubject') or ''), 'Body': y['body'],
                     'Created': y.get('created'), 'Team': y.get('team'), 'Source': 'teams'})
        for n in _load(T / 'onenote.json', {}).get('items') or []:
            code, name = teams_files.course_of_team(n.get('team') or '', tab)
            ex = _grading_excerpt(n.get('text') or '')
            if code and ex:
                by.setdefault(code, {'name': name or '', 'posts': [], 'docs': [], 'links': []})['posts'].append(
                    {'Id': 'onenote:' + n['id'] + '@' + (n.get('modified') or ''), 'Subject': 'Class Notebook · ' + (n.get('section') or '') + ' · ' + (n.get('title') or ''),
                     'Body': ex, 'Created': n.get('modified'), 'Team': n.get('team'), 'Source': 'teams'})
        # MỌI tài liệu của môn đã tải về Uni-Documents -> đọc nội dung (không chỉ file có tên "đánh giá")
        done = _load(T / 'files_done.json')
        files = {}
        for k, v in done.items():
            if v.get('mon') and v.get('rel') and (v.get('name') or '').lower().endswith(DOC_EXT):
                files.setdefault(v['mon'], []).append({'name': v['name'], 'path': str(Path(teams_files.UNI) / v['rel']), 'modified': v.get('modified')})
        for code, docs in _doc_hits(files).items():
            by.setdefault(code, {'name': '', 'posts': [], 'docs': [], 'links': []})['docs'].extend(docs)
    except Exception as e:
        print('grade_rules docs:', e)
    shared = [d for x in by.values() for d in x['docs'] if re.search(r'toán (đc|đại cương|cao cấp)|toan dc|toan cao cap', d['name'], re.I)]
    for code, x in by.items():
        if code.startswith('MI'):
            for d in shared:
                if d not in x['docs']: x['docs'].append(d)
    n_ai = 0
    for code, x in by.items():
        posts = sorted(x['posts'], key=lambda m: m.get('Created') or m.get('ReceivedDateTime') or '')
        links = []
        for m in posts:
            for u in URL_RX.findall(m.get('Body') or ''):
                u = u.rstrip('.,;')
                if re.search(r'hust\.edu\.vn|daotao\.ai', u) and not re.search(r'teams\.microsoft|forms\.|safelinks|sharepoint', u) and u not in links: links.append(u)
        x['docs'].sort(key=lambda d: (not d.get('excerpt'), not GRADING_DOC.search(d['name'])))   # file có đoạn cách tính lên trước
        key = '|'.join([m['Id'] for m in posts] + [d['name'] + str(d['modified']) for d in x['docs']] + links)
        h = hashlib.sha1(key.encode()).hexdigest()[:12]
        if (rules.get(code) or {}).get('hash') == h: continue
        # (6/10) chọn 8 bài NÓI RÕ NHẤT về cách tính (nhiều trọng số, tiêu đề về điểm) chứ không phải 8 bài mới nhất — bài giới thiệu đầu kỳ hay bị đẩy ra
        def score(m):
            t = (m.get('Subject') or '') + ' ' + (m.get('Body') or '')
            return len(re.findall(r'\d{1,3}\s?%', t)) + 3 * bool(GRADING_POST.search(m.get('Subject') or '')) + 2 * bool(STRICT_WEIGHT.search(t))
        top = sorted(sorted(posts, key=score, reverse=True)[:8], key=lambda m: m.get('Created') or m.get('ReceivedDateTime') or '')
        parts = [f"[BÀI {(m.get('Created') or m.get('ReceivedDateTime') or '')[:10]}] {m.get('Subject') or ''}\n{me.clean(m.get('Body') or '')[:2500]}" for m in top]
        parts += [f"[TRANG {u}]\n{_page(u)}" for u in links[:3]]
        parts += [f"[FILE {d['name']}]\n{d.get('excerpt') or _tika(d['path'])}" for d in x['docs'][:4] if Path(d['path']).exists()]
        if not parts: continue
        try:
            out = gemini(PROMPT.format(code=code, name=x['name'], posts='\n\n'.join(parts)[:30000]), caller='mail'); n_ai += 1
        except Exception as e:
            print('grade_rules', code, e); continue
        if isinstance(out, list): out = next((o for o in out if isinstance(o, dict)), {})
        if not (out or {}).get('thanh_phan'):   # nguồn không nói cách tính -> ghi hash để khỏi hỏi lại, nhưng không ghi đè luật đã có
            rules.setdefault(code, {})['hash'] = h; continue
        src = [{'subject': (m.get('Subject') or '')[:120], 'at': (m.get('Created') or m.get('ReceivedDateTime') or '')[:10],
                'where': ('Teams · ' + (m.get('Team') or '')[:50]) if m.get('Source') == 'teams' else 'Mail'} for m in sorted(top, key=score, reverse=True)[:3]]
        src += [{'subject': 'Trang ' + u, 'at': '', 'where': 'link trong bài'} for u in links[:2]]
        src += [{'subject': d['name'], 'at': (d.get('modified') or '')[:10], 'where': 'File trong nhóm Teams'} for d in x['docs'][:2]]
        rules[code] = {**out, 'hash': h, 'at': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'nguon': src}
    try:
        import teams_files
        for code, name, cls in teams_files.course_table():
            if not cls: continue   # chỉ môn đang học kỳ này (có lớp trong TKB)
            x = by.get(code) or {'posts': [], 'docs': []}
            rules.setdefault(code, {})['quet'] = {'at': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'bai': len(x['posts']), 'file': len(x['docs'])}
    except Exception as e:
        print('grade_rules scan:', e)
    RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True, 'courses': len([c for c in rules.values() if c.get('thanh_phan')]), 'ai_calls': n_ai}


def _qldt_components(code):
    """'TN/TH: 10 · GK: 7.5' (qldt) -> {'TN/TH': 10.0, 'GK': 7.5}."""
    tr = (_load(HERE / 'school' / 'latest.json').get('transcript') or {}).get('rows') or []
    out = {}
    for r in tr:
        if len(r) > 4 and r[1] == code:
            for part in re.split(r'[·;\n]|\s{2,}', ' '.join(r[4:])):
                m = re.match(r'\s*([^:]+?)\s*:\s*([\d.,]+)', part)
                if m: out[m.group(1).strip()] = float(m.group(2).replace(',', '.'))
    return out


def _mooc_weekly(code, now):
    mo = _load(HERE / 'school' / 'mooc.json')
    for cid, c in (mo.get('courses') or {}).items():
        if f'+{code}+' not in cid: continue
        start = c.get('start')
        try: start = dt.datetime.fromisoformat(start.replace('Z', '+00:00')) if start else None
        except Exception: start = None
        rows = []
        for it in c.get('items') or []:
            if (it.get('type') or '').lower() not in ('homework', 'bài tập') and 'bài tập' not in (it.get('name') or '').lower(): continue
            due = it.get('due')
            try: due = dt.datetime.fromisoformat(due.replace('Z', '+00:00')) if due else None
            except Exception: due = None
            if due and start and due < start: continue          # bài cũ của khoá trước
            rows.append({'ten': it['name'], 'diem': it.get('earned') or 0, 'toi_da': it.get('possible') or 0,
                         'han': due.astimezone(TZ).isoformat(timespec='minutes') if due else None, 'qua_han': bool(due and due < now)})
        done = [r for r in rows if r['qua_han'] and r['toi_da']]
        avg = round(sum(r['diem'] for r in done) / sum(r['toi_da'] for r in done) * 10, 2) if done else None
        return {'bai': rows, 'diem_10': avg, 'url': f"https://soict.daotao.ai/courses/{cid}/progress"}
    return None


def _fami(code, now):
    try:
        import fami
        its = [i for i in fami.items(now) if i['code'] == code]
    except Exception:
        return None
    if not its: return None
    rows = []
    for i in its:
        sc = i.get('score') or {}
        pts = sc.get('diem') if isinstance(sc, dict) else None
        rows.append({'ten': f"CĐ{i['stt']} — {i['topic']}", 'diem': pts, 'toi_da': i.get('max'), 'han': i['due'].isoformat(timespec='minutes'),
                     'qua_han': i['due'] < now, 'da_lam': bool(i.get('done'))})
    done = [r for r in rows if (r['qua_han'] or r['da_lam']) and r['toi_da']]
    avg = round(sum(float(r['diem'] or 0) for r in done) / sum(float(r['toi_da']) for r in done) * 10, 2) if done else None
    return {'bai': rows, 'diem_10': avg, 'url': its[0].get('url')}


def _sections(code, now):
    tt = _load(HERE / 'timetable_cache.json')
    g = {}
    for e in tt.get('events') or []:
        if e.get('kind') != 'Class' or not e['title'].startswith(code): continue
        parts = [x.strip() for x in e['title'].split('·')]
        x = g.setdefault(e['title'], {'loai': parts[2] if len(parts) > 2 else '', 'hinh_thuc': parts[3] if len(parts) > 3 else '',
                                      'tong': 0, 'da_hoc': 0, 'phong': set(), 'gv': None, 'ma_lop': None, 'ket_thuc': None})
        x['tong'] += 1; x['da_hoc'] += (e.get('start') or '') < now.isoformat()
        if e.get('location'): x['phong'].add(e['location'].split(' (')[0])
        n = e.get('notes') or ''
        m = re.search(r'GV ([^·]+)', n); x['gv'] = x['gv'] or (m.group(1).strip() if m else None)
        m = re.search(r'Mã lớp (\d+)', n); x['ma_lop'] = x['ma_lop'] or (m.group(1) if m else None)
        x['ket_thuc'] = max(x['ket_thuc'] or '', e.get('end') or '')
    return [{**v, 'phong': sorted(v['phong'])[:3]} for v in g.values()]


def view(code):
    import academic
    now = dt.datetime.now(TZ)
    rule = _load(RULES).get(code) or {}
    q = _qldt_components(code)
    mooc = _mooc_weekly(code, now)
    fam = _fami(code, now)
    comps = []
    for t in rule.get('thanh_phan') or []:
        w = float(t.get('trong_so') or 0); src = t.get('nguon'); score, where = None, None
        nm = academic.norm(t.get('ten'))   # (5/10) nguồn điểm theo TÊN thành phần (AI hay gán nhầm), chỉ khi có dữ liệu nguồn đó
        if re.search(r'lien tuc|theo chuong', nm) and fam: src = 'fami'
        elif re.search(r'giua ky|thuc hanh|thi nghiem|tn th', nm): src = 'qldt'
        elif re.search(r'mooc|truoc khi den lop|bai tap hang tuan', nm) and mooc: src = 'mooc_bt'
        elif 'chuyen can' in nm: src = 'chuyen_can'
        elif 'cuoi ky' in nm: src = 'cuoi_ky'
        if src == 'qldt' or t.get('nhan_qldt'):
            lab = t.get('nhan_qldt')
            hit = next((v for k, v in q.items() if lab and academic.norm(k) == academic.norm(lab)), None)
            if hit is None and len(q) == 1 and src == 'qldt': hit = next(iter(q.values()))
            if hit is not None: score, where = hit, 'qldt'
        if score is None and src == 'mooc_bt' and mooc and mooc['diem_10'] is not None:
            score, where = mooc['diem_10'], 'MOOC (bài đã qua hạn)'
        if score is None and src == 'fami' and fam and fam['diem_10'] is not None:
            score, where = fam['diem_10'], 'FAMI (chủ đề đã chấm / đã đóng)'
        comps.append({'ten': t.get('ten'), 'trong_so': w, 'nguon': src, 'diem': score, 'lay_tu': where,
                      'dong_gop': round(score * w / 100, 2) if score is not None else None, 'ghi_chu': t.get('ghi_chu')})
    known = sum(c['dong_gop'] for c in comps if c['dong_gop'] is not None)
    w_known = sum(c['trong_so'] for c in comps if c['diem'] is not None)
    ck = next((c for c in comps if c['nguon'] == 'cuoi_ky'), None)
    need = []
    others_unknown = [c for c in comps if c['diem'] is None and c is not ck]
    if ck and ck['diem'] is None and ck['trong_so'] and not others_unknown:
        for l, lo in LETTERS:
            x = (lo - 0.05 - known) / (ck['trong_so'] / 100)   # điểm HP làm tròn 1 chữ số
            if x <= 10: need.append({'chu': l, 'ck_toi_thieu': max(0.0, round(x + 0.049, 1))})
    return {'ok': True, 'code': code, 'cong_thuc': rule.get('cong_thuc'), 'ghi_chu': rule.get('ghi_chu'), 'nguon_cach_tinh': rule.get('nguon') or [],
            'thanh_phan': comps, 'diem_da_chac': round(known, 2), 'trong_so_da_co': w_known, 'ck_can': need,
            'qldt_tho': q, 'mooc': mooc, 'fami': fam, 'lop': _sections(code, now),
            'thieu': [c['ten'] for c in others_unknown], 'quet': rule.get('quet')}


if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(encoding='utf-8')
    print(refresh_rules())
    print(json.dumps(view(sys.argv[1] if len(sys.argv) > 1 else 'IT2000'), ensure_ascii=False, indent=1)[:3500])
