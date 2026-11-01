# -*- coding: utf-8 -*-
"""(v1.00.46, module Đi bộ) Đọc thành tích giải "10000 bước chạy" của CHÍNH chủ trên ctsv.hust.edu.vn. CHỈ ĐỌC.

Trang /running/10000-buoc-chay chỉ hiện top 100, nhưng chính trang gọi 2 API (thấy trong chunk JS của trang):
  api-t/Run/GetTopRunCompetitionLst {Sex}        -> tên giải + bảng top 100 (UC chỉ giữ tên giải + hạng của chủ nếu có)
  api-t/Run/GetDayRunByUser        {UserCode}    -> danh sách theo ngày (DayRunLst: DayRun, Distance km, ...)
UserCode = MSSV đã lưu ở tab Giới thiệu (mssv_store, DPAPI). MSSV chỉ nằm trong bộ nhớ tiến trình UC và trong trang:
mọi trường định danh (mã SV, tên, email) bị gỡ TRƯỚC khi trả về / ghi file. Không bao giờ đọc dữ liệu của người khác.
Ra: school/walk_ctsv.json
"""
import datetime as dt, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'walk_ctsv.json'
TZ = dt.timezone(dt.timedelta(hours=7))
_ID_KEY = re.compile(r'student|user|name|email|mssv|code|phone', re.I)   # khoá có thể chứa định danh -> bỏ

RUN_JS = """async (code) => {
  const tok = localStorage.getItem('adal.access.token.keyhttps://ctsv.hust.edu.vn');
  if (!tok) return {ok: false, error: 'no ctsv token'};
  const call = async (path, body) => {
    try {
      const r = await fetch('/api-t/' + path, {method: 'POST', signal: AbortSignal.timeout(30000),
        headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + tok}, body: JSON.stringify(body)});
      if (!r.ok) return {error: 'HTTP ' + r.status};
      const j = await r.json(); return j.RespCode === 0 || j.RespCode === undefined ? j : {error: j.RespText || ('RespCode ' + j.RespCode)};
    } catch (e) { return {error: String(e)}; }
  };
  const day = await call('Run/GetDayRunByUser', {UserCode: code});
  const top = await call('Run/GetTopRunCompetitionLst', {Sex: ''});
  const me = (top.TopRunLst || []).find(x => String(x.StudentID) === String(code));
  return {ok: !day.error, error: day.error || null, topError: top.error || null,
    competition: top.CompetitionName || null, topCount: (top.TopRunLst || []).length,
    myRank: me ? me.TopRank : null, myDistance: me ? me.Distance : null,
    top100Km: (top.TopRunLst || []).length ? top.TopRunLst[top.TopRunLst.length - 1].Distance : null,   // chỉ mốc km của hạng cuối top, không giữ tên ai
    // (01/11 tối) bảng xếp hạng như trang CTSV hiện cho người đã đăng nhập: hạng, họ tên, khoa, km. KHÔNG giữ mã SV của ai.
    board: (top.TopRunLst || []).map(x => ({r: x.TopRank, ten: x.StudentName || x.FullName || '', khoa: x.Faculty || '', km: x.Distance, me: String(x.StudentID) === String(code)})),
    dayKeys: Object.keys(day).filter(k => k !== 'DayRunLst'),
    dayExtra: Object.fromEntries(Object.entries(day).filter(([k, v]) => k !== 'DayRunLst' && typeof v !== 'object')),
    days: day.DayRunLst || []};
}"""


def _clean(obj, code):
    """Gỡ mọi khoá định danh và mọi giá trị chứa MSSV (lưới an toàn thứ hai sau JS)."""
    if isinstance(obj, dict):
        return {k: _clean(v, code) for k, v in obj.items() if not _ID_KEY.search(k)}
    if isinstance(obj, list):
        return [_clean(v, code) for v in obj]
    if isinstance(obj, str) and code and code in obj:
        return '[đã che]'
    return obj


EVERY_H = 2   # đặc tả: vài lần mỗi ngày, trong 6h–22h, không đọc dày


def due(now=None):
    now = now or dt.datetime.now(TZ)
    if not 6 <= now.hour < 22: return False
    at = view().get('at')
    return not at or (now - dt.datetime.fromisoformat(at)).total_seconds() > EVERY_H * 3600


def read_in_page(page):
    """Gọi từ một trang CTSV đã đăng nhập (vd lượt ctsv_live mỗi vài phút) -> ghi school/walk_ctsv.json. Không mở trình duyệt riêng."""
    import mssv_store
    out = {'at': dt.datetime.now(TZ).isoformat(timespec='seconds'), 'ok': False}
    code = mssv_store.load()
    if not code:
        out['error'] = 'chưa lưu MSSV (tab Giới thiệu)'; return out
    try: out.update(_clean(page.evaluate(RUN_JS, code), code))
    except Exception as e: out['error'] = f'{type(e).__name__}: {e}'[:300]
    code = None
    if out.get('ok'): OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    return out


def fetch():
    import mssv_store, school_fetch as f
    from school_mail import ChromeLock
    from playwright.sync_api import sync_playwright
    out = {'at': dt.datetime.now(TZ).isoformat(timespec='seconds'), 'ok': False}
    code = mssv_store.load()
    if not code:
        out['error'] = 'chưa lưu MSSV (tab Giới thiệu)'
        return out
    with ChromeLock(), sync_playwright() as p:
        ctx = f._launch(p, True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            f._open(page, f.CTSV + '/thong-bao', 'ctsv.hust.edu.vn/thong-bao', f.ctsv_logged_in)   # trang nhẹ, chỉ để có phiên
            page.wait_for_timeout(2500)
            r = page.evaluate(RUN_JS, code)
            out.update(_clean(r, code))
        except Exception as e:
            out['error'] = f'{type(e).__name__}: {e}'[:300]
        finally:
            try: ctx.close()
            except Exception: pass
    code = None
    if out.get('ok'):
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    return out


# CTSV chỉ trả quãng đường (Distance, mét). Số bước quy đổi như app trường: km × bước/km.
# 1385 bước/km lấy từ app iCTSV của chủ ngày 01/11 (2036 bước / 1,47 km, sải ≈ 0,72 m). Đi đổi sải chân thì sửa số này.
STEPS_PER_KM = 1385


def view():
    try: d = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return {'ok': False, 'error': 'chưa đọc lần nào'}
    for r in d.get('days') or []:
        km = (r.get('Distance') or 0) / 1000
        r['km'] = round(km, 2)
        r['steps'] = round(km * STEPS_PER_KM)
    d['stepsPerKm'] = STEPS_PER_KM
    return d
