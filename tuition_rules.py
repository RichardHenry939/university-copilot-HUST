# -*- coding: utf-8 -*-
"""💰 Luật học phí theo Tín chỉ học phí (TCHP) — Claude 2026-10-11. CHỈ ĐỌC trang công khai của trường, không đăng nhập.

Mỗi năm học trường ra một "Quyết định mức học phí các chương trình đào tạo…" (vd 12006/QĐ-ĐHBK ngày 05/10/2026),
đăng ở ctt.hust.edu.vn › Quy định › Đại học. Bài viết có link PDF trực tiếp trên máy chủ trường.
  • update(): tìm bài của năm học hiện tại -> tải PDF -> Tika trích chữ -> đọc
      - Phụ lục I: đơn giá (nghìn đồng / TCHP) của chương trình chuẩn của bạn (mặc định "Kỹ thuật máy tính")
      - Phụ lục II: quy đổi giờ học -> TCHP (lý thuyết + bài tập, thí nghiệm / thực hành, Giáo dục thể chất)
    Đọc không chắc (thiếu số, số lạ) -> KHÔNG ghi đè luật cũ, ghi lỗi để bạn xem.
  • maybe_update(): gọi từ vòng lặp trường; chỉ chạy từ tháng 8 tới tháng 11, tối đa 1 lần / ngày, dừng khi đã có luật năm học đó.
  • tchp(info, rules): TCHP của 1 học phần từ khối lượng "4(3-2-0-8)" (giờ / tuần: LT-BT-TN-tự học), tính 15 tuần.
    Giáo dục thể chất và Giáo dục quốc phòng: dữ liệu khối lượng của trường không đủ để tính chắc -> trả "chưa rõ", không đoán."""
import datetime as dt, html, json, re, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES = HERE / 'school' / 'tuition_rules.json'
STATE = HERE / 'school' / 'tuition_rules_state.json'
DOCS = HERE / 'school' / 'tuition_decisions'
CTT = 'https://ctt.hust.edu.vn'
LIST = CTT + '/DisplayWeb/DisplayQuyChe?tag=' + urllib.parse.quote('ĐTĐH')
TIKA = 'http://127.0.0.1:9998/tika'
UA = {'User-Agent': 'Mozilla/5.0 (University Copilot; read-only)'}   # header HTTP chỉ nhận ASCII
WEEKS = 15   # Phụ lục II tính theo tiết; khối lượng của trường là giờ / tuần -> nhân 15 tuần của một học kỳ chính


def _load(p, d):
    try: return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception: return d


def _save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')


def _get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def school_year(today=None):
    """Năm học đang diễn ra: từ tháng 8 là năm học mới (vd 10/2026 -> '2026-2027')."""
    d = today or dt.date.today()
    y = d.year if d.month >= 8 else d.year - 1
    return f'{y}-{y + 1}'


def find_decision(year):
    """Bài 'Quyết định / Quy định mức học phí … năm học <year>' trên trang Quy định › Đại học (3 trang đầu)."""
    for page in (1, 2, 3):
        h = _get(LIST + (f'&page={page}' if page > 1 else '')).decode('utf-8', 'ignore')
        for href, title in re.findall(r'<a href="(/DisplayWeb/DisplayBaiViet\?baiviet=\d+)"[^>]*>\s*<p class="title">(.*?)</p>', h, re.S):
            t = html.unescape(re.sub(r'<[^>]+>', '', title)).strip()
            if re.search(r'mức học phí', t, re.I) and year in t:
                return {'title': t, 'url': CTT + href}
    return None


def _pdf_link(article_url):
    h = _get(article_url).decode('utf-8', 'ignore')
    for u in re.findall(r'(?:href|src)="([^"]+\.pdf)"', h, re.I):
        u = html.unescape(u)
        return u if u.startswith('http') else CTT + urllib.parse.quote(u, safe='/%')
    return None


