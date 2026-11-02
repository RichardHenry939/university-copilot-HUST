# -*- coding: utf-8 -*-
"""(v1.00.49) Màn hình nền khi tập trung + số màn hình cho trang /widget (hình nền Lively).

- monitors(): số màn hình đang cắm (trang /widget đổi bố cục: chỉ laptop -> chỉ đồng hồ).
- loop(): mỗi 20 s. Đang tập trung (không tạm dừng) VÀ chỉ có 1 màn -> ẩn icon màn hình nền; hết tập trung
  hoặc cắm màn rời -> hiện lại. Chỉ hiện lại icon mà CHÍNH UC đã ẩn (cờ school/icons_hidden_by_uc), không
  đụng khi bạn tự ẩn. Dùng đúng lệnh "Hiện icon màn hình nền" của Explorer (WM_COMMAND 0x7402), không sửa registry.
Giới hạn: Explorer khởi động lại lúc đang ẩn thì icon tự hiện lại -> vòng sau UC ẩn tiếp (chậm tối đa 20 s).
"""
import ctypes, time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLAG = HERE / 'school' / 'icons_hidden_by_uc'
u32 = ctypes.windll.user32 if hasattr(ctypes, 'windll') else None


def monitors():
    return u32.GetSystemMetrics(80) if u32 else 1   # SM_CMONITORS


def _defview():
    """Cửa sổ SHELLDLL_DefView của màn hình nền (nằm dưới Progman, hoặc dưới WorkerW khi có hình nền động)."""
    found = []
    def cb(h, _):
        d = u32.FindWindowExW(h, None, 'SHELLDLL_DefView', None)
        if d: found.append(d); return False
        return True
    v = u32.FindWindowExW(u32.FindWindowW('Progman', None), None, 'SHELLDLL_DefView', None)
    if v: return v
    u32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found[0] if found else None


def icons_visible():
    d = _defview()
    lv = d and u32.FindWindowExW(d, None, 'SysListView32', None)
    return bool(lv and u32.IsWindowVisible(lv))


def set_icons(show):
    d = _defview()
    if d and icons_visible() != show:
        u32.SendMessageW(d, 0x0111, 0x7402, 0)   # WM_COMMAND: bật/tắt "Hiện icon màn hình nền"


def _focusing():
    import wallet
    a = (wallet.load() or {}).get('active') or {}
    return a.get('type') == 'focus' and not a.get('paused_at')


def tick():
    want_hide = _focusing() and monitors() == 1
    if want_hide and icons_visible():
        set_icons(False); FLAG.parent.mkdir(parents=True, exist_ok=True); FLAG.write_text('1')
    elif not want_hide and FLAG.exists():
        set_icons(True); FLAG.unlink(missing_ok=True)


def loop(every=20):
    while True:
        try: tick()
        except Exception as e: print('desktop_icons:', e)
        time.sleep(every)
