# -*- coding: utf-8 -*-
"""Đọc dữ liệu chính thức của trường (Claude 2026-10-03) — qldt.hust.edu.vn (eHUST web) + ctsv.hust.edu.vn (iCTSV).

Chạy Chrome thật trên máy với hồ sơ RIÊNG D:\\Tools\\uc-sync\\chrome-profile (không đụng hồ sơ Chrome chính).
  python school_fetch.py --login   mở cửa sổ Chrome để BẠN tự đăng nhập Office 365 một lần ("Duy trì đăng nhập": Có)
  python school_fetch.py           đọc ngầm (headless), ghi school/latest.json

Đăng nhập: phiên của trường chỉ là cookie tạm (đóng Chrome là mất) → mỗi lần đọc, nếu hết phiên thì TỰ ĐĂNG NHẬP LẠI bằng
tài khoản bạn tự cất trong Windows Credential Manager (python school_cred.py). Chỉ điền trên login.microsoftonline.com và
asso.hust.edu.vn (ADFS trường), tối đa 1 lần/lượt; bị từ chối → khoá (school/login.lock) và báo bạn; gặp xác minh 2 bước /
captcha → dừng, báo bạn. Mật khẩu không ghi ra file / log nào.

Chỉ ĐỌC những gì trang hiển thị cho bạn (dữ liệu API của trường được mã hoá — không phá lớp mã hoá).
"""
import uc_config as cfg
import json, re, sys, time, datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE = Path(cfg.path("chrome_profile"))
OUT = HERE / "school"
QLDT = "https://qldt.hust.edu.vn"
CTSV = "https://ctsv.hust.edu.vn"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"


def log(*a):
    """Nhật ký từng bước (KHÔNG bao giờ ghi email/mật khẩu) -> school/fetch.log"""
    OUT.mkdir(exist_ok=True)
    line = f"{dt.datetime.now():%H:%M:%S} " + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(OUT / "fetch.log", "a", encoding="utf-8") as fh: fh.write(line + chr(10))


class NeedLogin(Exception):
    """Microsoft/trường đòi đăng nhập thủ công (mật khẩu, xác minh, captcha) — người dùng phải tự làm."""


def _launch(p, headless):
    PROFILE.mkdir(parents=True, exist_ok=True)
    args = ["--no-first-run", "--no-default-browser-check", "--disable-features=Translate"]
    ctx = p.chromium.launch_persistent_context(str(PROFILE), channel="chrome", headless=headless, args=args,
                                               user_agent=None if not headless else UA, viewport={"width": 1366, "height": 860},
                                               locale="vi-VN")
    ctx.set_default_timeout(30000)
    return ctx


def _settle(page, ms=2500):
    try: page.wait_for_load_state("networkidle", timeout=15000)
    except Exception: pass
    page.wait_for_timeout(ms)


LOGIN_HOSTS = {"login.microsoftonline.com", "sso.hust.edu.vn", "asso.hust.edu.vn"}   # CHỈ điền tài khoản trên đúng các trang này (Microsoft + ADFS của trường)
LOCK = OUT / "login.lock"


def _creds():
    try:
        import school_cred
        return school_cred.get()
    except Exception:
        return None, None


def _fail_lock(why):
    """Bị từ chối mật khẩu → khoá tự đăng nhập để không thử lại (tránh khoá tài khoản). Mở khoá: python school_cred.py"""
    OUT.mkdir(exist_ok=True)
    LOCK.write_text(f"{dt.datetime.now():%Y-%m-%d %H:%M} {why}", encoding="utf-8")
    raise NeedLogin(why + " — đã khoá tự đăng nhập; nhập lại tài khoản bằng: python school_cred.py")


