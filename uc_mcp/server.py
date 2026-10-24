# -*- coding: utf-8 -*-
"""MCP connector cho University Copilot (v1.00.33) — CHỈ ĐỌC, chỉ thư viện chuẩn.

Nói chuyện với Claude theo giao thức MCP (JSON-RPC qua HTTP, một endpoint POST /mcp).
UC chạy trên máy bạn (127.0.0.1:8320), nên server này chỉ có dữ liệu khi máy đang bật.
Máy tắt -> mọi công cụ trả "máy đang tắt" để Claude chuyển sang nguồn Notion báo cáo sơ bộ.

Chạy:  python server.py [--port 8790]   (mặc định chỉ lắng nghe 127.0.0.1)
Xác thực tuỳ chọn: đặt biến môi trường UC_MCP_TOKEN, khi đó mọi yêu cầu phải có "Authorization: Bearer <token>".
Đưa ra internet (đường hầm HTTPS, Claude.ai connector) là QUYẾT ĐỊNH của chủ máy: xem README.md.
"""
import argparse, datetime as dt, json, os, socket, sys, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UC = os.environ.get("UC_BASE", "http://127.0.0.1:8320")
PROTO = "2025-03-26"
TZ = dt.timezone(dt.timedelta(hours=7))
OFFLINE = ("Máy tính đang tắt hoặc UC chưa chạy, nên chưa có dữ liệu trực tiếp. "
           "Hãy báo cho người dùng là máy đang tắt và dùng nguồn Notion (skill uc-briefing) để báo cáo sơ bộ, ghi rõ thời điểm dữ liệu.")
