# -*- coding: utf-8 -*-
"""📅 Weekly Reviews — đánh giá tiến độ theo TUẦN, không theo ngày (Claude 2026-10-03, ý tưởng gốc của Freebuff / người dùng).

Vì sao: bạn không làm đều mỗi ngày — có ngày nghỉ, có ngày dồn lên thư viện làm hăng (nguồn gốc Camp Mode). Giám sát theo ngày
coi "hôm nay chưa xong" là trễ -> cảnh báo sai. Ở đây chỉ kết luận khi nhìn cả tuần (thứ Hai → Chủ nhật).

Kết luận tuần:
  • Ổn          : không lỡ deadline thật, và giờ cần cho tuần sau ≤ sức làm (trung bình giờ/tuần 2 tuần gần nhất)
  • Cần tăng tốc: thiếu, nhưng ≤ 1 ngày camp (Camp Hours ở 🎛️ University Control) là bù được -> gợi ý ngày camp
  • Không ổn    : lỡ deadline thật, hoặc thiếu nhiều hơn 1 ngày camp
"Quá hạn" chỉ là deadline THẬT của bài tập (📋 Academic Work) đã qua mà chưa nộp; việc nhỏ trượt lịch chỉ là "dời lại".
Chạy: n8n Chủ nhật 21:00 -> /api/weekly (ghi 1 dòng 📅 Weekly Reviews, mỗi tuần 1 dòng) · Copilot "tuần này thế nào?" (tính tại chỗ).
"""
import uc_config as cfg
import datetime as dt
from academic import Notion, P, rt, title, TZ

DAILY = cfg.notion("daily_plan")
TASKS = cfg.notion("academic_tasks")
WORK = cfg.notion("academic_work")
ATTEND = cfg.notion("attendance")
GRADES = cfg.notion("grades")
CONTROL = cfg.notion("control")
WEEKLY = cfg.notion("weekly_reviews")
DONE_WORK = ("Submitted", "Graded")
DOW = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def _day(s):
    if not s: return None
    if len(s) <= 10: return dt.date.fromisoformat(s)
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(TZ).date()

def week_of(d):
    mon = d - dt.timedelta(days=d.weekday())
    return mon, mon + dt.timedelta(days=6)

def done_hours(daily, tasks, start, end):
    """Giờ đã làm theo ngày trong [start, end]: dòng 📅 Daily Task Done (theo Date) + task gốc Done không có dòng Daily (theo ngày sửa)."""
    per = {start + dt.timedelta(days=i): 0.0 for i in range((end - start).days + 1)}
    via_daily = set()
    for r in daily:
        d = _day(P(r, "Date"))
        if P(r, "Status") == "Done" and d and start <= d <= end:
            per[d] += float(P(r, "Estimate (hrs)") or 0)
            via_daily.update(P(r, "Source Task") or [])
    # task đóng bởi automation (A3 thay thế / rác automation) hoặc đóng hàng loạt cùng một phút (dọn dữ liệu) KHÔNG phải giờ học
    import collections
    batch = collections.Counter((t.get("last_edited_time") or "")[:16] for t in tasks if P(t, "Status") == "Done")
    def automated(t):
        note = (P(t, "Blocked Reason") or "").lower()
        stale = _day(P(t, "Due")) and _day(P(t, "Due")) < start - dt.timedelta(days=7)   # đóng sổ muộn việc cũ, không phải giờ học tuần này
        return note.startswith(("superseded", "invalid automation")) or batch[(t.get("last_edited_time") or "")[:16]] >= 5 or stale
    for t in tasks:
        d = _day(t.get("last_edited_time"))
        if P(t, "Status") == "Done" and d and start <= d <= end and t["id"] not in via_daily and not automated(t):
            per[d] += float(P(t, "Actual Time (hrs)") or P(t, "Estimate (hrs)") or 0)
    return per