def _through_sso(page, want, deadline=90):
    """Đi qua đăng nhập Office 365 tới khi URL chứa `want`.
    Có tài khoản trong Credential Manager (school_cred.py) → tự điền email/mật khẩu, CHỈ trên LOGIN_HOSTS, tối đa 1 lần/lượt.
    Gặp xác minh 2 bước / captcha / bị từ chối → dừng, báo cần đăng nhập thủ công."""
    from urllib.parse import urlparse
    email, pwd = _creds()
    if LOCK.exists(): email = pwd = None   # đang khoá sau lần bị từ chối
    sent_pwd = False
    t0 = time.time()
    while time.time() - t0 < deadline:
        u = page.url
        host = urlparse(u).hostname or ""
        log("sso @", host, urlparse(u).path[:40])
        pu = urlparse(u)   # so tên miền + đường dẫn + #route (qldt là SPA), BỎ query (redirect_uri của ADFS chứa tên trang đích)
        hp = host + pu.path + ('#' + pu.fragment if pu.fragment else '')
        if want in hp and "login" not in hp: return True
        if host in LOGIN_HOSTS or "login.live.com" in host:
            if page.locator("input[name=otc]:visible, #idDiv_SAOTCAS_Title, #idDiv_SAOTCC_Title, iframe[src*=captcha]").count():
                raise NeedLogin("Microsoft yêu cầu xác minh 2 bước / captcha")
            err = page.locator("#passwordError:visible, #usernameError:visible, #errorText:visible")
            if sent_pwd and err.count() and err.first.inner_text().strip():
                _fail_lock("Trường/Microsoft từ chối mật khẩu đã cất")
            if host not in LOGIN_HOSTS:
                raise NeedLogin(f"Trang đăng nhập lạ: {host}")
            # chọn tài khoản trường đã có sẵn
            tile = page.locator("[data-test-id$='@sis.hust.edu.vn'], div.table[role=button]:has-text('sis.hust.edu.vn')")
            if tile.count() and not page.locator("input[type=password]:visible").count():
                tile.first.click(); _settle(page, 1500); continue
            # Microsoft: ô email
            em = page.locator("input[name=loginfmt]:visible")
            if em.count():
                if not email: raise NeedLogin("Microsoft chưa có phiên — chưa cất tài khoản (python school_cred.py)")
                em.fill(email); page.locator("#idSIButton9").click(); _settle(page, 2000); continue
            # ADFS của trường: ô tài khoản
            au = page.locator("#userNameInput:visible")
            if au.count() and not au.input_value():
                if not email: raise NeedLogin("Cổng ADFS yêu cầu đăng nhập — chưa cất tài khoản")
                au.fill(email)
            nxt = page.locator("#nextButton:visible")   # ADFS 2 bước (asso.hust.edu.vn): tài khoản → Tiếp theo → mật khẩu
            if nxt.count() and au.count() and not page.locator("input[type=password]:visible").count():
                nxt.click(); _settle(page, 2000); continue
            pw = page.locator("input[name=passwd]:visible, #passwordInput:visible, input[type=password]:visible")
            if pw.count():
                if not pwd: raise NeedLogin("Yêu cầu mật khẩu — chưa cất tài khoản (python school_cred.py)")
                if sent_pwd: page.wait_for_timeout(2000); continue
                pw.first.fill(pwd); sent_pwd = True
                btn = page.locator("#idSIButton9:visible, #submitButton:visible")
                if btn.count(): btn.first.click()
                else: pw.first.press("Enter")
                _settle(page, 2500); continue
            kmsi = page.locator("#idSIButton9:visible")
            if kmsi.count() and ("kmsi" in u.lower() or page.locator("#KmsiCheckboxField, #KmsiDescription").count()):
                kmsi.click(); _settle(page, 1500); continue   # "Duy trì đăng nhập?" → Có
            try:   # trang lạ: ghi tiêu đề để chẩn đoán (không ghi giá trị ô nhập)
                head = page.locator("#lightbox [role=heading], .text-title, h1, #header").first.inner_text(timeout=1500)
                log("  trang:", head.strip()[:80].replace(chr(10), " "))
            except Exception:
                pass
        elif "e.hust.edu.vn/sso/login" in u or u.rstrip("/").endswith("qldt.hust.edu.vn") or "/login" in u:
            if page.locator("iframe[src*=recaptcha][src*=bframe]:visible").count(): raise NeedLogin("Trang trường hiện captcha")
            b = page.get_by_role("button", name=re.compile("Office 365", re.I))
            if not b.count(): b = page.locator("a:has-text('Office 365'), button:has-text('Office 365')")
            if b.count():
                b.first.click(); _settle(page, 2000); continue
            d = page.get_by_role("button", name=re.compile("^Đăng nhập$", re.I))
            if not d.count():   # (6/10) qldt đổi nút "ĐĂNG NHẬP" ở góc phải thành thẻ thường (không còn role=button)
                d = page.locator("a:visible, div:visible, span:visible").filter(has_text=re.compile(r"^\s*Đăng nhập\s*$", re.I))
            if d.count():
                d.last.click(); _settle(page, 1500); continue
        page.wait_for_timeout(1500)
    raise NeedLogin(f"Không vào được {want} sau {deadline}s (đang ở {urlparse(page.url).hostname})")


def qldt_logged_in(page):
    """Đăng nhập thật = API sinh viên trả 200 với cookie của trang (không đọc nội dung)."""
    try:
        return page.evaluate("fetch('https://student.hust.edu.vn/api/v1/semesters/current',{credentials:'include'}).then(r=>r.status)") == 200
    except Exception:
        return False


