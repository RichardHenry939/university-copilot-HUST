# -*- coding: utf-8 -*-
"""(v1.00.41) Lịch đè từ Teams: thông báo đổi buổi/phòng/giờ của lớp đứng TRƯỚC eHUST và qldt.

Nguồn: school/events.json, mục kind 'lop' (lịch lớp) có `chang` (các buổi đã đổi) và `changes` (dòng mô tả trước → nay).
Với mỗi buổi đổi (chưa huỷ), UC: bỏ các mục lịch cùng môn ở NGÀY CŨ (nếu đọc được), rồi thêm buổi ở NGÀY/GIỜ MỚI.
Không bịa: không đọc được ngày cũ thì chỉ thêm buổi mới, không xoá gì. Chỉ áp cho buổi từ 14 ngày trước trở đi.
"""
import datetime as dt, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVENTS = HERE / 'school' / 'events.json'
TZ = dt.timezone(dt.timedelta(hours=7))
DEFAULT_MIN = 90
LOOKBACK_DAYS = 14


def _load_events():
    try: return json.loads(EVENTS.read_text(encoding='utf-8')).get('events') or {}
    except Exception: return {}


def _code(ten):
    m = re.search(r'Lịch lớp\s+([A-Z]{2,4}\d{4}[A-Z]?)', ten or '')
    return m.group(1) if m else None


def _old_date(lines, label, year):
    """Tìm dòng mô tả của buổi `label` (vd 'Buổi học 7') có dạng 'ngày A/B → C/D'; trả về ngày cũ 'YYYY-MM-DD' hoặc None."""
    for ln in lines or []:
        if label.lower() not in ln.lower(): continue
        m = re.search(r'ngày\s*(\d{1,2})/(\d{1,2})\s*→', ln)
        if m: return f"{year}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def _duration(lines, default=DEFAULT_MIN):
    """Giờ kết thúc từ dòng 'Thời gian: HH:MM - HH:MM' sau mũi tên 'Nay' (nếu có)."""
    for ln in reversed(lines or []):
        m = re.search(r'Nay:?.*?(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2})', ln)
        if m:
            a = int(m.group(1)) * 60 + int(m.group(2)); b = int(m.group(3)) * 60 + int(m.group(4))
            if b > a: return b - a
    return default


def overrides(now=None, events=None):
    """Danh sách buổi đè: [{code, label, ten, date_old, start, end, location, notes}]."""
    now = now or dt.datetime.now(TZ)
    events = events if events is not None else _load_events()
    cutoff = (now - dt.timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    out = []
    for key, e in events.items():
        if e.get('kind') != 'lop': continue
        code = _code(e.get('ten'))
        if not code: continue
        lines = []
        for ln_rec in (e.get('changes') or []):
            lines += ln_rec.get('lines') or []
        cname = re.sub(r'^Lịch lớp\s+\S+\s*', '', e.get('ten') or '').strip() or code
        for ck, s in (e.get('chang') or {}).items():
            if s.get('huy') or not s.get('ngay') or not s.get('gio'): continue
            if s['ngay'] < cutoff: continue
            label = s.get('ten') or ck
            year = s['ngay'][:4]
            old = _old_date(lines, label, year)
            start = dt.datetime.fromisoformat(f"{s['ngay']}T{s['gio']}:00").replace(tzinfo=TZ)
            end = start + dt.timedelta(minutes=_duration(lines))
            out.append({'code': code, 'name': cname, 'label': label, 'date_old': old, 'start': start, 'end': end,
                        'location': s.get('dia_diem') or '', 'notes': s.get('ghi_chu') or ''})
    return out


def apply(cal_events, now=None, events=None):
    """Áp lịch đè lên danh sách sự kiện lịch (định dạng của timetable.get). Trả về danh sách mới."""
    ovs = overrides(now, events)
    if not ovs: return cal_events
    removed = set()
    res = [dict(e) for e in cal_events]   # sao chép: không sửa bộ đệm lịch dùng chung
    for o in ovs:
        if o['date_old']:
            for i, ev in enumerate(res):
                if i in removed or ev.get('kind') in ('Exam', 'Deadline'): continue
                if f"{o['code']} ·" not in (ev.get('title') or ''): continue
                if (ev.get('start') or '')[:10] == o['date_old']: removed.add(i)
    kept = [ev for i, ev in enumerate(res) if i not in removed]
    for o in ovs:
        new_start = o['start'].isoformat(timespec='milliseconds')
        same = [ev for ev in kept if ev.get('start') == new_start and f"{o['code']} ·" in (ev.get('title') or '')]
        if same:   # buổi đã có đúng giờ: chỉ cập nhật phòng/ghi chú theo Teams (vd đổi B1-103 -> B1-504)
            for ev in same:
                ev['location'] = o['location'] or ev.get('location')
                ev['notes'] = 'Đổi theo Teams' + (f" · {o['notes']}" if o['notes'] else '')
                ev['source'] = 'teams'
            continue
        kept.append({'kind': 'Class', 'title': f"{o['code']} · {o['name']} · Teams đổi lịch",
                     'start': new_start, 'end': o['end'].isoformat(timespec='milliseconds'),
                     'location': o['location'], 'notes': ('Đổi theo Teams' + (f" · {o['notes']}" if o['notes'] else '')),
                     'source': 'teams'})
    return kept
