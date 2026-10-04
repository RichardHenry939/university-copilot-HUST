# -*- coding: utf-8 -*-
"""Kiểm tra học tập cho bản tin (Claude 2026-10-03) — thay "Exam Revision Planner" (tác vụ ChatGPT, đã tạm dừng).

Bản tin 07:20/21:30 gọi POST /api/checks. CHỈ trả về chỗ có vấn đề (ngày bình thường: danh sách rỗng):
  • chuyên cần : môn còn ≤ 1 buổi được vắng (hoặc đã vượt)
  • điểm       : đã có QT + trọng số mà cuối kỳ cần > 7 mới qua (D = 4.0), hoặc không thể qua; điểm học phần < 4
  • ôn thi     : thi (Academic Work Midterm/Final/Quiz) trong 14 ngày mà chưa có dòng 📝 Exam Revision
                 (khớp theo ngày thi ±1 và tên/mã môn), hoặc thi ≤ 3 ngày mà ôn còn 'Not started' / tự tin 'Weak'
  • thiếu dữ liệu: (thứ 2) môn đang học chưa có luật môn (trọng số, số buổi được vắng)
"""
import uc_config as cfg
import datetime as dt
from academic import Notion, P, TZ, current_sem, course_status, norm

WORK = cfg.notion("academic_work")
REVISION = cfg.notion("exam_revision")
EXAM_TYPES = ("Midterm", "Final", "Quiz")
VN = {"Midterm": "giữa kỳ", "Final": "cuối kỳ", "Quiz": "kiểm tra"}


def _day(s):
    return dt.date.fromisoformat(str(s)[:10]) if s else None

def run(post, today=None):
    nt = Notion(post)
    today = dt.date.fromisoformat(today) if today else dt.datetime.now(TZ).date()
    sem = current_sem(nt)
    out = []
    taking = [c for c in nt.courses() if c["status"] == "Taking"]
    by_id = {c["id"]: c for c in nt.courses()}

    # chuyên cần + điểm
    for c in taking:
        try: st = course_status(nt, c, sem)
        except Exception: continue
        left = st.get("con_duoc_vang")
        if left is not None and left <= 1:
            out.append({"loai": "chuyen_can", "muc": "cao" if left <= 0 else "vua",
                        "noi_dung": f"{c['code']} {c['name']}: " + (f"đã vắng quá {st['vuot_vang']} buổi so với luật môn" if st.get("vuot_vang") else
                                                                   "hết buổi được vắng" if left == 0 else "chỉ còn 1 buổi được vắng")})
        hp = st.get("diem_hoc_phan")
        if hp is not None and hp < 4:
            out.append({"loai": "diem", "muc": "cao", "noi_dung": f"{c['code']} {c['name']}: điểm học phần {hp} (< 4, chưa qua)"})
        need = st.get("ck_can_de_qua")
        if need is not None and need > 7:
            out.append({"loai": "diem", "muc": "cao" if need > 10 else "vua",
                        "noi_dung": f"{c['code']} {c['name']}: " + ("điểm quá trình hiện tại không đủ để qua dù cuối kỳ 10" if need > 10
                                                                   else f"cuối kỳ cần ≥ {need} mới qua môn")})

    # ôn thi
    exams = []
    for w in nt.query(WORK, {"and": [{"property": "Type", "select": {"is_not_empty": True}},
                                     {"property": "Due", "date": {"on_or_after": today.isoformat()}},
                                     {"property": "Due", "date": {"on_or_before": (today + dt.timedelta(days=14)).isoformat()}}]}):
        if P(w, "Type") in EXAM_TYPES and P(w, "Status") != "Graded":
            cs = [by_id.get(i) for i in (P(w, "Course") or [])]
            exams.append({"name": P(w, "Name") or "", "type": P(w, "Type"), "day": _day(P(w, "Due")), "course": next((x for x in cs if x), None)})
    revs = [{"t": norm((P(r, "Revision Item") or "") + " " + (P(r, "Topic") or "")), "day": _day(P(r, "Exam Date")),
             "type": P(r, "Exam Type"), "status": P(r, "Status"), "conf": P(r, "Confidence")} for r in nt.query(REVISION)] if exams else []
    for e in exams:
        c = e["course"]; label = f"{c['code']} {c['name']}" if c else e["name"]
        keys = [norm(c["code"]), norm(c["name"])] if c else [norm(e["name"])]
        mine = [r for r in revs if (r["day"] and e["day"] and abs((r["day"] - e["day"]).days) <= 1 and (not r["type"] or r["type"] == e["type"]))
                and (any(k and k in r["t"] for k in keys) or len([x for x in exams if x["day"] == e["day"]]) == 1)]
        days = (e["day"] - today).days
        when = "hôm nay" if days == 0 else "ngày mai" if days == 1 else f"còn {days} ngày ({e['day']:%d/%m})"
        if not mine:
            out.append({"loai": "on_thi", "muc": "cao" if days <= 3 else "vua",
                        "noi_dung": f"Thi {VN[e['type']]} {label} {when} — chưa có kế hoạch ôn (nói với Copilot để lập)"})
        elif days <= 3 and any(r["status"] == "Not started" or r["conf"] == "Weak" for r in mine):
            out.append({"loai": "on_thi", "muc": "cao", "noi_dung": f"Thi {VN[e['type']]} {label} {when} — phần ôn còn chưa bắt đầu hoặc đang yếu"})

    # thiếu luật môn: nhắc mỗi thứ 2 (luật chỉ biết khi giảng viên nói ở buổi đầu)
    missing = [f"{c['code']} {c['name']}" for c in taking if c["credits"] and (c["w_qt"] is None or c["max_abs"] is None)]
    if missing and today.weekday() == 0:
        out.append({"loai": "thieu_du_lieu", "muc": "thap",
                    "noi_dung": "Chưa có luật môn (trọng số QT/CK, số buổi được vắng): " + ", ".join(missing) + " — nói với Copilot khi đã biết"})

    try:   # 🌗 chế độ hôm nay
        import daymode
        m = daymode.mode_of(nt, today)
        if m["mode"] == "Rest":
            out.append({"loai": "che_do", "muc": "thap", "noi_dung": "Hôm nay 💤 Rest — không xếp việc, chỉ nhắc deadline thật. Nghỉ cho khoẻ."})
        elif m["mode"] == "Camp":
            out.append({"loai": "che_do", "muc": "thap", "noi_dung": f"Hôm nay ⛺ Camp {float(m.get('hours') or 6):g} giờ — A4 xếp việc tới mức này."})
    except Exception as e:
        print("checks daymode:", e)
    if today.weekday() == 6:   # Chủ nhật: kèm kết luận đánh giá tuần (📅 Weekly Reviews)
        try:
            import weekly
            w = weekly.build(nt, today)
            out.append({"loai": "tuan", "muc": "cao" if w["verdict"] == "Không ổn" else "vua" if w["verdict"] == "Cần tăng tốc" else "thap",
                        "noi_dung": f"Đánh giá tuần: {w['verdict']} — {w['hours']:g}h ({w['pattern']}). {w['focus']}"})
        except Exception as e:
            print("checks weekly:", e)
    order = {"cao": 0, "vua": 1, "thap": 2}
    out.sort(key=lambda x: order[x["muc"]])
    return {"ok": True, "hom_nay": today.isoformat(), "canh_bao": out}
