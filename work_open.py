# -*- coding: utf-8 -*-
"""✍️ "Làm bài" từ tab Hôm nay (Claude 2026-10-11): bấm một hạn -> mở THẲNG chỗ làm bài, tự đăng nhập nếu cần, cửa sổ ở lại.

Tìm chỗ làm bài (chỉ đọc dữ liệu UC đã có):
  • FAMI số hoá  -> fami.items(): phòng kiểm tra của lớp (fami.hust.edu.vn/sohoa/phong-hoc/kiem-tra/<lớp>)
  • MOOC SoICT   -> school/mooc.json: link thẳng tới bài (soict.daotao.ai/.../jump_to/...)
  • Teams        -> school/events.json (hạn bài tập) -> bài đăng Teams: link thẻ Assignments (mở thẳng bài tập) hoặc link bài đăng
  • không biết   -> trả None (giao diện mở trang Notion của hạn như cũ)
Mở: Chrome THẬT với hồ sơ riêng (config: paths.chrome_open_profile) (KHÔNG phải hồ sơ đồng bộ — đồng bộ 5 phút/lần vẫn chạy khi cửa sổ này mở),
cổng điều khiển 127.0.0.1:9333. UC nối vào, mở tab mới, đi qua đăng nhập bằng đúng bộ tự đăng nhập của school_fetch (tài khoản bạn
cất trong Credential Manager, chỉ điền trên trang đăng nhập Microsoft / ADFS của trường; gặp xác minh 2 bước thì dừng để bạn tự làm),
rồi NGẮT kết nối — cửa sổ ở lại cho bạn làm bài. Một cửa sổ duy nhất: lần sau mở thêm tab vào chính cửa sổ đó.
UC không bấm nộp, không làm bài thay bạn."""
import datetime as dt, json, re, socket, subprocess, threading, time
from pathlib import Path
from urllib.parse import urlparse

import uc_config as cfg

HERE = Path(__file__).resolve().parent
SCHOOL = HERE / 'school'
PROFILE = Path(cfg.path('chrome_open_profile'))
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9333
ASSIGNMENTS_APP = 'https://teams.microsoft.com/l/app/66aeee93-507d-479a-a3ef-8f494af43945'   # ứng dụng Assignments của Microsoft Teams
_status = {}   # id hạn -> {at, state, msg, url}
_lock = threading.Lock()


def _load(p, d):
    try: return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception: return d


def _norm(s):
    import deadlines
    return deadlines.norm(s)


def resolve(dl):
    """dl: một hạn của deadlines.open_list (name, course, due). -> {'url', 'nguon', 'site'} hoặc None."""
    name, code = dl.get('name') or '', dl.get('course') or ''
    n = _norm(name)
    due = dt.datetime.fromisoformat(dl['due']) if dl.get('due') else None
    if '(FAMI)' in name:
        try:
            import fami
            for it in fami.items():
                if it['name'] == name: return {'url': it['url'], 'nguon': 'FAMI số hoá — phòng kiểm tra của lớp', 'site': 'fami'}
        except Exception: pass
    m = _load(SCHOOL / 'mooc.json', {})
    best = None
    for cid, c in (m.get('courses') or {}).items():
        mc = re.search(r'\+([A-Z]{2,4}\d{4})\+', cid)
        if not mc or (code and mc.group(1) != code): continue
        for it in c.get('items') or []:
            if not it.get('url'): continue
            hit = _norm(it['name']) and _norm(it['name']) in n
            near = False
            if due and it.get('due'):
                try: near = abs((dt.datetime.fromisoformat(it['due'].replace('Z', '+00:00')) - due).total_seconds()) <= 7200
                except Exception: pass
            if hit: return {'url': it['url'], 'nguon': 'MOOC SoICT — đúng bài', 'site': 'mooc'}
            if near and not best: best = {'url': it['url'], 'nguon': 'MOOC SoICT — bài cùng hạn', 'site': 'mooc'}
    ev = _load(SCHOOL / 'events.json', {})
    posts = (_load(SCHOOL / 'teams' / 'posts.json', {}) or {}).get('items') or []
    for e in (ev.get('events') or {}).values():
        if e.get('kind') != 'bt': continue
        for s in (e.get('chang') or {}).values():
            t = _norm(s.get('ten'))
            if not t or not (t in n or n in t): continue
            conv = set(e.get('conversations') or [])
            cand = [p for p in posts if p.get('ConversationId') in conv]
            cand.sort(key=lambda p: (t in _norm(p.get('Body')), p.get('ReceivedDateTime') or ''), reverse=True)
            for p in cand:
                if p.get('Links'): return {'url': p['Links'][0], 'nguon': 'Teams Assignments — mở thẳng bài tập', 'site': 'teams'}
            for p in cand:
                if p.get('WebUrl'): return {'url': p['WebUrl'], 'nguon': f'Teams — bài đăng giao bài ({p.get("Team")})', 'site': 'teams'}
            # chưa có link riêng (bài đăng lưu trước 11/10, chờ lượt đọc Teams kế tiếp) -> ứng dụng Assignments: danh sách bài tập mọi lớp
            return {'url': ASSIGNMENTS_APP, 'nguon': 'Teams Assignments — danh sách bài tập (chưa có link riêng của bài này)', 'site': 'teams'}
    return best