def build(nt, today=None):
    today = today or dt.datetime.now(TZ).date()
    start, end = week_of(today)
    nxt_end = end + dt.timedelta(days=7)
    daily, tasks, work = nt.query(DAILY), nt.query(TASKS), nt.query(WORK)
    ctrl = next(iter(nt.query(CONTROL)), None)
    camp_hours = float(P(ctrl, "Camp Hours") or 6) if ctrl else 6.0
    courses = {c["id"]: c for c in nt.courses()}
    cname = lambda ids: ", ".join(f"{courses[i]['code']} {courses[i]['name']}" for i in (ids or []) if i in courses) or "—"
    wmap = {w["id"]: w for w in work}

    # giờ làm tuần này + 2 tuần gần nhất (sức làm)
    per = done_hours(daily, tasks, start, end)
    week_hours = sum(per.values())
    prev = done_hours(daily, tasks, start - dt.timedelta(days=14), start - dt.timedelta(days=1))
    hist = (sum(prev.values()) + week_hours) / 3 if (sum(prev.values()) + week_hours) > 0 else 0.0
    try:   # 🌗 Chế độ ngày: ⛺ Camp / 💤 Rest
        import daymode
        modes = daymode.get_modes(nt, start, nxt_end)
    except Exception:
        modes = {}
    icon = lambda d: {"Camp": "⛺", "Rest": "💤"}.get((modes.get(d.isoformat()) or {}).get("mode"), "")
    pattern = " · ".join(f"{DOW[i]}{icon(start + dt.timedelta(days=i))} {per[start + dt.timedelta(days=i)]:g}h" for i in range(7))
    ahead = [today + dt.timedelta(days=i) for i in range(1, (nxt_end - today).days + 1)]
    planned_camp = [(d, float((modes.get(d.isoformat()) or {}).get("hours") or camp_hours)) for d in ahead if (modes.get(d.isoformat()) or {}).get("mode") == "Camp"]
    planned_rest = [d for d in ahead if (modes.get(d.isoformat()) or {}).get("mode") == "Rest"]
    burst_days = [DOW[i] for i in range(7) if per[start + dt.timedelta(days=i)] >= max(4, camp_hours * 0.75)]

    # deadline thật
    def wdue(w): return _day(P(w, "Due"))
    missed = [w for w in work if wdue(w) and wdue(w) <= min(today, end) and P(w, "Status") not in DONE_WORK]
    missed_this_week = [w for w in missed if wdue(w) >= start]
    submitted = [w for w in work if P(w, "Status") in DONE_WORK and _day(w.get("last_edited_time")) and start <= _day(w["last_edited_time"]) <= end]
    upcoming = sorted([w for w in work if wdue(w) and end < wdue(w) <= nxt_end and P(w, "Status") not in DONE_WORK], key=wdue)

    # giờ cần cho tuần sau: task chưa xong của bài có hạn ≤ hết tuần sau (bài chưa nộp), + task không thuộc bài có hạn riêng ≤ hết tuần sau
    open_tasks = [t for t in tasks if P(t, "Status") != "Done"]
    def need_by(t):
        ws = [wmap[i] for i in (P(t, "Academic Work") or []) if i in wmap]
        if ws: return wdue(ws[0]) if P(ws[0], "Status") not in DONE_WORK else None
        return _day(P(t, "Due"))
    need_next = sum(float(P(t, "Estimate (hrs)") or 1) for t in open_tasks if need_by(t) and today < need_by(t) <= nxt_end)
    slipped = [t for t in open_tasks if _day(P(t, "Due")) and _day(P(t, "Due")) < today and need_by(t) and need_by(t) > today]

    # ước lượng: task xong trong tuần có giờ thực tế
    est_pairs = [(float(P(t, "Estimate (hrs)") or 0), float(P(t, "Actual Time (hrs)") or 0)) for t in tasks
                 if P(t, "Status") == "Done" and P(t, "Actual Time (hrs)") and _day(t.get("last_edited_time")) and start <= _day(t["last_edited_time"]) <= end]
    drift = None
    if est_pairs and sum(e for e, _ in est_pairs):
        drift = round(100 * (sum(a for _, a in est_pairs) / sum(e for e, _ in est_pairs) - 1))

    # môn có rủi ro (checks.py), vắng & điểm ghi trong tuần
    try:
        import checks
        risks = [x["noi_dung"] for x in checks.run(nt.post, today.isoformat())["canh_bao"] if x["loai"] != "thieu_du_lieu"]
    except Exception:
        risks = []
    in_week = lambda r: _day(r.get("created_time")) and start <= _day(r["created_time"]) <= end
    absences = [f"{cname(P(r, 'Course'))}: {P(r, 'Status')}" for r in nt.query(ATTEND) if in_week(r)]
    grades = [f"{cname(P(r, 'Course'))} · {P(r, 'Component')} {P(r, 'Score 10')}" for r in nt.query(GRADES) if in_week(r)]

    # kết luận
    capacity = hist if hist >= 1 else None
    extra = sum(h for _, h in planned_camp)   # ngày camp bạn đã đặt = sức làm thêm
    gap = need_next - (capacity or 0) - extra
    if missed_this_week:   # bài lỡ hạn từ tuần trước chỉ được hỏi lại "đã nộp chưa?", không kéo mọi tuần sau thành "Không ổn"
        verdict = "Không ổn"
    elif capacity is None:
        verdict = "Ổn" if need_next <= camp_hours + extra else "Cần tăng tốc"
    elif gap <= 0:
        verdict = "Ổn"
    elif gap <= camp_hours:
        verdict = "Cần tăng tốc"
    else:
        verdict = "Không ổn"
    first_due = wdue(upcoming[0]) if upcoming else None
    camp_day, camp_days = None, 0
    short = gap if capacity is not None else need_next - camp_hours - extra   # giờ còn thiếu so với sức làm
    if verdict != "Ổn" and need_next > 0 and short > 0:
        import math
        camp_days = max(1, math.ceil(short / camp_hours))
        last_ok = (first_due or nxt_end) - dt.timedelta(days=1)
        free = [x for x in ahead if x <= last_ok and x not in planned_rest and x not in [p for p, _ in planned_camp]]
        camp_day = free[-1] if free else max(last_ok - dt.timedelta(days=1), today + dt.timedelta(days=1))   # tránh ngày 💤 Rest
    week_no = None
    try:
        import tkb
        week_no = (start - tkb.week1(start)).days // 7 + 1
    except Exception:
        pass

    focus = (f"Tuần sau cần ~{need_next:g}h cho {len(upcoming)} hạn nộp; sức làm gần đây ~{capacity:.1f}h/tuần." if capacity is not None
             else f"Tuần sau cần ~{need_next:g}h cho {len(upcoming)} hạn nộp; chưa đủ dữ liệu giờ làm để ước sức làm.")
    if camp_day:
        focus += (f" Thiếu ~{short:.1f}h: gợi ý {camp_days} ngày camp × {camp_hours:g}h, ngày đầu {DOW[camp_day.weekday()]} {camp_day:%d/%m} "
                  f"(bật Camp Mode hôm đó)" + ("." if camp_days == 1 else f" — {camp_days} ngày camp là nhiều, cân nhắc xin gia hạn / bỏ bớt việc."))
    if planned_camp or planned_rest:
        focus += (" Đã đặt: " + ", ".join([f"⛺ {DOW[d.weekday()]} {d:%d/%m} {h:g}h" for d, h in planned_camp] +
                                           [f"💤 {DOW[d.weekday()]} {d:%d/%m}" for d in planned_rest]) + ".")
    if missed_this_week:
        focus = "Lỡ deadline trong tuần: " + "; ".join(f"{P(w, 'Name')} (hạn {wdue(w):%d/%m})" for w in missed_this_week) +                 " — nộp muộn được không / đã nộp thì báo Copilot để đánh dấu. " + focus
    if drift is not None and abs(drift) >= 20:
        focus += f" Ước lượng của bạn đang {'thấp' if drift > 0 else 'cao'} hơn thực tế ~{abs(drift)}% — chia việc nên tính {'dư' if drift > 0 else 'bớt'} giờ."
    return {
        "week": f"Tuần {week_no} · {start:%d/%m}–{end:%d/%m/%Y}" if week_no and week_no > 0 else f"Tuần {start:%d/%m}–{end:%d/%m/%Y}",
        "start": start.isoformat(), "end": end.isoformat(), "verdict": verdict,
        "hours": round(week_hours, 2), "pattern": pattern, "per_day": {d.isoformat(): round(h, 2) for d, h in per.items()}, "burst_days": burst_days, "capacity": round(capacity, 1) if capacity is not None else None,
        "need_next": round(need_next, 2), "camp_day": camp_day.isoformat() if camp_day else None, "camp_days": camp_days,
        "submitted": [P(w, "Name") for w in submitted],
        "missed": [f"{P(w, 'Name')} · hạn {wdue(w):%d/%m} · {cname(P(w, 'Course'))}" for w in missed],
        "upcoming": [f"{P(w, 'Name')} · hạn {wdue(w):%d/%m} · {P(w, 'Type') or 'bài'} · {cname(P(w, 'Course'))}" for w in upcoming],
        "slipped": [P(t, "Task") for t in slipped], "risks": risks, "absences": absences, "grades": grades,
        "drift_pct": drift, "focus": focus,
    }

