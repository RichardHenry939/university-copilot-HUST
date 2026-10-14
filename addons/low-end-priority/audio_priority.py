# -*- coding: utf-8 -*-
"""🎙️ LUẬT TỐI CAO (chủ dự án, 12/10/2026): tiếng đi qua loa "CABLE Input" (Teams -> máy ghi) được ưu tiên tuyệt đối —
GPU có AI chạy hay việc gì đi nữa cũng phải NHƯỜNG ĐƯỜNG.

Vì sao (đo 12/10 09:48–10:00, buổi Giải tích): Teams đẩy tiếng vào cáp ảo liên tục (0 s im lặng ở cả CABLE Input lẫn CABLE Output),
nhưng máy ghi chỉ lấy được ~một nửa (28,9 s / 60 s là số 0) khi máy bận -> nghe trên laptop bị đứt. Nâng máy ghi lên ưu tiên Cao +
hạ model AI xuống Thấp nhất -> 0 s số 0 ngay lập tức.

Vòng lặp (UC gọi mỗi 5 giây): máy ghi đang ghi -> LectureRecorderCompanion = HIGH, mọi tiến trình AI nặng (llama-server, lms) = IDLE.
Dừng ghi -> trả về NORMAL. Không giết, không tạm dừng tiến trình nào — chỉ đổi mức ưu tiên (đổi lại được bất cứ lúc nào).
Các việc AI khác tự CHỜ khi đang ghi: cổng chép lời (speech_gate), cuộc thi Local AI + bộ chạy Qwen (ram_gate).

(12/10, chủ dự án) Máy sau này là HOMELAB BÁN THỜI GIAN mà vẫn dùng để học -> 4 bậc, ÁP MỌI LÚC (không chỉ khi đang ghi),
sửa trong school/audio_priority.json (không cần sửa code):
  hoc          (cao nhất)          -> HIGH          máy ghi bài giảng
  binh_thuong  (học trên web)      -> NORMAL        Chrome (MOOC, FAMI…), Edge, Teams — giữ đúng mức bình thường, không bị hạ
  homelab      (nhường đường)      -> BELOW_NORMAL  Docker/WSL (vmmemWSL). Thêm máy chủ homelab mới vào đây
  ai           (thấp nhất)         -> IDLE khi đang ghi (+2 phút), lúc khác BELOW_NORMAL (13/10)   llama-server (LM Studio: UC, cuộc thi, Qwen)
Tiến trình hệ thống từ chối đổi ưu tiên -> bỏ qua, không lỗi."""
import ctypes, json, urllib.request
from ctypes import wintypes

RECORDER = 'http://127.0.0.1:5681/health'
HIGH, NORMAL, IDLE, BELOW = 0x80, 0x20, 0x40, 0x4000
CFG = __import__('pathlib').Path(__file__).resolve().parent / 'school' / 'audio_priority.json'
DEFAULT = {'hoc': ['LectureRecorderCompanion.exe'], 'binh_thuong': ['chrome.exe', 'msedge.exe', 'ms-teams.exe'], 'homelab': ['vmmemWSL'], 'ai': ['llama-server.exe']}
GROUPS = (('hoc', HIGH), ('binh_thuong', NORMAL), ('homelab', BELOW), ('ai', IDLE))


def groups():
    """Đọc school/audio_priority.json (tạo bản mặc định nếu chưa có). Tên tiến trình so không phân biệt hoa thường."""
    try: g = json.loads(CFG.read_text(encoding='utf-8'))
    except Exception:
        g = dict(DEFAULT)
        try: CFG.write_text(json.dumps({'_ghi_chu': 'Luật của chủ dự án (áp mọi lúc): hoc=HIGH > binh_thuong=NORMAL > homelab=BELOW_NORMAL > ai=IDLE. Thêm tên .exe vào nhóm.', **g}, ensure_ascii=False, indent=1), encoding='utf-8')
        except Exception: pass
    return {k: {x.lower() for x in g.get(k, DEFAULT[k])} for k in DEFAULT}   # khoá thiếu trong file -> dùng mặc định
_state = {'recording': None}

k32 = ctypes.windll.kernel32


class PE(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_void_p),
                ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260)]


def _procs(names):
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    e = PE(); e.dwSize = ctypes.sizeof(PE); out = []
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        if e.szExeFile.lower() in names or e.szExeFile.lower().removesuffix('.exe') in names: out.append(e.th32ProcessID)
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def _set(pids, cls):
    for pid in pids:
        h = k32.OpenProcess(0x0200 | 0x0400, False, pid)   # PROCESS_SET_INFORMATION | QUERY_INFORMATION
        if h:
            if k32.GetPriorityClass(h) != cls: k32.SetPriorityClass(h, cls)
            k32.CloseHandle(h)


def recording():
    try:
        with urllib.request.urlopen(RECORDER, timeout=3) as r: return bool(json.loads(r.read()).get('recording'))
    except Exception:
        return False


HOLD_S = 120   # bộ chuyển: dừng ghi xong vẫn giữ AI ở IDLE thêm 2 phút, tránh bật/tắt liên tục khi máy ghi ngắt quãng


def tick():
    """Áp 4 bậc MỌI LÚC (12/10, chủ dự án). Mỗi vòng áp lại: tiến trình mới mở cũng vào đúng bậc ngay.
    (13/10, chủ dự án) BỘ CHUYỂN cho bậc AI: đang ghi (hoặc vừa dừng < HOLD_S) -> IDLE; còn lại -> BELOW_NORMAL (ngang homelab),
    vì IDLE cả ngày làm chép lời bị đói CPU (0,02 token/s). Máy ghi tự lên HIGH ngay lúc mở, nên 5 giây chờ vòng lặp không mất tiếng."""
    import time
    rec = recording(); now = time.monotonic()
    if rec: _state['last_rec'] = now
    ai_cls = IDLE if rec or now - _state.get('last_rec', -1e9) < HOLD_S else BELOW
    g = groups()
    for name, cls in GROUPS: _set(_procs(g.get(name, set())), ai_cls if name == 'ai' else cls)
    _state['recording'] = rec; _state['ai'] = 'IDLE' if ai_cls == IDLE else 'BELOW_NORMAL'
    return rec
