# -*- coding: utf-8 -*-
"""📅 Kế hoạch tự học + xuất Google Calendar / Excel (Claude 14/10/2026, theo chủ dự án — học từ "Công cụ xây dựng kế hoạch học tập"
của CLB o365 HUST, nhưng chạy trên dữ liệu UC đã đồng bộ sẵn, không phải nhập tay).

Nguồn (chỉ ĐỌC school/latest.json — bản đồng bộ trường 5 phút/lần):
  • Lịch học: tkb (qldt) -> school_sync.parse_tkb (mỗi buổi: môn, thứ, giờ, phòng, các tuần học).
  • Yêu cầu tự học: course_info[môn].creditInfo dạng "4(3-0-2-8)" = TC(LT-BT-TN-TỰ HỌC) -> số cuối = giờ tự học / tuần.
  • Tuần 1 của năm học: tkb.week1 (cùng mốc đồng bộ TKB dùng).
plan(pct):  chia giờ tự học (× pct %) ĐỀU vào các ngày, mỗi khối 1 giờ, trong khung 07:00–11:30, 13:30–17:30, 19:00–22:00,
            không trùng lớp học đều đặn (lớp học >= nửa số tuần chặn khung đó; .ics bỏ khối nào trùng buổi học THẬT của tuần đó), tối đa 4 giờ tự học / ngày thường, 6 giờ / ngày cuối tuần.
ics(pct):   file .ics (nhập vào Google Calendar: Cài đặt -> Nhập & xuất) gồm từng buổi học theo đúng tuần + khối tự học các tuần có học.
xlsx(pct):  file .xlsx 3 trang: Lịch học · Tự học hằng tuần · Yêu cầu tự học — viết bằng thư viện chuẩn (không cần openpyxl).
Giới hạn (cố ý đơn giản): kế hoạch tự học là MẪU 1 TUẦN lặp lại (không tránh lịch thi / ngày nghỉ / hoạt động ngoại khoá);
môn không có creditInfo thì không có yêu cầu tự học. Không ghi gì vào Notion."""
import datetime as dt, io, json, re, zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
SNAP = HERE / 'school' / 'latest.json'
TZ = dt.timezone(dt.timedelta(hours=7))
WINDOWS = [('07:00', '11:30'), ('13:30', '17:30'), ('19:00', '22:00')]
DAY_CAP_H = [4, 4, 4, 4, 4, 6, 6]   # tối đa giờ tự học / ngày (T2..CN): cuối tuần rộng hơn
THU = {'2': 0, '3': 1, '4': 2, '5': 3, '6': 4, '7': 5, 'cn': 6}
THU_NAME = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật']


def _m(hhmm): h, m = hhmm.split(':'); return int(h) * 60 + int(m)
def _hm(mins): return f'{mins // 60:02d}:{mins % 60:02d}'


def data():
    import school_sync, tkb
    snap = json.loads(SNAP.read_text(encoding='utf-8-sig'))
    t = snap.get('tkb') or {}
    lop, _, probs = school_sync.parse_tkb(t)
    sem = t.get('sem') or ''
    w1 = tkb.week1(dt.date(int(sem[:4]), 10, 1)) if sem[:4].isdigit() else None
    names = {}
    for r in t.get('rows') or []:   # "Nhập môn CNTT và TT\n768100 - IT2000 (TN)" -> tên môn
        m = re.search(r'([A-Z]{2,4}\d{3,4}[A-Z]?)', r[1] if len(r) > 1 else '')
        if m: names.setdefault(m.group(1), r[1].split('\n')[0].strip())
    req = {}
    for code, ci in (snap.get('course_info') or {}).items():
        m = re.search(r'\(([\d.]+)-([\d.]+)-([\d.]+)-([\d.]+)\)', ci.get('creditInfo') or '')
        if m and float(m.group(4)) > 0:
            req[code] = {'name': ci.get('name') or names.get(code, code), 'credit': ci.get('credit'), 'info': ci['creditInfo'], 'hours': float(m.group(4))}
            names.setdefault(code, req[code]['name'])
    return {'sem': sem, 'week1': w1, 'classes': lop, 'probs': probs, 'names': names, 'req': req}


