# -*- coding: utf-8 -*-
"""FAMI số hoá (fami.hust.edu.vn/sohoa) → UC (Claude 2026-10-04). CHỈ ĐỌC — không bao giờ bấm thi / nộp.

Mọi học phần mã MI (Toán cao cấp…) có "thi theo chương": mỗi chủ đề (CĐ 1…n) là một bài kiểm tra ngắn (10 phút, 5 câu, ≤1 điểm)
chỉ mở trong một khoảng ngày — KHÔNG được nhắc trên Teams / MOOC → trước đây là bài tập ngầm.
Đăng nhập: nút "Đăng nhập bằng Microsoft Teams" → phiên Microsoft của hồ sơ Chrome đồng bộ (bộ tự đăng nhập school_fetch).
Đọc (API của chính trang, Bearer lấy từ yêu cầu của trang):
  /api/student-lop-list                     lớp MI đang học
  /api/sinh-vien/hoc-phan-chuong/<lop>      chủ đề: tên, tuần mở/đóng, ngày mở/đóng thi, đã có điểm, điểm
  /api/lop/<lop>/sinh-vien-diem              điểm chuyên cần / LT / QT / CK / HP
  /api/student-diem-danh-list/<lop>          điểm danh
Ra: school/fami.json — fami.sync() áp vào 📋 Academic Work / ✅ Academic Tasks như MOOC (luật tối cao)."""
import datetime as dt, json, re, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'fami.json'
BASE = 'https://fami.hust.edu.vn/sohoa'
TZ = dt.timezone(dt.timedelta(hours=7))


def _get(path, tok, method='GET', body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': tok, 'Accept': 'application/json', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode('utf-8'))


def fetch():
    import school_fetch as f
    from school_mail import ChromeLock
    from playwright.sync_api import sync_playwright
    tok = {}
    with ChromeLock(), sync_playwright() as p:
        ctx = f._launch(p, True)
        ctx.on('request', lambda rq: tok.setdefault('v', rq.headers.get('authorization')) if '/sohoa/api/' in rq.url and rq.headers.get('authorization', '').startswith('Bearer ') else None)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(BASE + '/phong-hoc', wait_until='commit', timeout=90000); page.wait_for_timeout(8000)
            if '/login' in page.url:
                page.get_by_text(re.compile('Đăng nhập bằng Microsoft', re.I)).first.click(); page.wait_for_timeout(5000)
                f._through_sso(page, 'fami.hust.edu.vn/sohoa', deadline=120); page.wait_for_timeout(8000)
            if not tok.get('v'):   # trang chưa gọi API nào có token -> mở lại danh sách lớp
                page.goto(BASE + '/phong-hoc', wait_until='commit', timeout=60000); page.wait_for_timeout(6000)
        finally:
            try: ctx.close()
            except Exception: pass
    t = tok.get('v')
    if not t: return {'ok': False, 'error': 'chưa lấy được phiên FAMI'}
    lops = _get('/api/student-lop-list', t, 'POST', {'page': 1, 'per_page': 50}).get('list', [])
    out = {'ok': True, 'at': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'lops': []}
    for l in lops:
        ch = _get(f"/api/sinh-vien/hoc-phan-chuong/{l['id']}", t)
        diem = _get(f"/api/lop/{l['id']}/sinh-vien-diem", t)
        dd = _get(f"/api/student-diem-danh-list/{l['id']}", t)
        out['lops'].append({'id': l['id'], 'ma': l['ma'], 'ma_hp': l['ma_hp'], 'ten_hp': l['ten_hp'], 'ki_hoc': l['ki_hoc'], 'loai_thi': l.get('loai_thi'),
                            'chuongs': ch.get('chuongs', []), 'diems': ch.get('diems', []), 'diem_lop': diem, 'diem_danh': dd})
    try: old = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: old = {}
    out['missed_notified'] = old.get('missed_notified', [])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True, 'lops': len(out['lops']), 'chuongs': sum(len(x['chuongs']) for x in out['lops'])}


