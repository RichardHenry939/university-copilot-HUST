# -*- coding: utf-8 -*-
"""Nạp TKB toàn kỳ qua Uni Copilot (Claude 2026-10-03; dùng từ kỳ 2026.2).

Sinh viên dán TKB (chữ/ảnh) cho Copilot → agent tách thành danh sách lớp → công cụ nhap_tkb → POST /api/tkb.
  buoc=xem_truoc : sinh toàn bộ buổi, trả tóm tắt (không ghi) để Copilot đọc lại cho sinh viên xác nhận.
  buoc=ghi       : tạo buổi mới (Kind=Class, Sync Key "<mã kỳ>|<mã môn>|<loại>|<ngày>|<giờ>"), bỏ buổi Class cũ trong
                   khoảng ngày của kỳ vào thùng rác Notion (khôi phục được 30 ngày, qua webhook copilot-tkb-archive —
                   chỉ nhận trang thuộc Academic Timetable có Kind=Class), môn có trong TKB → Taking.
Chạy lại với TKB đã sửa: buổi trùng Sync Key được giữ, buổi không còn trong TKB mới bị thay.

lop: [{mon, loai, thu (2..7 | CN), bat_dau "HH:MM", ket_thuc, phong, giang_vien, hinh_thuc (Online/Offline),
       tu_ngay, den_ngay (tuỳ chọn, giới hạn lớp trong khoảng), tuan_chan_le ("chan"/"le", tuỳ chọn),
       tuan ([2,3,6,…] tuỳ chọn — chỉ học đúng các tuần này, như qldt ghi), ghi_chu}]
nghi: [{tu, den, ly_do, mon (tuỳ chọn: chỉ nghỉ môn đó)}]   — vd đợt QP-AN, nghỉ lễ
"""
import uc_config as cfg
import datetime as dt, json
from academic import Notion, P, rt, title, find_course, current_sem, TZ

EVENTS = cfg.notion("calendar_events")
THU = {"2": 0, "3": 1, "4": 2, "5": 3, "6": 4, "7": 5, "cn": 6, "8": 6}


def week1(day):
    """Thứ 2 của tuần 1 năm học chứa `day` (HUST đánh số tuần liên tục cả năm học; chẵn/lẻ tính từ mốc này).
    Lấy từ semester_calendar.json "week1" {"2026": "2026-08-31"}; chưa có thì = thứ 2 sau ngày khai kỳ lẻ 1 tuần."""
    import semester
    c = semester.cal(); y = day.year if day >= semester._d(day.year, c["odd_start"], c, "odd_start") else day.year - 1
    if str(y) in (c.get("week1") or {}): return _date(c["week1"][str(y)])
    d = semester._d(y, c["odd_start"], c, "odd_start") + dt.timedelta(days=7)
    return d - dt.timedelta(days=d.weekday())


def _date(s):
    return dt.date.fromisoformat(str(s).strip()[:10])

def _hhmm(s):
    s = str(s or "").strip().lower().replace("h", ":").replace(".", ":")
    h, _, m = s.partition(":")
    h, m = int(h), int(m or 0)
    if not (0 <= h < 24 and 0 <= m < 60): raise ValueError(s)
    return f"{h:02d}:{m:02d}"

def _load(x):
    if isinstance(x, (list, dict)): return x
    x = (x or "").strip()
    return json.loads(x) if x else []