def plan(pct=100, d=None, post=None):
    d = d or data()
    busy = {i: [] for i in range(7)}
    nweeks = len({w for c in d['classes'] for w in c['tuan']}) or 1
    if post is not None:   # đang trong kỳ thực tập hè -> tuần mẫu né luôn giờ làm
        today = dt.datetime.now(TZ).date()
        for it in extra(post).get('intern', []):
            if it['from'] <= today <= it['to']:
                for days, a, b in it['slots']:
                    for dd in days: busy[dd].append((a, b))
    for c in d['classes']:   # tuần MẪU: chỉ né lớp học >= nửa số tuần (lớp thí nghiệm vài tuần không chặn cả kỳ); .ics tự bỏ khối trùng từng tuần
        if len(c['tuan']) * 2 >= nweeks: busy[THU[c['thu']]].append((_m(c['bat_dau']), _m(c['ket_thuc'])))
    free = {i: [] for i in range(7)}   # các khối 60 phút còn trống
    for day in range(7):
        for a, b in WINDOWS:
            s = _m(a)
            while s + 60 <= _m(b):
                if not any(s < e and s + 60 > st for st, e in busy[day]): free[day].append(s)
                s += 60
    need = {code: max(1, round(r['hours'] * pct / 100)) for code, r in d['req'].items()}
    used = {i: 0 for i in range(7)}; out = []; left = dict(need); days_of = {c: set() for c in need}
    order = sorted(need, key=lambda c: -need[c])
    progress = True
    while any(left.values()) and progress:   # mỗi vòng: mỗi môn còn thiếu nhận 1 giờ vào ngày ít việc nhất, ưu tiên ngày môn đó chưa có -> rải đều
        progress = False
        for code in order:
            if not left[code]: continue
            ok = [dd for dd in range(7) if free[dd] and used[dd] < DAY_CAP_H[dd]]
            if not ok: continue
            dd = min(ok, key=lambda x: (x in days_of[code], used[x], x))
            s = free[dd].pop(0); used[dd] += 1; left[code] -= 1; days_of[code].add(dd); progress = True
            out.append({'code': code, 'name': d['names'].get(code, code), 'day': dd, 'thu': THU_NAME[dd], 'start': _hm(s), 'end': _hm(s + 60)})
    out.sort(key=lambda o: (o['day'], o['start']))
    summary = [{'code': c, 'name': d['req'][c]['name'], 'info': d['req'][c]['info'], 'yeu_cau_h': d['req'][c]['hours'],
                'muc_tieu_h': need[c], 'da_xep_h': need[c] - left[c]} for c in order]
    week = []
    notes = []
    if post is not None and d['week1']:
        x = extra(post); notes = x.get('notes', []); mon = dt.datetime.now(TZ).date(); mon -= dt.timedelta(days=mon.weekday())
        taken = {}
        for g in x['going']: taken.setdefault(g['day'], []).append((g['start'], g['end'], g['title']))
        for bl in out:
            day = mon + dt.timedelta(days=bl['day'])
            why = 'nghỉ (Rest)' if day in x['rest'] else next((t for st, e, t in taken.get(day, []) if _m(bl['start']) < e and _m(bl['end']) > st), None)
            if why: week.append({'ngay': f'{day:%d/%m}', 'thu': bl['thu'], 'start': bl['start'], 'name': bl['name'], 'vi': why})
    return {'sem': d['sem'], 'pct': pct, 'blocks': out, 'summary': summary, 'thieu_cho': {c: v for c, v in left.items() if v}, 'tuan_nay_bo': week, 'ghi_chu': notes,
            'probs': d['probs']}


