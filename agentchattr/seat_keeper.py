"""Giữ 4 ghế hội đồng AgentChattr luôn có mặt (Claude 2026-10-02).

Mỗi 20 giây:
  - máy chủ phòng chat (8300) chết -> bật lại (launcher_w.py);
  - ghế nào không có wrapper đang chạy -> bật lại bằng windows/start_<ghế>.bat trong cửa sổ console thu nhỏ
    (wrapper BẮT BUỘC chạy trong console thật vì AgentChattr gõ phím vào console);
  - đọc chữ trên console của từng ghế: thấy báo hết quota / cần đăng nhập -> ghi data/seat_status.json
    để phòng chat hiện ghế đó là OFF kèm lý do (không biến mất).
  - ghế bật hỏng -> thử lại giãn dần 2, 4, 8, tối đa 10 phút, ghi lý do;
  - nút Bat 4 ghe AI (--kick): quét ghế nào đã có thì bỏ qua, ghế thiếu thì bật NGAY (bỏ mọi thời gian chờ).

Chạy:  pythonw seat_keeper.py            (chạy nền mãi)
       python  seat_keeper.py --kick     (nút Bat 4 ghe AI)
       python  seat_keeper.py --once --dry-run   (in ra quyết định, không làm gì)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SEAT_FILE = DATA / "seat_status.json"
LOG = ROOT / "seat-keeper.log"
PEEK = ROOT / "peek_console.py"   # (14/10) bản cũ ở thư mục UC đã mất -> đọc console ghế im lặng trả rỗng (không nhận ra hết quota)
PYW = os.environ.get("AC_PYTHONW") or shutil.which("pythonw") or "pythonw"   # pythonw của Python hệ thống (máy chủ phòng chat)
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

SEATS = {"claude": "start_claude.bat", "codex": "start_codex.bat",
         "gemini": "start_gemini.bat", "local": "start_local.bat"}  # Kimi đã bỏ (2026-10-02)
LABEL = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini", "local": "Local AI"}

# Chữ trên console -> trạng thái. Chỉ xét ~15 dòng cuối để thông báo cũ trôi đi thì tự hết.
QUOTA_RE = re.compile(r"usage limit|hit your (usage )?limit|quota|RESOURCE_EXHAUSTED|rate.?limit|\b429\b|"
                      r"insufficient (balance|credit)|limit will reset|try again (at|in)|out of credits", re.I)
LOGIN_RE = re.compile(r"LLM not set|send /login|please (log ?in|sign ?in)|not (logged|signed) in|"
                      r"invalid api key|unauthori[sz]ed|\b401\b|authentication (failed|required)|Login with Google", re.I)

INTERVAL = 20
BOOT_GRACE = 150          # giây chờ ghế mới bật kịp đăng ký trước khi tính là hỏng
MAX_BACKOFF = 600         # bật hỏng thì thử lại sau 2, 4, 8, rồi tối đa 10 phút
KICK = DATA / "seat_kick" # nút Bat 4 ghe AI tạo file này -> bộ giữ ghế bật ngay ghế thiếu

ENV = dict(os.environ)
ENV["PATH"] = ENV.get("PATH", "") + os.path.expandvars(r";%USERPROFILE%\.local\bin;") + os.path.expandvars(r"%APPDATA%\npm") + \
    os.path.expandvars(r";%LOCALAPPDATA%\Microsoft\WinGet\Links;") + r";C:\Program Files\nodejs"


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if sys.stdout:
        try:
            print(line)
        except Exception:
            pass


def port_up(port):
    import socket
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


_token_ok = ""


def session_tokens():
    """Cac token gan nhat trong log, moi nhat truoc. (Claude 2026-10-03) Khi khoi dong may, 2 script cung bat
    server -> ban thu 2 khong chiem duoc cong va tu tat nhung VAN in token cua no SAU CUNG -> token cuoi trong
    log co the la cua server da chet (keeper bi 403 mai, khong an duoc cua so, Codex khong nhan Enter)."""
    try:
        text = (ROOT / "ac-stdout.log").read_text(encoding="utf-8", errors="replace")
        return list(dict.fromkeys(reversed(re.findall(r"Session token: ([0-9a-f]+)", text))))[:6]
    except OSError:
        return []


def get_status():
    global _token_ok
    cands = ([_token_ok] if _token_ok else []) + [t for t in session_tokens() if t != _token_ok]
    err = None
    for tok in cands or [""]:
        req = urllib.request.Request("http://127.0.0.1:8300/api/status", headers={"x-session-token": tok})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
            _token_ok = tok
            return data
        except urllib.error.HTTPError as e:
            if e.code != 403:
                raise
            err = e
    raise err


def wrapper_pids():
    """{ghế: [pid của python wrapper.py <ghế>]}"""
    out = {s: [] for s in SEATS}
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
            if not p.info["name"] or "python" not in p.info["name"].lower():
                continue
            if any(c.endswith(("wrapper.py", "wrapper_api.py")) for c in cmd):
                i = next(i for i, c in enumerate(cmd) if c.endswith(("wrapper.py", "wrapper_api.py")))
                if i + 1 < len(cmd) and cmd[i + 1] in out:
                    out[cmd[i + 1]].append(p.info["pid"])
        except (psutil.Error, StopIteration):
            continue
    return out


def console_text(pid, lines=15):
    try:
        r = subprocess.run([PY, str(PEEK), str(pid), str(lines)], capture_output=True, timeout=10,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return r.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


# --- Ẩn / hiện cửa sổ ghế (cùng cách với Focus Mode: ShowWindow lên cửa sổ console) ---
# Cửa sổ ẩn vẫn nhận phím AgentChattr gõ vào, chỉ là không hiện trên màn hình/taskbar -> không lỡ tay đóng được.
# KHÔNG ẩn khi ghế còn cần người: chưa vào phòng, đang hỏi đăng nhập / xác nhận (lần chạy đầu).
SHOW_UNTIL = DATA / "seat_show_until"   # --show tạo file này: tạm không ẩn trong 15 phút
PROMPT_RE = re.compile(r"choose the text style|do you trust|trust (this|the) folder|press enter|"
                       r"select (a|an|your)|login|log in|sign in|authenticate|\(y/n\)|\[y/n\]|yes, proceed", re.I)


def _user32():
    import ctypes
    from ctypes import wintypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    return ctypes, wintypes, u


def seat_windows():
    """{ghế: [hwnd cửa sổ console thuộc ghế đó]} — nhận ra cửa sổ qua cây tiến trình (tiêu đề hay bị CLI đổi)."""
    ctypes, wintypes, u = _user32()
    wins = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(h, cls, 64)
        if cls.value == "ConsoleWindowClass":
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            wins.append((h, pid.value))
        return True

    u.EnumWindows(cb, 0)
    out = {s: [] for s in SEATS}
    for h, pid in wins:
        try:
            p = psutil.Process(pid)
            text = " ".join(p.cmdline()).lower()
            for q in p.children(recursive=True):
                try:
                    text += " " + " ".join(q.cmdline()).lower()
                except psutil.Error:
                    pass
        except psutil.Error:
            continue
        for seat, bat in SEATS.items():
            if bat.lower() in text or re.search(rf"wrapper(_api)?\.py {seat}\b", text):
                out[seat].append(h)
                break
    return out


GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
SWP_FLAGS = 0x1 | 0x4 | 0x10            # NOSIZE | NOZORDER | NOACTIVATE
OFF_X = OFF_Y = -32000


def set_seat_windows(seats, show):
    """Ẩn kiểu "ra ngoài màn hình": cửa sổ vẫn VISIBLE (Codex/crossterm bỏ qua phím gõ vào cửa sổ SW_HIDE),
    nhưng bị đẩy ra ngoài màn hình + thành tool window -> không còn trên taskbar / Alt+Tab, không lỡ tay đóng."""
    ctypes, wintypes, u = _user32()
    u.GetWindowLongW.restype = ctypes.c_long
    for seat, hwnds in seat_windows().items():
        if seat not in seats:
            continue
        for h in hwnds:
            ex = u.GetWindowLongW(h, GWL_EXSTYLE)
            hidden = bool(ex & WS_EX_TOOLWINDOW)
            if show:
                if hidden or not u.IsWindowVisible(h):
                    u.ShowWindow(h, 0)
                    u.SetWindowLongW(h, GWL_EXSTYLE, (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
                    u.ShowWindow(h, 4)                      # SW_SHOWNOACTIVATE
                    u.SetWindowPos(h, 0, 80, 80, 0, 0, SWP_FLAGS)
            elif not hidden or not u.IsWindowVisible(h):
                u.ShowWindow(h, 0)
                u.SetWindowLongW(h, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
                u.ShowWindow(h, 4)
                u.SetWindowPos(h, 0, OFF_X, OFF_Y, 0, 0, SWP_FLAGS)


def show_mode_active():
    try:
        return time.time() < float(SHOW_UNTIL.read_text())
    except (OSError, ValueError):
        return False


def read_seat_file():
    try:
        return json.loads(SEAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_notes(notes):
    data = read_seat_file()
    data["seats"] = list(SEATS)
    if data.get("notes") == notes:
        return
    data["notes"] = notes
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = SEAT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SEAT_FILE)


def close_stale_windows(seat):
    """Cửa sổ .bat cũ của ghế đã chết (đang đứng ở 'pause' sau lỗi) -> đóng, để không chất đống cửa sổ."""
    bat = SEATS[seat].lower()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() == "cmd.exe" and bat in " ".join(p.info["cmdline"] or []).lower():
                for ch in p.children(recursive=True):
                    ch.kill()
                p.kill()
        except psutil.Error:
            pass


# --- Tự hồi phục khi hết quota: tới mốc reset thì khởi động lại ghế (xoá hộp thoại "Usage limit reached" đang treo)
def quota_retry_time(seat, text, now):
    """Mốc thử lại: đọc từ thông báo lỗi nếu có; Gemini = nửa đêm giờ Thái Bình Dương (+5'); còn lại 2 giờ."""
    from datetime import datetime, timedelta
    t = text.lower()
    m = re.search(r"(?:try again|reset[s]?|available again|resets?)\D{0,15}in\s+(\d+)\s*(h|hour|giờ|m|min|phút)", t)
    if m:
        n = int(m.group(1)); return now + (n * 3600 if m.group(2) in ("h", "hour", "giờ") else n * 60) + 120
    m = re.search(r"(?:try again|reset[s]?|available)\D{0,15}at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if m:
        h, mi = int(m.group(1)) % 12 if m.group(3) else int(m.group(1)), int(m.group(2) or 0)
        if m.group(3) == "pm":
            h += 12
        d = datetime.now().replace(hour=h % 24, minute=mi, second=0, microsecond=0)
        if d.timestamp() <= now:
            d += timedelta(days=1)
        return d.timestamp() + 120
    if seat == "gemini":
        from zoneinfo import ZoneInfo
        pt = datetime.now(ZoneInfo("America/Los_Angeles"))
        return (pt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1, minutes=5)).timestamp()
    return now + 2 * 3600


def restart_seat(seat):
    """Tắt đúng cây tiến trình của ghế này (wrapper + CLI con + cửa sổ .bat). KHÔNG đụng tiến trình nào khác."""
    roots = set(wrapper_pids()[seat])
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() == "cmd.exe" and SEATS[seat].lower() in " ".join(p.info["cmdline"] or []).lower():
                roots.add(p.info["pid"])
        except psutil.Error:
            pass
    victims = {}
    for pid in roots:
        try:
            pr = psutil.Process(pid)
            victims[pid] = pr
            for ch in pr.children(recursive=True):
                victims[ch.pid] = ch
        except psutil.Error:
            pass
    for pr in victims.values():
        try:
            pr.kill()
        except psutil.Error:
            pass
    return len(victims)


def launch(seat, dry):
    bat = ROOT / "windows" / SEATS[seat]
    log(f"bật ghế {seat}: {bat.name}" + (" (dry-run)" if dry else ""))
    if dry:
        return
    close_stale_windows(seat)
    subprocess.Popen(["cmd.exe", "/c", "start", f"Ghe {seat}", "/min", "cmd.exe", "/c", str(bat)],
                     cwd=str(ROOT / "windows"), env=ENV, creationflags=subprocess.CREATE_NO_WINDOW)


def seat_report():
    """[(ghế, đang chạy?, trạng thái chữ)] — dùng cho nút Bat 4 ghe AI."""
    try:
        status = get_status()
    except Exception:
        status = {}
    pids = wrapper_pids()
    rows = []
    for seat in SEATS:
        reg = [v for v in status.values() if isinstance(v, dict) and v.get("base") == seat and not v.get("placeholder")]
        ph = status.get(seat) if isinstance(status.get(seat), dict) else {}
        if reg and reg[0].get("available"):
            rows.append((seat, True, "ON"))
        elif reg or pids[seat]:
            note = (reg[0] if reg else ph).get("note") or "cửa sổ đang chạy, chưa sẵn sàng"
            rows.append((seat, True, f"đang chạy nhưng OFF: {note}"))
        else:
            rows.append((seat, False, "chưa bật"))
    return rows


def kick():
    """Nút Bat 4 ghe AI: quét ghế, báo ghế nào đã có, gửi lệnh 'bật ngay ghế thiếu' cho bộ giữ ghế."""
    print("\n  Quét 4 ghế AI...")
    for seat, running, text in seat_report():
        print(f"  [{'ON ' if running else 'OFF'}] {LABEL[seat]:<7} {text}" + ("" if running else "  -> bật ngay"))
    KICK.write_text(str(time.time()), encoding="utf-8")


def wait_or_kick(seconds):
    """Ngủ giữa 2 vòng, nhưng dậy ngay nếu có lệnh kick."""
    end = time.time() + seconds
    while time.time() < end:
        if KICK.exists():
            return
        time.sleep(1)


def main():
    once = "--once" in sys.argv
    dry = "--dry-run" in sys.argv
    fails = {s: 0 for s in SEATS}         # số lần bật liên tiếp mà ghế không vào được phòng
    retry_at = {s: 0 for s in SEATS}      # chưa tới giờ này thì chưa bật lại (giãn dần 2 -> 4 -> 8 -> 10 phút)
    last_launch = {s: 0 for s in SEATS}
    quota_retry = {}                      # ghế đang hết quota -> mốc tự khởi động lại
    log("seat_keeper chạy" + (" (dry-run)" if dry else ""))
    hung = 0                              # (14/10) số vòng liên tiếp cổng 8300 mở mà /api/status không trả lời = máy chủ treo
    while True:
        now = time.time()
        if KICK.exists():
            # Người dùng bấm Bat 4 ghe AI: bỏ mọi thời gian chờ, bật ngay ghế nào còn thiếu
            try:
                KICK.unlink()
            except OSError:
                pass
            log("lệnh bật ngay từ nút Bat 4 ghe AI")
            fails = {s: 0 for s in SEATS}
            retry_at = {s: 0 for s in SEATS}
            last_launch = {s: 0 for s in SEATS}
        if not port_up(8300):
            log("máy chủ 8300 không chạy -> bật lại")
            if not dry:
                subprocess.Popen([PYW, "launcher_w.py"], cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(INTERVAL)
            if once:
                break
            continue
        try:
            status = get_status(); hung = 0
        except Exception as e:
            log(f"không đọc được /api/status: {e}")
            status = {}; hung += 1
            # (14/10) 14/10 21:33 máy chủ TREO: vẫn giữ cổng 8300 (nên kiểm "cổng mở" tưởng còn sống) nhưng không nhận kết nối,
            # bản bật lại thì thoát vì khoá data/server.lock -> không ai cứu. 3 vòng liền (~1 phút) -> tắt hẳn bản treo rồi bật lại.
            if hung >= 3 and not dry:
                log("máy chủ phòng chat TREO 3 vòng liền -> tắt hẳn rồi bật lại")
                for pr in psutil.process_iter(["pid", "cmdline"]):
                    try:
                        if any(c.endswith("launcher_w.py") or c.endswith("run.py") for c in (pr.info["cmdline"] or [])): pr.kill()
                    except psutil.Error:
                        pass
                time.sleep(5)
                subprocess.Popen([PYW, "launcher_w.py"], cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW)
                hung = 0; wait_or_kick(INTERVAL); continue
        pids = wrapper_pids()
        autostart = read_seat_file().get("autostart", list(SEATS))
        # Ghế bật lại khi tên cũ còn được giữ chỗ -> bị đặt "codex-2"/"gemini-2". Chỉ còn 1 bản thì đổi về tên gốc.
        for seat in SEATS:
            names = [k for k, v in status.items() if isinstance(v, dict) and v.get("base") == seat
                     and not v.get("placeholder")]
            if len(names) == 1 and names[0] != seat and not dry:
                label = "Local" if seat == "local" else LABEL[seat]   # id sinh từ label phải đúng bằng tên ghế
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:8300/api/label/{names[0]}", method="POST",
                                                 data=json.dumps({"label": label}).encode(),
                                                 headers={"x-session-token": _token_ok,
                                                          "Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=5).read()
                    log(f"đổi tên {names[0]} -> {seat}")
                except Exception as e:
                    log(f"không đổi được tên {names[0]}: {e}")
        notes = {}
        ready_to_hide = []
        for seat in SEATS:
            registered = any(v.get("base") == seat and not v.get("placeholder")
                             for k, v in status.items() if isinstance(v, dict))
            alive = pids[seat]
            if registered:
                fails[seat] = 0
                last_launch[seat] = 0   # lần bật trước đã thành công -> ghế rớt sau này không tính là "bật hỏng"
            # 1) Đọc console ghế đang chạy -> quota / login
            if alive:
                text = console_text(alive[0])
                tail = [l for l in text.splitlines() if l.strip()][-15:]
                hit_q = next((l for l in reversed(tail) if QUOTA_RE.search(l)), None)
                hit_l = next((l for l in reversed(tail) if LOGIN_RE.search(l)), None)
                if hit_q:
                    if seat not in quota_retry:
                        quota_retry[seat] = quota_retry_time(seat, " ".join(tail), now)
                        log(f"ghế {seat} hết quota -> tự thử lại lúc {time.strftime('%H:%M %d/%m', time.localtime(quota_retry[seat]))}")
                    if now >= quota_retry[seat] and not dry:
                        n = restart_seat(seat)
                        log(f"ghế {seat}: đã tới mốc reset quota -> khởi động lại ghế ({n} tiến trình) để gỡ hộp thoại hết quota")
                        quota_retry.pop(seat, None); last_launch[seat] = 0; fails[seat] = 0
                        notes[seat] = {"state": "off", "note": "Đang khởi động lại sau mốc reset quota..."}
                        continue
                    notes[seat] = {"state": "quota", "note": f"Hết quota: {hit_q.strip()[:120]} — tự thử lại lúc "
                                                             f"{time.strftime('%H:%M %d/%m', time.localtime(quota_retry[seat]))}"}
                elif hit_l:
                    notes[seat] = {"state": "login", "note": f"Cần đăng nhập: {hit_l.strip()[:140]}"}
                elif not registered and now - last_launch[seat] > BOOT_GRACE:
                    notes[seat] = {"state": "off", "note": "Cửa sổ ghế đang mở nhưng chưa vào phòng (kẹt khởi động?)"}
                if not hit_q:
                    quota_retry.pop(seat, None)
                if registered and not hit_l and not any(PROMPT_RE.search(l) for l in tail[-6:]):
                    ready_to_hide.append(seat)
                continue
            # 2) Không có wrapper -> bật lại (có giới hạn)
            if registered:
                # Wrapper vừa chết nhưng phòng chat còn giữ tên (tối đa ~15s). Bật ngay sẽ sinh tên trùng
                # "gemini-2"/"gemini-1" -> chờ vòng sau khi tên cũ đã được giải phóng.
                notes[seat] = {"state": "off", "note": "Đang dọn phiên cũ, sắp bật lại..."}
                continue
            if seat not in autostart:
                notes[seat] = {"state": "off", "note": "Ghế đang tắt (không tự bật)"}
                continue
            if now - last_launch[seat] < BOOT_GRACE and last_launch[seat]:
                notes[seat] = {"state": "off", "note": "Đang khởi động..."}
                continue
            if last_launch[seat] and not registered and retry_at[seat] <= last_launch[seat]:
                # lần bật trước không vào được phòng -> giãn thời gian thử lại
                fails[seat] += 1
                wait = min(120 * 2 ** (fails[seat] - 1), MAX_BACKOFF)
                retry_at[seat] = now + wait
                log(f"ghế {seat} bật hỏng lần {fails[seat]} -> thử lại sau {wait // 60} phút (bấm Bat 4 ghe AI để bật ngay)")
            if now < retry_at[seat]:
                left = int((retry_at[seat] - now) / 60) + 1
                notes[seat] = {"state": "off", "note": f"Bật hỏng {fails[seat]} lần, tự thử lại sau ~{left} phút "
                                                       f"(hoặc bấm Bat 4 ghe AI để bật ngay)"}
                continue
            launch(seat, dry)
            last_launch[seat] = now
            notes[seat] = {"state": "off", "note": "Đang khởi động..."}
        if dry:
            log("ghi chú: " + json.dumps(notes, ensure_ascii=False))
        else:
            write_notes(notes)
            # Ẩn cửa sổ các ghế đã vào phòng và không cần người thao tác
            if read_seat_file().get("hide_windows", True) and not show_mode_active():
                hide = [s for s in SEATS if s in ready_to_hide]
                try:
                    set_seat_windows(hide, show=False)
                except Exception as e:
                    log(f"không ẩn được cửa sổ ghế: {e}")
        if once:
            break
        wait_or_kick(INTERVAL)


if __name__ == "__main__":
    if not sys.stdout:  # pythonw
        sys.stdout = None
    # venv\Scripts\pythonw.exe là launcher: nó sinh 1 tiến trình con cùng dòng lệnh -> bỏ qua cha/con của chính mình
    me = psutil.Process()
    family = {me.pid} | {p.pid for p in me.parents()} | {c.pid for c in me.children(recursive=True)}
    others = []
    for p in psutil.process_iter(["pid", "cmdline", "create_time"]):
        try:
            cmd = p.info["cmdline"] or []
            if p.info["pid"] not in family and any(c.endswith("seat_keeper.py") for c in cmd) \
                    and "--once" not in cmd and "--kick" not in cmd:
                others.append(p)
        except psutil.Error:
            pass

    if "--show" in sys.argv or "--hide" in sys.argv:
        # --show: hiện lại cửa sổ 4 ghế (tạm dừng tự ẩn 15 phút); --hide: ẩn ngay
        if "--show" in sys.argv:
            SHOW_UNTIL.write_text(str(time.time() + 900), encoding="utf-8")
            set_seat_windows(list(SEATS), show=True)
            print("  Đã hiện cửa sổ các ghế (15 phút sau sẽ tự ẩn lại).")
        else:
            SHOW_UNTIL.unlink(missing_ok=True)
            set_seat_windows(list(SEATS), show=False)
            print("  Đã ẩn cửa sổ các ghế.")
        sys.exit(0)

    if "--kick" in sys.argv:
        # Bộ giữ ghế đang chạy bản code cũ hơn file hiện tại -> thay bằng bản mới
        code_mtime = Path(__file__).stat().st_mtime
        for p in others:
            try:
                if p.info["create_time"] < code_mtime:
                    p.kill()
                    others = [o for o in others if o.pid != p.pid]
            except psutil.Error:
                pass
        kick()
        if not others:
            subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "pythonw.exe"), str(Path(__file__))],
                             cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW)
            print("  Bộ giữ ghế: vừa bật.")
        else:
            print("  Bộ giữ ghế: đang chạy, đã nhận lệnh bật ngay.")
        sys.exit(0)

    if others and "--once" not in sys.argv:
        sys.exit(0)  # chỉ 1 bản keeper
    # (14/10) chạy bằng pythonw thì stderr = None: lỗi bất ngờ làm bộ giữ ghế CHẾT IM LẶNG (14/10 11:36 -> cả buổi không ai giữ ghế).
    # Nay: lỗi ghi vào seat-keeper.log kèm traceback, nghỉ 10 s rồi chạy lại vòng lặp — không bao giờ tự chết.
    import traceback
    if sys.stderr is None:
        sys.stderr = open(ROOT / "seat-keeper-err.log", "a", encoding="utf-8", buffering=1)
    while True:
        try:
            main(); break
        except SystemExit:
            raise
        except Exception:
            log("LỖI vòng giữ ghế (tự chạy lại sau 10 s): " + " | ".join(traceback.format_exc().splitlines()[-8:]))
            time.sleep(10)
