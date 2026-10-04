# -*- coding: utf-8 -*-
"""Đọc mail trường (Office 365 @sis.hust.edu.vn) cho UC (Claude 2026-10-04).

Dùng chung hồ sơ Chrome đồng bộ + tự đăng nhập của school_fetch.py (Microsoft/ADFS, mật khẩu ở Credential Manager).
Đọc qua REST của chính Outlook Web (token của trang) -> KHÔNG mở thư, KHÔNG đổi trạng thái đã đọc, không gửi/xoá/di chuyển gì.
Khoá school/chrome.lock dùng chung với school_fetch để hai bên không mở cùng hồ sơ một lúc.
  python school_mail.py            đọc thư mới -> school/mail/inbox.json (lưu cục bộ, giữ 400 thư gần nhất)
Kết quả in 1 dòng JSON: {ok, new, total, error?}"""
import json, sys, time, datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIL = HERE / 'school' / 'mail'
BOX = MAIL / 'inbox.json'
LOCK = HERE / 'school' / 'chrome.lock'
KEEP = 400

JS = r"""async (since) => {
  const toks = [];
  for (const store of [localStorage, sessionStorage]) for (const k of Object.keys(store)) {
    if (!/accesstoken/i.test(k)) continue;
    try { const o = JSON.parse(store.getItem(k)); if (/outlook\.office/i.test(o.target || '')) toks.push(o.secret); } catch (e) {}
  }
  const sel = 'Id,InternetMessageId,ConversationId,Subject,From,ToRecipients,ReceivedDateTime,BodyPreview,Body,IsRead,HasAttachments';
  const filt = since ? '&$filter=' + encodeURIComponent('ReceivedDateTime ge ' + since) : '';
  let last = 'no token';
  for (const t of toks) {   // token nào được API chấp nhận thì dùng; danh sách rỗng (không có thư mới) vẫn là thành công
    let url = 'https://outlook.office.com/api/v2.0/me/mailfolders/inbox/messages?$top=50&$orderby=ReceivedDateTime%20desc&$select=' + sel + filt;
    const out = []; let failed = false;
    for (let page = 0; page < 8 && url; page++) {
      let r;   // giới hạn 30 s/lần gọi (fetch treo -> evaluate chờ vô hạn -> giữ khoá Chrome)
      try { r = await fetch(url, {headers: {Authorization: 'Bearer ' + t, Prefer: 'outlook.body-content-type="text"'}, signal: AbortSignal.timeout(30000)}); }
      catch (e) { last = 'timeout'; failed = true; break; }
      if (!r.ok) { last = 'HTTP ' + r.status; failed = true; break; }
      const j = await r.json(); out.push(...(j.value || [])); url = j['@odata.nextLink'] || null;
    }
    if (!failed) return {ok: true, items: out};
  }
  return {ok: false, error: last};
}"""


class ChromeLock:
    """Khoá liên tiến trình cho hồ sơ Chrome đồng bộ (msvcrt). Chờ tối đa `wait` giây."""
    def __init__(self, wait=900): self.wait, self.fh = wait, None
    def __enter__(self):
        import msvcrt
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(LOCK, 'a+b'); t0 = time.time()
        while True:
            try:
                self.fh.seek(0); msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1); return self
            except OSError:
                if time.time() - t0 > self.wait: raise TimeoutError('hồ sơ Chrome đồng bộ đang bận')
                time.sleep(5)
    def __exit__(self, *a):
        import msvcrt
        try: self.fh.seek(0); msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
        finally: self.fh.close()


def _load():
    try: return json.loads(BOX.read_text(encoding='utf-8'))
    except Exception: return {'items': [], 'last_fetch': None}


def fetch():
    import school_fetch as f
    from playwright.sync_api import sync_playwright
    box = _load()
    have = {m['Id'] for m in box['items']}
    since = None
    if box['items']:   # lùi 2 ngày để bắt thư đến muộn / đồng hồ lệch; trùng thì bỏ theo Id
        newest = max(m['ReceivedDateTime'] for m in box['items'])
        since = (dt.datetime.fromisoformat(newest.replace('Z', '+00:00')) - dt.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    with ChromeLock(), sync_playwright() as p:
        ctx = f._launch(p, True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            ok = lambda: any(h in page.url for h in ('outlook.office.com/mail', 'outlook.cloud.microsoft/mail')) and 'login' not in page.url
            # tên miền mới của Outlook; chỉ chờ 'commit' (Outlook có service worker + chuỗi chuyển hướng làm domcontentloaded treo)
            page.goto('https://outlook.cloud.microsoft/mail/', wait_until='commit', timeout=90000)
            for _ in range(30):
                if ok() or 'login' in page.url or 'adfs' in page.url or 'sso' in page.url: break
                page.wait_for_timeout(1000)
            f._settle(page, 2000)
            if not ok():
                try: f._through_sso(page, 'outlook.office.com/mail', deadline=90)
                except f.NeedLogin:
                    if not ok(): raise
            page.wait_for_timeout(6000)
            res = None
            for _ in range(3):   # token có thể chưa sẵn ngay khi trang vừa tải
                res = page.evaluate(JS, since)
                if res.get('ok'): break
                page.wait_for_timeout(5000)
        finally:
            try: ctx.close()
            except Exception: pass
    if not res or not res.get('ok'): return {'ok': False, 'error': (res or {}).get('error', 'no result')}
    new = []
    for m in res['items']:
        if m['Id'] in have: continue
        fr = (m.get('From') or {}).get('EmailAddress') or {}
        new.append({'Id': m['Id'], 'InternetMessageId': m.get('InternetMessageId'), 'ConversationId': m.get('ConversationId'),
                    'Subject': m.get('Subject') or '', 'FromName': fr.get('Name') or '', 'FromAddress': fr.get('Address') or '',
                    'ReceivedDateTime': m.get('ReceivedDateTime'), 'Preview': m.get('BodyPreview') or '',
                    'Body': ((m.get('Body') or {}).get('Content') or '')[:20000], 'HasAttachments': m.get('HasAttachments'),
                    'fetched_at': dt.datetime.now().isoformat(timespec='seconds'), 'processed': False})
    box['items'] = sorted(box['items'] + new, key=lambda x: x['ReceivedDateTime'])[-KEEP:]
    box['last_fetch'] = dt.datetime.now().isoformat(timespec='seconds')
    MAIL.mkdir(parents=True, exist_ok=True)
    BOX.write_text(json.dumps(box, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True, 'new': len(new), 'total': len(box['items'])}


if __name__ == '__main__':
    try: r = fetch()
    except Exception as e: r = {'ok': False, 'error': f'{type(e).__name__}: {e}'[:300]}
    print(json.dumps(r, ensure_ascii=False))
