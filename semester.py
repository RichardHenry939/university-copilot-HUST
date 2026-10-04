# -*- coding: utf-8 -*-
"""Bộ chuyển kỳ (Claude 2026-10-03) — thay tác vụ hằng ngày của ChatGPT ("Semester Progression Agent").

n8n gọi mỗi ngày 00:15 (và webhook copilot-run-hk để chạy tay):  POST /api/semester-tick  {"dry": true|false}
Logic ở đây, ghi Notion qua webhook n8n copilot-notion. Mốc ngày ở semester_calendar.json (Tết đổi theo âm lịch -> sửa file).

Chu kỳ: S1 → Tết → S2 → Hè → S3 → … → S8 (sau S8 dừng tự suy diễn).
  Kỳ lẻ → Tết       : tạo 4 task "Khai xuân" (hạn trước khi hết Tết 2 ngày).
  Sang kỳ mới       : chốt môn kỳ trước — Pass → Completed; Fail → học lại kỳ sau (Planned, giữ Original Semester, bật Retake,
                      Remaining Credits = Credits, ghi chú); chưa có kết quả → hỏi sinh viên (Exception Queue), không đoán.
                      Môn chưa học của kỳ trước → hỏi dời sang kỳ nào. "Đang học" CHỈ lấy từ TKB → nhắc gửi TKB kỳ mới.
  Bắt đầu S5        : hỏi chọn Module 1/2/3 (nếu chưa chọn).
  Kỳ chẵn → Hè      : tạo phiếu ☀️ Summer Planning + hỏi Study Summer / Relax / Internship.
  Mỗi ngày          : tính lại Semester Credit Tracker từ Courses.
"""
import uc_config as cfg
import datetime as dt, json
from pathlib import Path
from academic import Notion, P, rt, title, COURSES, STATE, TZ

HERE = Path(__file__).resolve().parent
CAL_FILE = HERE / "semester_calendar.json"
TASKS = cfg.notion("academic_tasks")
EQ = cfg.notion("exam_questions")
SUMMER = cfg.notion("summer")
TRACKER = cfg.notion("credit_tracker")
MILESTONES = cfg.notion("milestones")   # ⚙️ Mốc năm học (Notion) — người dùng tự đặt; ghi đè semester_calendar.json
ALLOW = [TASKS, EQ, SUMMER]  # cần có trong whitelist cổng copilot-notion (build.py)

DEFAULT_CAL = {
    "first_year": 2026,
    "_note": "Mốc theo lời người dùng 2026: kỳ lẻ 24/08→18/01, Tết 19/01→15/02, kỳ chẵn 16/02→18/07, hè 19/07→23/08. "
             "Tết đổi theo âm lịch: sửa tet_start/even_start theo năm trong 'overrides' (vd {\"2028\": {\"tet_start\": \"01-24\", \"even_start\": \"02-21\"}}).",
    "odd_start": "08-24", "tet_start": "01-19", "even_start": "02-16", "summer_start": "07-19",
    "overrides": {},
    "module_chosen": None,
    "week1": {"2026": "2026-08-31"},
}

def cal():
    if not CAL_FILE.exists():
        CAL_FILE.write_text(json.dumps(DEFAULT_CAL, ensure_ascii=False, indent=2), encoding="utf-8")
    return json.loads(CAL_FILE.read_text(encoding="utf-8"))

def sync_from_notion(nt):
    """Đọc ⚙️ Mốc năm học -> ghi đè 'overrides' + 'week1' trong semester_calendar.json (Notion là nguồn chính).
    Dòng '2026–2027': kỳ lẻ thuộc năm 2026; Tết, kỳ chẵn, hè thuộc năm 2027."""
    c = cal()
    ov, wk = {}, dict(c.get("week1") or {})
    for r in nt.query(MILESTONES):
        name = (P(r, "Năm học") or "").strip()
        if not name[:4].isdigit(): continue
        y = int(name[:4])
        for key, prop, yy in (("odd_start", "Bắt đầu kỳ lẻ", y), ("tet_start", "Bắt đầu nghỉ Tết", y + 1),
                              ("even_start", "Bắt đầu kỳ chẵn", y + 1), ("summer_start", "Bắt đầu hè", y + 1)):
            v = P(r, prop)
            if v:
                d = dt.date.fromisoformat(v[:10])
                if d.year != yy: continue   # nhập nhầm năm -> bỏ qua dòng mốc đó
                ov.setdefault(str(yy), {})[key] = d.strftime("%m-%d")
        if P(r, "Tuần 1 (thứ Hai)"): wk[str(y)] = P(r, "Tuần 1 (thứ Hai)")[:10]
    if ov != c.get("overrides") or wk != c.get("week1"):
        c["overrides"], c["week1"] = ov, wk
        CAL_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return c