def extra(post=None):
    """(14/10) Ngoài lịch học, UC còn biết:
      • 💤 Rest (tab Hôm nay, bảng 🌗 Chế độ ngày) -> ngày đó KHÔNG xếp tự học.
      • Hoạt động bạn đã bấm "Sẽ đi" (school/events.json, mỗi chặng có ngày + giờ bắt đầu) -> bỏ khối tự học trùng giờ, và đưa vào .ics.
        Chỉ có giờ bắt đầu -> coi như 2 tiếng; không có giờ -> cả ngày (07:00–22:00); "00:00"/"23:59" là hạn chót, không phải giờ diễn ra -> bỏ qua.
      • 💼 Thực tập hè (☀️ Summer Planning, Choice = Internship): giờ "Work Hours" trong đúng khoảng hè đó = giờ bận (+ đưa vào .ics).
    Làm thêm khác: chủ dự án đã rào -> không có nguồn riêng."""
    rest, going = set(), []
    if post:
        try:
            import daymode, academic
            today = dt.datetime.now(TZ).date()
            for k, v in daymode.get_modes(academic.Notion(post), today - dt.timedelta(days=7), today + dt.timedelta(days=150)).items():
                if v.get('mode') == 'Rest': rest.add(dt.date.fromisoformat(k))
        except Exception as e: print('study_plan: không đọc được chế độ ngày:', e)
    try:
        import uc_state
        ev = uc_state.load_json(HERE / 'school' / 'events.json', {'events': {}})['events']
    except Exception: ev = {}
    for e in ev.values():
        for k, ch in (e.get('chang') or {}).items():
            if ((e.get('ack') or {}).get(k) or {}).get('choice') != 'Sẽ đi' or ch.get('huy') or not ch.get('ngay'): continue
            try: day = dt.date.fromisoformat(ch['ngay'][:10])
            except ValueError: continue
            m = re.match(r'(\d{1,2})[:hH](\d{2})', str(ch.get('gio') or ''))
            if m and (m.group(1), m.group(2)) in (('00', '00'), ('23', '59')): continue
            a, b = ((int(m.group(1)) * 60 + int(m.group(2)), int(m.group(1)) * 60 + int(m.group(2)) + 120) if m else (_m('07:00'), _m('22:00')))
            going.append({'day': day, 'start': a, 'end': min(b, 24 * 60 - 1), 'title': f"{e.get('ten', '')} · {ch.get('ten', '')}", 'where': ch.get('dia_diem') or ''})
    notes, intern = [], []
    if post:   # 💼 thực tập hè (☀️ Summer Planning): mỗi ca làm trong khoảng hè = giờ bận, cũng đưa vào .ics
        try:
            for it in _internships(post):
                intern.append(it)
                if it['note']: notes.append(it['note'])
                day = it['from']
                while day <= it['to']:
                    for days, a, b in it['slots']:
                        if day.weekday() in days: going.append({'day': day, 'start': a, 'end': b, 'title': it['title'], 'where': '', 'kind': 'intern'})
                    day += dt.timedelta(days=1)
        except Exception as e: print('study_plan: không đọc được thực tập hè:', e)
    return {'rest': rest, 'going': going, 'intern': intern, 'notes': notes}


def parse_work_hours(text):
    """(14/10) Cột "Work Hours" (☀️ Summer Planning, chữ tự do) -> [(tập thứ 0..6, phút bắt đầu, phút kết thúc)].
    Hiểu: "T2-T6 8:00-17:00", "T2,T4,T6 13h-17h30", "thứ 2 - thứ 6, 8h30-12h", "CN 8-12"; nhiều đoạn cách nhau bằng ; hoặc xuống dòng.
    Trả ([], lý do) nếu không đọc được."""
    out = []
    for seg in re.split(r'[;\n]+', str(text or '')):
        s = seg.lower().replace('thứ', 't').replace('–', '-').replace('—', '-')
        tm = re.search(r'(\d{1,2})(?:[:h](\d{2})?)?\s*(?:h)?\s*-\s*(\d{1,2})(?:[:h](\d{2})?)?', s)
        if not tm: continue
        a = int(tm.group(1)) * 60 + int(tm.group(2) or 0); b = int(tm.group(3)) * 60 + int(tm.group(4) or 0)
        dpart = s[:tm.start()] + ' ' + s[tm.end():]
        days = set()
        for m in re.finditer(r't\s*([2-8])\s*-\s*t?\s*([2-8])|t\s*([2-8])|\bcn\b|chủ nhật', dpart):
            if m.group(1): days |= set(range(int(m.group(1)) - 2, int(m.group(2)) - 1))
            elif m.group(3): days.add(int(m.group(3)) - 2)
            else: days.add(6)
        if not days: days = set(range(5))   # chỉ ghi giờ -> coi như T2–T6
        if b > a: out.append((days, a, b))
    return out


