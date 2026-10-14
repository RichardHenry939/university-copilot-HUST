"""Council relay — cầu nối Notion/n8n <-> phòng họp AgentChattr (mục 9 bản vẽ).

Lắng nghe 127.0.0.1:8310 (Docker Desktop chuyển host.docker.internal về loopback).

Luồng theo bản vẽ (mục 9):
  Chủ tọa tick Convene trong Notion (🏛️ Council Sessions)
    -> n8n (N9) khoá snapshot hồ sơ, gọi POST /council/ask {mode:"start", session_key, page_id, question}
    -> relay xáo thứ tự các ghế đang online, gửi hồ sơ vào #council, THEO DÕI phiên
    -> ghế cuối nói xong (hoặc hết giờ) -> relay gửi transcript về n8n (webhook council-transcript)
       -> Notion: Status = Awaiting Chair, Transcript = biên bản. Hội đồng DỪNG HOÀN TOÀN.
  Chủ tọa: viết góp ý vào Chair Prompt + tick Convene  -> n8n gọi /council/ask {mode:"continue"} (vòng mới)
           viết Final Decision + tick Convene          -> n8n chốt (Finalized) + gọi /council/note báo phòng họp.
  Council KHÔNG tự khởi động; chỉ Finalize mới ghi kết quả.

  POST /council/ask   {"question", "channel"?, "session_key"?, "page_id"?, "mode": start|continue, "title"?}
       (gọi từ chat Copilot thì không có session_key -> relay tự tạo + ghi Council Session qua council-convene)
  POST /council/note  {"text", "channel"?}            -> đăng 1 thông báo vào phòng họp
  GET  /council/transcript?channel=council&limit=40   -> các tin gần nhất (Copilot tóm tắt)
  GET  /council/sessions                              -> các phiên relay đang/đã theo dõi
  GET  /health
Chạy bằng python của .venv AgentChattr (có sẵn thư viện websockets).
"""
import asyncio, json, random, re, subprocess, threading, time, urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import websockets

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "ac-stdout.log"
SEATS = ["claude", "codex", "gemini", "local"]  # (Claude 2026-10-02) Kimi -> Local AI (LM Studio, ghế phản biện)
CRITIC = "local"  # ghế phản biện (yếu hơn) không bao giờ là ghế mở đầu hay ghế tổng hợp
AC = "http://127.0.0.1:8300"
N8N = "http://127.0.0.1:5678/webhook"
SECRET_FILE = Path(os.environ.get("UC_DIR") or Path(__file__).resolve().parent.parent / "university-copilot") / ".copilot-secret"   # khoá chung của UC
STATE = ROOT / "data" / "council_sessions.json"
PORT = 8310
QUIET_AFTER_LAST = 25      # giây im lặng sau khi ghế cuối nói -> coi như xong vòng
ROUND_TIMEOUT = 20 * 60    # quá 20 phút mà chưa xong -> vẫn dừng, ghi biên bản kèm ghi chú

_lock = threading.Lock()
SESS = {}                  # session_key -> dict


_TOKEN_OK = {"tok": ""}


def session_token():
    """Token cua server DANG CHAY. (Claude 2026-10-03) Token cuoi trong log co the cua ban server bat trung
    da tu tat -> thu cac token gan nhat voi /api/status, nho token dung."""
    if _TOKEN_OK["tok"]:
        return _TOKEN_OK["tok"]
    if not LOG.exists():
        return ""
    with open(LOG, "rb") as f:
        f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 4_000_000))
        tail = f.read().decode("utf-8", "ignore")
    cands = list(dict.fromkeys(reversed(re.findall(r"Session token: ([0-9a-f]{32,})", tail))))[:6]
    for tok in cands:
        try:
            urllib.request.urlopen(urllib.request.Request(AC + "/api/status", headers={"x-session-token": tok}),
                                   timeout=3).read()
            _TOKEN_OK["tok"] = tok
            return tok
        except Exception:
            continue
    return cands[0] if cands else ""


