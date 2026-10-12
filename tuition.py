# -*- coding: utf-8 -*-
"""💰 Học phí kỳ này (Claude 2026-10-06) — CHỈ ĐỌC, không nộp tiền thay bạn.

Đúng 3 mục người dùng yêu cầu:
  • Giá đơn vị (đồng / tín chỉ): theo năm / kỳ, hiếm khi đổi -> school/tuition.json. Nguồn: bạn nhập (có Xác nhận) hoặc
    UC suy ra từ hoá đơn học phí đầu tiên của trường (tổng cần đóng ÷ số tín chỉ) rồi giữ cho các kỳ sau.
  • Số tín chỉ: các học phần của kỳ đang học (bảng điểm qldt, mục kỳ học) — tự cập nhật mỗi kỳ.
  • Tổng học phí = giá đơn vị × số tín chỉ, ĐỐI CHIẾU với hoá đơn trên trang học phí của trường
    (qldt /students/tuition, api/v1/payment/query — school_fetch đọc mỗi lượt).
Nút "Nộp học phí tại đây" mở trang học phí của trường (hoá đơn + cách thanh toán của trường).

(11/10) Có luật của năm học (tuition_rules.py, đọc Quyết định mức học phí trên ctt.hust.edu.vn mỗi năm): đơn giá lấy từ quyết định,
tổng = đơn giá × Tín chỉ học phí (TCHP) từng môn tính theo Phụ lục II, không còn × số tín chỉ học tập. Môn chưa tính chắc (GDQP, GDTC)
ghi "chưa rõ" và để hoá đơn của trường cho biết phần đó.

(12/10) SỬA SAI NGHIÊM TRỌNG (chủ dự án báo): tổng UC tự tính thiếu hẳn các môn GDQP / GDTC so với số trường tính, và link "tra cứu" chỉ là một
trang thông báo. Nay số CHUẨN lấy thẳng từ trang học phí thật của trường ctt-sis.hust.edu.vn/Students/CheckTuition.aspx
(school_fetch.fetch_sis_tuition: từng môn — TCHP, hệ số lớp, tiền; công nợ — đã nộp, BHYT, phí khám…, CÒN PHẢI ĐÓNG, hạn đóng).
Luật TCHP tự tính chỉ còn để ĐỐI CHIẾU từng môn (lệch thì ghi rõ). Nút nộp / tra cứu trỏ đúng trang SIS."""
import datetime as dt, json, re
import tuition_rules
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / 'school' / 'tuition.json'
PAY_URL = 'https://ctt-sis.hust.edu.vn/Students/CheckTuition.aspx'   # (12/10) trang học phí THẬT: số tiền, công nợ, cách thanh toán
NOTICE = {'title': 'THÔNG BÁO VỀ HỌC PHÍ KỲ I NĂM HỌC 2026-2027 – ĐỢT 1', 'url': 'https://ctt.hust.edu.vn/DisplayWeb/DisplayKehoach?kehoach=30245',
          'note': 'Tra cứu từ 12/10/2026 · đóng từ 12/10 đến hết 25/10/2026 · đợt 2 tính lại chính xác'}


def _load(p, d):
    try: return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception: return d


def _num(v):
    try: return float(str(v).replace(',', '').replace(' ', ''))
    except Exception: return None


def credits_now(latest):
    """Học phần của kỳ đang học: khối đầu tiên của bảng điểm qldt (dòng tiêu đề 'Học kỳ …' rồi các môn), đối chiếu TKB."""
    rows = (latest.get('transcript') or {}).get('rows') or []
    sem_title, courses = None, []
    for r in rows:
        if len(r) == 1 and re.search(r'Học kỳ', r[0]):
            if sem_title: break
            sem_title = r[0]; continue
        if sem_title and len(r) >= 4 and re.match(r'^[A-Z]{2,4}\d{4}', r[1] or ''):
            courses.append({'code': r[1], 'name': r[2], 'tc': _num(r[3]) or 0})
    return sem_title, courses


def _invoice_fields(x):
    """Hoá đơn của trường: chưa biết chắc tên trường dữ liệu -> đoán theo tên khoá, giữ nguyên bản gốc để hiển thị."""
    k = {kk.lower(): kk for kk in x}
    pick = lambda *ns: next((x[k[n]] for n in ns if n in k and x[k[n]] not in (None, '')), None)
    return {'ma': pick('code', 'invoicecode', 'billcode', 'id'), 'hoc_ky': pick('semester', 'semestercode', 'term'),
            'can_dong': _num(pick('amount', 'totalamount', 'amountdue', 'needpay', 'total')),
            'da_dong': _num(pick('paidamount', 'amountpaid', 'paid')),
            'loai': pick('typename', 'type', 'feetype', 'name', 'content', 'title'), 'trang_thai': pick('statusname', 'status'),
            'cap_nhat': pick('updatedat', 'updatedtime', 'lastupdated', 'createdat')}