def _d(year, mmdd, c, key):
    mmdd = (c.get("overrides", {}).get(str(year), {}) or {}).get(key, mmdd)
    m, d = map(int, mmdd.split("-"))
    return dt.date(year, m, d)

def expected(day=None, c=None):
    """-> (period, semester_no) theo lịch. period ∈ Semester | Tết | Hè | Done."""
    c = c or cal(); day = day or dt.datetime.now(TZ).date(); y, y0 = day.year, c["first_year"]
    if day >= _d(y, c["odd_start"], c, "odd_start"):
        k = 2 * (y - y0) + 1
    elif day >= _d(y, c["summer_start"], c, "summer_start"):
        return ("Hè", 2 * (y - 1 - y0) + 2) if 2 * (y - 1 - y0) + 2 <= 8 else ("Done", 8)
    elif day >= _d(y, c["even_start"], c, "even_start"):
        k = 2 * (y - 1 - y0) + 2
    elif day >= _d(y, c["tet_start"], c, "tet_start"):
        return ("Tết", 2 * (y - 1 - y0) + 1)
    else:
        k = 2 * (y - 1 - y0) + 1
    if k < 1: return ("Semester", 1)
    if k > 8: return ("Done", 8)
    return ("Semester", k)

def eq_item(nt, key, issue, reason, rtype, sev="Medium", plan=None):
    if any(P(r, "Review Key") == key for r in nt.query(EQ, {"property": "Review Key", "rich_text": {"equals": key}})):
        return None
    props = {"Issue": title(issue), "Review Key": rt(key), "Reason": rt(reason), "Reason Type": {"select": {"name": rtype}},
             "Source Agent": {"select": {"name": "Semester"}}, "Severity": {"select": {"name": sev}}, "Status": {"select": {"name": "Open"}},
             "Source Workflow": rt("University — Copilot · Chuyển kỳ (n8n + semester.py)"),
             "Detected At": {"date": {"start": dt.datetime.now(TZ).isoformat(timespec="seconds")}}}
    plan.append(("tạo câu hỏi", issue, lambda: nt.create(EQ, props)))

def close_out(nt, prev, new_sem, plan):
    """Chốt môn kỳ prev khi sang kỳ new_sem."""
    for c in [c for c in nt.courses() if c["semester"] == f"S{prev}"]:
        res, st = c["result"], c["status"]
        if st == "Taking" and (res == "Pass" or (res == "Fail" and c.get("improve"))):   # cải thiện không đạt: vẫn giữ lần đạt trước
            plan.append(("hoàn thành", f"{c['code']} {c['name']}", lambda c=c: nt.patch(c["id"], {"Status": {"status": {"name": "Completed"}}})))
        elif st in ("Taking", "Completed") and res == "Fail" and not c.get("improve"):
            note = (c["notes"] + " | " if c["notes"] else "") + f"Học lại (trượt S{prev}, chuyển sang S{new_sem})"
            props = {"Semester": {"select": {"name": f"S{new_sem}"}}, "Retake": {"checkbox": True},
                     "Remaining Credits": {"number": c["credits"]}, "Status": {"status": {"name": "Planned"}},
                     "Result": {"select": {"name": "Unknown"}}, "Current GPA 4": {"number": None}, "Course Notes": rt(note),
                     "GPA 4 lần trước": {"number": c["gpa4"] if c["gpa4"] is not None else 0}}   # QCĐT 2025: F vẫn tính GPA kỳ trượt + CPA
            if not c["orig"]: props["Original Semester"] = {"select": {"name": f"S{prev}"}}
            from academic import record_attempt   # lưu lần trượt vào 🔁 Lần học trước khi chuyển kỳ
            plan.append(("học lại", f"{c['code']} {c['name']} → S{new_sem}", lambda c=c, props=props: (record_attempt(nt, c), nt.patch(c["id"], props))))
        elif st == "Taking":
            eq_item(nt, f"semester:{c['code']}:S{prev}:noresult", f"Chưa có kết quả môn {c['code']} {c['name']} (S{prev})",
                    f"Đã sang S{new_sem} nhưng môn chưa có điểm tổng kết. Báo điểm cho Copilot để chốt qua môn / học lại.", "Chuyển kỳ", plan=plan)
        elif st == "Planned" and res != "Not Taken - Other Module":
            eq_item(nt, f"semester:{c['code']}:S{prev}:nottaken", f"Môn {c['code']} {c['name']} (S{prev}) chưa học",
                    f"Môn thuộc S{prev} nhưng kỳ đó không học. Nói với Copilot: dời sang kỳ nào (vd 'dời {c['code']} sang S{new_sem}').",
                    "Chuyển kỳ", plan=plan)

