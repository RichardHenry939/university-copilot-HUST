# -*- coding: utf-8 -*-
"""(v1.00.49) UC đăng nhập lại app iCTSV (com.bk.ctsv) trong máy ảo Android (emulator-5554).

Lấy tài khoản từ ictsv_cred.get() (Credential Manager), điền bằng adb, bấm Đăng nhập, rồi kiểm lại.
Không in tài khoản / mật khẩu ra màn hình hay log. Bị từ chối 1 lần -> tạo school/ictsv_login.lock và
dừng hẳn (tránh khoá tài khoản); mở khoá bằng `python ictsv_cred.py` (nhập lại).
Gặp captcha / mã OTP / xác minh -> dừng, báo bạn tự làm (UC không vượt captcha).

  python ictsv_login.py           đăng nhập nếu app đang ở màn đăng nhập (đang đăng nhập thì thôi)
  python ictsv_login.py --force   đăng xuất rồi đăng nhập lại (để xem UC làm trước mặt)

Giới hạn (đi tắt): điền chữ bằng `adb shell input text`, nên mật khẩu đi qua dòng lệnh shell của máy ảo
trong chốc lát, và ký tự ngoài ASCII (chữ có dấu) không gõ được. Cần chắc hơn thì làm bàn phím IME riêng.
Nhận diện màn hình dựa vào nhãn ("Đăng nhập", "Trang chủ", "Tài khoản"...); app đổi nhãn thì phải sửa.
"""
import re, subprocess, sys, threading, time, xml.etree.ElementTree as ET
from pathlib import Path

import ictsv_cred

ADB = r'D:\Android\Sdk\platform-tools\adb.exe'
S = ['-s', 'emulator-5554']
PKG = 'com.bk.ctsv'
LOCK = ictsv_cred.LOCK
UI = threading.RLock()   # một lúc chỉ một việc điều khiển màn hình máy ảo (iCTSV, eHUST đối chiếu, ...)
STOP_WORDS = re.compile(r'captcha|otp|mã xác|xác minh|xác thực', re.I)
CONFIRM = ('Đồng ý', 'Có', 'OK', 'Xác nhận', 'Đăng xuất')


def adb(*a, **kw):
    # UC chạy bằng pythonw (không có console): gọi adb.exe mà thiếu cờ này thì mỗi lần Windows bật 1 cửa sổ cmd (02/11)
    # (v1.00.56, 03/11) adb server kẹt thì lệnh treo vô hạn -> cả vòng canh đứng im; đặt hạn 60 s (quá hạn = lỗi, vòng ghi log rồi chạy tiếp)
    kw.setdefault('timeout', 60)
    return subprocess.run([ADB, *S, *a], capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), **kw)


