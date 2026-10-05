# -*- coding: utf-8 -*-
"""Dời hạn TỰ ĐẶT qua chat UC (Claude 2026-10-05) — công cụ doi_han của não Copilot.

Chỉ dời được hạn "Tự luyện" / "Tự luyện cốt lõi" (bạn tự đặt). Hạn "Môn học" và mọi hạn lấy từ hệ thống của trường
(Teams / MOOC / FAMI / mail) KHÔNG BAO GIỜ dời được — luật tối cao: trường thắng, bộ đồng bộ sẽ sửa lại ngay.
Hai bước như nhap_tkb: buoc=xem_truoc (chỉ đọc, trả về kế hoạch) -> sinh viên đồng ý -> buoc=ghi.
Ghi: 📋 Academic Work (Due) + dòng lịch của hạn (deadline|id) + việc con chưa xong có hạn ≤ hạn mới -> hạn mới,
rồi chạy lại A4 để kế hoạch hôm nay xếp lại. Trả về ĐÚNG những gì đã ghi để chat đọc lại cho bạn."""
import uc_config as cfg
import datetime as dt, re

TZ = dt.timezone(dt.timedelta(hours=7))
WORK = cfg.notion("academic_work")
EVENTS = cfg.notion("calendar_events")
TASKS = cfg.notion("academic_tasks")
MOVABLE = {'Tự luyện', 'Tự luyện cốt lõi'}
SCHOOL_URL = re.compile(r'daotao\.ai|fami\.hust|teams\.(microsoft|cloud)|hust\.edu\.vn', re.I)
SCHOOL_NAME = re.compile(r'\((FAMI|MOOC)\)\s*$')


def _when(s):
    """'2026-10-05T19:00' / '2026-10-05 19:00' / '2026-10-05' -> datetime +07:00 (ngày trơn = 23:59)."""
    s = (s or '').strip().replace(' ', 'T')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s): s += 'T23:59'
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=TZ)


def _fmt(d): return f'{d:%H:%M} {d.day}/{d.month}'


def run(post, args, kick_a4=None):
    from academic import Notion, P
    nt = Notion(post)
    buoc = (args.get('buoc') or 'xem_truoc').strip()
    ids = [x for x in re.split(r'[\s,;]+', str(args.get('work_ids') or '')) if x]
    if not ids: return {'ok': False, 'thieu': 'work_ids (lấy [work_id …] trong ngữ cảnh, mục HẠN CHƯA NỘP)'}
    try: new = _when(args.get('han_moi'))
    except Exception: return {'ok': False, 'thieu': 'han_moi dạng YYYY-MM-DDTHH:MM (vd 2026-10-05T21:00)'}
    now = dt.datetime.now(TZ)
    if new <= now: return {'ok': False, 'tu_choi': f'Hạn mới {_fmt(new)} đã qua — chọn một mốc trong tương lai.'}
    plan, refused = [], []
    rows = {r['id'].replace('-', ''): r for r in nt.query(WORK, {'property': 'Entry Kind', 'select': {'equals': 'Deadline'}})}
    for wid in ids:
        r = rows.get(wid.replace('-', ''))
        if not r:
            refused.append({'work_id': wid, 'ly_do': 'không thấy hạn này trong 📋 Academic Work'}); continue
        wid = r['id']
        name, kind = P(r, 'Name') or '?', P(r, 'Loại hạn') or ''
        url = ((r['properties'].get('Submission/Repo') or {}).get('url')) or ''
        old_s = ((r['properties'].get('Due') or {}).get('date') or {}).get('start')
        if kind not in MOVABLE or SCHOOL_URL.search(url) or SCHOOL_NAME.search(name):
            refused.append({'ten': name, 'ly_do': f'hạn "{kind or "chưa phân loại"}" của trường/môn học — không dời được (luật tối cao: trường thắng)'}); continue
        if not old_s:
            refused.append({'ten': name, 'ly_do': 'hạn chưa có ngày'}); continue
        old = _when(old_s[:16])
        kids = [t for t in nt.query(TASKS, {'property': 'Academic Work', 'relation': {'contains': wid}})
                if P(t, 'Status') != 'Done' and (((t['properties'].get('Due') or {}).get('date') or {}).get('start') or '')[:16] <= new.isoformat()[:16]]
        cal = nt.query(EVENTS, {'property': 'Sync Key', 'rich_text': {'equals': f'deadline|{wid}'}})
        plan.append({'work_id': wid, 'ten': name, 'loai': kind, 'cu': old, 'kids': kids, 'cal': cal})
    out = {'ok': True, 'buoc': buoc, 'han_moi': _fmt(new),
           'se_doi' if buoc != 'ghi' else 'da_doi': [f"{p['ten']} ({p['loai']}): {_fmt(p['cu'])} → {_fmt(new)} · kèm {len(p['kids'])} việc con, {len(p['cal'])} dòng lịch" for p in plan],
           'tu_choi': [f"{x.get('ten') or x.get('work_id')}: {x['ly_do']}" for x in refused]}
    if buoc != 'ghi':
        out['nhac'] = 'CHƯA ghi gì. Đọc danh sách này cho sinh viên; chỉ khi họ đồng ý mới gọi lại buoc=ghi với cùng work_ids và han_moi.'
        return out
    iso = new.isoformat(timespec='minutes')
    n_task = n_cal = 0
    for p in plan:
        nt.patch(p['work_id'], {'Due': {'date': {'start': iso}}})
        for c in p['cal']: nt.patch(c['id'], {'When': {'date': {'start': iso}}}); n_cal += 1
        for t in p['kids']: nt.patch(t['id'], {'Due': {'date': {'start': iso}}}); n_task += 1
    out['tong'] = f'Đã dời {len(plan)} hạn, {n_task} việc con, {n_cal} dòng lịch sang {_fmt(new)}.'
    if plan and kick_a4:
        try: kick_a4(); out['a4'] = 'đã chạy lại A4 — kế hoạch hôm nay được xếp lại'
        except Exception as e: out['a4'] = f'chưa chạy lại được A4 ({type(e).__name__}) — sẽ tự chạy ở lượt 30 phút tới'
    return out
