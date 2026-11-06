# -*- coding: utf-8 -*-
"""(v1.00.53, chủ 02/11; luật điện thoại chủ chốt 04/11) Khoá tiến vào máy ảo Android và điện thoại thật qua adb.

Khoá máy tính (chặn tên miền + chính sách trình duyệt trên Windows) không chạm tới app trong máy ảo / điện thoại.
UC tạm khoá app bằng adb trên MỌI máy adb đang thấy (máy ảo + điện thoại cắm dây / adb qua Wi-Fi), theo 4 chế độ:
  - mặc định (mọi lúc ngoài giờ khoá)  -> khoá app mạng xã hội (lướt MXH)
  - tập trung (ví đang chạy, hoặc bạn tự bấm dừng; UC tự dừng thì như mặc định)
                                       -> + YouTube (cả ReVanced), trình duyệt, Play Store, game
  - ngủ trưa (nap_spans trong school/nap.json) -> như khoá trưa máy tính: + YouTube; chừa Messenger
  - đêm 22:00–06:00 (lõi cứng)         -> như khoá đêm máy tính: + YouTube + Messenger
Luôn chừa: LinkedIn, iCTSV, eHUST và mọi app không nằm trong nhóm nào (điện thoại, tin nhắn, báo thức, ngân hàng...).
App YouTube đã sửa (ReVanced, bỏ Shorts) chỉ chừa ở mặc định.
Danh sách riêng của từng người (game, MXH thêm) ở school/phone_apps.json: {"games": [...], "social": [...]} — không lên public.

Cách khoá: `cmd package suspend` (app vẫn còn, bấm vào chỉ hiện hộp "đã tạm dừng"); máy không cho shell suspend thì
dùng `pm disable-user`. Chỉ mở lại đúng app CHÍNH UC đã khoá (ghi theo từng máy ở school/phone_lock.json).

Giới hạn (đi tắt, ghi rõ):
  - Lướt MXH trên WEB ngoài giờ khoá: adb không chặn được theo tên miền trên máy chưa root (chặn tên miền thì app
    YouTube chết theo). Cần app lọc DNS trên máy (vd RethinkDNS) chặn facebook.com / youtube.com, loại trừ app YouTube.
  - Trong giờ khoá thì trình duyệt bị khoá cả app.
  - Điện thoại chỉ bị khoá khi laptop bật + adb thấy máy (cắm dây, hoặc adb Wi-Fi cùng mạng). App đã khoá thì GIỮ khoá
    khi mất kết nối (suspend nằm trên máy), nhưng chế độ mới (vd tới 22:00) không áp được cho tới khi nối lại.
  - Ai có adb / tự gỡ trong cài đặt nhà phát triển vẫn mở lại được. Đây là rào cho lúc lười, không phải két sắt.
"""
import datetime as dt, json, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / 'school' / 'phone_lock.json'
APPS = HERE / 'school' / 'phone_apps.json'
NAP = HERE / 'school' / 'nap.json'
ADB = r'D:\Android\Sdk\platform-tools\adb.exe'
TZ = dt.timezone(dt.timedelta(hours=7))

SOCIAL = ('com.facebook.katana', 'com.facebook.lite', 'com.instagram.android', 'com.instagram.barcelona',   # Threads
          'com.zhiliaoapp.musically', 'com.ss.android.ugc.trill', 'com.twitter.android', 'com.reddit.frontpage',
          'com.snapchat.android', 'com.discord', 'com.pinterest', 'com.tumblr', 'xyz.blueskyweb.app')
YOUTUBE = ('com.google.android.youtube', 'app.revanced.android.youtube')   # ReVanced = YouTube đã sửa của chủ (chỉ chừa ở mặc định)
MESSENGER = ('com.facebook.orca',)
BROWSERS = ('com.android.chrome', 'org.mozilla.firefox', 'com.microsoft.emmx', 'com.opera.browser', 'com.brave.browser',
            'com.sec.android.app.sbrowser', 'com.coccoc.trinhduyet', 'org.torproject.torbrowser',   # Tor: trình duyệt, không phải MXH (chủ 04/11)
            'com.google.android.googlequicksearchbox')   # app Google mở kết quả tìm kiếm bằng trình xem web riêng