def _internships(post):
    """Thực tập hè (☀️ Summer Planning, Choice = Internship, chưa xong) -> [{'from','to','slots','title','note'}] theo đúng khoảng hè."""
    import academic, program, semester
    nt = academic.Notion(post); c = semester.cal(); res = []
    for r in nt.query(program.SUMMER):
        if academic.P(r, 'Choice') != 'Internship' or academic.P(r, 'Status') == 'Done': continue
        m = re.match(r'Hè sau S(\d)', academic.P(r, 'Plan') or '')
        if not m: continue
        y = int(c.get('first_year', 2026)) + int(m.group(1)) // 2
        start = semester._d(y, c['summer_start'], c, 'summer_start'); end = semester._d(y, c['odd_start'], c, 'odd_start') - dt.timedelta(days=1)
        wh = academic.P(r, 'Work Hours') or ''
        slots = parse_work_hours(wh); note = ''
        if not slots: slots = [(set(range(5)), _m('08:00'), _m('17:00'))]; note = f'không đọc được giờ thực tập “{wh[:40]}” -> tạm coi T2–T6 08:00–17:00'
        res.append({'from': start, 'to': end, 'slots': slots, 'title': 'Thực tập: ' + (academic.P(r, 'Company') or '') + (' · ' + academic.P(r, 'Position') if academic.P(r, 'Position') else ''), 'note': note})
    return res


def _sessions(d):
    """Mọi buổi học cụ thể theo ngày (tuần học × thứ)."""
    for c in d['classes']:
        for w in c['tuan']:
            day = d['week1'] + dt.timedelta(days=(w - 1) * 7 + THU[c['thu']])
            yield day, c


def ics(pct=100, post=None):
    d = data(); p = plan(pct, d); x = extra(post)
    if not d['week1']: raise ValueError('chưa có mốc tuần 1 của năm học')
    weeks = sorted({w for c in d['classes'] for w in c['tuan']})
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    def ev(uid, day, a, b, title, where='', note=''):
        s = dt.datetime.combine(day, dt.time(*map(int, a.split(':'))), TZ).astimezone(dt.timezone.utc)
        e = dt.datetime.combine(day, dt.time(*map(int, b.split(':'))), TZ).astimezone(dt.timezone.utc)
        esc = lambda x: x.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')
        return ['BEGIN:VEVENT', f'UID:{uid}@uc', f'DTSTAMP:{stamp}', f'DTSTART:{s:%Y%m%dT%H%M%SZ}', f'DTEND:{e:%Y%m%dT%H%M%SZ}',
                f'SUMMARY:{esc(title)}'] + ([f'LOCATION:{esc(where)}'] if where else []) + ([f'DESCRIPTION:{esc(note)}'] if note else []) + ['END:VEVENT']
    L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//University Copilot//study_plan//VI', 'CALSCALE:GREGORIAN',
         f'X-WR-CALNAME:Học kỳ {d["sem"]} (UC)', 'X-WR-TIMEZONE:Asia/Ho_Chi_Minh']
    for i, (day, c) in enumerate(_sessions(d)):
        L += ev(f'class-{d["sem"]}-{c["mon"]}-{day:%Y%m%d}-{c["bat_dau"].replace(":", "")}-{i}', day, c['bat_dau'], c['ket_thuc'],
                f'{d["names"].get(c["mon"], c["mon"])} ({c["loai"]})', c.get('phong') or '', f'{c["mon"]} · {c.get("ghi_chu") or ""}')
    taken = {}
    for day, c in _sessions(d): taken.setdefault(day, []).append((_m(c['bat_dau']), _m(c['ket_thuc'])))
    for g in x['going']: taken.setdefault(g['day'], []).append((g['start'], g['end']))   # hoạt động "Sẽ đi" cũng chiếm giờ
    for w in range(min(weeks), max(weeks) + 1) if weeks else []:
        for b in p['blocks']:
            day = d['week1'] + dt.timedelta(days=(w - 1) * 7 + b['day'])
            if day in x['rest']: continue   # 💤 Rest (tab Hôm nay) -> không tự học ngày đó
            if any(_m(b['start']) < e and _m(b['end']) > st for st, e in taken.get(day, [])): continue   # trùng buổi học / hoạt động "Sẽ đi" của tuần đó -> bỏ khối
            L += ev(f'self-{d["sem"]}-{b["code"]}-{day:%Y%m%d}-{b["start"].replace(":", "")}', day, b['start'], b['end'],
                    f'Tự học: {b["name"]}', '', f'{b["code"]} · kế hoạch tự học UC ({pct}% yêu cầu)')
    for i, g in enumerate(x['going']):
        L += ev(f'going-{g["day"]:%Y%m%d}-{g["start"]}-{i}', g['day'], _hm(g['start']), _hm(g['end']),
                g['title'] if g.get('kind') == 'intern' else 'Hoạt động: ' + g['title'], g['where'],
                'Thực tập hè (☀️ Summer Planning)' if g.get('kind') == 'intern' else 'Bạn đã chọn "Sẽ đi" trong UC')
    L.append('END:VCALENDAR')
    return ('\r\n'.join(L) + '\r\n').encode('utf-8')


