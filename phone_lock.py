# -*- coding: utf-8 -*-
"""(v1.00.53, chủ 02/11 — việc A2 dời từ v1.00.52) Khoá tiến vào máy ảo Android (emulator-5554), sau này điện thoại thật.

Khoá máy tính (chặn tên miền + chính sách trình duyệt trên Windows) không chạm tới app trong máy ảo / điện thoại.
UC tự tạm khoá app mạng xã hội trong máy ảo bằng adb, đúng lúc máy tính đang khoá:
  - đêm 22:00–06:00 (lõi cứng, không cần tín hiệu)        -> khoá SOCIAL + YOUTUBE + BROWSERS + STORE
  - ngủ trưa: phần vàng trong school/nap.json (nap_spans)  -> như đêm
  - tập trung (ví đang chạy, kể cả pause tay; dừng bắt buộc vì thể dục thì KHÔNG) -> như đêm, TRỪ YouTube
Không bao giờ đụng: Messenger, iCTSV (com.bk.ctsv), eHUST (uni.hust.ehust), app hệ thống ngoài danh sách.

Cách khoá: `cmd package suspend` (app vẫn còn, bấm vào chỉ hiện hộp "đã tạm dừng"); máy không cho shell suspend thì
dùng `pm disable-user`. Chỉ mở lại đúng app CHÍNH UC đã khoá (ghi ở school/phone_lock.json) -> app bạn tự tắt vẫn tắt.

Giới hạn (đi tắt, ghi rõ):
  - Trình duyệt bị khoá cả app trong giờ khoá (kể cả lúc tập trung) vì chưa chặn được theo tên miền trong máy ảo
    (Play Store image không root -> không sửa được hosts của Android). Làm lại khi có cách chặn DNS riêng cho máy ảo.
  - YouTube lúc tập trung: chừa cả app nên Shorts trong app vẫn lọt (app không tách Shorts ra được).
  - Game: chỉ khoá gói có trong GAMES (chưa tự nhận diện game). Thêm tên gói vào đây khi cài game mới.
  - Ai có adb vẫn tự mở lại được (`cmd package unsuspend`). Đây là rào cho lúc lười, không phải két sắt.
"""
import datetime as dt, json, subprocess, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / 'school' / 'phone_lock.json'
NAP = HERE / 'school' / 'nap.json'
ADB = r'D:\Android\Sdk\platform-tools\adb.exe'
SERIAL = 'emulator-5554'
TZ = dt.timezone(dt.timedelta(hours=7))

SOCIAL = ('com.facebook.katana', 'com.facebook.lite', 'com.instagram.android', 'com.instagram.barcelona',   # Threads
          'com.zhiliaoapp.musically', 'com.ss.android.ugc.trill', 'com.twitter.android', 'com.reddit.frontpage',
          'com.snapchat.android', 'com.discord', 'com.pinterest', 'com.tumblr', 'xyz.blueskyweb.app')
YOUTUBE = ('com.google.android.youtube',)
BROWSERS = ('com.android.chrome', 'org.mozilla.firefox', 'com.microsoft.emmx', 'com.opera.browser', 'com.brave.browser',
            'com.sec.android.app.sbrowser', 'com.coccoc.trinhduyet',
            'com.google.android.googlequicksearchbox')   # app Google mở kết quả tìm kiếm bằng trình xem web riêng
STORE = ('com.android.vending',)   # chặn cài app mới trong giờ khoá
GAMES = ()
NEVER = {'com.facebook.orca', 'com.bk.ctsv', 'uni.hust.ehust'}   # Messenger, iCTSV, eHUST: không bao giờ khoá


def _focus_on():
    try:
        import wallet
        a = (wallet.load() or {}).get('active') or {}
        return a.get('type') == 'focus' and not a.get('forced')   # pause tay giữ khoá; dừng bắt buộc (thể dục) gỡ hết (chủ 03/11)
    except Exception: return False