STORE = ('com.android.vending', 'com.sec.android.app.samsungapps')   # chặn cài app mới trong giờ khoá
NEVER = {'com.linkedin.android', 'com.bk.ctsv', 'uni.hust.ehust', 'com.everytime.v2',   # LinkedIn, iCTSV, eHUST, Everytime (cộng đồng SV)
         'com.locket.Locket'}   # Locket: app chụp ảnh cho nhóm bạn hẹp, không lướt được (chủ 04/11) — không bao giờ khoá


def _apps_cfg():
    try: return json.loads(APPS.read_text(encoding='utf-8'))
    except Exception: return {}


def apps():
    """Danh sách riêng (game, MXH thêm) chủ đã duyệt. Không có file -> rỗng."""
    d = _apps_cfg()
    return tuple(d.get('games') or ()), tuple(d.get('social') or ())


def approved(serial):
    """Chỉ khoá máy ảo (emulator-*) và điện thoại chủ đã duyệt ("devices" trong phone_apps.json):
    cắm một máy lạ / máy bạn bè vào laptop thì UC không đụng."""
    return serial.startswith('emulator-') or serial in (_apps_cfg().get('devices') or ())


def _focus_on():
    try:
        import wallet
        a = (wallet.load() or {}).get('active') or {}
        return a.get('type') == 'focus' and (not a.get('paused_at') or wallet.by_user(a))   # UC dừng gỡ khoá; bạn tự dừng giữ khoá
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


FORCE = HERE / 'school' / 'phone_force_night.json'


CLASS = HERE / 'school' / 'phone_class_lock.json'
# (chủ 05/11) PhoneClassLock: giờ học cấm điện thoại (IT2000, giảng viên rất nghiêm) -> khoá MỌI app có biểu tượng, chỉ chừa:
CLASS_ALLOW = {'vn.uc.app', 'com.tailscale.ipn', 'com.samsung.android.dialer', 'com.google.android.dialer',
               'com.sec.android.app.launcher', 'com.sec.android.app.clockpackage'}   # UC (để mở khoá), Tailscale (đường adb), gọi điện, màn hình chính, báo thức
# mở trước khi hết giờ: camera / app trường / trình duyệt (để điểm danh ngay)
CLASS_FIRST = ('com.sec.android.app.camera', 'com.bk.ctsv', 'uni.hust.ehust', 'com.android.chrome', 'com.zing.zalo')


def class_until(now=None):
    """Khoá giờ học đang bật tới lúc nào (datetime) hoặc None. Mở sớm chỉ bằng MSSV nhập 2 lần (copilot_app /api/class-lock)."""
    try:
        u = dt.datetime.fromisoformat(json.loads(CLASS.read_text(encoding='utf-8'))['until'])
        return u if (now or dt.datetime.now(TZ)) < u else None
    except Exception: return None


def launchable(serial):
    rc, out = adb(serial, 'shell', 'cmd', 'package', 'query-activities', '--brief', '-a', 'android.intent.action.MAIN',
                  '-c', 'android.intent.category.LAUNCHER', timeout=40)
    return {l.strip().split('/')[0] for l in out.splitlines() if '/' in l} if rc == 0 else set()


def _forced_night(now):
    """school/phone_force_night.json {"until": ISO} -> khoá đêm cho điện thoại tới giờ đó (tự hết hạn)."""
    try: return now < dt.datetime.fromisoformat(json.loads(FORCE.read_text(encoding='utf-8'))['until'])
    except Exception: return False


def mode(now=None, focus=None, nap=None):
    """-> 'night' | 'nap' | 'focus' | 'default'."""
    now = now or dt.datetime.now(TZ)
    hm = now.strftime('%H:%M')
    if hm >= '22:00' or hm < '06:00': return 'night'
    if class_until(now): return 'class'   # (05/11) khoá giờ học: cao nhất ban ngày
    if _forced_night(now): return 'night'   # (chủ 05/11) khoá đêm tạm cho điện thoại (giờ học cấm dùng điện thoại)
    if (_nap_on(now) if nap is None else nap): return 'nap'
    if (_focus_on() if focus is None else focus): return 'focus'
    return 'default'