def save(nt, r):
    def T(xs, empty): return "\n".join("• " + x for x in xs)[:1900] if xs else empty
    done_txt = (f"{r['hours']:g} giờ · {r['pattern']}" + (f" · ngày dồn: {', '.join(r['burst_days'])}" if r["burst_days"] else "")
                + ("\nĐã nộp: " + "; ".join(r["submitted"]) if r["submitted"] else ""))
    carry = r["slipped"] and [f"{len(r['slipped'])} việc nhỏ dời lại (bài chưa tới hạn — bình thường)"] or []
    carry += [f"Deadline thật đã qua, chưa đánh dấu nộp: {m} — đã nộp chưa?" for m in r["missed"]]
    props = {"Week": title(f"{r['week']} · {r['verdict']}"), "Week Start": {"date": {"start": r["start"]}},
             "Completed": rt(done_txt), "At Risk Courses": rt(T(r["risks"], "Không có")),
             "Attendance Notes": rt(T(r["absences"], "Không ghi buổi vắng nào trong tuần")),
             "GPA Notes": rt(T(r["grades"], "Không có điểm mới trong tuần")),
             "Upcoming Deadlines": rt(T(r["upcoming"], "Tuần sau không có hạn nộp")),
             "Carry Over": rt(T(carry, "Không có")), "Next Week Focus": rt(r["focus"]), "Status": {"select": {"name": "Draft"}}}
    old = [x for x in nt.query(WEEKLY) if (P(x, "Week Start") or "")[:10] == r["start"]]
    if old:
        nt.patch(old[0]["id"], props); return old[0]["id"]
    return nt.create(WEEKLY, props).get("id")

def run(post, save_row=False, today=None):
    nt = Notion(post)
    r = build(nt, dt.date.fromisoformat(today) if today else None)
    if save_row: r["notion_id"] = save(nt, r)
    return {"ok": True, "ket_qua": r}