def nodes():
    """-> danh sách nút màn hình hiện tại (dict). Không in gì."""
    adb('shell', 'uiautomator', 'dump', '/sdcard/ui.xml')
    xml = adb('exec-out', 'cat', '/sdcard/ui.xml').stdout.decode('utf-8', 'replace')
    adb('shell', 'rm', '/sdcard/ui.xml')
    try: root = ET.fromstring(xml)
    except ET.ParseError: return []
    out = []
    for n in root.iter('node'):
        m = re.findall(r'\d+', n.get('bounds', ''))
        if len(m) != 4: continue
        x1, y1, x2, y2 = map(int, m)
        out.append({'cls': n.get('class', ''), 'label': (n.get('content-desc') or n.get('text') or '').strip(),
                    'click': n.get('clickable') == 'true', 'pw': n.get('password') == 'true',
                    'pkg': n.get('package', ''), 'xy': ((x1 + x2) // 2, (y1 + y2) // 2)})
    return out


def find(ns, label, click=True):
    return next((n for n in ns if n['label'] == label and (n['click'] or not click)), None)


def tap(n): adb('shell', 'input', 'tap', str(n['xy'][0]), str(n['xy'][1])); time.sleep(1.2)


def logged_in(ns): return bool(find(ns, 'Trang chủ') and find(ns, 'Tài khoản'))


def login_form(ns): return [n for n in ns if 'EditText' in n['cls']]


def type_into(n, value):
    tap(n)
    adb('shell', 'input', 'keyevent', 'KEYCODE_MOVE_END')
    adb('shell', 'input', 'keyevent', *['KEYCODE_DEL'] * 60)   # xoá chữ cũ trong ô (nếu có)
    sh = "'" + value.replace("'", "'\\''").replace(' ', '%s') + "'"   # input text: %s = dấu cách
    adb('shell', 'input text ' + sh)


def report(ok, msg):
    print(msg)
    try:
        import alerts
        alerts.notify('UC · iCTSV', msg, level='red' if not ok else 'change')
    except Exception as e: print('(không gửi được thông báo:', e, ')')


def logout():
    tap(find(nodes(), 'Tài khoản'))
    ns = nodes(); b = find(ns, 'Đăng xuất')
    if not b: return False
    tap(b)
    for _ in range(3):   # hộp xác nhận (nếu có)
        ns = nodes()
        if login_form(ns): return True
        c = next((find(ns, w) for w in CONFIRM if find(ns, w)), None)
        if c: tap(c)
        else: time.sleep(1.5)
    return bool(login_form(nodes()))


def user_busy():
    """(02/11) bạn đang dùng máy ảo = cửa sổ máy ảo (qemu) đang ở trước trên Windows -> UC KHÔNG điều khiển máy ảo
    (trước đây lượt kiểm iCTSV / đối chiếu eHUST giành màn hình, bạn không dùng được Pixel 6)."""
    try:
        import ctypes
        from ctypes import wintypes
        pid = wintypes.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(ctypes.windll.user32.GetForegroundWindow(), ctypes.byref(pid))
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value); buf = ctypes.create_unicode_buffer(512); n = wintypes.DWORD(512)
        ok = h and ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)); h and ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and 'qemu-system' in buf.value.lower()
    except Exception: return False


def foreground():
    """-> True nếu iCTSV đang ở màn hình trước của máy ảo (không mở app hộ)."""
    return PKG.encode() in adb('shell', 'dumpsys window | grep mCurrentFocus').stdout


EXPIRED = re.compile(r'hết hạn|đăng nhập lại|phiên đăng nhập|unauthori|401', re.I)
PROBE_TILE, PROBE_OK = '10.000 bước', 'Tổng bước chân'   # dịch vụ dùng để thử: còn phiên thì hiện "Tổng bước chân"


def online():
    """Mạng tới CTSV có thông không (mất mạng thì dịch vụ cũng hỏng, không phải hết phiên)."""
    import urllib.request
    try: urllib.request.urlopen('https://ctsv.hust.edu.vn/', timeout=8); return True
    except Exception as e: return getattr(e, 'code', None) is not None   # có mã HTTP = mạng vẫn thông


def probe():
    """UC tự mở iCTSV -> Trang chủ -> '10.000 bước'. -> 'ok' | 'expired' | 'login' | 'unknown'."""
    adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1')
    for _ in range(10):   # khởi động nguội có màn chào lâu: chờ tới ~20 s
        time.sleep(2); ns = nodes()
        if find(ns, 'Trang chủ') or find(ns, 'Quay lại') or len(login_form(ns)) >= 2: break
    for _ in range(3):   # app mở lại đúng màn đang dở -> lùi về tới thanh điều hướng
        if find(ns, 'Trang chủ') or len(login_form(ns)) >= 2: break
        adb('shell', 'input', 'keyevent', 'KEYCODE_BACK'); time.sleep(1.5); ns = nodes()
    if len(login_form(ns)) >= 2: return 'login'
    home = find(ns, 'Trang chủ')
    if home: tap(home); ns = nodes()
    tile = find(ns, PROBE_TILE, click=False)
    for _ in range(3):   # ô nằm dưới mép màn hình (mục "Tiện ích") -> cuộn xuống tìm
        if tile: break
        adb('shell', 'input', 'swipe', '540', '1800', '540', '900', '400'); time.sleep(1.2)
        ns = nodes(); tile = find(ns, PROBE_TILE, click=False)
    if not tile: return 'unknown'
    tap(tile)
    for _ in range(6):   # dữ liệu tải qua mạng, có lúc chậm: chờ tới ~12 s
        time.sleep(2); ns = nodes(); labels = [n['label'] for n in ns]
        if any(l == PROBE_OK or EXPIRED.search(l) for l in labels) or len(login_form(ns)) >= 2: break
    if PROBE_OK in labels:   # đã đứng đúng trang: đọc luôn số bước thật từng lượt (walk_app.json)
        try:
            import walk_app
            res = walk_app.read_page(nodes, adb)
            if walk_app.looks_empty(res):   # (v1.00.52, chủ 02/11) dịch vụ hiện 0 khi phiên hết hạn: KHÔNG ghi đè số cũ, coi là hết phiên
                adb('shell', 'input', 'keyevent', 'KEYCODE_BACK'); return 'expired'
            out = walk_app.save(res)
            plog('ghi walk_app.json: hôm nay %s bước' % ((out['days'].get(time.strftime('%Y-%m-%d')) or {}).get('steps', 0)))
        except Exception as e: plog('walk_app lỗi: %r' % e)
    adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
    if any(EXPIRED.search(l) for l in labels): return 'expired'
    if any(l == PROBE_OK for l in labels): return 'ok'
    if len(login_form(ns)) >= 2: return 'login'
    return 'unknown'   # trống / lỗi khác: chưa kết luận


