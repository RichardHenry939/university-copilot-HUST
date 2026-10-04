# -*- coding: utf-8 -*-
"""🌗 Chế độ ngày + tab "Hôm nay" (Daily Task) — Claude 2026-10-03.

Bạn không làm đều mỗi ngày: có ngày ⛺ Camp (dồn sức, ví dụ lên thư viện) và ngày 💤 Rest (nghỉ). Chế độ ghi ở bảng 🌗 Chế độ ngày
(mỗi ngày đặc biệt 1 dòng; không có dòng = Bình thường). Các "giám sát viên" nhìn vào đây:
  • A4 (n8n) đọc 🎛️ University Control — web app đồng bộ chế độ HÔM NAY sang Control (Camp Mode / Camp Hours / Rest Mode)
    Rest: không xếp việc mới, chỉ giữ việc có hạn đúng hôm nay · Camp: trần giờ = số giờ camp
  • weekly.py: hiện ⛺/💤 từng ngày, gợi ý camp tránh ngày Rest, tính cả ngày camp đã đặt
  • checks.py / bản tin: ngày Rest không đẩy việc · Copilot: "mai mình nghỉ", "thứ Bảy camp 7 tiếng"
"""
import uc_config as cfg
import datetime as dt, time
from academic import Notion, P, rt, title, TZ

MODES = cfg.notion("day_modes")
CONTROL = cfg.notion("control")
DAILY = cfg.notion("daily_plan")
VALID = ("Bình thường", "Camp", "Rest")
DOW_FULL = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]

def _today():
    return dt.datetime.now(TZ).date()

def get_modes(nt, start, end):
    rows = nt.query(MODES, {"and": [{"property": "Date", "date": {"on_or_after": start.isoformat()}},
                                    {"property": "Date", "date": {"on_or_before": end.isoformat()}}]})
    out = {}
    for r in sorted(rows, key=lambda r: r.get("last_edited_time", "")):
        d = (P(r, "Date") or "")[:10]
        if d: out[d] = {"id": r["id"], "mode": P(r, "Chế độ") or "Bình thường", "hours": P(r, "Giờ"), "note": P(r, "Ghi chú") or ""}
    return out

def mode_of(nt, day):
    return get_modes(nt, day, day).get(day.isoformat(), {"mode": "Bình thường", "hours": None})

def camp_default(nt):
    c = next(iter(nt.query(CONTROL)), None)
    return float(P(c, "Camp Hours") or 6) if c else 6.0

def sync_control(nt):
    """Chế độ HÔM NAY -> 🎛️ University Control (A4 đọc Control)."""
    today = _today()
    m = mode_of(nt, today)
    c = next(iter(nt.query(CONTROL)), None)
    if not c: return
    hours = float(m.get("hours") or P(c, "Camp Hours") or 6)
    label = {"Camp": f"⛺ Camp {hours:g}h", "Rest": "💤 Rest", "Bình thường": "Bình thường"}[m["mode"]] + f" · {today:%d/%m/%Y}"
    want = {"Camp Mode": m["mode"] == "Camp", "Rest Mode": m["mode"] == "Rest", "Chế độ hôm nay": label}
    if m["mode"] == "Camp": want["Camp Hours"] = hours
    if all((P(c, k) if k != "Chế độ hôm nay" else (P(c, k) or "")) == v for k, v in want.items()): return
    props = {k: ({"checkbox": v} if isinstance(v, bool) else {"number": v} if isinstance(v, float) else rt(v)) for k, v in want.items()}
    nt.patch(c["id"], props)