def wanted(m, installed, games=(), social=()):
    """Các gói cần khoá ở chế độ m, chỉ trong số đang cài."""
    # (chủ 04/11) trình duyệt thường KHÔNG tạm dừng nữa (đi qua laptop để chặn theo tên miền); riêng Tor khoá cứng vì lách được mọi chặn tên miền
    tor = ('org.torproject.torbrowser',)
    yt = ('com.google.android.youtube',)   # (chủ 04/11) app YouTube gốc có Shorts -> khoá; xem bằng ReVanced là đủ
    groups = {'default': SOCIAL + social + yt,
              'focus': SOCIAL + social + tor + STORE + games + YOUTUBE,   # (chủ 05/11) tập trung: ReVanced cũng khoá (xem Shorts chế trong giờ tập trung)
              'nap': SOCIAL + social + tor + STORE + games + YOUTUBE,
              'night': SOCIAL + social + tor + STORE + games + YOUTUBE + MESSENGER}.get(m or 'default', ())
    return {p for p in groups if p in installed} - NEVER


def adb(serial, *a, timeout=20):
    try:
        r = subprocess.run([ADB, *(['-s', serial] if serial else []), *a], capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.returncode, r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
    except Exception as e: return -1, str(e)


def devices():
    """Các máy adb đang sẵn sàng (bỏ máy 'unauthorized' / 'offline')."""
    rc, out = adb(None, 'devices', timeout=10)
    return [l.split('\t')[0] for l in out.splitlines()[1:] if l.endswith('\tdevice')] if rc == 0 else []


def installed(serial):
    rc, out = adb(serial, 'shell', 'pm', 'list', 'packages')
    return {l[8:].strip() for l in out.splitlines() if l.startswith('package:')} if rc == 0 else None


_recon = [0.0]


def reconnect(now=None, every=600):
    """(chủ 06/11) Điện thoại thật rớt adb (mất mạng, hoặc chủ TỰ tắt gỡ lỗi khi dùng app ngân hàng — app NH ngừng phục vụ nếu thấy
    gỡ lỗi bật) -> UC tự thử nối lại mỗi 10 phút. CHỈ gọi 'adb connect' tới địa chỉ Tailscale của điện thoại (phone_apps.json 'adb_addr');
    KHÔNG BAO GIỜ đụng công tắc gỡ lỗi. Gỡ lỗi đang tắt -> connect fail vô hại; chủ bật lại -> trong 10 phút tự nối. Thiếu 'adb_addr' -> bỏ qua."""
    addr = _apps_cfg().get('adb_addr') or ''
    if not addr or addr in devices(): return None   # chưa cấu hình, hoặc đang nối sẵn
    t = (now or dt.datetime.now(TZ)).timestamp()
    if t - _recon[0] < every: return None            # mới thử dưới 10 phút
    _recon[0] = t
    adb(None, 'disconnect', addr, timeout=10)         # dọn mục offline cũ
    rc, out = adb(None, 'connect', addr, timeout=15)
    ok = 'connected' in out.lower()
    log(f'adb reconnect {addr}: ' + ('ok' if ok else 'chưa được (gỡ lỗi tắt / mất mạng)'))
    return ok


def _load():
    try: st = json.loads(STATE.read_text(encoding='utf-8'))
    except Exception: st = {}
    if 'locked' in st and 'devices' not in st:   # dạng cũ (chỉ máy ảo) -> chuyển sang theo từng máy
        st = {'devices': {'emulator-5554': {'locked': st['locked']}}}
    st.setdefault('devices', {})
    return st


def _save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')


def lock(serial, pkg):
    """-> 'suspend' | 'disable' | None. force-stop trước để app đang mở bị đóng ngay."""
    adb(serial, 'shell', 'am', 'force-stop', pkg)
    rc, out = adb(serial, 'shell', 'cmd', 'package', 'suspend', '--user', '0', pkg)
    if rc == 0 and 'new suspended state: true' in out.lower(): return 'suspend'
    rc, out = adb(serial, 'shell', 'pm', 'disable-user', '--user', '0', pkg)
    return 'disable' if rc == 0 and 'disabled' in out.lower() else None


def unlock(serial, pkg, how):
    if how == 'suspend': rc, _ = adb(serial, 'shell', 'cmd', 'package', 'unsuspend', '--user', '0', pkg)
    else: rc, _ = adb(serial, 'shell', 'pm', 'enable', '--user', '0', pkg)
    return rc == 0


# (chủ 04/11) PhoneLock: 4 khoá của điện thoại, mỗi khoá NEO vào khoá tương ứng của máy tính (cùng nguồn tín hiệu, không tự đặt giờ):
#   PhoneDefaultLock luôn bật · PhoneFocusLock theo khoá tập trung (ví) · PhoneNapLock theo NapLock (school/nap.json)
#   · PhoneNightLock theo NightLock (22:00–06:00). Khoá sau bao trùm khoá trước, nên chặn = khoá cao nhất đang bật.
LOCK_NAME = {'class': 'PhoneClassLock', 'default': 'PhoneDefaultLock', 'focus': 'PhoneFocusLock', 'nap': 'PhoneNapLock', 'night': 'PhoneNightLock'}
def set_exit(serial, on):
    """(04/11, chủ duyệt) Trong giờ khoá điện thoại đi qua laptop (Tailscale exit node) -> ăn chặn tên miền của laptop.
    Bật / tắt exit node trên app Tailscale của điện thoại (lệnh USE_EXIT_NODE, app nhận từ adb — đã thử 04/11).
    Tên máy laptop trong tailnet: "exit_node" ở phone_apps.json (riêng từng người); thiếu -> không đổi đường đi.
    Đi qua laptop chậm hơn (~225 ms so với ~58 ms) nên chỉ bật trong giờ khoá. Lưu ý: app phải TẮT "Run as exit node"."""
    node = _apps_cfg().get('exit_node') or ''
    if not node: return False
    rc, out = adb(serial, 'shell', 'am', 'broadcast', '-a', 'com.tailscale.ipn.USE_EXIT_NODE', '-n', 'com.tailscale.ipn/.IPNReceiver',
                  '--es', 'exitNode', node if on else "''", '--ez', 'allowLanAccess', 'true')   # '' rỗng bị adb nuốt -> phải gửi cặp nháy
    return rc == 0


def tick(now=None, m='auto'):
    """Một lượt trên mọi máy: khoá app còn thiếu, mở app hết giờ khoá. -> dict báo cáo (không gửi thông báo)."""
    ds = devices()
    if not ds: return {'device': False}
    m = mode(now) if m == 'auto' else m
    games, social = apps()
    st, done = _load(), {'mode': m, 'locked': [], 'unlocked': [], 'failed': []}
    # (chủ 04/11 ~12:40) PhoneLock = bộ chặn RIÊNG của điện thoại, KHÔNG đi qua Tailscale nữa: exit node luôn tắt.
    # set_exit giữ lại để trả điện thoại về đường thường nếu trước đó đang bật.
    phones = [s for s in ds if approved(s) and not s.startswith('emulator-')]
    # (chủ 04/11 ~12:50 "áp dụng khi có lock") Focus/Nap/Night: điện thoại đi qua laptop (exit node) -> trình duyệt vẫn dùng được,
    # chỉ tên miền máy tính đang chặn là không vào được; ngoài giờ khoá thì đi thẳng.
    ex = st.setdefault('exit', {}); want_exit = False   # (chủ 06/11) exit node làm mất split DNS: bật lên thì web YouTube / Facebook MỞ (đo thật 06/11). Luôn tắt, chặn web chỉ dựa vào PhoneDNS
    t = (now or dt.datetime.now(TZ)).timestamp()
    if phones and (ex.get('on') != want_exit or t - ex.get('at', 0) > 600):
        if set_exit(phones[0], want_exit): ex.update(on=want_exit, at=t); done['exit_node'] = want_exit
    done['khoa'] = LOCK_NAME.get(m, m)
    for s in ds:
        if not approved(s): continue
        inst = installed(s)
        if inst is None: continue
        mine = st['devices'].setdefault(s, {'locked': {}})['locked']
        want = wanted(m, inst, games, social)
        if m == 'class':   # (05/11) khoá theo lô: 1 lệnh adb cho cả trăm app (từng app một mất vài phút)
            want = (want | launchable(s)) - CLASS_ALLOW - NEVER
            new = sorted(want - set(mine))
            if new:
                for p in new: adb(s, 'shell', 'am', 'force-stop', p, timeout=10) if p in ('com.android.chrome',) else None
                rc, out = adb(s, 'shell', 'cmd', 'package', 'suspend', '--user', '0', *new, timeout=120)
                # dòng kết quả: "Package <tên> new suspended state: true"
                ok = {l.split()[1] for l in out.splitlines() if l.lower().startswith('package ') and 'new suspended state: true' in l.lower()}
                for p in new:
                    if p in ok: mine[p] = 'suspend'; done['locked'].append(f'{s}:{p}')
                    else: done['failed'].append(f'{s}:{p}')
            continue
        lot = sorted([p for p in set(mine) - want if mine[p] == 'suspend' and p in inst], key=lambda p: (p not in CLASS_FIRST, p))
        if len(lot) > 5:   # (05/11) mở theo lô (hết khoá giờ học): ưu tiên camera / app trường trước, rồi phần còn lại 1 lệnh
            first = [p for p in lot if p in CLASS_FIRST]
            for part in (first, [p for p in lot if p not in CLASS_FIRST]):
                if part and adb(s, 'shell', 'cmd', 'package', 'unsuspend', '--user', '0', *part, timeout=120)[0] == 0:
                    for p in part: mine.pop(p); done['unlocked'].append(f'{s}:{p}')
        for p in sorted(want - set(mine)):
            how = lock(s, p)
            if how: mine[p] = how; done['locked'].append(f'{s}:{p}')
            else: done['failed'].append(f'{s}:{p}')
        for p in sorted(set(mine) - want):
            if p not in inst or unlock(s, p, mine[p]): mine.pop(p); done['unlocked'].append(f'{s}:{p}')
            else: done['failed'].append(f'{s}:{p}')
    st['mode'], st['at'] = m, (now or dt.datetime.now(TZ)).isoformat(timespec='seconds')
    _save(st)
    return done


LOG = HERE / 'school' / 'phone_lock.log'


def log(msg, now=None):
    """(v1.00.59) UC chạy bằng pythonw nên print mất hết -> ghi nhật ký để kiểm được khoá có chạy thật (vd đêm qua)."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as f: f.write(f"{(now or dt.datetime.now(TZ)).isoformat(timespec='seconds')} {msg}\n")
    except Exception: pass


def loop(every=60):
    """Vòng canh trong UC: mỗi phút. Không thấy máy nào thì bỏ qua (nối lại thì lượt kế tiếp tự khoá đúng).
    Nhật ký: mỗi lần khoá / mở / lỗi, và mỗi lần chế độ hoặc trạng thái máy đổi (không ghi mỗi phút)."""
    last = None
    while True:
        try:
            reconnect()   # (chủ 06/11) điện thoại rớt adb -> thử nối lại mỗi 10 phút (không đụng gỡ lỗi)
            r = tick()
            key = (r.get('device', True), r.get('mode'), tuple(devices()))
            if r.get('locked') or r.get('unlocked') or r.get('failed') or key != last:
                log(json.dumps({**r, 'devices': list(key[2])}, ensure_ascii=False)); last = key
        except Exception as e: log(f'loi: {e}')
        u = class_until()
        left = (u - dt.datetime.now(TZ)).total_seconds() if u else every
        time.sleep(max(1, min(every, left + 1)))   # (05/11) hết khoá giờ học thì mở NGAY, không chờ tới phút sau


if __name__ == '__main__':
    import sys
    if '--mode' in sys.argv: print(mode())
    else: print(json.dumps(tick(), ensure_ascii=False, indent=1))
