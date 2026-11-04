# -*- coding: utf-8 -*-
"""(v1.00.59) Chỉ một bản UC chạy tại một lúc.

03/11 tối có hai bản copilot_app chạy song song (bộ tự khởi động lại bật bản mới khi bản cũ chưa tắt hẳn): bản không giữ
được cổng 8320 vẫn chạy đủ vòng lặp nền -> khoá máy ảo, iCTSV, thông báo... chạy đôi, hai bên ghi đè nhau.
Cách làm: mutex có tên của Windows. Bản sau chờ tối đa `wait` giây cho bản trước tắt hẳn (trường hợp khởi động lại),
quá hạn thì tự thoát. Mutex tự nhả khi tiến trình chết (kể cả bị kill), nên không có khoá treo.
Ngoài Windows (CI Ubuntu) thì bỏ qua.
"""
import sys, time

NAME = 'Local\\UniversityCopilotApp'
ERROR_ALREADY_EXISTS = 183
_held = []   # giữ handle tới hết đời tiến trình


def acquire(name=NAME, wait=90, step=3):
    """-> True nếu bản này được chạy. Gọi một lần, đầu chương trình."""
    if sys.platform != 'win32': return True
    import ctypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    t0 = time.time()
    while True:
        h = k.CreateMutexW(None, False, name)
        if h and ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
            _held.append(h); return True
        if h: k.CloseHandle(ctypes.c_void_p(h))
        if time.time() - t0 >= wait: return False
        time.sleep(step)