def ctsv_logged_in(page):
    try:
        return "/login" not in page.url and "Xin chào" in page.inner_text("body", timeout=3000)
    except Exception:
        return False


def ctsv_login(page, tries=3):
    """iCTSV: trang chủ vẫn mở được khi chưa đăng nhập (hiện nút "Đăng nhập", hoặc hộp "Phiên đăng nhập đã hết hạn"
    → "Đăng nhập lại" che cả trang, thêm từ 10/2026). Bấm nút đó → /login → Office 365 → về trang chủ đã đăng nhập."""
    for _ in range(tries):
        if ctsv_logged_in(page): return True
        again = page.get_by_role("button", name=re.compile("Đăng nhập lại", re.I))
        btn = again if again.count() else page.get_by_text("Đăng nhập", exact=True)
        if btn.count():
            btn.first.click(); _settle(page, 2500)
        if "ctsv.hust.edu.vn" not in page.url or "/login" in page.url:
            try: _through_sso(page, "ctsv.hust.edu.vn")
            except NeedLogin: raise
        _settle(page, 2500)
    return ctsv_logged_in(page)


HIDE_POPUP_JS = """() => { for (const s of ['#uni-survey-popup-root']) { const r = document.querySelector(s); if (r) r.style.display = 'none'; } }"""


def _goto(page, url):
    """goto chịu được việc trang tự chuyển hướng chen ngang (qldt SPA hay tự nhảy trang khi vừa có phiên)."""
    try: page.goto(url, wait_until="domcontentloaded")
    except Exception as e:
        if "interrupted by another navigation" not in str(e): raise
        page.wait_for_timeout(2000)
    _settle(page)
    if "qldt.hust.edu.vn" in page.url:   # (6/10) popup "Danh sách khảo sát" của trường che cả trang (không có nút đóng) -> chỉ ẨN trên máy, KHÔNG trả lời khảo sát
        page.wait_for_timeout(1500)
        try: page.evaluate(HIDE_POPUP_JS)
        except Exception: pass


def _open(page, url, want, check=None):
    log("open", url)
    _goto(page, url)
    if want in page.url and "login" not in page.url and (check is None or check(page)): return
    if check is qldt_logged_in:   # qldt không tự chuyển trang khi hết phiên → bắt đầu đăng nhập từ trang chủ
        _goto(page, QLDT + "/")
        if not (want in page.url and check(page)): _through_sso(page, "qldt.hust.edu.vn/students")
    else:   # iCTSV: đăng nhập xong trường đưa về trang chủ (không phải trang đang mở) → chỉ cần về đúng tên miền
        ctsv_login(page)
    for i in range(5):   # vừa đăng nhập xong, phiên / token của trang có thể chưa sẵn ngay -> chờ rồi thử lại (lỗi 12:30 & 14:11 4/10)
        _goto(page, url)
        if want in page.url and (check is None or check(page)): return
        page.wait_for_timeout(3000)
    raise NeedLogin(f"Chưa vào được {url}")


ROWS_JS = """(scope) => {
  const root = (scope && document.querySelector(scope)) || document;
  // Bảng Ant Design có thể tách tiêu đề (thead) và thân (tbody) thành 2 <table> trong cùng .ant-table
  const bodies = [...root.querySelectorAll('table')].map(t => [t, t.querySelectorAll(':scope > tbody > tr:not(.ant-table-measure-row)').length]);
  bodies.sort((a, b) => b[1] - a[1]);
  if (!bodies.length || !bodies[0][1]) return {heads: [], rows: []};
  const t = bodies[0][0], wrap = t.closest('.ant-table') || t.parentElement;
  const th = wrap.querySelectorAll('thead th');
  return {heads: [...th].map(x => x.innerText.trim()),
          rows: [...t.querySelectorAll(':scope > tbody > tr:not(.ant-table-measure-row)')].map(r => [...r.cells].map(c => c.innerText.trim())).filter(r => r.some(Boolean))};
}"""