def plan(nt, a):
    """-> (events, courses{code: course}, problems[])"""
    probs = []
    try:
        start, end = _date(a.get("bat_dau")), _date(a.get("ket_thuc"))
    except Exception:
        return [], {}, ["Thiếu ngày bắt đầu / kết thúc kỳ học (dạng YYYY-MM-DD)."]
    if not (dt.timedelta(days=20) <= end - start <= dt.timedelta(days=200)):
        return [], {}, [f"Khoảng ngày {start}→{end} không giống một kỳ học."]
    sem = (a.get("ky") or "").upper().replace(" ", "") or current_sem(nt)
    code_sem = a.get("ma_ky") or f"{start.year if start.month >= 8 else start.year - 1}{'1' if start.month >= 8 else '2'}"
    try:
        lop, nghi = _load(a.get("lop")), _load(a.get("nghi"))
    except Exception as e:
        return [], {}, [f"Danh sách lớp/nghỉ không đọc được ({e})."]
    if not lop: return [], {}, ["Chưa có lớp nào trong TKB."]
    offs = []
    for n in nghi:
        try: offs.append((_date(n["tu"]), _date(n.get("den") or n["tu"]), n.get("ly_do") or "Nghỉ", (n.get("mon") or "").strip()))
        except Exception: probs.append(f"Đợt nghỉ không rõ ngày: {n}")
    events, courses = [], {}
    for o in offs:   # mỗi đợt nghỉ dài/ngày lễ: 1 dòng nhiều ngày (tiêu đề không có '·' để tab Lịch hiện thành dải)
        if not o[3]:
            events.append({"date": o[0], "code": "", "course": None, "title": f"⛔ {o[2]} ({o[0]:%d/%m} → {o[1]:%d/%m})",
                           "start": o[0].isoformat(), "end": o[1].isoformat() if o[1] > o[0] else None,
                           "room": "", "notes": "Các lớp khác nghỉ trong đợt này.", "key": f"{code_sem}|NGHI|{o[0]}"})
    for i, l in enumerate(lop, 1):
        c, ask = find_course(nt, l.get("mon"), sem)
        if ask: probs.append(f"Lớp {i} ({l.get('mon')}): {ask}"); continue
        wd = THU.get(str(l.get("thu", "")).lower().replace("thứ", "").replace("t", "").strip())
        try: t0, t1 = _hhmm(l.get("bat_dau")), _hhmm(l.get("ket_thuc"))
        except Exception: probs.append(f"Lớp {i} ({c['code']}): giờ học không rõ."); continue
        if wd is None: probs.append(f"Lớp {i} ({c['code']}): không rõ thứ mấy."); continue
        lo = _date(l["tu_ngay"]) if l.get("tu_ngay") else start
        hi = _date(l["den_ngay"]) if l.get("den_ngay") else end
        parity = (l.get("tuan_chan_le") or "").lower()
        kind = (l.get("loai") or "Lớp").strip()
        mode = (l.get("hinh_thuc") or ("Online" if "online" in str(l.get("phong", "")).lower() else "Offline")).strip()
        courses[c["code"]] = c
        d = lo + dt.timedelta(days=(wd - lo.weekday()) % 7)
        while d <= min(hi, end):
            week = (d - week1(d)).days // 7 + 1
            off = next((o for o in offs if o[0] <= d <= o[1] and (not o[3] or o[3].lower() in (c["code"].lower(), c["name"].lower()))), None)
            if not off and not (parity == "chan" and week % 2) and not (parity == "le" and not week % 2) \
                    and (not l.get("tuan") or week in l["tuan"]):   # danh sách tuần học theo qldt
                note = " · ".join(x for x in (f"GV {l['giang_vien']}" if l.get("giang_vien") else "", l.get("ghi_chu") or "") if x)
                events.append({"date": d, "code": c["code"], "course": c["id"],
                               "title": f"{c['code']} · {c['name']} · {kind} · {mode}",
                               "start": f"{d}T{t0}:00+07:00", "end": f"{d}T{t1}:00+07:00",
                               "room": l.get("phong") or mode, "notes": note, "key": f"{code_sem}|{c['code']}|{kind}|{d}|{t0}"})
            d += dt.timedelta(days=7)
    return events, courses, probs, (start, end, sem, code_sem, offs)


