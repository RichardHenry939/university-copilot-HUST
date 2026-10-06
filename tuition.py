# -*- coding: utf-8 -*-
"""💰 Học phí kỳ này (Claude 2026-10-06) — CHỈ ĐỌC, không nộp tiền thay bạn.

Đúng 3 mục người dùng yêu cầu:
  • Giá đơn vị (đồng / tín chỉ): theo năm / kỳ, hiếm khi đổi -> school/tuition.json. Nguồn: bạn nhập (có Xác nhận) hoặc
    UC suy ra từ hoá đơn học phí đầu tiên của trường (tổng cần đóng ÷ số tín chỉ) rồi giữ cho các kỳ sau.
  • Số tín chỉ: các học phần của kỳ đang học (bảng điểm qldt, mục kỳ học) — tự cập nhật mỗi kỳ.
  • Tổng học phí = giá đơn vị × số tín chỉ, ĐỐI CHIẾU với hoá đơn trên trang học phí của trường
    (qldt /students/tuition, api/v1/payment/query — school_fetch đọc mỗi lượt).
Nút "Nộp học phí tại đây" mở trang học phí của trường (hoá đơn + cách thanh toán của trường)."""
import datetime as dt, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / 'school' / 'tuition.json'
PAY_URL = 'https://qldt.hust.edu.vn/students/tuition'
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
    price, src = cfg.get('don_gia'), cfg.get('nguon')
    if not price and school_total and tc:   # chưa có giá: suy ra từ hoá đơn đầu tiên rồi GIỮ cho các kỳ sau
        price, src = round(school_total / tc), f'suy ra từ hoá đơn học phí kỳ {sem} của trường ({int(school_total):,} đ ÷ {tc:g} tín chỉ)'.replace(',', '.')
        CFG.parent.mkdir(parents=True, exist_ok=True)
        CFG.write_text(json.dumps({'don_gia': price, 'nguon': src, 'tu_ky': sem, 'at': dt.datetime.now().isoformat(timespec='minutes')}, ensure_ascii=False, indent=1), encoding='utf-8')
    total = round(price * tc) if price and tc else None
    if total is None or school_total is None: check = None
    else:
        diff = school_total - total
        check = {'khop': abs(diff) < 1000, 'chenh': diff,
                 'giai_thich': None if abs(diff) < 1000 else 'Số tín chỉ tính học phí của trường có thể khác số tín chỉ học tập (vd học phần GDQP, GDTC, học lại); đợt 2 trường tính lại chính xác.'}
    return {'ok': True, 'hoc_ky': sem, 'hoc_ky_ten': sem_title, 'don_gia': price, 'don_gia_nguon': src,
            'so_tin_chi': tc, 'hoc_phan': courses, 'tong_tinh': total,
            'truong': {'doc_duoc': bool(tu.get('ok')), 'loi': tu.get('error'), 'hoa_don': [{k: v for k, v in i.items() if k != 'raw'} for i in inv],
                       'tong_can_dong': school_total, 'luc': latest.get('at')},
            'doi_chieu': check, 'nop_tai': PAY_URL, 'thong_bao': NOTICE}


def set_price(v):
    v = int(float(str(v).replace('.', '').replace(',', '')))
    if not (50_000 <= v <= 10_000_000): raise ValueError('giá đơn vị không hợp lý')
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps({'don_gia': v, 'nguon': 'bạn nhập', 'at': dt.datetime.now().isoformat(timespec='minutes')}, ensure_ascii=False, indent=1), encoding='utf-8')
    return view()


if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(view(), ensure_ascii=False, indent=1))