STATUS_VN = {"co_lich": "có lịch thi", "du_kien": "dự kiến", "chua_lich": "có thi, chưa có lịch", "chua_co": "chưa có thông báo", "khong_thi": "không thi giữa kỳ"}
NO_ARGS = {"type": "object", "properties": {}}
TOOLS = [
    {"name": "uc_status", "description": "Kiểm tra máy tính có đang chạy University Copilot không (online/offline).", "inputSchema": NO_ARGS},
    {"name": "uc_today", "description": "Tổng quan hôm nay từ UC: lịch thi giữa kỳ, hạn đang mở (có cờ môn thi giữa kỳ, tự gia hạn), việc hôm nay.", "inputSchema": NO_ARGS},
    {"name": "uc_deadlines", "description": "Các hạn nộp đang mở, sắp hết hạn trước. Tham số days (mặc định 21).",
     "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "default": 21}}}},
    {"name": "uc_exams", "description": "Lịch thi giữa kỳ sắp tới (môn, ngày, kíp, phòng).", "inputSchema": NO_ARGS},
    {"name": "uc_briefing", "description": "Báo cáo sơ bộ một trang (lịch thi, hạn gần nhất) hoặc thông báo máy đang tắt.", "inputSchema": NO_ARGS},
]


def _fetch():
    """-> (dữ liệu /api/today, None) khi UC chạy; (None, lý do) khi máy tắt hoặc UC không trả lời."""
    try:
        with urllib.request.urlopen(UC + "/api/today", timeout=60) as r:
            return json.loads(r.read().decode("utf-8")), None
    except (TimeoutError, socket.timeout):   # UC có chạy nhưng đang bận (đang đồng bộ): KHÔNG phải máy tắt
        return None, "UC đang bận, thử lại sau ít phút"
    except (urllib.error.URLError, ConnectionError, OSError) as e:   # không kết nối được = máy tắt hoặc UC chưa chạy
        return None, f"{type(e).__name__}: {e}"[:160]


def _deadline_view(x):
    return {"ten": x.get("name"), "mon": x.get("course"), "loai": x.get("kind"), "han": x.get("due"),
            "con_phut": x.get("minsLeft"), "mon_co_thi_giua_ki": bool(x.get("gkExam")),
            "tu_gia_han_so_lan": x.get("extended", 0), "tu_luyen": bool(x.get("self"))}


def _song(d):   # hạn còn sống (chưa tới giờ hết hạn), sắp hết trước
    return sorted([x for x in (d.get("deadlines") or []) if (x.get("minsLeft") or 0) >= 0], key=lambda x: x.get("minsLeft") or 0)


def _qua(d):   # hạn đã quá mà chưa đánh dấu hoàn tất (UC không nhắc nữa, chỉ đếm)
    return [x for x in (d.get("deadlines") or []) if (x.get("minsLeft") or 0) < 0]


def t_status(args):
    d, err = _fetch()
    return {"online": d is not None, "kiem_tra_luc": dt.datetime.now(TZ).isoformat(timespec="minutes"), "chi_tiet": None if d else err}


def t_today(args):
    d, err = _fetch()
    if d is None: return {"online": False, "thong_bao": OFFLINE, "chi_tiet": err}
    return {"online": True, "luc": dt.datetime.now(TZ).isoformat(timespec="minutes"),
            "lich_thi_giua_ki": d.get("exams") or [],
            "thi_giua_ki_tung_mon": d.get("examStatus") or [],
            "han_dang_mo": [_deadline_view(x) for x in _song(d)[:30]],
            "han_da_qua_chua_nop": len(_qua(d)),
            "viec_hom_nay": [{"viec": i.get("task"), "trang_thai": i.get("status"), "gio_uoc": i.get("est")} for i in (d.get("items") or [])[:20]],
            "che_do_ngay": d.get("mode")}


def t_deadlines(args):
    days = int(args.get("days") or 21)
    d, err = _fetch()
    if d is None: return {"online": False, "thong_bao": OFFLINE, "chi_tiet": err}
    rows = [x for x in _song(d) if (x.get("minsLeft") or 0) <= days * 1440]
    return {"online": True, "so_luong": len(rows), "han": [_deadline_view(x) for x in rows]}


def t_exams(args):
    d, err = _fetch()
    if d is None: return {"online": False, "thong_bao": OFFLINE, "chi_tiet": err}
    return {"online": True, "lich_thi_giua_ki": d.get("exams") or [], "thi_giua_ki_tung_mon": d.get("examStatus") or []}


def t_briefing(args):
    d, err = _fetch()
    if d is None: return {"online": False, "thong_bao": OFFLINE, "chi_tiet": err}
    ex = d.get("exams") or []
    hs = _song(d)
    lines = [f"Báo cáo UC lúc {dt.datetime.now(TZ):%H:%M %d/%m/%Y} (máy đang bật)."]
    st = d.get("examStatus") or []
    if st:   # (v1.00.34) mỗi môn 1 dòng, kể cả môn chưa có lịch / không thi
        lines.append("Thi giữa kỳ từng môn:")
        for r in st:
            lines.append(f"  - {r.get('ten_hp')}: {STATUS_VN.get(r.get('trang_thai'), r.get('trang_thai'))}"
                         + (f" {r.get('ngay')} {r.get('kip') or ''} phòng {r.get('phong') or '?'}" if r.get("ngay") else "")
                         + (f" ({r.get('trich')})" if r.get("trich") and r.get("trang_thai") != "co_lich" else ""))
    else:
        lines.append("Lịch thi giữa kỳ: " + ("; ".join(f"{e.get('ten_hp') or e.get('ma_hp')} {e.get('ngay')} {e.get('kip') or ''} phòng {e.get('phong') or '?'}" for e in ex) if ex else "không có"))
    lines.append(f"Hạn đang mở: {len(hs)}")
    for x in hs[:5]:
        lines.append(f"  - {x.get('name')} ({x.get('course') or '-'}) hạn {str(x.get('due'))[:16]}" + (" [môn thi giữa kì]" if x.get("gkExam") else ""))
    return {"online": True, "bao_cao": "\n".join(lines), "lich_thi_giua_ki": ex, "so_han": len(hs)}


DISPATCH = {"uc_status": t_status, "uc_today": t_today, "uc_deadlines": t_deadlines, "uc_exams": t_exams, "uc_briefing": t_briefing}


def handle(msg):
    """Một thông điệp JSON-RPC -> phản hồi (dict), hoặc None với thông báo không cần trả lời."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None: return None
    try:
        if method == "initialize":
            res = {"protocolVersion": PROTO, "capabilities": {"tools": {}}, "serverInfo": {"name": "uc", "version": "1.0.0"}}
        elif method == "tools/list":
            res = {"tools": TOOLS}
        elif method == "tools/call":
            fn = DISPATCH.get(params.get("name"))
            if fn is None:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "không có công cụ " + str(params.get("name"))}}
            out = fn(params.get("arguments") or {})
            res = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}], "isError": False}
        elif method == "ping":
            res = {}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "không hỗ trợ " + str(method)}}
        return {"jsonrpc": "2.0", "id": mid, "result": res}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"Lỗi: {type(e).__name__}: {e}"}], "isError": True}}


class H(BaseHTTPRequestHandler):
    token = os.environ.get("UC_MCP_TOKEN", "").strip()

    def _send(self, code, obj=None):
        body = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self):
        if not self.token: return True
        return self.headers.get("Authorization", "") == "Bearer " + self.token

    def do_GET(self):
        if self.path == "/health": return self._send(200, {"ok": True, "ten": "uc-mcp"})
        self._send(405, {"loi": "dùng POST /mcp"})

    def do_POST(self):
        if self.path != "/mcp": return self._send(404, {"loi": "không có"})
        if not self._auth_ok(): return self._send(401, {"loi": "sai hoặc thiếu token"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            msg = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return self._send(400, {"loi": "JSON không hợp lệ"})
        out = handle(msg)
        if out is None: return self._send(202)
        self._send(200, out)

    def log_message(self, fmt, *args):   # không ghi nội dung yêu cầu (có dữ liệu học tập) ra log
        return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"uc-mcp lắng nghe tại http://{a.host}:{a.port}/mcp (xác thực: {'có' if H.token else 'không'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
