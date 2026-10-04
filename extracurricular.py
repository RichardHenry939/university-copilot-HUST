# -*- coding: utf-8 -*-
"""🎯 Hoạt động ngoại khoá — tách hẳn khỏi lịch học / hạn học tập (Claude 2026-10-04).

Nguồn:
  • CTSV (ctsv.hust.edu.vn, đọc trong school_fetch.fetch_ctsv qua API của chính trang, chỉ đọc):
      hoạt động BẠN đã đăng ký (+ trạng thái Chờ xác nhận / Đã xác nhận…), hạn nộp minh chứng (MC, tính điểm rèn luyện),
      hoạt động đang mở, học bổng còn hạn.
  • Mail / Teams: sự kiện mail_events xếp nhóm "ngoai_khoa" (CLB, Đoàn/Hội, cuộc thi, tuyển đội, khai giảng, sinh hoạt…).
Ghi: school/extracurricular.json (cho tab "Ngoại khoá" của UC) + 🎯 Hoạt động ngoại khoá (Notion, khoá Sync Key).
Lịch học (🗓️ Academic Timetable) và 📋 Academic Work KHÔNG nhận mục ngoại khoá nữa.
Nhắc: hoạt động đã đăng ký có giờ cụ thể -> 24 giờ + 2 giờ trước; hạn nộp MC còn mở -> mốc như "Tự luyện cốt lõi"."""
import uc_config as cfg
import datetime as dt, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'extracurricular.json'
EXTRA_DB = cfg.notion("extracurricular")
TZ = dt.timezone(dt.timedelta(hours=7))
CTSV = 'https://ctsv.hust.edu.vn'
UA = {'1': 'Chờ xác nhận', '2': 'Đã xác nhận', '3': 'Không đạt', '-1': 'Không đạt'}


def _t(s):
    if not s: return None
    try: return dt.datetime.fromisoformat(s.replace(' ', 'T')).replace(tzinfo=TZ)
    except Exception: return None


def build(now=None):
    now = now or dt.datetime.now(TZ)
    try: snap = json.loads((HERE / 'school' / 'latest.json').read_text(encoding='utf-8')).get('ctsv') or {}
    except Exception: snap = {}
    if not snap.get('ok'):   # lượt đọc trường lỗi -> giữ danh sách CTSV lần trước
        try: snap = json.loads(OUT.read_text(encoding='utf-8')).get('ctsv_raw') or snap
        except Exception: pass
    items = []
    mine_ids = set()
    for a in snap.get('mine', []):
        mine_ids.add(str(a['id']))
        st, en, dl = _t(a['start']), _t(a['end']), _t(a['deadline'])
        status = a.get('status') or UA.get(str(a.get('ua')), 'Chờ xác nhận')
        items.append({'key': f"ctsv|mine|{a['id']}", 'name': a['name'], 'loai': 'Đã đăng ký', 'start': st and st.isoformat(),
                      'end': en and en.isoformat(), 'han': None, 'place': a.get('place') or '', 'org': a.get('org') or '', 'type': a.get('type') or '',
                      'status': status, 'src': 'CTSV', 'url': f"{CTSV}/hoat-dong/{a['id']}/chi-tiet", 'note': a.get('note') or ''})
        # còn mở + chưa được xác nhận -> hạn nộp minh chứng (điểm rèn luyện)
        if dl and dl > now and status != 'Đã xác nhận':
            items.append({'key': f"ctsv|mc|{a['id']}", 'name': a['name'], 'loai': 'Hạn nộp minh chứng', 'start': None, 'end': None,
                          'han': dl.isoformat(), 'place': a.get('place') or '', 'org': a.get('org') or '', 'type': a.get('type') or '',
                          'status': status, 'src': 'CTSV', 'url': f"{CTSV}/hoat-dong/{a['id']}/chi-tiet", 'note': 'Nộp minh chứng trên CTSV để được tính điểm rèn luyện'})
    for a in snap.get('open', []):
        en = _t(a['end'])
        if str(a['id']) in mine_ids or not en or en < now: continue
        st = _t(a['start'])
        items.append({'key': f"ctsv|open|{a['id']}", 'name': a['name'], 'loai': 'Đang mở', 'start': st and st.isoformat(), 'end': en.isoformat(),
                      'han': _t(a['deadline']) and _t(a['deadline']).isoformat(), 'place': a.get('place') or '', 'org': a.get('org') or '',
                      'type': a.get('type') or '', 'status': 'Chưa đăng ký', 'src': 'CTSV', 'url': f"{CTSV}/hoat-dong/{a['id']}/chi-tiet", 'note': ''})
    for s in snap.get('scholarships', []):
        dl = _t(s['deadline'])
        if str(s.get('expired')) == '1' or not dl or dl < now: continue
        items.append({'key': f"ctsv|sch|{s['id']}", 'name': s['name'], 'loai': 'Học bổng', 'start': None, 'end': None, 'han': dl.isoformat(),
                      'place': '', 'org': s.get('type') or '', 'type': 'Học bổng', 'status': 'Đã nộp hồ sơ' if str(s.get('applied')) not in ('0', '') else 'Chưa đăng ký',
                      'src': 'CTSV', 'url': f"{CTSV}/hoc-bong/{s['id']}/chi-tiet", 'note': f"{s.get('quantity') or '?'} suất"})
    # khoá MOOC không phải học phần (vd Sinh hoạt công dân) -> đang học + bài kiểm tra còn chưa làm
    try:
        mo = json.loads((HERE / 'school' / 'mooc.json').read_text(encoding='utf-8'))
        for cid, c in mo.get('courses', {}).items():
            if re.search(r'\+[A-Z]{2,4}\d{4}\+', cid): continue
            todo = [i for i in c['items'] if not (i.get('earned') or 0)]
            st = _t((c.get('start') or '').replace('Z', '').replace('T', ' ')[:19])
            items.append({'key': f"mooc|{cid}", 'name': c['name'], 'loai': 'Đã đăng ký', 'start': st and st.isoformat(),
                          'end': None, 'han': None, 'place': 'MOOC soict.daotao.ai', 'org': 'SoICT', 'type': 'Khoá học MOOC',
                          'status': 'Đang học', 'src': 'CTSV', 'url': f"https://soict.daotao.ai/courses/{cid}/course/",
                          'note': ('Chưa làm: ' + ', '.join(i['name'] for i in todo)) if todo else 'Đã làm đủ bài tính điểm'})
    except FileNotFoundError: pass
    # sự kiện ngoại khoá từ mail / Teams
    import mail_events as me
    for eid, e in me.load()['events'].items():
        if e.get('nhom') != 'ngoai_khoa': continue
        src = 'Teams' if any((m.get('nguon') or '').startswith('Teams') for m in e['mails']) else 'Mail'
        for k, s in e['chang'].items():
            w = me.when_of(s)
            if not w: continue
            dl = s.get('loai_chang') == 'han_nop' or re.search(r'hạn|deadline', s['ten'], re.I)
            items.append({'key': f"mail|{eid}|{k}", 'name': f"{e['ten']} · {s['ten']}", 'loai': 'Sự kiện (mail/Teams)',
                          'start': None if dl else w.isoformat(), 'end': None, 'han': w.isoformat() if dl else None,
                          'place': s.get('dia_diem') or '', 'org': e.get('sender') or '', 'type': 'Hạn' if dl else 'Sự kiện',
                          'status': 'Quan tâm' if not e.get('must') else 'Đã đăng ký', 'src': src, 'url': None, 'note': s.get('ghi_chu') or '',
                          'eid': eid, 'must': bool(e.get('must'))})
    items.sort(key=lambda x: x.get('start') or x.get('han') or '')
    data = {'at': now.isoformat(timespec='minutes'), 'items': items, 'ctsv_at': (json.loads((HERE / 'school' / 'latest.json').read_text(encoding='utf-8')).get('at')
                                                                             if (HERE / 'school' / 'latest.json').exists() else None), 'ctsv_raw': snap}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return data