def view():
    latest = _load(HERE / 'school' / 'latest.json', {})
    cfg = _load(CFG, {})
    sem = (latest.get('tkb') or {}).get('sem')
    sem_title, courses = credits_now(latest)
    tc = sum(c['tc'] for c in courses)
    tu = latest.get('tuition') or {}
    inv = [{**_invoice_fields(x), 'raw': x} for x in (tu.get('items') or []) if isinstance(x, dict)]
    inv_hp = [i for i in inv if not i['loai'] or re.search(r'học phí|hoc phi|tuition', str(i['loai']), re.I)]
    inv_sem = [i for i in inv_hp if not sem or not i['hoc_ky'] or str(sem) in str(i['hoc_ky'])]
    school_total = sum(i['can_dong'] or 0 for i in inv_sem) if inv_sem else None
    rules = _load(tuition_rules.RULES, {})
    if rules.get('don_gia') and not cfg.get('ghi_de'):   # (11/10) luật của năm học thắng; bạn nhập tay (ghi_de) thắng luật
        price, src = rules['don_gia'], f"Quyết định {rules.get('so_qd') or ''} · năm học {rules.get('nam_hoc')} (ctt.hust.edu.vn)"
    else:
        price, src = cfg.get('don_gia'), cfg.get('nguon')
    info = latest.get('course_info') or {}
    tchp_sum, chua_ro = None, []
    if rules.get('tchp_lt_bt_15_tiet'):
        tchp_sum = 0
        for c in courses:
            n, how = tuition_rules.tchp(c['code'], info.get(c['code']), rules)
            c['tchp'], c['cach_tinh'] = n, how
            if n is None: chua_ro.append(c['code'])
            else: tchp_sum += n
    if not price and school_total and tc and tchp_sum is None:   # chưa có giá: suy ra từ hoá đơn đầu tiên rồi GIỮ cho các kỳ sau
        price, src = round(school_total / tc), f'suy ra từ hoá đơn học phí kỳ {sem} của trường ({int(school_total):,} đ ÷ {tc:g} tín chỉ)'.replace(',', '.')
        CFG.parent.mkdir(parents=True, exist_ok=True)
        CFG.write_text(json.dumps({'don_gia': price, 'nguon': src, 'tu_ky': sem, 'at': dt.datetime.now().isoformat(timespec='minutes')}, ensure_ascii=False, indent=1), encoding='utf-8')
    base = tchp_sum if tchp_sum is not None else tc
    total = round(price * base) if price and base else None
    sis = latest.get('sis_tuition') or {}
    if sis.get('ok'):   # (12/10) số của TRƯỜNG là chuẩn; UC tự tính chỉ để đối chiếu từng môn
        by = {x['code']: x for x in sis.get('hoc_phan') or []}
        for c in courses:
            s = by.get(c['code'])
            if not s: continue
            c['tchp_truong'], c['tien_truong'], c['he_so'] = s.get('tchp'), s.get('tien'), s.get('he_so')
            c['lech'] = c.get('tchp') is not None and s.get('tchp') is not None and abs(c['tchp'] - s['tchp']) > 0.01
        extra = [x for x in by.values() if x['code'] not in {c['code'] for c in courses}]   # môn trường tính mà bảng điểm chưa có
        courses += [{'code': x['code'], 'name': x['name'], 'tc': None, 'tchp': None, 'tchp_truong': x.get('tchp'), 'tien_truong': x.get('tien'),
                     'he_so': x.get('he_so'), 'lech': False, 'cach_tinh': 'chỉ có trên trang học phí của trường'} for x in extra]
        school_total = sis.get('tong_hoc_phi')
    if total is None or school_total is None: check = None
    else:
        diff = school_total - total
        if abs(diff) < 1000: why = None
        elif chua_ro and price: why = f'Chênh ≈ {diff / price:.2f} tín chỉ học phí — nhiều khả năng là phần trường tính cho {", ".join(chua_ro)} (UC chưa tính chắc được).'
        else: why = 'Số tín chỉ tính học phí của trường có thể khác (vd học lại, môn ngoài khung); đợt 2 trường tính lại chính xác.'
        check = {'khop': abs(diff) < 1000, 'chenh': diff, 'giai_thich': why}
    return {'ok': True, 'hoc_ky': sem, 'hoc_ky_ten': sem_title, 'don_gia': price, 'don_gia_nguon': src,
            'so_tin_chi': tc, 'so_tchp': tchp_sum, 'chua_ro': chua_ro, 'hoc_phan': courses, 'tong_tinh': total,
            'luat': {k: rules.get(k) for k in ('so_qd', 'nam_hoc', 'bai_viet', 'pdf', 'tchp_lt_bt_15_tiet', 'tchp_tn_15_tiet', 'tchp_gdtc_moi_tcht')} if rules else None,
            'truong': {'doc_duoc': bool(tu.get('ok')), 'loi': tu.get('error'), 'hoa_don': [{k: v for k, v in i.items() if k != 'raw'} for i in inv],
                       'tong_can_dong': school_total, 'luc': latest.get('at')},
            'doi_chieu': check, 'nop_tai': PAY_URL, 'thong_bao': NOTICE,
            'sis': {'doc_duoc': bool(sis.get('ok')), 'loi': sis.get('error'), 'url': sis.get('url') or PAY_URL, 'hoc_ky': sis.get('hoc_ky'),
                    'tong_hoc_phi': sis.get('tong_hoc_phi'), 'cong_no': sis.get('cong_no') or [], 'con_phai_dong': sis.get('con_phai_dong'),
                    'han': sis.get('han'), 'luc': sis.get('at')},
            'mon_lech': [c['code'] for c in courses if c.get('lech')]}


def set_price(v):
    v = int(float(str(v).replace('.', '').replace(',', '')))
    if not (50_000 <= v <= 10_000_000): raise ValueError('giá đơn vị không hợp lý')
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps({'don_gia': v, 'nguon': 'bạn nhập', 'ghi_de': True, 'at': dt.datetime.now().isoformat(timespec='minutes')}, ensure_ascii=False, indent=1), encoding='utf-8')
    return view()


if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(view(), ensure_ascii=False, indent=1))