def _port_open():
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', PORT)) == 0


def _ensure_chrome():
    if _port_open(): return
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([CHROME, f'--user-data-dir={PROFILE}', f'--remote-debugging-port={PORT}', '--remote-debugging-address=127.0.0.1',
                      '--no-first-run', '--no-default-browser-check', '--disable-background-mode', '--hide-crash-restore-bubble',
                      '--disable-session-crashed-bubble', 'about:blank'], creationflags=0x00000008)   # DETACHED: UC tắt thì cửa sổ vẫn còn
    for _ in range(40):
        if _port_open(): return
        time.sleep(0.5)
    raise RuntimeError('không bật được cửa sổ Chrome làm bài')


def _login_if_needed(page, site, target):
    import school_fetch as f
    host = urlparse(page.url).hostname or ''
    if site == 'fami' and '/login' in page.url:
        page.get_by_text(re.compile('Đăng nhập bằng Microsoft', re.I)).first.click(); page.wait_for_timeout(4000)
        f._through_sso(page, 'fami.hust.edu.vn/sohoa', deadline=120); page.goto(target, wait_until='commit', timeout=90000)
    elif site == 'mooc' and ('/login' in page.url or 'Đăng nhập' in page.inner_text('body')[:300]):
        if '/login' not in page.url: page.goto('https://soict.daotao.ai/login', wait_until='commit', timeout=90000); page.wait_for_timeout(3000)
        page.get_by_text(re.compile('Đăng nhập bằng HUST', re.I)).first.click(); page.wait_for_timeout(4000)
        f._through_sso(page, 'soict.daotao.ai', deadline=120); page.goto(target, wait_until='commit', timeout=90000)
    elif host in f.LOGIN_HOSTS or 'login.live.com' in host:
        f._through_sso(page, urlparse(target).hostname or '', deadline=120)


def _open_job(key, target, site):
    from playwright.sync_api import sync_playwright
    import school_fetch as f
    st = lambda state, msg: _status.__setitem__(key, {'at': dt.datetime.now().isoformat(timespec='seconds'), 'state': state, 'msg': msg, 'url': target})
    try:
        _ensure_chrome()
        st('dang_mo', 'Đang mở và đăng nhập…')
        p = sync_playwright().start()
        try:
            b = p.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}')
            ctx = b.contexts[0] if b.contexts else b.new_context()
            blank = [pg for pg in ctx.pages if pg.url in ('about:blank', 'chrome://newtab/')]
            page = blank[0] if blank else ctx.new_page()
            page.goto(target, wait_until='commit', timeout=90000); page.wait_for_timeout(5000)
            try:
                _login_if_needed(page, site, target); page.wait_for_timeout(2000)
                st('xong', 'Đã mở chỗ làm bài — cửa sổ Chrome làm bài đang ở trên cùng.')
            except f.NeedLogin as e:
                st('can_ban', f'Cần bạn tự đăng nhập trong cửa sổ vừa mở: {e}')
            page.bring_to_front()
        finally:
            p.stop()   # chỉ NGẮT kết nối; Chrome do UC bật riêng (detached) nên cửa sổ ở lại
    except Exception as e:
        st('loi', f'{type(e).__name__}: {e}'[:300])


def open_dl(dl):
    r = resolve(dl)
    key = dl.get('id')
    if not r: return {'ok': False, 'khong_ro': True, 'error': 'UC chưa biết chỗ làm bài này (không phải bài FAMI / MOOC / Teams) — mở trang Notion của hạn.', 'notion': dl.get('url')}
    with _lock:
        cur = _status.get(key)
        if cur and cur['state'] == 'dang_mo': return {'ok': True, **r, 'status': cur}
        _status[key] = {'at': dt.datetime.now().isoformat(timespec='seconds'), 'state': 'dang_mo', 'msg': 'Đang mở…', 'url': r['url']}
    threading.Thread(target=_open_job, args=(key, r['url'], r['site']), daemon=True).start()
    return {'ok': True, **r, 'status': _status[key]}


def status(key):
    return _status.get(key) or {'state': 'chua'}