def items(now=None):
    """-> danh sách bài thi theo chương: {code, stt, name, open, due, done, score, can_exam, mins, n_q, url}.
    "đến trước ngày 05/10" -> hạn 23:59 ngày 04/10."""
    try: d = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return []
    out = []
    for l in d.get('lops', []):
        scores = {x.get('chuong_id') or x.get('hoc_phan_chuong_id'): x for x in (l.get('diems') or []) if isinstance(x, dict)}
        for c in l['chuongs']:
            ex = c.get('extra') or {}
            if not ex.get('ngay_dong_thi'): continue
            close = dt.datetime.strptime(ex['ngay_dong_thi'], '%d/%m/%Y').replace(tzinfo=TZ)
            opn = dt.datetime.strptime(ex['ngay_mo_thi'], '%d/%m/%Y').replace(tzinfo=TZ) if ex.get('ngay_mo_thi') else None
            sc = scores.get(c['id'])
            out.append({'code': l['ma_hp'], 'stt': c['stt'], 'name': f"{l['ma_hp']} CĐ{c['stt']} — {c['ten']} (FAMI)", 'topic': c['ten'],
                        'open': opn, 'due': close - dt.timedelta(minutes=1), 'done': bool(ex.get('da_co_diem')), 'score': sc,
                        'can_exam': bool(ex.get('can_exam')), 'mins': c.get('thoi_gian_thi'), 'n_q': c.get('so_cau_hoi'), 'max': c.get('diem_toi_da'),
                        'url': f"{BASE}/phong-hoc/kiem-tra/{l['id']}"})
    return out


def sync(post):
    """LUẬT TỐI CAO như MOOC: bài còn hạn -> 📋 Academic Work (Môn học, thêm / sửa hạn) · có điểm -> Hoàn tất ·
    hết hạn -> KHÔNG ghi thành hạn (expired.py ghi vào ✅ Academic Tasks)."""
    import deadlines as D
    from academic import Notion, title
    nt = Notion(post)
    rows = D._fetch(post)
    courses = {c['code']: c['id'] for c in nt.courses()}
    now = dt.datetime.now(TZ); out = {'added': [], 'fixed': [], 'done': []}
    for it in items(now):
        tag = f"{it['code']} CĐ{it['stt']} "
        x = next((r for r in rows if r['name'].startswith(tag)), None)
        if x:
            if abs((dt.datetime.fromisoformat(x['due']) - it['due']).total_seconds()) > 60 and it['due'] >= now:
                D.fix_due(post, x['id'], x['name'], x['due'], it['due'].isoformat(), 'FAMI số hoá'); out['fixed'].append(x['name'])
            if it['done'] and x['status'] not in D.DONE:
                nt.patch(x['id'], {'Status': {'status': {'name': 'Submitted'}}}); out['done'].append(x['name'])
            continue
        if it['due'] < now or it['done']: continue   # hết hạn / đã làm: không tạo hạn mới
        if it['open'] and it['open'] > now + dt.timedelta(days=7): continue   # chưa mở: thêm khi còn ≤ 7 ngày nữa mở (tránh A3 chia việc quá sớm)
        props = {'Name': title(it['name']), 'Entry Kind': {'select': {'name': 'Deadline'}}, 'Loại hạn': {'select': {'name': 'Môn học'}},
                 'Due': {'date': {'start': it['due'].isoformat()}}, 'Status': {'status': {'name': 'Not started'}},
                 'Type': {'select': {'name': 'Quiz'}}, 'Workload Status': {'select': {'name': 'Needs review'}},
                 'Submission/Repo': {'url': it['url']},
                 'Location': {'rich_text': [{'type': 'text', 'text': {'content':
                     f"FAMI số hoá · mở {it['open']:%d/%m} · {it['mins']} phút · {it['n_q']} câu · tối đa {it['max']} điểm (điểm quá trình)"}}]}}
        if courses.get(it['code']): props['Course'] = {'relation': [{'id': courses[it['code']]}]}
        nt.create(D.WORK, props); out['added'].append(it['name'])
    if out['added'] or out['fixed'] or out['done']: D.refresh(post)
    return {'ok': True, **out}


if __name__ == '__main__':
    print(json.dumps(fetch(), ensure_ascii=False))