def recover(why):
    """Hết phiên: UC tự đăng xuất (chủ cho phép riêng iCTSV, 02/11) rồi đăng nhập lại."""
    report(True, f'UC thấy iCTSV không vào được dịch vụ ({why}). Đang tự đăng xuất và đăng nhập lại...')
    if why != 'login' and not logout():
        report(False, 'UC không đăng xuất được iCTSV. Dừng, bạn kiểm trong máy ảo.'); return 1
    return main(auto=True)


SLOT_FILE = Path(__file__).resolve().parent / 'school' / 'walk_slot.json'   # khung đi bộ (đỏ) hôm nay do walk.view chốt


def after_slot_due(kept, last_probe, now, grace=180):
    """(v1.00.52, chủ 02/11) Đọc app NGAY một lần sau khung đi bộ đỏ (hết khung + 3 phút), nếu lần đọc cuối còn trước lúc hết khung."""
    end = ((kept or {}).get('slot') or {}).get('end')
    if not end: return False
    import datetime as _dt
    e = _dt.datetime.fromisoformat(end).timestamp()
    return now >= e + grace and last_probe < e


def red_fast_due(kept, last_probe, now, every=180):
    """(03/11, chủ: "UC phải cập nhật nhanh") Từ lúc khung đỏ bắt đầu tới khi đã đọc được app SAU lúc hết khung: đọc mỗi 3 phút,
    để đi đủ là đỏ tắt ngay và khung không bị dời oan. Ngoài khung vẫn đọc mỗi giờ."""
    sl = (kept or {}).get('slot') or {}
    if not sl.get('start') or not sl.get('end'): return False
    import datetime as _dt
    s, e = _dt.datetime.fromisoformat(sl['start']).timestamp(), _dt.datetime.fromisoformat(sl['end']).timestamp()
    return now >= s and last_probe < e and now - last_probe >= every


def _slot_kept():
    try:
        import json; return json.loads(SLOT_FILE.read_text(encoding='utf-8'))
    except Exception: return {}


PROBE_LOG = Path(__file__).resolve().parent / 'school' / 'ictsv_probe.log'
AUTOSTART_OFF = Path(__file__).resolve().parent / 'school' / 'android_autostart.off'   # có file này -> UC chỉ báo, không tự bật máy ảo
OPEN_ANDROID = r'D:\Android\open-android.ps1'


def plog(msg):
    """(v1.00.56, 03/11) UC chạy bằng pythonw nên print không tới đâu (03/11 không chứng minh được lượt đọc nào đã chạy).
    Ghi từng lượt vào school/ictsv_probe.log; quá ~200 KB thì giữ ~100 KB cuối."""
    try:
        PROBE_LOG.parent.mkdir(parents=True, exist_ok=True)
        if PROBE_LOG.exists() and PROBE_LOG.stat().st_size > 200_000:
            PROBE_LOG.write_text(PROBE_LOG.read_text(encoding='utf-8', errors='replace')[-100_000:], encoding='utf-8')
        with PROBE_LOG.open('a', encoding='utf-8') as h: h.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
    except Exception: pass