def _nap_on(now):
    """Đang trong phần vàng ngủ trưa. Tín hiệu cũ > 10 phút / sai ngày -> không khoá trưa (giống phía máy tính)."""
    try:
        d = json.loads(NAP.read_text(encoding='utf-8'))
        if d.get('date') != now.date().isoformat(): return False
        if (now - dt.datetime.fromisoformat(d['at'])).total_seconds() > 600: return False
        hm = now.strftime('%H:%M')
        return any(a <= hm < b for a, b in d.get('nap_spans') or [])
    except Exception: return False


def mode(now=None, focus=None, nap=None):
    """-> 'night' | 'nap' | 'focus' | None (không khoá)."""
    now = now or dt.datetime.now(TZ)
    hm = now.strftime('%H:%M')
    if hm >= '22:00' or hm < '06:00': return 'night'
    if (_nap_on(now) if nap is None else nap): return 'nap'
    if (_focus_on() if focus is None else focus): return 'focus'
    return None


def wanted(m, installed):
    """Các gói cần khoá ở chế độ m, chỉ trong số đang cài."""
    if not m: return set()
    groups = SOCIAL + BROWSERS + STORE + GAMES + (YOUTUBE if m != 'focus' else ())
    return {p for p in groups if p in installed} - NEVER


def adb(*a, timeout=20):
    try:
        r = subprocess.run([ADB, '-s', SERIAL, *a], capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.returncode, r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
    except Exception as e: return -1, str(e)


def installed():
    rc, out = adb('shell', 'pm', 'list', 'packages')
    return {l[8:].strip() for l in out.splitlines() if l.startswith('package:')} if rc == 0 else None


def _load():
    try: return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception: return {'locked': {}}


def _save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')


def lock(pkg):
    """-> 'suspend' | 'disable' | None. force-stop trước để app đang mở bị đóng ngay."""
    adb('shell', 'am', 'force-stop', pkg)
    rc, out = adb('shell', 'cmd', 'package', 'suspend', '--user', '0', pkg)
    if rc == 0 and 'new suspended state: true' in out.lower(): return 'suspend'
    rc, out = adb('shell', 'pm', 'disable-user', '--user', '0', pkg)
    return 'disable' if rc == 0 and 'disabled' in out.lower() else None


def unlock(pkg, how):
    if how == 'suspend': rc, _ = adb('shell', 'cmd', 'package', 'unsuspend', '--user', '0', pkg)
    else: rc, _ = adb('shell', 'pm', 'enable', '--user', '0', pkg)
    return rc == 0


def tick(now=None, m='auto'):
    """Một lượt: khoá app còn thiếu, mở app hết giờ khoá. -> dict báo cáo (không gửi thông báo)."""
    rc, out = adb('get-state', timeout=8)
    if 'device' not in out: return {'device': False}
    inst = installed()
    if inst is None: return {'device': False}
    m = mode(now) if m == 'auto' else m
    want, st = wanted(m, inst), _load()
    done = {'mode': m, 'locked': [], 'unlocked': [], 'failed': []}
    for p in sorted(want - set(st['locked'])):
        how = lock(p)
        if how: st['locked'][p] = how; done['locked'].append(p)
        else: done['failed'].append(p)
    for p in sorted(set(st['locked']) - want):
        if p not in inst or unlock(p, st['locked'][p]): st['locked'].pop(p); done['unlocked'].append(p)
        else: done['failed'].append(p)
    st['mode'], st['at'] = m, (now or dt.datetime.now(TZ)).isoformat(timespec='seconds')
    _save(st)
    return done


def loop(every=60):
    """Vòng canh trong UC: mỗi phút. Máy ảo tắt thì bỏ qua (khi bật lại, lượt kế tiếp tự khoá đúng)."""
    while True:
        try:
            r = tick()
            if r.get('locked') or r.get('unlocked') or r.get('failed'): print('phone_lock:', r)
        except Exception as e: print('phone_lock loop:', e)
        time.sleep(every)


if __name__ == '__main__':
    import sys
    if '--mode' in sys.argv: print(mode())
    else: print(json.dumps(tick(), ensure_ascii=False, indent=1))