def load():
    try: return json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return build()


def sync_notion(post, data=None):
    """Đồng bộ danh sách -> 🎯 Hoạt động ngoại khoá (thêm / sửa theo Sync Key; không xoá dòng cũ)."""
    from academic import Notion, rt, title, P
    data = data or load()
    nt = Notion(post)
    have = {P(r, 'Sync Key'): r for r in nt.query(EXTRA_DB)}
    n_new = n_upd = 0
    for x in data['items']:
        props = {'Hoạt động': title(x['name']), 'Loại': {'select': {'name': x['loai']}},
                 'Bắt đầu': {'date': {'start': x['start']}} if x.get('start') else {'date': None},
                 'Kết thúc': {'date': {'start': x['end']}} if x.get('end') else {'date': None},
                 'Hạn': {'date': {'start': x['han']}} if x.get('han') else {'date': None},
                 'Địa điểm': rt(x['place']), 'Đơn vị': rt(x['org']), 'Hình thức': rt(x['type']),
                 'Trạng thái của tôi': {'select': {'name': x['status']}} if x.get('status') else {'select': None},
                 'Nguồn': {'select': {'name': x['src']}}, 'Link': {'url': x.get('url')}, 'Ghi chú': rt(x.get('note') or ''), 'Sync Key': rt(x['key'])}
        r = have.get(x['key'])
        if not r: nt.create(EXTRA_DB, props); n_new += 1; continue
        cur = (P(r, 'Hoạt động'), P(r, 'Trạng thái của tôi'), (r['properties']['Bắt đầu']['date'] or {}).get('start', '')[:16],
               (r['properties']['Hạn']['date'] or {}).get('start', '')[:16], P(r, 'Địa điểm'))
        new = (x['name'], x.get('status'), (x.get('start') or '')[:16], (x.get('han') or '')[:16], x['place'])
        if cur != new: nt.patch(r['id'], props); n_upd += 1
    return {'new': n_new, 'updated': n_upd, 'total': len(data['items'])}


def alert_items(data, now):
    """Mục ngoại khoá cần nhắc: hoạt động đã đăng ký có giờ cụ thể (≤1 ngày) sắp diễn ra; hạn nộp MC còn mở."""
    out = []
    for x in data.get('items', []):
        if x['loai'] == 'Đã đăng ký' and x.get('start') and x.get('end'):
            st, en = dt.datetime.fromisoformat(x['start']), dt.datetime.fromisoformat(x['end'])
            if (en - st) <= dt.timedelta(days=1) and st > now and x['status'] != 'Không đạt':
                out.append({**x, 'when': x['start'], 'marks': (1440, 120)})
        elif x['loai'] == 'Hạn nộp minh chứng' and x.get('han'):
            out.append({**x, 'when': x['han'], 'marks': (72 * 60, 48 * 60, 36 * 60, 24 * 60, 420, 300, 180, 60, 30, 20, 10)})
    return out