def _sheet(rows):
    """rows: list[list] -> XML trang tính (chuỗi inline, hàng đầu in đậm)."""
    def cell(ref, v, bold):
        st = ' s="1"' if bold else ''
        if isinstance(v, (int, float)) and not isinstance(v, bool): return f'<c r="{ref}"{st}><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{escape(str(v if v is not None else ""))}</t></is></c>'
    col = lambda i: (chr(65 + i) if i < 26 else chr(64 + i // 26) + chr(65 + i % 26))
    xs = ''.join(f'<row r="{r + 1}">' + ''.join(cell(f'{col(c)}{r + 1}', v, r == 0) for c, v in enumerate(row)) + '</row>' for r, row in enumerate(rows))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{xs}</sheetData></worksheet>')


def xlsx(pct=100):
    d = data(); p = plan(pct, d)
    s1 = [['Ngày', 'Thứ', 'Tuần', 'Bắt đầu', 'Kết thúc', 'Mã HP', 'Môn', 'Loại', 'Phòng', 'Ghi chú']]
    for day, c in sorted(_sessions(d), key=lambda x: (x[0], x[1]['bat_dau'])):
        s1.append([f'{day:%d/%m/%Y}', THU_NAME[day.weekday()], (day - d['week1']).days // 7 + 1, c['bat_dau'], c['ket_thuc'], c['mon'],
                   d['names'].get(c['mon'], c['mon']), c['loai'], c.get('phong') or '', c.get('ghi_chu') or ''])
    s2 = [['Thứ', 'Bắt đầu', 'Kết thúc', 'Mã HP', 'Tự học môn']] + [[b['thu'], b['start'], b['end'], b['code'], b['name']] for b in p['blocks']]
    s3 = [['Mã HP', 'Môn', 'Khối lượng', 'Yêu cầu tự học (giờ/tuần)', f'Mục tiêu ({pct}%)', 'Đã xếp (giờ/tuần)']] + \
         [[x['code'], x['name'], x['info'], x['yeu_cau_h'], x['muc_tieu_h'], x['da_xep_h']] for x in p['summary']]
    names = ['Lịch học', 'Tự học hằng tuần', 'Yêu cầu tự học']
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + ''.join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(3)) + '</Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + ''.join(f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names)) + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + ''.join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(3))
                   + '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
                   '<cellXfs count="2"><xf fontId="0"/><xf fontId="1" applyFont="1"/></cellXfs></styleSheet>')
        for i, rows in enumerate((s1, s2, s3)): z.writestr(f'xl/worksheets/sheet{i + 1}.xml', _sheet(rows))
    return buf.getvalue()


if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(plan(), ensure_ascii=False, indent=1)[:3000])
