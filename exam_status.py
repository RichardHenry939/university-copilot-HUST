# -*- coding: utf-8 -*-
"""(v1.00.34) Trạng thái thi giữa kỳ cho TỪNG môn đang học — không môn nào bị bỏ sót. CHỈ ĐỌC dữ liệu UC đã thu.

Trường không có trang lịch thi giữa kỳ chung (SIS, e.hust, qldt đều không có; đã dò 24/10). Nên gộp 3 nguồn:
  1. FAMI (lịch thi chính thức, chỉ các môn Toán): fami.json -> 'co_lich' kèm ngày, kíp, phòng.
  2. Thông báo trong Teams / mail của lớp: 'khong_thi' ("không tổ chức thi giữa kỳ") hoặc 'du_kien' (trích nguyên câu).
  3. Cách tính điểm (grade_rules.json) có thành phần "Giữa kỳ" mà chưa thấy lịch -> 'chua_lich'.
Còn lại -> 'chua_co' (chưa có thông báo gì).
"""
import datetime as dt, json, re, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHOOL = HERE / 'school'
TZ = dt.timezone(dt.timedelta(hours=7))
SKIP = ('MIL', 'PE')   # Giáo dục quốc phòng / thể chất: học tập trung, không có thi giữa kỳ kiểu thường
# Tên gọi của môn trong tên team / mail khi team không ghi mã môn. Đi tắt: bảng tay cho 4 môn kỳ 2026.1;
# kỳ sau cần thêm tên môn mới (hoặc lấy tên môn từ TKB khi UC có nguồn tên môn ổn định).
ALIASES = {'IT2000': ['nhap mon cntt'], 'MI1111': ['giai tich'], 'MI1141': ['dai so'], 'IT1108': ['nhap mon lap trinh', 'nmlt']}
NAMES = {'IT2000': 'Nhập môn CNTT&TT', 'MI1111': 'Giải tích I', 'MI1141': 'Đại số', 'IT1108': 'Nhập môn lập trình'}

NONE_RE = re.compile(r'không\s+(?:tổ\s+chức\s+)?(?:thi|kiểm\s+tra)\s+giữa\s+k[ỳì]', re.I)
PLAN_RE = re.compile(r'lịch\s+thi|thi\s+giữa\s+k[ỳì]|kiểm\s+tra\s+giữa\s+k[ỳì]|thi\s+GK\b', re.I)
NOT_PLAN_RE = re.compile(r'thi\s+thử|cuối\s+k[ỳì]|thi\s+đấu|olympic', re.I)
DATE_RE = re.compile(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b|(?:đầu|giữa|cuối)\s+tháng\s+\d{1,2}', re.I)


def _norm(s):
    s = unicodedata.normalize('NFD', s or '').replace('đ', 'd').replace('Đ', 'D')
    return re.sub(r'[̀-ͯ]', '', s).lower()


def _load(name):
    try: d = json.loads((SCHOOL / name).read_text(encoding='utf-8'))
    except Exception: return None
    return d


def _items(d):
    if d is None: return []
    return d if isinstance(d, list) else (list(d.values())[0] if d else [])


def _courses():
    g = _load('grade_rules.json') or {}
    return {c: g[c] for c in g if not c.startswith(SKIP)}


def _belongs(code, text):
    t = _norm(text)
    return code.lower() in t or any(a in t for a in ALIASES.get(code, []))


def _sentences(body):
    return [s.strip() for s in re.split(r'[\n\r]+|(?<=[.!?])\s+', body or '') if s.strip()]


def _notices(code):
    """Câu thông báo thi giữa kỳ mới nhất của môn: (kind, câu, nguồn, lúc) hoặc None."""
    found = []
    for x in _items(_load('teams/posts.json')):
        if _belongs(code, x.get('Team') or ''): found.append(('Teams', x))
    for x in _items(_load('mail/inbox.json')):
        if _belongs(code, (x.get('Subject') or '') + ' ' + (x.get('Body') or '')[:3000]): found.append(('mail', x))
    best = None
    for src, x in found:
        for s in _sentences(x.get('Body')):
            if NONE_RE.search(s): kind = 'khong_thi'
            elif PLAN_RE.search(s) and not NOT_PLAN_RE.search(s): kind = 'du_kien'
            else: continue
            at = x.get('ReceivedDateTime') or ''
            if best is None or at > best[3]: best = (kind, s[:220], src, at)
    return best


def _midterm_in_rules(rule):
    parts = rule.get('thanh_phan') if isinstance(rule, dict) else None
    return any('giữa' in (p.get('ten') or '').lower() for p in parts or [] if isinstance(p, dict))


def overview(now=None):
    """Mỗi môn đang học 1 dòng: {ma_hp, ten_hp, trang_thai, ngay?, kip?, phong?, trich?, nguon?, luc?}. Môn có lịch FAMI lên đầu."""
    today = (now or dt.datetime.now(TZ)).date().isoformat()
    fami = {}
    for e in (_load('fami.json') or {}).get('exams') or []:
        if (e.get('ngay') or '') >= today and e.get('ma_hp'): fami.setdefault(e['ma_hp'], e)
    rows = []
    for code, rule in _courses().items():
        if code in fami:
            e = fami[code]
            rows.append({'ma_hp': code, 'ten_hp': e.get('ten_hp') or code, 'trang_thai': 'co_lich', 'ngay': e.get('ngay'),
                         'kip': e.get('kip'), 'phong': e.get('phong'), 'nguon': 'FAMI'})
            continue
        n = _notices(code)
        row = {'ma_hp': code, 'ten_hp': NAMES.get(code, code)}
        if n:
            m = DATE_RE.search(n[1])
            row.update(trang_thai=n[0], trich=n[1], nguon=n[2], luc=n[3][:10], ngay_goi_y=m.group(0) if (m and n[0] == 'du_kien') else None)
        elif _midterm_in_rules(rule):
            row.update(trang_thai='chua_lich', trich='Cách tính điểm có phần Giữa kỳ, chưa thấy lịch thi', nguon='cách tính điểm')
        else:
            row.update(trang_thai='chua_co')
        rows.append(row)
    order = {'co_lich': 0, 'du_kien': 1, 'chua_lich': 2, 'chua_co': 3, 'khong_thi': 4}
    return sorted(rows, key=lambda r: (order[r['trang_thai']], r.get('ngay') or '', r['ma_hp']))


def midterm_codes(rows):
    """Mã môn để tô đỏ hạn: CHỈ môn đã có lịch thi chính thức (chủ dặn 25/10: môn chưa có lịch thì hạn để màu thường)."""
    return {r['ma_hp'] for r in rows if r['trang_thai'] == 'co_lich'}