def fetch_qldt(page, out):
    # TKB (chi tiết)
    _open(page, QLDT + "/students/learn/timetable", "/students/", qldt_logged_in)
    try: page.wait_for_selector(".ant-spin-spinning", state="detached", timeout=45000)   # trang còn đang tải thì vòng xoay che nút
    except Exception: pass
    try: page.evaluate(HIDE_POPUP_JS)
    except Exception: pass
    page.get_by_text("Chi tiết", exact=True).first.click(); _settle(page, 2500)
    page.wait_for_function("document.querySelectorAll('table tbody tr:not(.ant-table-measure-row)').length > 0", timeout=25000)
    t = page.evaluate(ROWS_JS)
    m = re.search(r"Kỳ\s*\n?\s*(\d{5})", page.inner_text("body"))
    out["tkb"] = {"sem": m.group(1) if m else None, **t}
    # Bảng điểm chi tiết + tổng hợp
    _open(page, QLDT + "/students/learn/personal-transcript", "/students/", qldt_logged_in)
    page.wait_for_function("document.querySelectorAll('table tbody tr:not(.ant-table-measure-row)').length > 0", timeout=25000); _settle(page, 1500)
    body = page.inner_text("article") if page.locator("article").count() else page.inner_text("body")
    out["transcript"] = {**page.evaluate(ROWS_JS, ".ant-tabs-tabpane-active"), "head": body[:400]}
    page.get_by_role("tab", name=re.compile("Điểm tổng hợp")).click(); _settle(page, 2500)
    out["summary"] = page.evaluate(ROWS_JS, ".ant-tabs-tabpane-active")
    # Chương trình đào tạo
    _open(page, QLDT + "/students/learn/education-program", "/students/", qldt_logged_in)
    page.wait_for_function("document.querySelectorAll('table tbody tr:not(.ant-table-measure-row)').length > 0", timeout=25000); _settle(page, 2000)
    out["program"] = page.evaluate(ROWS_JS)
    # (6/10) Học phí: trang /students/tuition tự gọi api/v1/payment/query (có checkSum của trang) -> đọc lại đúng phản hồi đó, CHỈ ĐỌC
    try:
        with page.expect_response(lambda r: "/api/v1/payment/query" in r.url, timeout=30000) as rr:
            _goto(page, QLDT + "/students/tuition")
        j = rr.value.json()
        out["tuition"] = {"ok": True, "items": j if isinstance(j, list) else (j.get("data") or j.get("items") or [])}
    except Exception as e:
        out["tuition"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}


CTSV_API_JS = """async (user) => {
  const tok = localStorage.getItem('adal.access.token.keyhttps://ctsv.hust.edu.vn');
  if (!tok) return {ok: false, error: 'no ctsv token'};
  const call = async (path, body) => {
    const r = await fetch('/api-t/' + path, {method: 'POST', signal: AbortSignal.timeout(30000), headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + tok},
                                             body: JSON.stringify({...body, UserName: user})});
    if (!r.ok) return {error: r.status};
    const j = await r.json(); return j.RespCode === 0 ? j : {error: j.RespText};
  };
  const strip = h => (h || '').replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\\s+/g, ' ').trim().slice(0, 1500);
  const act = x => ({id: x.AId, name: (x.AName || '').trim(), type: x.AType, start: x.StartTime, end: x.FinishTime, deadline: x.Deadline,
                     place: x.APlace, org: x.GName, ua: x.UAStatus, role: x.UserRole, note: x.UANote || '', desc: strip(x.ADesc),
                     criteria: JSON.stringify(x.ACriteriaLst || []).slice(0, 400), created: x.CreateDate});
  const mine = await call('Activity/GetActivityByUser', {UserCode: user, Search: '', NumberRow: 100, PageNumber: 1});
  const pub = await call('Activity/GetPublishActivity', {NumberRow: 1000, PageNumber: 1});   // (5/10) như trang danh-sach-su-kien; 40 thì sót sự kiện
  const sch = await call('HWScholarship/GetApprovedScholarship', {NumberRow: 100, PageNumber: 1});
  return {ok: !mine.error, error: mine.error,
          mine: (mine.Activities || []).map(act), open: (pub.Activities || []).map(act),
          scholarships: (sch.ScholarshipLst || []).map(x => ({id: x.DocumentId, name: x.Title, deadline: x.Deadline, type: x.TypeInfo,
                                                               quantity: x.Quantity, applied: x.StatusApply, expired: x.Expired,
                                                               price: x.TotalPrice, created: x.CreateTime, contact: [x.ContactName, x.ContactEmail].filter(Boolean).join(' · '),
                                                               desc: strip(x.Description || x.Content), more: strip(x.MoreInfo).slice(0, 300)}))};
}"""