def set_mode(post, day, mode, hours=None, note="", source="Bạn"):
    nt = Notion(post)
    d = day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day)[:10])
    if mode not in VALID: return {"ok": False, "loi": "Chế độ: Bình thường, Camp hoặc Rest."}
    if d < _today() - dt.timedelta(days=7): return {"ok": False, "loi": "Chỉ đặt chế độ cho tuần này trở đi."}
    hours = float(hours) if hours not in (None, "") else (camp_default(nt) if mode == "Camp" else None)
    if mode == "Camp" and not (1 <= hours <= 14): return {"ok": False, "loi": "Giờ camp từ 1 đến 14."}
    props = {"Ngày": title(f"{DOW_FULL[d.weekday()]} {d:%d/%m/%Y}"), "Date": {"date": {"start": d.isoformat()}},
             "Chế độ": {"select": {"name": mode}}, "Giờ": {"number": hours if mode == "Camp" else None},
             "Nguồn": {"select": {"name": source}}, "Ghi chú": rt(note or "")}
    cur = get_modes(nt, d, d).get(d.isoformat())
    if cur: nt.patch(cur["id"], props)
    elif mode != "Bình thường": nt.create(MODES, props)
    if d == _today(): sync_control(nt)
    vi = f"⛺ Camp {hours:g} giờ" if mode == "Camp" else "💤 nghỉ (Rest)" if mode == "Rest" else "bình thường"
    return {"ok": True, "da_ghi": [f"{DOW_FULL[d.weekday()]} {d:%d/%m}: {vi}"]}

_cache = {"at": 0, "week": None, "busy": False}

def _week_async(post, today):
    """Dựng 📅 đánh giá tuần ở luồng nền (một lượt tại một thời điểm); lỗi (vd Notion giới hạn tần suất) giữ bản cũ."""
    import threading
    if _cache["busy"]: return
    _cache["busy"] = True
    def job():
        try:
            import weekly
            _cache.update(week=weekly.build(Notion(post), today), at=time.time())
        except Exception as e:
            if not _cache["week"] or "error" in _cache["week"]: _cache["week"] = {"error": str(e)[:200]}
            _cache["at"] = time.time() - 240   # thử lại sau ~1 phút
        finally:
            _cache["busy"] = False
    threading.Thread(target=job, daemon=True).start()

def today_view(post, refresh=False):
    nt = Notion(post)
    today = _today()
    mon = today - dt.timedelta(days=today.weekday())
    modes = get_modes(nt, mon, today + dt.timedelta(days=13))
    daily = nt.query(DAILY, {"property": "Date", "date": {"equals": today.isoformat()}})
    items = [{"id": r["id"], "task": P(r, "Task") or "", "est": P(r, "Estimate (hrs)") or 0, "status": P(r, "Status") or "Not started",
              "priority": P(r, "Priority") or "", "note": P(r, "Planner Notes") or ""} for r in daily]
    items.sort(key=lambda x: (x["status"] == "Done", {"High": 0, "Medium": 1, "Low": 2}.get(x["priority"], 3)))
    if refresh or not _cache["week"] or time.time() - _cache["at"] > 300:
        _week_async(post, today)   # đánh giá tuần gọi Notion rất nhiều lần → dựng ngầm, tab Hôm nay không phải chờ
    w = _cache["week"] or {"error": "Đang tính đánh giá tuần…"}
    days = []
    for i in range(14):
        d = mon + dt.timedelta(days=i)
        m = modes.get(d.isoformat(), {"mode": "Bình thường", "hours": None})
        days.append({"date": d.isoformat(), "dow": DOW_FULL[d.weekday()], "mode": m["mode"], "hours": m.get("hours"),
                     "done": (w.get("per_day") or {}).get(d.isoformat()),
                     "suggested": w.get("camp_day") == d.isoformat(), "past": d < today, "today": d == today})
    m = modes.get(today.isoformat(), {"mode": "Bình thường", "hours": None})
    done_h = sum(float(x["est"] or 0) for x in items if x["status"] == "Done")
    plan_h = sum(float(x["est"] or 0) for x in items)
    return {"today": today.isoformat(), "dow": DOW_FULL[today.weekday()], "mode": m["mode"], "hours": m.get("hours") or camp_default(nt),
            "items": items, "doneHours": round(done_h, 2), "planHours": round(plan_h, 2), "days": days,
            "week": {k: w.get(k) for k in ("week", "verdict", "hours", "pattern", "need_next", "capacity", "camp_day", "camp_days", "focus", "error")}}

def mark_daily(post, row_id, done):
    Notion(post).patch(row_id, {"Status": {"status": {"name": "Done" if done else "Not started"}}})
    _cache["at"] = 0
    return {"ok": True}
