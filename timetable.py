# -*- coding: utf-8 -*-
"""Bộ nhớ đệm lịch cho tab Lịch (Claude 2026-10-03).

Trước: mỗi lần bấm tab / đổi tuần -> web app -> n8n -> 2 truy vấn Notion (~1,5 s), giao diện xoá trắng chờ.
Giờ: web app giữ sẵn toàn bộ 🗓️ Academic Timetable Events (−120 → +240 ngày) trong RAM + file timetable_cache.json,
làm mới ngầm (khi dữ liệu cũ hơn MAX_AGE giây, hoặc ép làm mới sau khi nạp TKB). Giao diện lấy 1 lần rồi tự vẽ tuần/tháng.
"""
import uc_config as cfg
import datetime as dt, json, threading, time
from pathlib import Path
from academic import Notion, P, TZ

EVENTS = cfg.notion("calendar_events")
CACHE_FILE = Path(__file__).resolve().parent / "timetable_cache.json"
MAX_AGE = 60          # giây: cũ hơn thì làm mới ngầm (vẫn trả ngay bản đang có)
BACK, AHEAD = 120, 240

_lock = threading.Lock()
_state = {"events": [], "fetchedAt": 0.0, "busy": False, "error": None}
if CACHE_FILE.exists():
    try: _state.update(json.loads(CACHE_FILE.read_text(encoding="utf-8")))
    except Exception: pass
_state["busy"] = False


def _fetch(post):
    nt = Notion(post)
    today = dt.datetime.now(TZ).date()
    rows = nt.query(EVENTS, {"and": [
        {"property": "When", "date": {"on_or_after": (today - dt.timedelta(days=BACK)).isoformat()}},
        {"property": "When", "date": {"on_or_before": (today + dt.timedelta(days=AHEAD)).isoformat()}}]},
        [{"property": "When", "direction": "ascending"}])
    out = []
    for r in rows:
        w = (r.get("properties", {}).get("When") or {}).get("date") or {}
        if not w.get("start"): continue
        out.append({"id": r["id"], "title": P(r, "Event") or "", "kind": P(r, "Kind") or "", "start": w["start"],
                    "end": w.get("end"), "location": P(r, "Location") or "", "notes": P(r, "Notes") or "", "url": r.get("url")})
    out.sort(key=lambda e: e["start"])
    return out

def refresh(post):
    with _lock:
        if _state["busy"]: return
        _state["busy"] = True
    try:
        ev = _fetch(post)
        _state.update({"events": ev, "fetchedAt": time.time(), "error": None})
        CACHE_FILE.write_text(json.dumps({"events": ev, "fetchedAt": _state["fetchedAt"]}, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        _state["error"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        _state["busy"] = False

def get(post, force=False):
    """Trả ngay bản đang có; nếu cũ (hoặc force) thì làm mới ở luồng nền. Lần đầu chưa có gì -> chờ lấy."""
    age = time.time() - _state["fetchedAt"]
    if not _state["events"] and not _state["fetchedAt"]:
        refresh(post)
    elif force or age > MAX_AGE:
        threading.Thread(target=refresh, args=(post,), daemon=True).start()
    return {"events": _state["events"], "fetchedAt": int(_state["fetchedAt"]), "refreshing": _state["busy"], "error": _state["error"]}

def window(post, f, t):
    """Tương thích /api/timetable?from&to cũ (lọc theo ngày Việt Nam từ bộ đệm)."""
    d = get(post)
    ev = [e for e in d["events"] if (e["end"] or e["start"])[:10] >= f and e["start"][:10] <= t]
    return {"from": f, "to": t, "events": ev}
