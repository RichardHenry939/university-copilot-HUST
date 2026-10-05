# -*- coding: utf-8 -*-
"""CTSV nhanh mỗi giờ (Claude 2026-10-05): Sự kiện / hoạt động + phần HÀNH CHÍNH của ctsv.hust.edu.vn. CHỈ ĐỌC.

Mở CTSV MỘT lần rồi gọi thẳng API của chính trang (không cào từng trang con):
  Activity/GetPublishActivity (1000 dòng, như /danh-sach-su-kien — kèm mô tả chi tiết + tiêu chí điểm rèn luyện),
  Activity/GetActivityByUser, HWScholarship/GetApprovedScholarship  (dùng chung CTSV_API_JS với school_fetch)
  User/GetUserMessage            -> Thông báo gửi riêng cho bạn          (/thong-bao)
  api-q/Paper/GetPaperAllByToken -> Giấy tờ / thủ tục đã xin + trạng thái (/giay-to/danh-sach-giay-da-xin)
  api-q/Paper/GetPaper           -> Các thủ tục có thể xin               (/xin-cap-giay)
  bknexus/Event/GetEvents        -> Đặt vé: sự kiện sắp tới + vé của tôi (/dat-ve) — đọc lại đúng phản hồi trang tự tải,
                                    UC không giữ / tự dựng mã phiên của trang.
Công nợ (/cong-no) có reCAPTCHA -> KHÔNG tự tra (chỉ đưa link).
Ra: school/ctsv_live.json — extracurricular.py (🎯) và tab 🏛️ Hành chính đọc."""
import datetime as dt, json, re, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'ctsv_live.json'
TZ = dt.timezone(dt.timedelta(hours=7))
EVERY_MIN = 4   # (5/10) người dùng: mọi nguồn 5 phút / lần

ADMIN_JS = """async (user) => {
  const tok = localStorage.getItem('adal.access.token.keyhttps://ctsv.hust.edu.vn');
  if (!tok) return {ok: false, error: 'no ctsv token'};
  const call = async (path, body) => {
    try {
      const r = await fetch(path, {method: 'POST', signal: AbortSignal.timeout(30000),
                                   headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + tok}, body: JSON.stringify(body || {})});
      if (!r.ok) return {error: r.status};
      const j = await r.json(); return j.RespCode === 0 || j.RespCode === undefined ? j : {error: j.RespText};
    } catch (e) { return {error: String(e)}; }
  };
  const strip = h => (h || '').replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\\s+/g, ' ').trim();
  const msg = await call('/api-t/User/GetUserMessage', {PageNumber: 1, RowspPage: 1, UserName: user});
  const mine = await call('/api-q/Paper/GetPaperAllByToken', {});
  const avail = await call('/api-q/Paper/GetPaper', {});
  return {ok: !msg.error, error: msg.error || mine.error || avail.error || null,
    messages: (msg.UserMessageLst || []).map(x => ({subject: (x.Subject || '').trim(), text: strip(x.Message).slice(0, 2000), at: x.TimeSent,
      links: [...new Set([...(x.Message || '').matchAll(/href=["']([^"']+)["']/gi)].map(m => m[1]).concat([...(x.Message || '').replace(/<[^>]+>/g, ' ').matchAll(/https?:[/][/][^ \\n\\t<>"')]+/g)].map(m => m[0])))].slice(0, 6)})),
    papers: (mine.HSPaperStudentInforLst || []).map(x => ({id: x.RowID, name: strip(x.Description || x.TypePaper || x.DescriptionPaper).slice(0, 160),
      office: x.Office, service: x.TypeService, note: x.Note, created: x.TimeCreate, status: x.Status, accepted: x.TimeAccept, by: x.UserAccept, ship: x.Ship})),
    procedures: (avail.HSPaperLst || []).map(x => ({id: x.PaperID, name: strip(x.Description || x.DescriptionPaper).slice(0, 160), office: x.Office,
      service: x.TypeService, auto: x.Automatic, desc: strip(x.DescriptionPaper).slice(0, 300)}))};
}"""


def due():
    try:
        at = json.loads(OUT.read_text(encoding='utf-8')).get('at')
        return not at or (dt.datetime.now(TZ) - dt.datetime.fromisoformat(at)).total_seconds() > EVERY_MIN * 60
    except Exception:
        return True