def fetch_ctsv(page, out):
    _open(page, CTSV + "/cham-diem-ren-luyen", "ctsv.hust.edu.vn/cham-diem", ctsv_logged_in)
    txt = page.inner_text("body")
    m = re.search(r"Tổng SV:\s*([\d.,]+)\s*-\s*GV:\s*([\d.,]*)", txt)
    out["drl"] = {"sv": m.group(1) if m else None, "gv": (m.group(2) or None) if m else None}
    # 🎯 ngoại khoá (4/10): hoạt động đã đăng ký + đang mở + học bổng — API JSON của chính trang (chỉ đọc)
    try:
        page.goto(CTSV + "/hoat-dong", wait_until="domcontentloaded"); _settle(page, 3000)
        status = {r[1]: r[5] for r in page.evaluate(ROWS_JS)["rows"] if len(r) > 5}   # tên hoạt động -> chữ trạng thái trên trang
        user = page.evaluate("() => { try { return JSON.parse(atob(localStorage.getItem('adal.idtoken').split('.')[1])).upn.split('@')[0] } catch (e) { return '' } }")
        m = re.search(r"\d{9}", user or "") or re.search(r"\b(20\d{7})\b", page.inner_text("body"))
        api = page.evaluate(CTSV_API_JS, m.group(0) if m else "")
        for a in api.get("mine", []): a["status"] = status.get(a["name"]) or next((v for k, v in status.items() if k.strip() == a["name"]), None)
        out["ctsv"] = api
    except Exception as e:
        out["ctsv"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}


def run(headless=True):
    from playwright.sync_api import sync_playwright
    out = {"at": dt.datetime.now().isoformat(timespec="seconds"), "ok": False}
    from school_mail import ChromeLock   # khoá hồ sơ Chrome dùng chung với bộ đọc mail
    with ChromeLock(), sync_playwright() as p:
        ctx = _launch(p, headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            fetch_qldt(page, out)
            try: fetch_ctsv(page, out)   # iCTSV lỗi không làm mất dữ liệu qldt đã đọc
            except Exception as e: out["drl_error"] = f"{type(e).__name__}: {e}"[:300]
            out["ok"] = True
        except NeedLogin as e:
            out.update(need_login=True, error=str(e))
        except Exception as e:
            out.update(error=f"{type(e).__name__}: {e}"[:500])
        finally:
            ctx.close()
    OUT.mkdir(exist_ok=True)
    # (5/10) đọc 5 phút / lần -> lượt lỗi KHÔNG được đè dữ liệu tốt: trạng thái lượt gần nhất -> fetch_last.json,
    # latest.json chỉ ghi khi đọc thành công (trước đây một lỗi tạm "OSError 22" xoá sạch bảng điểm / TKB của lần trước)
    (OUT / "fetch_last.json").write_text(json.dumps({k: out.get(k) for k in ("at", "ok", "error", "need_login", "drl_error")}, ensure_ascii=False), encoding="utf-8")
    if out["ok"]:
        (OUT / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if out["ok"]:
        (OUT / f"snap-{dt.datetime.now():%Y%m%d-%H%M}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        for old in sorted(OUT.glob("snap-*.json"))[:-30]: old.unlink()
    return out


def login():
    """Mở cửa sổ Chrome (hồ sơ đồng bộ) để người dùng TỰ đăng nhập Office 365 vào qldt và iCTSV. Đợi tối đa 15 phút."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _launch(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        ok = {"qldt": False, "ctsv": False}
        page.goto(QLDT + "/students/learn/timetable")
        t0 = time.time()
        while time.time() - t0 < 900 and not all(ok.values()):
            try:
                for pg in ctx.pages:   # người dùng có thể mở tab khác
                    if not ok["qldt"] and "qldt.hust.edu.vn/students/" in pg.url and qldt_logged_in(pg):
                        ok["qldt"] = True; print("qldt ok", flush=True)
                        pg.wait_for_timeout(2000); pg.goto(CTSV + "/login"); break
                    if ok["qldt"] and "ctsv.hust.edu.vn" in pg.url and ctsv_logged_in(pg):
                        ok["ctsv"] = True; print("ctsv ok", flush=True); break
            except Exception:
                pass
            ctx.pages[0].wait_for_timeout(1500) if ctx.pages else time.sleep(1.5)
        if ctx.pages: ctx.pages[0].wait_for_timeout(5000)   # cho Chrome ghi cookie rồi mới đóng đàng hoàng
        ctx.close()
    return ok


if __name__ == "__main__":
    if "--login" in sys.argv:
        print(json.dumps(login()))
    else:
        r = run(headless="--show" not in sys.argv)
        print(json.dumps({k: (v if k in ("at", "ok", "error", "need_login") else (len(v.get("rows", [])) if isinstance(v, dict) and "rows" in v else v))
                          for k, v in r.items()}, ensure_ascii=False))