def start_semester(nt, k, plan):
    # "Đang học" chỉ lấy từ TKB (môn tự chọn như Bóng rổ/chuyền/đá chỉ học 1) -> không tự đẩy Taking, chỉ hỏi TKB.
    names = ", ".join(c["code"] for c in nt.courses() if c["semester"] == f"S{k}" and c["status"] == "Planned")
    eq_item(nt, f"semester:S{k}:tkb", f"Gửi TKB kỳ S{k} cho Copilot",
            f"Đã sang S{k}. Gửi TKB toàn kỳ cho Copilot (dán chữ hoặc ảnh) để chốt môn thật sự học và lịch. Môn dự kiến S{k}: {names}.",
            "Chuyển kỳ", "High", plan)
    if k == 5:
        eq_item(nt, "semester:S5:module", "Chọn Module 1 / 2 / 3",
                "Từ S5 cần chọn Module. Môn của Module không chọn sẽ ghi 'Not Taken - Other Module' (không ghi Pass giả).",
                "Chuyển kỳ", "High", plan)

def khai_xuan(nt, k, c, plan):
    year = c["first_year"] + (k + 1) // 2
    due = (_d(year, c["even_start"], c, "even_start") - dt.timedelta(days=2)).isoformat()
    for name in ("Khai xuân: rà kết quả các môn kỳ vừa qua", "Khai xuân: kiểm tra môn phải học lại",
                 "Khai xuân: xem lịch / TKB kỳ mới", "Khai xuân: chuẩn bị tài liệu tuần đầu"):
        props = {"Task": title(name), "Status": {"status": {"name": "To do"}}, "Due": {"date": {"start": due}},
                 "Priority": {"select": {"name": "Medium"}}, "Task Kind": {"select": {"name": "Admin"}}, "Estimate (hrs)": {"number": 1}}
        plan.append(("task Tết", name, lambda props=props: nt.create(TASKS, props)))

def summer(nt, k, plan):
    props = {"Plan": title(f"Hè sau S{k}"), "Status": {"status": {"name": "Not started"}},
             "Notes": rt("Tạo tự động khi vào kỳ hè. Trả lời Copilot: học hè / nghỉ / thực tập.")}
    plan.append(("phiếu hè", f"Hè sau S{k}", lambda: nt.create(SUMMER, props)))
    eq_item(nt, f"semester:summer:S{k}", "Hè này bạn chọn gì: học hè, nghỉ hay thực tập?",
            "Học hè → chọn học phần + số tín; Nghỉ → không tạo việc; Thực tập → công ty, vị trí, giờ làm (đưa giờ làm vào lịch).",
            "Chuyển kỳ", "High", plan)