def http_json(url, token="", data=None, method=None, timeout=8, headers=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["x-session-token"] = token
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            t = r.read().decode("utf-8")
            return json.loads(t) if t else {}
    except urllib.error.HTTPError as e:
        if e.code == 403 and token and token == _TOKEN_OK["tok"]:
            _TOKEN_OK["tok"] = ""   # server da khoi dong lai (token moi) -> lan sau do lai
        raise


def n8n_post(path, data, timeout=30):
    key = SECRET_FILE.read_text(encoding="utf-8").strip() if SECRET_FILE.exists() else ""
    return http_json(f"{N8N}/{path}", data=data, timeout=timeout, headers={"X-Copilot-Key": key})


def load_state():
    global SESS
    try:
        SESS = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        SESS = {}


def save_state():
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(SESS, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def server_up():
    try:
        http_json(AC + "/api/status", session_token(), timeout=3)
        return True
    except Exception:
        return False


def seats_online():
    try:
        st = http_json(AC + "/api/status", session_token(), timeout=4)
    except Exception:
        return []
    out = []
    for k, v in st.items():
        if isinstance(v, dict) and v.get("available"):
            base = v.get("base") or k.split("-")[0]
            if base in SEATS and base not in out:
                out.append(base)
    return out


def ensure_running():
    """Bật server (ẩn) + các ghế còn thiếu bằng Bat-4-ghe-AI.ps1 (quét ghế, chỉ bật ghế thiếu, chạy ẩn)."""
    if not server_up():
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                        "-File", str(ROOT / "launch.ps1"), "-NoBrowser"], timeout=60)
    online = seats_online()
    if len(online) < len(SEATS):
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File",
                          str(ROOT / "AgentChattr.ps1"), "-AtLogon"],   # (14/10) Bat-4-ghe-AI.ps1 không còn -> trước đây bật ghế thiếu vào khoảng không
                         creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(10):          # chờ tối đa ~30s; ghế hết quota sẽ không bao giờ lên -> đi tiếp với ghế đang có
            time.sleep(3)
            online = seats_online()
            if len(online) == len(SEATS):
                break
    return online


async def _ws_send(text, channel):
    tok = session_token()
    async with websockets.connect(f"ws://127.0.0.1:8300/ws?token={tok}", max_size=None, open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "message", "text": text, "channel": channel}))
        await asyncio.sleep(0.5)


def post(text, channel="council"):
    asyncio.run(_ws_send(text, channel))


def read_msgs(channel, since_id=0, limit=200):
    q = f"channel={channel}&limit={limit}" + (f"&since_id={since_id}" if since_id else "")
    msgs = http_json(f"{AC}/api/messages?{q}", session_token())
    if isinstance(msgs, dict):
        msgs = msgs.get("messages", msgs.get("data", []))
    return [m for m in msgs if int(m.get("id", 0)) > since_id]


def seat_order(online):
    """Chỉ xếp ghế ĐANG ONLINE (ghế OFF/hết quota mà được @ thì chuỗi đứt).
    Ghế mạng xáo ngẫu nhiên; ghế phản biện (local) đứng áp chót -> ghế cuối (tổng hợp) luôn là AI mạnh."""
    cloud = [s for s in SEATS if s != CRITIC and s in online]
    random.shuffle(cloud)
    if CRITIC in online:
        return cloud[:-1] + [CRITIC] + cloud[-1:] if cloud else [CRITIC]
    return cloud