class EmuWatch:
    """(v1.00.56, 03/11) Máy ảo sập lúc 17:29 -> cả buổi UC lặng lẽ bỏ qua lượt đọc, không ai biết.
    step() -> việc cần làm: 'down' (báo mất máy ảo), 'start' (tự bật lại), 'giveup' (thôi tự bật), 'back' (chạy lại).
    Chỉ trong 06–22h; mất quá 2 phút mới tính (adb chập chờn / đang khởi động); bật lại cách nhau >= 10 phút, tối đa 3 lần/ngày.
    Giới hạn (đi tắt): không phân biệt máy ảo SẬP với bạn TỰ TẮT -> bạn tắt ban ngày thì UC vẫn bật lại
    (tối đa 3 lần); không muốn thì tạo school/android_autostart.off."""
    GRACE, GAP, MAX = 120, 600, 3

    def __init__(self): self.since, self.alerted, self.gave_up, self.starts = None, False, False, []

    def new_day(self): self.starts, self.gave_up = [], False

    def step(self, up, now, hour, off=False):
        if up:
            back = self.alerted; self.since, self.alerted, self.gave_up = None, False, False
            return ['back'] if back else []
        if not 6 <= hour < 22: return []
        if self.since is None: self.since = now
        if now - self.since < self.GRACE: return []
        out = []
        if not self.alerted: self.alerted = True; out.append('down')
        if off: return out
        if len(self.starts) < self.MAX:
            if not self.starts or now - self.starts[-1] >= self.GAP: self.starts.append(now); out.append('start')
        elif not self.gave_up: self.gave_up = True; out.append('giveup')
        return out


def emu_act(a, off):
    plog('máy ảo: ' + a)
    if a == 'down':
        report(False, 'Máy ảo Android không chạy: UC không đọc được số bước iCTSV.'
               + ('' if off else ' UC đang tự bật lại (không muốn thì tạo school/android_autostart.off).'))
    elif a == 'start':
        subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', OPEN_ANDROID],
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    elif a == 'giveup':
        report(False, 'UC đã bật máy ảo 3 lần hôm nay mà không lên. Thôi tự bật; bạn mở shortcut "Pixel 6 (Android 14)".')
    elif a == 'back':
        report(True, 'Máy ảo Android đã chạy lại. UC đọc lại số bước iCTSV sau khoảng 2 phút.')


def loop(every=30, probe_every=3600):
    """Vòng canh trong UC (không cần ai bấm):
    - mỗi 30 s: iCTSV đang mở mà hiện màn đăng nhập -> tự đăng nhập lại;
    - mỗi giờ (06–22h): tự thử dịch vụ '10.000 bước'. Báo hết phiên -> đăng xuất + đăng nhập lại ngay;
      không rõ (trống / lỗi lạ) 2 lần liên tiếp mà mạng vẫn thông -> cũng coi là hết phiên.
    - (v1.00.56) máy ảo không chạy (06–22h) -> báo + tự bật lại (EmuWatch); mọi lượt ghi vào school/ictsv_probe.log.
    Đang khoá (lần trước bị từ chối) thì im lặng chờ bạn mở khoá."""
    last, bad = time.time() - probe_every + 600, 0   # lượt kiểm đầu: 10 phút sau khi UC chạy, không chạy ngay lúc khởi động
    last_read, pend = 0.0, None   # last_read: lần đọc app thật gần nhất; pend: khung đỏ chưa được đọc sau khi hết
    emu, day, waited = EmuWatch(), time.strftime('%Y-%m-%d'), False   # waited: đã ghi log "đến lượt nhưng bạn đang dùng máy ảo"
    plog('vòng canh iCTSV bắt đầu')
    while True:
        try:
            if time.strftime('%Y-%m-%d') != day: day = time.strftime('%Y-%m-%d'); emu.new_day()
            up, off = b'device' in adb('get-state').stdout, AUTOSTART_OFF.exists()
            for a in emu.step(up, time.time(), time.localtime().tm_hour, off):
                emu_act(a, off)
                if a == 'back': last = time.time() - probe_every + 120   # máy ảo vừa lên: chờ ~2 phút cho xong khởi động rồi đọc
            k = _slot_kept()   # walk.view ghi đè khung mới khi khung cũ qua -> giữ khung cũ tới khi đã đọc xong
            if (k.get('slot') or {}).get('end') and (not pend or not after_slot_due(pend, last_read, 1e12)): pend = k
            due = (time.time() - last >= probe_every or after_slot_due(pend, last_read, time.time())
                   or red_fast_due(k, last_read, time.time())) and 6 <= time.localtime().tm_hour < 22
            if due and up and not waited and user_busy(): plog('đến lượt đọc nhưng bạn đang dùng máy ảo -> chờ'); waited = True
            if not LOCK.exists() and not user_busy() and up:
              with UI:
                if foreground() and len(login_form(nodes())) >= 2: plog('thấy màn đăng nhập -> tự đăng nhập lại'); recover('login')
                elif due and online():
                    last = last_read = time.time(); waited = False; r = probe(); plog('đọc app: ' + r)
                    bad = bad + 1 if r == 'unknown' else 0
                    if r in ('expired', 'login') or bad >= 2: bad = 0; recover(r if r != 'unknown' else 'dịch vụ trống 2 lần')
        except Exception as e: plog('lỗi vòng canh: %r' % e)
        time.sleep(every)