def credit_sync(nt, plan, chosen=None):
    """Như credit_sync.py: Planned = tín chung + tín Module đã chọn; Completed = Completed & Pass; Đối soát với Required."""
    from collections import Counter, defaultdict
    chung, mods, done = Counter(), defaultdict(Counter), Counter()
    for c in nt.courses():
        s = c["semester"]
        if not s or c["result"] == "Not Taken - Other Module": continue
        if c["module"]: mods[s][c["module"]] += c["credits"]
        else: chung[s] += c["credits"]
        if c["status"] == "Completed" and c["result"] == "Pass": done[s] += c["credits"]
    for r in nt.query(TRACKER):
        s = "S" + (P(r, "Semester") or "").split()[-1]
        req, m = P(r, "Required Credits") or 0, mods.get(s, {})
        planned = chung[s] + (m.get(chosen, 0) if chosen else 0)
        mtext = " · ".join(f"{k.replace('Module ', 'M')} +{v}" for k, v in sorted(m.items())) if m else "—"
        if m and not chosen:
            lo, hi = chung[s] + min(m.values()), chung[s] + max(m.values())
            note = f"Chưa chọn Module (chọn ở S5): {lo}–{hi} tín tuỳ Module; chương trình ghi {req}."
            if not (lo <= req <= hi): note += f" LỆCH: danh sách môn không thể đạt {req}."
        else:
            note = "Khớp chương trình." if planned == req else f"Danh sách môn kỳ này cộng ra {planned} tín, chương trình ghi {req} (cộng thiếu {req - planned} — chưa phải nợ tín)."
        want = {"Planned Credits": planned, "Completed Credits": done[s], "Tín chỉ chung": chung[s], "Tín chỉ Module": mtext, "Đối soát": note}
        diff = {k: v for k, v in want.items() if P(r, k) != v}
        if diff:
            props = {k: (rt(v) if isinstance(v, str) else {"number": v}) for k, v in diff.items()}
            plan.append(("tín chỉ", f"{s}: " + ", ".join(f"{k}={v}" for k, v in diff.items() if k != "Đối soát"),
                         lambda r=r, props=props: nt.patch(r["id"], props)))

def tick(post, dry=True, today=None):
    nt = Notion(post)
    try: c = sync_from_notion(nt)
    except Exception: c = cal()
    day = dt.date.fromisoformat(today) if today else dt.datetime.now(TZ).date()
    period, k = expected(day, c)
    rows = nt.query(STATE)
    cur = next((r for r in rows if P(r, "State") == "Current"), None)
    if not cur: return {"ok": False, "loi": "Không thấy dòng 'Current' trong Semester State."}
    cur_period, cur_no = (P(cur, "Period") or "Semester"), (P(cur, "Semester No.") or "1")
    cur_k = int(cur_no) if cur_no.isdigit() else None
    plan, jump = [], False
    changed = (period != "Done") and (period != cur_period or (cur_k is not None and k != cur_k))
    if changed:
        if period == "Tết":
            khai_xuan(nt, k, c, plan)
        elif period == "Hè":
            summer(nt, k, plan)
        elif period == "Semester" and cur_k is not None and k == cur_k + 1:
            close_out(nt, cur_k, k, plan)
            start_semester(nt, k, plan)
        elif period == "Semester" and cur_k is not None and k > cur_k + 1:
            jump = True
            eq_item(nt, f"semester:jump:{cur_k}->{k}", f"Lịch nhảy từ S{cur_k} sang S{k}",
                    "Bộ chuyển kỳ thấy chênh hơn 1 kỳ (máy tắt lâu hoặc mốc sai). Không tự xử lý; kiểm tra semester_calendar.json.",
                    "Chuyển kỳ", "High", plan)
        if not jump:
            props = {"Period": {"select": {"name": period}}, "Semester No.": {"select": {"name": str(k)}},
                     "Updated By": rt("n8n · Chuyển kỳ"), "Notes": rt(f"{period} S{k} từ {day.strftime('%d/%m/%Y')} (bộ chuyển kỳ n8n).")}
            plan.append(("trạng thái kỳ", f"{cur_period} S{cur_no} → {period} S{k}", lambda: nt.patch(cur["id"], props)))
    for rule in c.get("tu_dong_qua") or []:   # môn không thi (vd QP-AN): tự ghi Qua khi đã qua ngày kết thúc đợt
        if day > dt.date.fromisoformat(rule["sau_ngay"]):
            for x in nt.courses():
                if x["code"] in rule["ma"] and x["result"] != "Pass":
                    props = {"Result": {"select": {"name": "Pass"}}, "Status": {"status": {"name": "Completed"}}}
                    plan.append(("qua môn", f"{x['code']} {x['name']} ({rule.get('ly_do', '')})", lambda x=x, props=props: nt.patch(x["id"], props)))
    credit_sync(nt, plan, c.get("module_chosen"))
    if not dry:   # chứng chỉ ngoại ngữ: hết hạn -> tự sang "Đã hết hạn", cập nhật bậc / miễn học phần trong Notion
        try:
            import certs; certs.build(nt)
        except Exception as e: plan.append(("lỗi chứng chỉ", str(e)[:120], lambda: None))
    if not dry:
        for _, _, fn in plan: fn()
    return {"ok": True, "hom_nay": day.isoformat(), "lich": f"{period} S{k}", "hien_tai": f"{cur_period} S{cur_no}",
            "doi_ky": changed, "dry": dry, "viec": [f"{a}: {b}" for a, b, _ in plan]}


