# -*- coding: utf-8 -*-
"""🌐 Add-on network-guard (v1.00.22) — UC phát hiện mạng TẮT / BẬT. Chạy mỗi 1 phút bằng Task Scheduler, rất nhẹ
(2 lần gọi google.com/generate_204, không tải gì nặng).

  Có mạng  -> nếu vừa mất mạng: gỡ cờ OFFLINE.flag + `docker unpause n8n`. Dịch vụ UC nào đang tắt (UC, n8n, cổng chép lời, máy ghi…)
              -> chạy open_copilot.ps1 -NoBrowser để bật lại (tối đa 1 lần / 5 phút, tránh bật dồn dập).
  Mất mạng 3 phút liên tiếp -> TẠM DỪNG việc cần mạng: đặt cờ OFFLINE.flag (UC bỏ qua các lượt đồng bộ trường / mail / tài liệu)
              + `docker pause n8n` (đóng băng nguyên trạng, unpause là chạy tiếp, không mất workflow hay dữ liệu).
              UC, máy ghi, model AI trên máy, cổng chép lời VẪN CHẠY (đều chạy trên máy, không cần mạng).

Đặt file này cạnh copilot_app.py. Cờ: <thư mục UC>/OFFLINE.flag (đổi bằng biến môi trường UC_OFFLINE_FLAG — UC đọc cùng biến).
Nhật ký: school/netguard.log · trạng thái: school/netguard.json.
Giới hạn: chỉ kiểm "ra được Internet tới Google", không đo tốc độ (wifi rất chậm vẫn tính là có mạng); lúc offline n8n bị đóng băng
cả luồng không cần mạng (gần như mọi luồng n8n của UC đều gọi Google/Notion nên chấp nhận)."""
import json, os, shutil, socket, subprocess, time, urllib.request
from datetime import datetime
from pathlib import Path

UC = Path(__file__).resolve().parent
STATE, LOG = UC / 'school' / 'netguard.json', UC / 'school' / 'netguard.log'
FLAG = Path(os.environ.get('UC_OFFLINE_FLAG') or UC / 'OFFLINE.flag')
DOCKER = os.environ.get('DOCKER_EXE') or shutil.which('docker') or 'docker'
LAUNCHER = UC / 'open_copilot.ps1'
PORTS = {8320: 'UC', 5678: 'n8n', 8340: 'cổng chép lời', 5681: 'máy ghi', 8350: 'cổng Gemini', 8300: 'phòng họp AI', 8310: 'relay hội đồng'}   # thêm cổng dịch vụ của bạn nếu có
FAIL_LIMIT, RESTART_COOLDOWN = 3, 300


def log(m):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f: f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} {m}\n')


def online():
    for _ in range(2):
        try:
            with urllib.request.urlopen('https://www.google.com/generate_204', timeout=5) as r:
                if r.status == 204: return True
        except Exception: pass
        time.sleep(2)
    return False


def up(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2): return True
    except OSError: return False


def docker(*a):
    try: return subprocess.run([DOCKER, *a], capture_output=True, text=True, timeout=60, creationflags=0x08000000).returncode == 0
    except Exception: return False


AC = Path(os.environ.get("AC_DIR") or UC.parent / "agentchattr")   # phòng họp 4 ghế AI (thư mục agentchattr/ của repo)


def keeper_alive():
    """(v1.00.28) Bộ giữ ghế AgentChattr từng chết im lặng -> mỗi phút: có AgentChattr mà không thấy seat_keeper thì bật lại (--kick)."""
    if not (AC / "seat_keeper.py").exists(): return
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                            "@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'seat_keeper[.]py' -and $_.CommandLine -notmatch '--once|--kick' }).Count"],
                           capture_output=True, text=True, timeout=60, creationflags=0x08000000)
        if r.stdout.strip() == "0":
            log("bộ giữ ghế AgentChattr không chạy -> bật lại (--kick)")
            py = AC / ".venv" / "Scripts" / "pythonw.exe"
            subprocess.Popen([str(py) if py.exists() else "pythonw", str(AC / "seat_keeper.py"), "--kick"], cwd=str(AC), creationflags=0x08000000)
    except Exception as e: log(f"không kiểm được bộ giữ ghế: {type(e).__name__}")


def main():
    try: st = json.loads(STATE.read_text(encoding='utf-8-sig'))
    except Exception: st = {'mode': 'online', 'fails': 0, 'last_restart': 0}
    if online():
        if st['mode'] == 'offline':
            FLAG.unlink(missing_ok=True); ok = docker('unpause', 'n8n')
            log(f'CÓ MẠNG lại sau {st["fails"]} phút mất -> gỡ cờ OFFLINE, n8n chạy tiếp ({"ok" if ok else "không cần/không được"})')
        st.update(mode='online', fails=0)
        keeper_alive()
        dead = [n for p, n in PORTS.items() if not up(p)]
        if dead and LAUNCHER.exists() and time.time() - st.get('last_restart', 0) > RESTART_COOLDOWN:
            st['last_restart'] = time.time()
            log('dịch vụ tắt: ' + ', '.join(dead) + ' -> chạy open_copilot.ps1 -NoBrowser')
            subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', str(LAUNCHER), '-NoBrowser'],
                             creationflags=0x08000000)
    else:
        st['fails'] = st.get('fails', 0) + 1
        if st['mode'] == 'online' and st['fails'] >= FAIL_LIMIT:
            FLAG.write_text(datetime.now().isoformat(timespec='seconds'), encoding='utf-8'); ok = docker('pause', 'n8n')
            st['mode'] = 'offline'
            log(f'MẤT MẠNG {st["fails"]} phút liên tiếp -> TẠM DỪNG việc cần mạng (cờ OFFLINE, n8n đóng băng: {"ok" if ok else "không được"})')
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
