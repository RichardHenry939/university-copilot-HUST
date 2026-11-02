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
            import walk_app; walk_app.save(walk_app.read_page(nodes, adb))
        except Exception as e: print('walk_app:', e)
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


def loop(every=30, probe_every=3600):
    """Vòng canh trong UC (không cần ai bấm):
    - mỗi 30 s: iCTSV đang mở mà hiện màn đăng nhập -> tự đăng nhập lại;
    - mỗi giờ (06–22h): tự thử dịch vụ '10.000 bước'. Báo hết phiên -> đăng xuất + đăng nhập lại ngay;
      không rõ (trống / lỗi lạ) 2 lần liên tiếp mà mạng vẫn thông -> cũng coi là hết phiên.
    Đang khoá (lần trước bị từ chối) thì im lặng chờ bạn mở khoá."""
    last, bad = 0.0, 0
    while True:
        try:
            if not LOCK.exists() and b'device' in adb('get-state').stdout:
              with UI:
                if foreground() and len(login_form(nodes())) >= 2: recover('login')
                elif time.time() - last >= probe_every and 6 <= time.localtime().tm_hour < 22 and online():
                    last = time.time(); r = probe(); print('ictsv probe:', r)
                    bad = bad + 1 if r == 'unknown' else 0
                    if r in ('expired', 'login') or bad >= 2: bad = 0; recover(r if r != 'unknown' else 'dịch vụ trống 2 lần')
        except Exception as e: print('ictsv_login loop:', e)
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