def fetch():
    import school_fetch as f
    from school_mail import ChromeLock
    from playwright.sync_api import sync_playwright
    out = {'at': dt.datetime.now(TZ).isoformat(timespec='seconds'), 'ok': False}
    with ChromeLock(), sync_playwright() as p:
        ctx = f._launch(p, True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            # mở trang NHẸ để có phiên (trang danh-sach-su-kien tải ảnh của ~400 sự kiện -> hay quá 30 s); dữ liệu sự kiện lấy qua API
            f._open(page, f.CTSV + '/thong-bao', 'ctsv.hust.edu.vn/thong-bao', f.ctsv_logged_in)
            page.wait_for_timeout(2500)
            user = page.evaluate("() => { try { return JSON.parse(atob(localStorage.getItem('adal.idtoken').split('.')[1])).upn.split('@')[0] } catch (e) { return '' } }")
            m = re.search(r"\d{9}", user or "")
            user = m.group(0) if m else ''
            out['ctsv'] = page.evaluate(f.CTSV_API_JS, user)
            out['admin'] = page.evaluate(ADMIN_JS, user)
            # Đặt vé: đọc phản hồi trang /dat-ve tự tải (bknexus/Event/GetEvents)
            try:
                with page.expect_response(lambda r: 'bknexus/Event/GetEvents' in r.url, timeout=30000) as rr:
                    page.goto(f.CTSV + '/dat-ve', wait_until='domcontentloaded')
                j = rr.value.json()
                out['tickets'] = _tickets(j)
            except Exception as e:
                out['tickets'] = {'ok': False, 'error': f'{type(e).__name__}: {e}'[:200]}
            out['ok'] = bool(out['ctsv'].get('ok') or out['admin'].get('ok'))
        except Exception as e:
            out['error'] = f'{type(e).__name__}: {e}'[:300]
        finally:
            try: ctx.close()
            except Exception: pass
    if not out['ok']:   # lỗi -> giữ dữ liệu lần trước, chỉ ghi lỗi
        try:
            old = json.loads(OUT.read_text(encoding='utf-8')); old['lastError'] = out.get('error') or 'không đọc được'; old['lastTry'] = out['at']
            OUT.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding='utf-8')
        except Exception:
            OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
        return {'ok': False, 'error': out.get('error')}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    a = out.get('admin') or {}
    return {'ok': True, 'events': len(out['ctsv'].get('open') or []), 'messages': len(a.get('messages') or []),
            'papers': len(a.get('papers') or []), 'tickets': len((out.get('tickets') or {}).get('events') or [])}


def _tickets(j):
    """bknexus/Event/GetEvents: Id, Title, Content, Location, StartTime, EndTime, OpenTime, CloseTime, Capacity, Registered,
    IsOpen, AllowCancel, Status, MyTicket {RegId, SeatNo, TicketCode, CheckedIn, TimeCreate} (khi bạn đã có vé)."""
    lst = next((v for v in (j.values() if isinstance(j, dict) else [j]) if isinstance(v, list)), [])
    ev = []
    for x in lst:
        if not isinstance(x, dict): continue
        t = x.get('MyTicket') if isinstance(x.get('MyTicket'), dict) else None
        ev.append({'id': x.get('Id'), 'name': (x.get('Title') or '').strip(), 'start': x.get('StartTime'), 'end': x.get('EndTime'),
                   'open': x.get('OpenTime'), 'close': x.get('CloseTime'), 'place': x.get('Location'), 'seats': x.get('Capacity'),
                   'taken': x.get('Registered'), 'isOpen': bool(x.get('IsOpen')),
                   'ticket': {'seat': t.get('SeatNo'), 'code': t.get('TicketCode'), 'checkedIn': t.get('CheckedIn'), 'at': t.get('TimeCreate')} if t else None})
    return {'ok': True, 'events': ev}


def view():
    try: d = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return {'ok': False, 'error': 'chưa có dữ liệu — lượt CTSV đầu tiên chạy trong vòng đồng bộ 20 phút'}
    a = d.get('admin') or {}
    import html
    for m in a.get('messages') or []: m['text'] = html.unescape(m.get('text') or ''); m['subject'] = html.unescape(m.get('subject') or '')
    for x in (a.get('papers') or []) + (a.get('procedures') or []): x['name'] = html.unescape(x.get('name') or '')
    C = 'https://ctsv.hust.edu.vn'
    for x in a.get('procedures') or []: x['url'] = f"{C}/viet-giay/{x['id']}" if x.get('id') else C + '/xin-cap-giay'   # mở thẳng form đăng ký
    for x in a.get('papers') or []: x['url'] = f"{C}/chi-tiet-giay/{x['id']}" if x.get('id') else C + '/giay-to/danh-sach-giay-da-xin'
    for t in (d.get('tickets') or {}).get('events') or []: t['url'] = C + '/dat-ve'   # trang đặt vé không có link riêng từng sự kiện
    msgs = sorted(a.get('messages') or [], key=lambda x: x.get('at') or '', reverse=True)
    return {'ok': True, 'at': d.get('at'), 'lastError': d.get('lastError'), 'lastTry': d.get('lastTry'),
            'messages': msgs[:60], 'papers': a.get('papers') or [], 'procedures': a.get('procedures') or [],
            'tickets': (d.get('tickets') or {}).get('events') or [], 'ticketsError': (d.get('tickets') or {}).get('error'),
            'links': {'congNo': 'https://ctsv.hust.edu.vn/cong-no', 'xinGiay': 'https://ctsv.hust.edu.vn/xin-cap-giay',
                      'phanHoi': 'https://ctsv.hust.edu.vn/giay-to/danh-sach-giay-da-xin', 'datVe': 'https://ctsv.hust.edu.vn/dat-ve',
                      'thongBao': 'https://ctsv.hust.edu.vn/thong-bao', 'hoi': 'https://ctsv.hust.edu.vn/viet-giay/1',
                      'suKien': 'https://ctsv.hust.edu.vn/danh-sach-su-kien'}}


if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(fetch(), ensure_ascii=False))
