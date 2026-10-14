# -*- coding: utf-8 -*-
"""Đọc N dòng cuối trên cửa sổ console của một tiến trình ghế (Claude 14/10/2026 — viết lại: bản cũ nằm ở
thư mục UC đã mất, seat_keeper gọi vào khoảng không nên không nhận ra ghế hết quota / cần đăng nhập).

Dùng:  python peek_console.py <pid> [số dòng=15]   -> in ra chữ (UTF-8). Lỗi -> in rỗng, mã thoát 1.
Cách làm: tách khỏi console của mình -> AttachConsole(pid) -> mở CONOUT$ -> ReadConsoleOutputCharacterW các dòng quanh con trỏ.
Phải chạy thành TIẾN TRÌNH RIÊNG (seat_keeper gọi qua subprocess) vì gắn console đổi console của chính tiến trình gọi.
Chỉ ĐỌC, không gõ gì vào cửa sổ ghế."""
import ctypes, sys
from ctypes import wintypes

k32 = ctypes.WinDLL('kernel32', use_last_error=True)


class COORD(ctypes.Structure): _fields_ = [('X', wintypes.SHORT), ('Y', wintypes.SHORT)]
class SMALL_RECT(ctypes.Structure): _fields_ = [('Left', wintypes.SHORT), ('Top', wintypes.SHORT), ('Right', wintypes.SHORT), ('Bottom', wintypes.SHORT)]
class CSBI(ctypes.Structure):
    _fields_ = [('dwSize', COORD), ('dwCursorPosition', COORD), ('wAttributes', wintypes.WORD), ('srWindow', SMALL_RECT), ('dwMaximumWindowSize', COORD)]


def peek(pid, lines=15):
    k32.FreeConsole()
    if not k32.AttachConsole(wintypes.DWORD(pid)): return None
    try:
        k32.CreateFileW.restype = wintypes.HANDLE
        h = k32.CreateFileW('CONOUT$', 0x80000000 | 0x40000000, 0x1 | 0x2, None, 3, 0, None)   # GENERIC_READ|WRITE, SHARE_READ|WRITE, OPEN_EXISTING
        if not h or h == wintypes.HANDLE(-1).value: return None
        info = CSBI()
        if not k32.GetConsoleScreenBufferInfo(wintypes.HANDLE(h), ctypes.byref(info)): return None
        width = info.dwSize.X; last = info.dwCursorPosition.Y; first = max(0, last - lines + 1)
        out = []
        for y in range(first, last + 1):
            buf = ctypes.create_unicode_buffer(width + 1); n = wintypes.DWORD(0)
            k32.ReadConsoleOutputCharacterW(wintypes.HANDLE(h), buf, width, COORD(0, y), ctypes.byref(n))
            out.append(buf.value[:n.value].rstrip())
        k32.CloseHandle(wintypes.HANDLE(h))
        return '\n'.join(out).strip('\n')
    finally:
        k32.FreeConsole()


if __name__ == '__main__':
    try:
        txt = peek(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 15)
    except Exception:
        txt = None
    sys.stdout.buffer.write((txt or '').encode('utf-8'))
    sys.exit(0 if txt is not None else 1)