def _tika(data):
    req = urllib.request.Request(TIKA, data=data, method='PUT', headers={'Accept': 'text/plain; charset=utf-8'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode('utf-8', 'ignore')


def _norm(s):
    s = s.replace(chr(92), '').replace('&#32;', ' ')
    return re.sub(r'\s+', ' ', s)


def _num_vi(s):
    return float(s.replace(',', '.'))


def parse(text, program):
    """Đọc đơn giá + quy đổi từ chữ của quyết định. Trả (rules, lỗi)."""
    t = _norm(text)
    out, err = {}, []
    # Phụ lục I, mục I.1: bảng chương trình chuẩn hệ chính quy (KHÔNG nhầm với mục II.1 vừa làm vừa học, cũng tên "chương trình đào tạo chuẩn")
    m = re.search(r'I\. Các chương trình đào tạo đại học chính quy\s*1\) Các chương trình đào tạo chuẩn(.*?)2\) Các chương trình', t, re.S)
    if not m: err.append('không thấy bảng "I.1 Các chương trình đào tạo chuẩn" (hệ chính quy)')
    else:
        rows = re.findall(r'(.+?)\s(\d{3,4})(?=\s|$)', m.group(1).replace('Chương trình Mức học phí', ''))
        want = program.lower()
        for names, price in rows:
            n = names.lower().replace('kt ', 'kỹ thuật ')
            if want in n:
                out['don_gia'] = int(price) * 1000; out['dong_bang'] = names.strip()[:300]; break
        else:
            err.append(f'không thấy "{program}" trong bảng chương trình chuẩn')
    # Phụ lục II, mục I (hệ đại học chính quy)
    m = re.search(r'QUY ĐỔI TÍN CHỈ HỌC TẬP.*?I\. *Hệ đại học chính quy(.*?)II\. *Hệ đào tạo thường xuyên', t, re.S)
    if not m: err.append('không thấy Phụ lục II, mục I (hệ chính quy)')
    else:
        p2 = m.group(1)
        q = re.findall(r'15 tiết = ([\d,]+) TCHP', p2)
        if len(q) >= 2: out['tchp_lt_bt_15_tiet'], out['tchp_tn_15_tiet'] = _num_vi(q[0]), _num_vi(q[1])
        else: err.append('không đọc được "15 tiết = … TCHP" (lý thuyết / thí nghiệm)')
        g = re.search(r'Giáo dục thể chất\s*1 TCHT = ([\d,]+) TCHP', p2)
        if g: out['tchp_gdtc_moi_tcht'] = _num_vi(g.group(1))
        else: err.append('không đọc được quy đổi Giáo dục thể chất')
    # kiểm số cho hợp lý: lệch là dừng, không ghi
    if out.get('don_gia') and not (200_000 <= out['don_gia'] <= 5_000_000): err.append(f'đơn giá lạ: {out["don_gia"]}')
    for k in ('tchp_lt_bt_15_tiet', 'tchp_tn_15_tiet', 'tchp_gdtc_moi_tcht'):
        if k in out and not (0.5 <= out[k] <= 5): err.append(f'{k} lạ: {out[k]}')
    return out, err


def update(program=None, force=False):
    """Tìm + đọc quyết định học phí của năm học hiện tại. Ghi school/tuition_rules.json khi đọc đủ và hợp lý."""
    cfg = _load(HERE / 'school' / 'tuition.json', {})
    program = program or cfg.get('chuong_trinh') or 'Kỹ thuật máy tính'
    year = school_year()
    cur = _load(RULES, {})
    if cur.get('nam_hoc') == year and not force: return {'ok': True, 'skip': 'đã có luật năm học ' + year, 'rules': cur}
    dec = find_decision(year)
    if not dec: return {'ok': False, 'error': f'chưa thấy quyết định học phí năm học {year} trên ctt.hust.edu.vn'}
    pdf_url = _pdf_link(dec['url'])
    if not pdf_url: return {'ok': False, 'error': 'bài viết không có link PDF: ' + dec['url']}
    data = _get(pdf_url, timeout=120)
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / f'{year}.pdf').write_bytes(data)
    rules, err = parse(_tika(data), program)
    if err or 'don_gia' not in rules: return {'ok': False, 'error': '; '.join(err) or 'thiếu đơn giá', 'nguon': dec, 'pdf': pdf_url}
    so = re.search(r'(\d{3,6})_Q', urllib.parse.unquote(pdf_url))   # ô "Số" trong văn bản để trống, số nằm ở dấu đóng + tên file
    if so: rules['so_qd'] = so.group(1) + '/QĐ-ĐHBK'
    rules.update(nam_hoc=year, chuong_trinh=program, nguon=dec['title'], bai_viet=dec['url'], pdf=pdf_url,
                 file=str(DOCS / f'{year}.pdf'), at=dt.datetime.now().isoformat(timespec='minutes'))
    _save(RULES, rules)
    return {'ok': True, 'rules': rules}


def maybe_update(now=None):
    """Từ vòng lặp trường: tháng 8–11, chưa có luật năm học hiện tại, chưa thử hôm nay -> thử 1 lần."""
    now = now or dt.datetime.now()
    if now.month not in (8, 9, 10, 11): return None
    if _load(RULES, {}).get('nam_hoc') == school_year(now.date()): return None
    st = _load(STATE, {})
    if st.get('last_try') == now.date().isoformat(): return None
    try: res = update()
    except Exception as e: res = {'ok': False, 'error': f'{type(e).__name__}: {e}'[:300]}
    _save(STATE, {'last_try': now.date().isoformat(), 'last': {k: v for k, v in res.items() if k != 'rules'}})
    return res


CI = re.compile(r'^\s*([\d.]+)\s*\(\s*([\d.]+)\s*-\s*([\d.]+)\s*-\s*([\d.]+)\s*-\s*([\d.]+)\s*\)\s*$')


def tchp(code, info, rules):
    """TCHP của 1 học phần. info = courses/<mã> của qldt (creditInfo, gdCreditInfo, credit). Trả (số | None, cách tính)."""
    if not info: return None, 'chưa có khối lượng học phần'
    if code.startswith('MIL'):
        return None, 'Giáo dục quốc phòng học dồn, khối lượng trường ghi không theo tuần — chờ hoá đơn để đối chiếu'
    if code.startswith('PE'):
        tc = info.get('credit') or 0
        if not tc: return None, f'Giáo dục thể chất ghi 0 tín chỉ ({info.get("creditInfo")}) — chờ hoá đơn để đối chiếu'
        return round(tc * rules['tchp_gdtc_moi_tcht'], 2), f'{tc:g} TCHT × {rules["tchp_gdtc_moi_tcht"]:g} (GDTC)'
    m = CI.match(info.get('creditInfo') or '')
    if not m: return None, f'khối lượng không đọc được: {info.get("creditInfo")!r}'
    _, lt, bt, tn, _ = (float(x) for x in m.groups())
    a = (lt + bt) * WEEKS / 15 * rules['tchp_lt_bt_15_tiet']
    b = tn * WEEKS / 15 * rules['tchp_tn_15_tiet']
    return round(a + b, 2), f'{info["creditInfo"]}: ({lt:g}+{bt:g}) giờ LT+BT × {WEEKS} tuần = {a:g} · {tn:g} giờ TN × {WEEKS} tuần × {rules["tchp_tn_15_tiet"]:g}/15 = {b:g}'


if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(update(force='--force' in sys.argv), ensure_ascii=False, indent=1))