def run(post, a):
    nt = Notion(post)
    r = plan(nt, a)
    if len(r) == 3:
        return {"ok": False, "thieu": r[2]}
    events, courses, probs, (start, end, sem, code_sem, offs) = r
    if probs:
        return {"ok": False, "thieu": probs, "goi_y": "Hỏi lại sinh viên đúng các chỗ trên rồi gọi lại nhap_tkb."}
    per = {}
    for e in events:
        if e["code"]: per[e["code"]] = per.get(e["code"], 0) + 1
    sem_courses = [c for c in nt.courses() if c["semester"] == sem and c["status"] != "Completed"]
    missing = [f"{c['code']} {c['name']}" for c in sem_courses if c["code"] not in courses]
    summary = {"ky": sem, "ma_ky": code_sem, "tu": start.isoformat(), "den": end.isoformat(), "so_buoi": sum(per.values()),
               "theo_mon": {f"{k} {courses[k]['name']}": v for k, v in per.items()},
               "nghi": [f"{o[0]:%d/%m}→{o[1]:%d/%m} {o[2]}" + (f" ({o[3]})" if o[3] else "") for o in offs],
               "mon_du_kien_khong_co_trong_tkb": missing,
               "tuan_dau": [f"{e['date']:%a %d/%m} {e['start'][11:16]}–{e['end'][11:16]} {e['title']} · {e['room']}"
                            for e in events if e["date"] < start + dt.timedelta(days=7)]}
    if (a.get("buoc") or "xem_truoc") != "ghi":
        return {"ok": True, "xem_truoc": summary,
                "huong_dan": "Đọc tóm tắt cho sinh viên. Chỉ khi sinh viên đồng ý mới gọi lại nhap_tkb với buoc=ghi và CÙNG dữ liệu."}
    # buổi Class cũ trong khoảng kỳ
    old = nt.query(EVENTS, {"and": [{"property": "Kind", "select": {"equals": "Class"}},
                                    {"property": "When", "date": {"on_or_after": (start - dt.timedelta(days=1)).isoformat()}},
                                    {"property": "When", "date": {"on_or_before": (end + dt.timedelta(days=1)).isoformat()}}]})
    keys = {e["key"] for e in events}
    have = {P(o, "Sync Key") for o in old}
    drop = [o["id"] for o in old if P(o, "Sync Key") not in keys]
    if drop:
        res = post("copilot-tkb-archive", {"ids": drop})
        res = res[0] if isinstance(res, list) else res
        if res.get("bo_qua"): return {"ok": False, "loi": f"Cổng lưu trữ từ chối {len(res['bo_qua'])} trang — dừng, chưa tạo buổi mới."}
    ops = [{"method": "POST", "url": "https://api.notion.com/v1/pages", "body": {"parent": {"database_id": EVENTS}, "properties": {
        "Event": title(e["title"]), "Kind": {"select": {"name": "Class"}}, "Course": {"relation": [{"id": e["course"]}] if e["course"] else []},
        "When": {"date": {"start": e["start"], "end": e["end"]}}, "Location": rt(e["room"]), "Notes": rt(e["notes"]),
        "Sync Key": rt(e["key"])}}} for e in events if e["key"] not in have]
    for i in range(0, len(ops), 50): nt.ops(ops[i:i + 50])
    for c in courses.values():
        props = {} if c["status"] == "Taking" else {"Status": {"status": {"name": "Taking"}}}
        if c["semester"] != sem:   # học sớm / học lại / dời kỳ theo TKB thật
            props["Semester"] = {"select": {"name": sem}}
            if not c["orig"] and c["semester"]: props["Original Semester"] = {"select": {"name": c["semester"]}}
            props["Course Notes"] = rt((c["notes"] + " | " if c["notes"] else "") + f"Học ở {sem} theo TKB {code_sem} (dự kiến {c['semester']}).")
        if props: nt.patch(c["id"], props)
    for c in sem_courses:
        if c["code"] not in courses and c["status"] == "Taking":
            nt.patch(c["id"], {"Status": {"status": {"name": "Planned"}},
                               "Course Notes": rt((c["notes"] + " | " if c["notes"] else "") + f"Không có trong TKB {code_sem} ({dt.datetime.now(TZ):%d/%m/%Y}).")})
    return {"ok": True, "da_ghi": [f"{len(ops)} buổi mới", f"{len(drop)} buổi cũ vào thùng rác Notion",
                                   f"đang học: {', '.join(sorted(courses))}"], "tom_tat": summary}