def main(auto=False):
    if LOCK.exists():
        report(False, 'Tự đăng nhập iCTSV đang KHOÁ (lần trước bị từ chối). Kiểm lại mật khẩu: python ictsv_cred.py --verify'); return 2
    user, pw = ictsv_cred.get()
    if not (user and pw):
        report(False, 'Chưa cất tài khoản iCTSV. Chạy: python ictsv_cred.py'); return 2
    if b'device' not in adb('get-state').stdout:
        report(False, 'Máy ảo chưa bật (emulator-5554). Mở shortcut "Pixel 6 (Android 14)" rồi chạy lại.'); return 1
    if not auto: adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1'); time.sleep(4)
    ns = nodes()
    if logged_in(ns):
        if '--force' not in sys.argv: print('iCTSV đang đăng nhập sẵn, không làm gì.'); return 0
        print('Đăng xuất để đăng nhập lại...')
        if not logout(): report(False, 'Không tìm thấy màn đăng nhập sau khi đăng xuất. Dừng.'); return 1
        ns = nodes()
    if any(STOP_WORDS.search(n['label']) for n in ns):
        report(False, 'iCTSV đòi captcha / mã xác minh. UC dừng, bạn tự làm trong máy ảo.'); return 1
    fields = login_form(ns)
    if len(fields) < 2:
        report(False, f'Không nhận ra màn đăng nhập iCTSV (thấy {len(fields)} ô nhập). Dừng.'); return 1
    pwf = next((f for f in fields if f['pw']), fields[1])
    usf = next(f for f in fields if f is not pwf)
    print('Điền tài khoản...'); type_into(usf, user)
    print('Điền mật khẩu...'); type_into(pwf, pw)
    adb('shell', 'input', 'keyevent', 'KEYCODE_ESCAPE'); time.sleep(0.8)   # ẩn bàn phím
    ns = nodes()
    btn = next((n for n in ns if n['click'] and n['label'].lower() == 'đăng nhập'), None) \
        or next((n for n in ns if n['label'].lower() == 'đăng nhập'), None)
    if not btn: report(False, 'Không thấy nút Đăng nhập. Dừng (chưa gửi).'); return 1
    print('Bấm Đăng nhập...'); tap(btn)
    for _ in range(12):
        time.sleep(2); ns = nodes()
        if logged_in(ns): report(True, 'UC đã đăng nhập lại iCTSV thành công.'); return 0
        if any(STOP_WORDS.search(n['label']) for n in ns):
            report(False, 'iCTSV đòi captcha / mã xác minh sau khi bấm. Bạn tự làm trong máy ảo.'); return 1
    LOCK.parent.mkdir(parents=True, exist_ok=True); LOCK.write_text(time.strftime('%Y-%m-%d %H:%M'), encoding='utf-8')
    msg = next((n['label'] for n in ns if n['label'] and 'EditText' not in n['cls'] and len(n['label']) < 120
                and re.search(r'sai|không đúng|lỗi|thất bại|không tồn tại', n['label'], re.I)), '')
    report(False, 'Đăng nhập iCTSV KHÔNG thành công' + (f' ("{msg}")' if msg else '') +
           '. Đã khoá tự đăng nhập. Kiểm mật khẩu: python ictsv_cred.py --verify')
    return 1


if __name__ == '__main__':
    sys.exit(main())