# ----------------------------------------------------------------------------- câu trả lời của sinh viên (qua ghi_hoc_tap)
def _close_eq(nt, key, text):
    for r in nt.query(EQ, {"property": "Review Key", "rich_text": {"equals": key}}):
        if P(r, "Status") == "Open":
            nt.patch(r["id"], {"Status": {"select": {"name": "Resolved"}}, "Reason": rt("Đã trả lời qua Copilot: " + text)})

def answer(nt, loai, a, sem):
    """loai: he | module | doi_mon. Trả {ok, da_ghi | thieu}."""
    from academic import find_course, norm
    pick = norm(a.get("lua_chon") or "")
    if loai == "he":
        choice = ("Internship" if any(w in pick for w in ("thuc tap", "intern")) else
                  "Relax" if any(w in pick for w in ("nghi", "relax", "choi", "khong hoc")) else
                  "Study Summer" if any(w in pick for w in ("hoc", "study")) else None)
        if not choice: return {"ok": False, "thieu": ["Hè này học hè, nghỉ hay đi thực tập?"]}
        k = int(sem[1:]) if sem and sem[1:].isdigit() else None
        rows = [r for r in nt.query(SUMMER) if P(r, "Plan") == f"Hè sau S{k}"]
        props = {"Choice": {"select": {"name": choice}}, "Status": {"status": {"name": "In progress" if choice != "Relax" else "Done"}}}
        note = a.get("ghi_chu") or ""
        if note: props["Notes"] = rt(note)
        if choice == "Internship" and not note:
            return {"ok": False, "thieu": ["Thực tập ở công ty nào, vị trí gì, giờ làm thế nào?"]}
        if rows: nt.patch(rows[0]["id"], props)
        else: nt.create(SUMMER, {"Plan": title(f"Hè sau S{k}"), **props})
        _close_eq(nt, f"semester:summer:S{k}", choice)
        return {"ok": True, "da_ghi": [f"Hè sau S{k}: {choice}" + (f" ({note})" if note else "")]}
    if loai == "module":
        m = next((f"Module {d}" for d in "123" if d in pick), None)
        if not m: return {"ok": False, "thieu": ["Chọn Module 1, 2 hay 3?"]}
        c = cal(); c["module_chosen"] = m
        CAL_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
        n = 0
        for x in nt.courses():
            if x["module"] and x["module"] != m and x["status"] == "Planned" and x["result"] != "Not Taken - Other Module":
                nt.patch(x["id"], {"Result": {"select": {"name": "Not Taken - Other Module"}}}); n += 1
        _close_eq(nt, "semester:S5:module", m)
        return {"ok": True, "da_ghi": [f"Đã chọn {m}; {n} môn của Module khác ghi 'Not Taken - Other Module'."]}
    if loai == "doi_mon":
        if not a.get("mon"): return {"ok": False, "thieu": ["Dời môn nào?"]}
        ky = (a.get("ky") or "").upper().replace(" ", "")
        if ky not in [f"S{i}" for i in range(1, 9)]: return {"ok": False, "thieu": ["Dời sang kỳ nào (S1–S8)?"]}
        c, ask = find_course(nt, a["mon"], sem)
        if ask: return {"ok": False, "thieu": [ask]}
        props = {"Semester": {"select": {"name": ky}}, "Status": {"status": {"name": "Taking" if ky == sem else "Planned"}},
                 "Course Notes": rt((c["notes"] + " | " if c["notes"] else "") + f"Dời từ {c['semester']} sang {ky}" + (f": {a['ghi_chu']}" if a.get("ghi_chu") else ""))}
        if not c["orig"]: props["Original Semester"] = {"select": {"name": c["semester"]}}
        nt.patch(c["id"], props)
        for suf in ("nottaken", "noresult"): _close_eq(nt, f"semester:{c['code']}:{c['semester']}:{suf}", f"dời sang {ky}")
        return {"ok": True, "da_ghi": [f"{c['code']} {c['name']}: {c['semester']} → {ky}"]}
    return {"ok": False, "thieu": ["Không rõ loại."]}