def build_message(header, body, order):
    # CHỈ được có đúng 1 "@" (Ghế 1): phòng chat đánh thức MỌI ghế được @ trong tin -> ghế khác nói trước lượt.
    # Ghế sau chỉ được gọi khi ghế trước viết "@tên" lúc xong lượt.
    n = len(order)
    lines = [header, "", body.strip(), "",
             "Thứ tự ghế (xáo ngẫu nhiên): " + " → ".join(f"Ghế {i+1} {s}" for i, s in enumerate(order)), "",
             f"Quy trình {n} ghế (xong lượt thì gọi ghế kế tiếp bằng cách viết @ liền tên ghế đó):"]
    for i, s in enumerate(order):
        nxt = f" Xong thì gọi ghế kế tiếp: {order[i+1]}." if i + 1 < n else ""
        if n == 1:
            role = "đọc hồ sơ, trả lời đầy đủ. Sau đó DỪNG, không gọi ai nữa — chờ Chủ tọa."
        elif i == n - 1:
            role = "đọc toàn bộ, sửa chỗ sai và TỔNG HỢP kết luận đầy đủ. Sau đó DỪNG, không gọi ai nữa — chờ Chủ tọa."
        elif s == CRITIC:
            role = "PHẢN BIỆN — soi lỗ hổng, giả định chưa chắc, rủi ro bị bỏ qua, phương án đơn giản hơn." + nxt
        elif i == 0:
            role = "đọc hồ sơ, trình bày lại vấn đề + bối cảnh + câu trả lời ban đầu." + nxt
        else:
            role = "đọc hồ sơ + ý các ghế trước, bổ sung câu hỏi sắc / điểm mù / góc nhìn còn thiếu." + nxt
        lines.append(f"• Ghế {i+1} ({s}): {role}")
    lines += ["Trả lời bằng tiếng Việt, gọn, có lập luận. Chỉ nói khi tới lượt mình.", "",
              f"@{order[0]} mời Ghế 1 bắt đầu."]
    return "\n".join(lines)


def ask(question, channel="council", session_key=None, page_id=None, mode="start", title=None):
    online = ensure_running()
    order = seat_order(online)
    if not order:
        return {"ok": False, "error": "Không có ghế nào online (xem thanh trạng thái phòng chat)."}
    from_chat = not session_key
    key = session_key or ("CS-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    with _lock:
        s = SESS.get(key) or {"key": key, "page_id": page_id, "channel": channel, "title": title or question[:80],
                              "round": 0, "transcript": "", "active": False}
        if s.get("active"):
            return {"ok": False, "error": f"Phiên {key} đang họp (vòng {s['round']}) — chờ hội đồng dừng đã."}
        s["round"] += 1
        s.update(channel=channel, page_id=page_id or s.get("page_id"))
    if mode == "continue":
        header = f"🔁 VÒNG {s['round']} — Chủ tọa góp ý / yêu cầu bàn tiếp (phiên {key})"
    else:
        header = f"📋 HỒ SƠ HỘI ĐỒNG — phiên {key}" + (f" · {title}" if title else "")
    text = build_message(header, question, order)
    before = read_msgs(channel, limit=1)
    start_id = int(before[-1]["id"]) if before else 0
    post(text, channel)
    with _lock:
        s.update(order=order, start_id=start_id, started=time.time(), active=True, last_seen=time.time(),
                 round_header=f"=== Vòng {s['round']} ({datetime.now():%d/%m %H:%M}) · thứ tự: "
                              + " → ".join(order) + " ===\n" + ("Chủ tọa góp ý: " if mode == "continue" else "Hồ sơ: ")
                              + question.strip()[:1500])
        SESS[key] = s
        save_state()
    notion = "Notion: phiên có sẵn" if not from_chat else "skipped"
    if from_chat:
        try:   # gọi từ chat Copilot -> tạo dòng Council Session (Status In council)
            n8n_post("council-convene", {"sessionKey": key, "session": (title or question)[:80],
                                         "prompt": question.strip()[:1900]}, timeout=20)
            notion = "Council Session " + key
        except Exception as e:
            notion = f"không ghi được Council Session: {e}"
    return {"ok": True, "channel": channel, "order": order, "round": s["round"], "seats_online": online,
            "offline": [x for x in SEATS if x not in online], "session_key": key, "notion": notion,
            "xem_tai": f"http://localhost:8300 (kênh #{channel})"}


def _finish_round(key, note=""):
    """Hội đồng dừng hẳn: gom biên bản vòng này, gửi n8n -> Notion Awaiting Chair."""
    with _lock:
        s = SESS[key]
        msgs = [m for m in read_msgs(s["channel"], s["start_id"])
                if m.get("type", "chat") == "chat" and m.get("sender") != "system"]
        body = "\n\n".join(f"[{m.get('time','')}] {m.get('sender')}: {str(m.get('text','')).strip()}"
                           for m in msgs[1:])          # msgs[0] là chính hồ sơ relay vừa gửi
        s["transcript"] = (s.get("transcript", "") + "\n\n" + s["round_header"] + "\n\n" + body
                           + (f"\n\n({note})" if note else "")).strip()
        s["active"] = False
        save_state()
        payload = {"sessionKey": key, "pageId": s.get("page_id") or "", "round": s["round"],
                   "transcript": s["transcript"], "order": s["order"]}
        channel = s["channel"]
    try:
        n8n_post("council-transcript", payload)
        ok = "đã ghi biên bản vào Notion (Status: Awaiting Chair)"
    except Exception as e:
        ok = f"CHƯA ghi được Notion: {e}"
    post(f"⏸ Hội đồng dừng — vòng {payload['round']} của phiên {key} đã xong, {ok}.\n"
         "Chủ tọa quyết định trong Notion (🏛️ Council Sessions):\n"
         "• Bàn tiếp / góp ý: ghi vào Chair Prompt rồi tick Convene\n"
         "• Chốt: ghi Final Decision rồi tick Convene" + (f"\n({note})" if note else ""), channel)


def tracker():
    """Theo dõi các phiên đang họp: ghế cuối nói xong + im lặng 25s -> dừng vòng."""
    while True:
        time.sleep(8)
        try:
            with _lock:
                active = [k for k, s in SESS.items() if s.get("active")]
            for key in active:
                s = SESS[key]
                msgs = [m for m in read_msgs(s["channel"], s["start_id"]) if m.get("type", "chat") == "chat"]
                last = s["order"][-1]
                said = {(m.get("sender") or "").split("-")[0] for m in msgs}
                last_done = any((m.get("sender") or "").split("-")[0] == last for m in msgs[1:])
                if len(msgs) > (s.get("_n") or 0):
                    s["_n"] = len(msgs); s["last_seen"] = time.time()
                if last_done and time.time() - s["last_seen"] >= QUIET_AFTER_LAST:
                    _finish_round(key)
                elif time.time() - s["started"] > ROUND_TIMEOUT:
                    missing = [x for x in s["order"] if x not in said]
                    _finish_round(key, "hết 20 phút; ghế chưa nói: " + (", ".join(missing) or "không"))
        except Exception as e:
            print("tracker:", e)


def transcript(channel="council", limit=40):
    out = []
    for m in read_msgs(channel, limit=limit)[-limit:]:
        if m.get("type", "chat") != "chat" or "disconnected" in str(m.get("text", "")):
            continue
        out.append({"sender": m.get("sender"), "time": m.get("time"), "text": str(m.get("text", ""))[:3000]})
    return {"channel": channel, "messages": out}


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path == "/health":
                return self._send(200, {"relay": "ok", "server": server_up(), "seats_online": seats_online()})
            if u.path == "/council/transcript":
                return self._send(200, transcript(q.get("channel", ["council"])[0], int(q.get("limit", ["40"])[0])))
            if u.path == "/council/sessions":
                with _lock:
                    return self._send(200, {k: {x: v.get(x) for x in ("round", "active", "order", "page_id", "title")}
                                            for k, v in SESS.items()})
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/council/ask":
                q = str(body.get("question", "")).strip()
                if not q:
                    return self._send(400, {"error": "question is required"})
                return self._send(200, ask(q, body.get("channel") or "council", body.get("session_key") or None,
                                           body.get("page_id") or None, body.get("mode") or "start",
                                           body.get("title") or None))
            if u.path == "/council/note":
                t = str(body.get("text", "")).strip()
                if t:
                    post(t, body.get("channel") or "council")
                key = body.get("session_key")
                if key and key in SESS:
                    with _lock:
                        SESS[key]["active"] = False; SESS[key]["finalized"] = True; save_state()
                return self._send(200, {"ok": True})
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    load_state()
    threading.Thread(target=tracker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
