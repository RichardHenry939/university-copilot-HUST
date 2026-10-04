# -*- coding: utf-8 -*-
"""Học tập: luật môn, điểm, chuyên cần, rèn luyện, GPA/CPA (Claude 2026-10-03).

Não Copilot (n8n) tách câu nói tự nhiên của sinh viên thành 1 lệnh ghi_hoc_tap -> POST /api/academic (web app) -> record().
Mọi phép tính ở đây là code, không để AI tự tính. Ghi/đọc Notion qua webhook n8n copilot-notion (credential của n8n).
Thiếu thông tin -> trả "thieu" mô tả chính xác phần thiếu để Copilot hỏi lại đúng 1 câu.

Thang điểm HUST: thang 10 -> chữ -> thang 4
  A+ ≥9.5 (4.0) · A ≥8.5 (4.0) · B+ ≥8.0 (3.5) · B ≥7.0 (3.0) · C+ ≥6.5 (2.5) · C ≥5.5 (2.0) · D+ ≥5.0 (1.5) · D ≥4.0 (1.0) · F (0)
  Điểm học phần = QT × w + CK × (1 − w), làm tròn 1 chữ số. w = "Trọng số QT (%)" của môn (giảng viên nói buổi 1).
  GPA kỳ / CPA: trung bình theo tín chỉ, bỏ môn 0 tín (thể chất, quốc phòng, tiếng Anh cơ sở = môn điều kiện).
Rèn luyện (thang 100): Xuất sắc ≥90 · Tốt ≥80 · Khá ≥65 · Trung bình ≥50 · Yếu ≥35 · Kém.
"""
import uc_config as cfg
import datetime as dt, difflib, json, re, time, unicodedata, urllib.request

COURSES = cfg.notion("courses")
GRADES = cfg.notion("grades")
ATTEMPTS = cfg.notion("attempts")   # 🔁 Lần học — lịch sử các lần học đã kết thúc
ATTEND = cfg.notion("attendance")
CONDUCT = cfg.notion("conduct")
STATE = cfg.notion("semester_state")
TZ = dt.timezone(dt.timedelta(hours=7))

GRADE_MAP = [(9.5, "A+", 4.0), (8.5, "A", 4.0), (8.0, "B+", 3.5), (7.0, "B", 3.0), (6.5, "C+", 2.5),
             (5.5, "C", 2.0), (5.0, "D+", 1.5), (4.0, "D", 1.0), (0.0, "F", 0.0)]
COMPONENT = {  # lời nói -> option của cột Component
    "chuyen can": "Attendance", "chuyên cần": "Attendance", "attendance": "Attendance",
    "bai tap": "Assignment", "bài tập": "Assignment", "btl": "Assignment", "assignment": "Assignment",
    "thi nghiem": "Lab", "thí nghiệm": "Lab", "lab": "Lab", "thuc hanh": "Lab", "thực hành": "Lab",
    "giua ky": "Midterm", "giữa kỳ": "Midterm", "giua ki": "Midterm", "midterm": "Midterm",
    "cuoi ky": "Final", "cuối kỳ": "Final", "cuoi ki": "Final", "thi": "Final", "final": "Final",
    "qua trinh": "Quá trình", "quá trình": "Quá trình", "qt": "Quá trình",
    "tong ket": "Overall", "tổng kết": "Overall", "hoc phan": "Overall", "học phần": "Overall", "overall": "Overall",
}

def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

def letter(score10):
    for lo, l, g in GRADE_MAP:
        if score10 >= lo - 1e-9:
            return l, g
    return "F", 0.0

def course_score(qt, ck, w_qt_percent):
    w = w_qt_percent / 100.0
    return round(qt * w + ck * (1 - w) + 1e-9, 1)

def conduct_rank(x):
    return "Xuất sắc" if x >= 90 else "Tốt" if x >= 80 else "Khá" if x >= 65 else "Trung bình" if x >= 50 else "Yếu" if x >= 35 else "Kém"

def weighted_gpa(items):
    """items: [(credits, gpa4)] -> GPA theo tín chỉ, bỏ môn 0 tín."""
    xs = [(c, g) for c, g in items if c and g is not None]
    tot = sum(c for c, _ in xs)
    return round(sum(c * g for c, g in xs) / tot, 2) if tot else None

def num(x):
    """Số từ AI: '7,5' / '7.5' / 7.5 / '' / 0 không hợp lệ -> None."""
    if x is None or x == "": return None
    try:
        v = float(str(x).replace(",", ".").strip())
    except ValueError:
        return None
    return v

# ----------------------------------------------------------------------------- Notion qua n8n
class Notion:
    def __init__(self, n8n_post):
        self.post = n8n_post   # hàm (path, body) -> json của copilot_app
        self._courses = None

    def ops(self, ops):
        res = self.post("copilot-notion", {"ops": ops})
        res = res[0] if isinstance(res, list) else res
        out = res.get("res", [])
        bad = [r for r in out if r.get("code") != 200]
        if bad:
            raise RuntimeError("Notion: " + str((bad[0].get("body") or {}).get("message", bad[0]))[:300])
        return [r["body"] for r in out]

    def query(self, db, flt=None, sorts=None):
        rows, cursor = [], None
        while True:
            body = {"page_size": 100}
            if flt: body["filter"] = flt
            if sorts: body["sorts"] = sorts
            if cursor: body["start_cursor"] = cursor
            r = self.ops([{"method": "POST", "url": f"https://api.notion.com/v1/databases/{db}/query", "body": body}])[0]
            rows += r.get("results", [])
            if not r.get("has_more"): return rows
            cursor = r["next_cursor"]

    def create(self, db, props):
        self.forget(db)
        return self.ops([{"method": "POST", "url": "https://api.notion.com/v1/pages", "body": {"parent": {"database_id": db}, "properties": props}}])[0]

    def patch(self, page_id, props):
        getattr(self, "_cache", {}).clear()
        return self.ops([{"method": "PATCH", "url": f"https://api.notion.com/v1/pages/{page_id}", "body": {"properties": props}}])[0]

    def all_rows(self, db):
        """Đọc cả bảng 1 lần rồi lọc trong Python (mỗi lần gọi Notion qua n8n tốn ~1 s)."""
        if not hasattr(self, "_cache"): self._cache = {}
        if db not in self._cache: self._cache[db] = self.query(db)
        return self._cache[db]

    def forget(self, db):
        getattr(self, "_cache", {}).pop(db, None)

    def attempts(self):
        if getattr(self, "_att", None) is None:
            self._att = attempts_by_course(self.query(ATTEMPTS))
        return self._att

    def courses(self):
        if self._courses is None:
            self._courses = [course_view(p) for p in self.query(COURSES)]
        return self._courses

def P(p, name):
    v = (p.get("properties") or {}).get(name)
    if not v: return None
    t = v["type"]
    if t in ("title", "rich_text"): return "".join(x.get("plain_text", "") for x in v[t])
    if t in ("select", "status"): return (v[t] or {}).get("name")
    if t in ("number", "checkbox"): return v[t]
    if t == "relation": return [x["id"] for x in v["relation"]]
    if t == "date": return (v["date"] or {}).get("start")
    if t in ("url", "email", "phone_number"): return v[t]
    if t == "multi_select": return [x["name"] for x in v[t]]
    if t == "formula": return v["formula"].get(v["formula"]["type"])
    return None

def course_view(p):
    return {"id": p["id"], "code": P(p, "Code") or "", "name": P(p, "Name") or "", "credits": P(p, "Credits") or 0,
            "semester": P(p, "Semester"), "status": P(p, "Status"), "result": P(p, "Result"), "gpa4": P(p, "Current GPA 4"),
            "rule": P(p, "Luật môn") or "", "w_qt": P(p, "Trọng số QT (%)"), "max_abs": P(p, "Vắng tối đa"),
            "category": P(p, "Category"), "module": P(p, "Module/Track"), "orig": P(p, "Original Semester"),
            "notes": P(p, "Course Notes") or "", "retake": bool(P(p, "Retake")), "improve": bool(P(p, "Học cải thiện")), "prev4": P(p, "GPA 4 lần trước"),
            "abs_school": P(p, "Vắng (trường)")}

# GPA/CPA theo Quy chế đào tạo ĐHBK 2025 (QĐ 5445, hiệu lực từ HK1 2025-2026):
#  Đ7.2 GPA kỳ = mọi học phần đã học TRONG kỳ (kể cả điểm F) · Đ7.3 CPA = các học phần đã học từ đầu khoá
#  Đ5.8 học lại: điểm lần cao nhất là điểm chính thức · Đ5.9 R/P/I/X/W không tính · Đ12 ngoại ngữ cơ bản, GDTC, QP-AN không tính (0 tín trong Notion)
# Một dòng Courses = một học phần, giữ LẦN HỌC HIỆN TẠI. Mỗi lần học đã kết thúc (trượt trước khi học lại, đạt trước khi học
# cải thiện) là một dòng 🔁 Lần học — trượt bao nhiêu lần cũng lưu đủ. "GPA 4 lần trước" chỉ để đọc nhanh lần gần nhất.
def _k(s): return int(s[1:]) if s and str(s)[1:].isdigit() else 99

def attempt_start(sem):
    """Ngày bắt đầu kỳ sem (theo semester_calendar.json) — để lần học lại/cải thiện chỉ đếm điểm và buổi vắng của lần đó."""
    try:
        import semester
        c, k = semester.cal(), int(str(sem)[1:])
        y0 = c["first_year"]
        d = (semester._d(y0 + (k - 1) // 2, c["odd_start"], c, "odd_start") if k % 2 else semester._d(y0 + k // 2, c["even_start"], c, "even_start"))
        return d.isoformat()
    except Exception:
        return None

def attempts_by_course(rows):
    out = {}
    for r in rows:
        if P(r, "Loại") == "Đã huỷ": continue
        for cid in P(r, "Course") or []:
            out.setdefault(cid, []).append({"id": r["id"], "sem": P(r, "Semester"), "gpa4": P(r, "GPA 4"), "result": P(r, "Kết quả"), "kind": P(r, "Loại")})
    for v in out.values(): v.sort(key=lambda x: _k(x["sem"]))
    return out

def attach_history(cs, att):
    for c in cs: c["hist"] = att.get(c["id"], [])
    return cs

def past(c):
    """Các lần học đã kết thúc của môn (cũ → mới)."""
    if c.get("hist"): return c["hist"]
    if (c.get("retake") or c.get("improve")) and c.get("prev4") is not None and c.get("orig"):   # dữ liệu trước khi có 🔁 Lần học
        return [{"sem": c["orig"], "gpa4": c["prev4"], "result": "Pass" if c.get("improve") else "Fail", "kind": "Lần đầu"}]
    return []

def fail_count(c):
    """Số lần PHẢI học lại (trượt, không tính lần cải thiện không đạt) — dùng cho ngưỡng 5% khi xếp hạng tốt nghiệp."""
    n = sum(1 for x in past(c) if x["result"] == "Fail" and x["kind"] != "Cải thiện")
    return n + (1 if c["result"] == "Fail" and not c.get("improve") else 0)

def record_attempt(nt, c):
    """Lưu lần học hiện tại của môn vào 🔁 Lần học (gọi TRƯỚC khi chuyển môn sang kỳ học lại / cải thiện)."""
    kind = "Cải thiện" if c.get("improve") else "Học lại" if c.get("retake") else "Lần đầu"
    g4 = c["gpa4"] if c["gpa4"] is not None else (0 if c["result"] == "Fail" else None)
    props = {"Lần": title(f"{c['code']} · {c['semester']} · {kind}"), "Course": {"relation": [{"id": c["id"]}]},
             "Semester": {"select": {"name": c["semester"]}}, "GPA 4": {"number": g4}, "Tín": {"number": c["credits"]},
             "Loại": {"select": {"name": kind}}, "Ghi lúc": {"date": {"start": dt.datetime.now(TZ).isoformat(timespec="minutes")}}}
    if c["result"] in ("Pass", "Fail"): props["Kết quả"] = {"select": {"name": c["result"]}}
    return nt.create(ATTEMPTS, props)

def sem_items(cs, sem):
    """GPA kỳ: mọi lần học diễn ra trong kỳ sem (lần hiện tại trên Courses + các lần trong 🔁 Lần học)."""
    out = [(c["credits"], c["gpa4"]) for c in cs if c["semester"] == sem and c["credits"] and c["gpa4"] is not None and c["result"] in ("Pass", "Fail")]
    out += [(c["credits"], x["gpa4"]) for c in cs if c["credits"] for x in past(c) if x["sem"] == sem and x["gpa4"] is not None]
    return out

def cpa_items(cs, upto=None):
    """CPA: mỗi học phần một lần, lấy lần điểm cao nhất (tới kỳ upto nếu có)."""
    out = []
    for c in cs:
        if not c["credits"]: continue
        tries = [x["gpa4"] for x in past(c) if x["gpa4"] is not None and (upto is None or _k(x["sem"]) <= upto)]
        if c["gpa4"] is not None and c["result"] in ("Pass", "Fail") and (upto is None or _k(c["semester"]) <= upto): tries.append(c["gpa4"])
        if tries: out.append((c["credits"], max(tries)))
    return out

def rt(s): return {"rich_text": [{"type": "text", "text": {"content": str(s)[:1900]}}]}
def title(s): return {"title": [{"type": "text", "text": {"content": str(s)[:200]}}]}

def current_sem(nt):
    rows = nt.query(STATE)
    cur = next((r for r in rows if P(r, "State") == "Current"), rows[0] if rows else None)
    no = P(cur, "Semester No.") if cur else "1"
    return "S" + no if no and no.isdigit() else "S1"

def find_course(nt, said, sem):
    """Khớp tên/mã môn sinh viên nói. Trả (course, None) hoặc (None, câu hỏi lại)."""
    cs = nt.courses()
    if not said:
        return None, "Bạn đang nói môn nào?"
    s = norm(said)
    code = [c for c in cs if norm(c["code"]) == s.replace(" ", "")]
    if code:
        return code[0], None
    pref = lambda c: (c["status"] == "Taking", c["semester"] == sem)
    w = lambda x: f" {x} "   # khớp theo nguyên từ ("hoa hoc" không được khớp "khoa hoc")
    hits = [c for c in cs if s and (w(s) in w(norm(c["name"])) or w(norm(c["name"])) in w(s))]
    if not hits:   # theo bộ từ khoá (số 1/2/3 = I/II/III) hoặc chữ viết tắt (NMLT, GT1, CTDL)
        roman = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "6": "vi"}
        tok = lambda x: [roman.get(t, t) for t in norm(x).split()]
        st = tok(said)
        def initials(c):
            t = tok(c["name"]); return "".join(x[0] for x in t if not x.strip("iv") == "") + "".join(x for x in t if x.strip("iv") == "" and x).replace("iii", "3").replace("ii", "2").replace("i", "1")
        hits = [c for c in cs if st and all(t in tok(c["name"]) for t in st)]
        if not hits and len(st) == 1 and 2 <= len(st[0]) <= 8:
            ab = st[0].replace("iii", "3").replace("ii", "2")
            hits = [c for c in cs if initials(c) in (ab, ab.rstrip("1"))]
            if not hits and len(ab) >= 4:   # CTDL -> Cấu trúc dữ liệu và thuật toán
                hits = [c for c in cs if initials(c).startswith(ab)]
    if not hits:
        scored = sorted(cs, key=lambda c: difflib.SequenceMatcher(None, s, norm(c["name"])).ratio(), reverse=True)
        hits = [c for c in scored[:3] if difflib.SequenceMatcher(None, s, norm(c["name"])).ratio() >= 0.6]
    hits.sort(key=pref, reverse=True)
    taking = [c for c in hits if c["status"] == "Taking"]
    if len(taking) == 1 or (len(hits) == 1):
        return (taking or hits)[0], None
    if not hits:
        return None, f"Mình không tìm thấy môn “{said}” trong chương trình. Bạn nói mã môn (ví dụ MI1111) giúp mình nhé."
    names = ", ".join(f"{c['code']} {c['name']}" for c in hits[:4])
    return None, f"“{said}” khớp nhiều môn: {names}. Bạn muốn môn nào?"

def today():
    return dt.datetime.now(TZ).date().isoformat()

# ----------------------------------------------------------------------------- tính toán theo môn
def course_status(nt, c, sem):
    grades = [r for r in nt.all_rows(GRADES) if c["id"] in (P(r, "Course") or [])]
    again = c.get("retake") or c.get("improve")   # lần học lại / cải thiện: chỉ lấy điểm của lần này
    if again: grades = [r for r in grades if P(r, "Semester") == c["semester"]]
    g = {}
    for r in grades:
        comp = P(r, "Component")
        if comp and comp != "Overall":
            g.setdefault(comp, []).append({"id": r["id"], "score": P(r, "Score 10"), "note": P(r, "Notes")})
    abs_rows = [r for r in nt.all_rows(ATTEND) if c["id"] in (P(r, "Course") or [])]
    if again and attempt_start(c["semester"]):
        abs_rows = [r for r in abs_rows if (P(r, "Date") or "")[:10] >= attempt_start(c["semester"])]
    absent = sum(1 for r in abs_rows if P(r, "Status") == "Absent")
    if c.get("abs_school") is not None: absent = int(c["abs_school"])   # điểm danh của trường (qldt) là cao nhất
    late = sum(1 for r in abs_rows if P(r, "Status") == "Late")
    out = {"mon": f"{c['code']} {c['name']}", "tin_chi": c["credits"], "luat": c["rule"] or None,
           "trong_so_qt": c["w_qt"], "vang": absent, "muon": late, "vang_toi_da": c["max_abs"],
           "diem_thanh_phan": {k: [x["score"] for x in v] for k, v in g.items()}}
    if c["max_abs"] is not None:
        out["con_duoc_vang"] = max(0, int(c["max_abs"]) - absent)
    qt = (g.get("Quá trình") or g.get("Midterm") or [{}])[-1].get("score")
    ck = (g.get("Final") or [{}])[-1].get("score")
    if qt is not None and ck is not None and c["w_qt"] is not None:
        sc = course_score(qt, ck, c["w_qt"])
        l, g4 = letter(sc)
        out.update({"diem_hoc_phan": sc, "diem_chu": l, "thang_4": g4, "qua_mon": l != "F",
                    "cach_tinh": f"QT {qt} × {int(c['w_qt'])}% + CK {ck} × {100 - int(c['w_qt'])}%"
                                 + ("" if g.get("Quá trình") else " (QT lấy điểm giữa kỳ vì chưa có điểm quá trình riêng)")})
    else:
        need = []
        if c["w_qt"] is None: need.append("trọng số quá trình/cuối kỳ của môn")
        if qt is None: need.append("điểm quá trình (hoặc giữa kỳ)")
        if ck is None: need.append("điểm cuối kỳ")
        out["chua_tinh_duoc_vi_thieu"] = need
        if qt is not None and ck is None and c["w_qt"] is not None and c["w_qt"] < 100:
            w = c["w_qt"] / 100   # điểm cuối kỳ tối thiểu để điểm học phần (làm tròn 1 số) đạt 4.0 = D
            out["ck_can_de_qua"] = max(0.0, round(-(-(3.95 - qt * w) / (1 - w) * 10 // 1) / 10, 1))
    if c["max_abs"] is not None and absent > c["max_abs"]:
        out["vuot_vang"] = absent - int(c["max_abs"])
    return out

def apply_overall(nt, c, st, sem):
    """Có đủ QT + CK + trọng số -> ghi dòng Overall + cập nhật Course (GPA 4, Result)."""
    if "diem_hoc_phan" not in st:
        return None
    props = {"Record": title(f"{c['code']} · Tổng kết"), "Course": {"relation": [{"id": c["id"]}]}, "Semester": {"select": {"name": sem}},
             "Component": {"select": {"name": "Overall"}}, "Score 10": {"number": st["diem_hoc_phan"]},
             "Letter Grade": {"select": {"name": st["diem_chu"]}}, "GPA 4": {"number": st["thang_4"]},
             "Credits": {"number": c["credits"]}, "Passed": {"checkbox": st["qua_mon"]}, "Notes": rt(st["cach_tinh"])}
    old = nt.query(GRADES, {"and": [{"property": "Course", "relation": {"contains": c["id"]}},
                                    {"property": "Component", "select": {"equals": "Overall"}}]})
    if old: nt.patch(old[0]["id"], props)
    else: nt.create(GRADES, props)
    nt.patch(c["id"], {"Current GPA 4": {"number": st["thang_4"]}, "Result": {"select": {"name": "Pass" if st["qua_mon"] else "Fail"}}})
    if c.get("improve"):
        tail = "lần học cải thiện — điểm chính thức lấy lần cao nhất" + (f" (lần trước {c['prev4']:g})" if c.get("prev4") is not None else "")
    else:
        tail = "qua môn" if st["qua_mon"] else "TRƯỢT, sẽ vào quy trình học lại kỳ sau"
    return f"Điểm học phần {c['code']}: {st['diem_hoc_phan']} → {st['diem_chu']} ({st['thang_4']}) — {tail}."

def summary(nt, sem):
    cs = nt.courses()
    cur = [c for c in cs if c["status"] == "Taking" or (c["semester"] == sem and c["status"] != "Planned")]
    per = [course_status(nt, c, sem) for c in cur if c["status"] == "Taking"]
    gpa = weighted_gpa([(c["credits"], c["gpa4"]) for c in cur if c["gpa4"] is not None])
    cpa = weighted_gpa(cpa_items(attach_history(list(cs), nt.attempts())))
    rl = [(P(r, "Semester"), P(r, "Điểm")) for r in nt.query(CONDUCT)]
    return {"hoc_ky": sem, "mon": per, "gpa_ky": gpa, "cpa": cpa,
            "ren_luyen": {s: {"diem": d, "xep_loai": conduct_rank(d) if d is not None else None} for s, d in rl}}

# ----------------------------------------------------------------------------- lệnh chính
def record(post, a):
    """a: dict từ công cụ ghi_hoc_tap. Trả {ok, da_ghi, thieu, ket_qua}."""
    nt = Notion(post)
    loai = norm(a.get("loai"))
    sem = current_sem(nt)
    done, missing = [], []
    if loai in ("xem", "tong hop", "hoi"):
        if a.get("mon"):
            c, ask = find_course(nt, a.get("mon"), sem)
            if ask: return {"ok": False, "thieu": [ask]}
            return {"ok": True, "ket_qua": course_status(nt, c, sem)}
        return {"ok": True, "ket_qua": summary(nt, sem)}

    if loai in ("che do", "che_do", "camp", "rest", "nghi"):
        import daymode
        pick = norm(a.get("lua_chon") or loai)
        mode = "Rest" if any(w in pick for w in ("rest", "nghi")) else "Camp" if "camp" in pick else "Bình thường" if ("binh thuong" in pick or "huy" in pick) else None
        if not mode: return {"ok": False, "thieu": ["Ngày đó là camp (dồn sức), rest (nghỉ) hay bình thường?"]}
        return daymode.set_mode(post, a.get("ngay") or today(), mode, a.get("so_buoi"), a.get("ghi_chu") or "", "Copilot")

    if loai in ("tuan", "danh gia tuan", "tong ket tuan"):
        import weekly
        return weekly.run(post, save_row=False)

    if loai in ("he", "module", "doi mon", "doi_mon"):
        import semester
        return semester.answer(nt, loai.replace(" ", "_"), a, sem)

    if loai in ("ren luyen", "renluyen", "drl"):
        d = num(a.get("diem"))
        ky = (a.get("ky") or sem).upper().replace(" ", "")
        if d is None or not 0 <= d <= 100:
            return {"ok": False, "thieu": ["điểm rèn luyện (thang 100) của kỳ " + ky]}
        old = nt.query(CONDUCT, {"property": "Semester", "select": {"equals": ky}})
        props = {"Kỳ": title(f"Rèn luyện {ky}"), "Semester": {"select": {"name": ky}}, "Điểm": {"number": d},
                 "Ghi chú": rt(a.get("ghi_chu") or "")}
        if old: nt.patch(old[0]["id"], props)
        else: nt.create(CONDUCT, props)
        return {"ok": True, "da_ghi": [f"Điểm rèn luyện {ky}: {d:g} → {conduct_rank(d)}"]}

    c, ask = find_course(nt, a.get("mon"), sem)
    if ask:
        return {"ok": False, "thieu": [ask]}

    if loai in ("luat", "quy tac", "quy dinh"):
        txt = (a.get("luat") or "").strip()
        w, mx = num(a.get("trong_so_qt")), num(a.get("vang_toi_da"))
        if not txt and w is None and mx is None:
            return {"ok": False, "thieu": [f"nội dung luật của môn {c['name']} (trọng số điểm, giới hạn vắng, cách cộng/trừ điểm…)"]}
        props = {}
        if txt:
            stamp = dt.datetime.now(TZ).strftime("%d/%m/%Y")
            props["Luật môn"] = rt((c["rule"] + "\n" if c["rule"] else "") + f"[{stamp}] {txt}")
        if w is not None:
            if not 0 < w < 100: return {"ok": False, "thieu": ["trọng số quá trình phải trong khoảng 1–99 %, ví dụ 30 (nghĩa là 30% QT, 70% CK)"]}
            props["Trọng số QT (%)"] = {"number": w}; done.append(f"trọng số QT {w:g}% / CK {100 - w:g}%")
        if mx is not None:
            props["Vắng tối đa"] = {"number": int(mx)}; done.append(f"vắng tối đa {int(mx)} buổi")
        nt.patch(c["id"], props)
        if txt: done.insert(0, f"đã lưu luật: “{txt}”")
        c.update({"rule": props.get("Luật môn", {}).get("rich_text", [{}])[0].get("text", {}).get("content", c["rule"]) if txt else c["rule"],
                  "w_qt": w if w is not None else c["w_qt"], "max_abs": int(mx) if mx is not None else c["max_abs"]})
        st = course_status(nt, c, sem)
        if c["w_qt"] is None: missing.append("trọng số quá trình/cuối kỳ (chưa có — cần để tính điểm học phần)")
        if c["max_abs"] is None: missing.append("số buổi được vắng tối đa (chưa có — cần để cảnh báo cấm thi)")
        msg = apply_overall(nt, c, st, sem)
        if msg: done.append(msg)
        return {"ok": True, "mon": f"{c['code']} {c['name']}", "da_ghi": done, "con_thieu_trong_luat": missing, "ket_qua": st}

    if loai in ("diem",):
        d = num(a.get("diem"))
        comp = COMPONENT.get(norm(a.get("thanh_phan"))) or COMPONENT.get(str(a.get("thanh_phan") or "").lower().strip())
        if d is None or not 0 <= d <= 10:
            missing.append("số điểm (thang 10)")
        if not comp:
            missing.append("đây là điểm gì: chuyên cần, bài tập, thí nghiệm, giữa kỳ, quá trình, cuối kỳ hay tổng kết")
        if missing:
            return {"ok": False, "mon": f"{c['code']} {c['name']}", "thieu": missing}
        w = c["w_qt"]
        weight = (100 - w) if (w is not None and comp == "Final") else (w if (w is not None and comp in ("Quá trình", "Midterm")) else None)
        props = {"Record": title(f"{c['code']} · {a.get('thanh_phan')}"), "Course": {"relation": [{"id": c["id"]}]},
                 "Semester": {"select": {"name": c['semester'] or sem}}, "Component": {"select": {"name": comp}},
                 "Score 10": {"number": d}, "Credits": {"number": c["credits"]}, "Notes": rt(a.get("ghi_chu") or "")}
        if weight is not None: props["Weight %"] = {"number": weight}
        if comp == "Overall":
            l, g4 = letter(d)
            props.update({"Letter Grade": {"select": {"name": l}}, "GPA 4": {"number": g4}, "Passed": {"checkbox": l != "F"}})
            nt.create(GRADES, props)
            nt.patch(c["id"], {"Current GPA 4": {"number": g4}, "Result": {"select": {"name": "Pass" if l != "F" else "Fail"}}})
            done.append(f"điểm tổng kết {c['code']}: {d:g} → {l} ({g4})")
            return {"ok": True, "mon": f"{c['code']} {c['name']}", "da_ghi": done}
        nt.create(GRADES, props)
        done.append(f"{a.get('thanh_phan')} {c['code']}: {d:g}/10")
        st = course_status(nt, c, sem)
        msg = apply_overall(nt, c, st, sem)
        if msg: done.append(msg)
        return {"ok": True, "mon": f"{c['code']} {c['name']}", "da_ghi": done, "ket_qua": st}


    if loai in ("ket qua", "ket_qua", "dat", "qua mon"):
        # môn không chấm điểm số (GDTC, Lý luận TDTT, QP-AN…) hoặc được miễn: Đạt / Không đạt / Miễn (R)
        pick = norm(a.get("lua_chon") or "")
        words = pick.split()
        res = ("Fail" if any(w in pick for w in ("truot", "khong dat", "khong qua", "fail")) or "rot" in words else
               "Miễn (R)" if "mien" in words or words == ["r"] else
               "Pass" if any(w in words for w in ("dat", "qua", "pass")) else None)
        if not res: return {"ok": False, "mon": f"{c['code']} {c['name']}", "thieu": ["Kết quả là đạt, không đạt hay được miễn (R)?"]}
        props = {"Result": {"select": {"name": res}}}
        if res == "Miễn (R)": props["Status"] = {"status": {"name": "Completed"}}
        if a.get("ghi_chu"): props["Course Notes"] = rt(((c.get("notes") or "") + " | " if c.get("notes") else "") + a["ghi_chu"])
        nt.patch(c["id"], props)
        vi = {"Pass": "Đạt", "Fail": "Không đạt — sẽ vào quy trình học lại kỳ sau", "Miễn (R)": "Miễn (R), giá trị toàn khoá"}[res]
        extra = " Chưa có điểm số nên môn này không tính vào GPA." if res == "Pass" and c["credits"] else ""
        return {"ok": True, "mon": f"{c['code']} {c['name']}", "da_ghi": [f"{c['code']} {c['name']}: {vi}.{extra}"]}

    if loai in ("thi", "lich thi", "kiem tra"):
        kind = {"giua ky": "Midterm", "cuoi ky": "Final", "kiem tra": "Quiz", "quiz": "Quiz"}.get(norm(a.get("thanh_phan") or ""), None)
        if not kind:
            t = norm(a.get("thanh_phan") or "")
            kind = "Midterm" if "giua" in t else "Final" if "cuoi" in t else "Quiz" if ("kiem tra" in t or "quiz" in t) else None
        day = a.get("ngay")
        if not kind: missing.append("thi giữa kỳ, cuối kỳ hay bài kiểm tra")
        if not day: missing.append("ngày thi (và giờ nếu có)")
        if missing: return {"ok": False, "mon": f"{c['code']} {c['name']}", "thieu": missing}
        when = day if "T" in day else (day + ("T" + a["gio"] + ":00+07:00" if a.get("gio") else ""))
        vi = {"Midterm": "giữa kỳ", "Final": "cuối kỳ", "Quiz": "kiểm tra"}[kind]
        name = f"Thi {vi} {c['code']} {c['name']}"
        nt.create(cfg.notion("academic_work"), {"Name": title(name), "Type": {"select": {"name": kind}}, "Due": {"date": {"start": when}},
                  "Loại hạn": {"select": {"name": "Môn học"}},
                  "Course": {"relation": [{"id": c["id"]}]}, "Entry Kind": {"select": {"name": "Deadline"}}, "Status": {"status": {"name": "Not started"}},
                  "Location": rt(a.get("phong") or "")})
        nt.create(cfg.notion("calendar_events"), {"Event": title("🎓 " + name), "Kind": {"select": {"name": "Deadline"}},
                  "When": {"date": {"start": when}}, "Course": {"relation": [{"id": c["id"]}]}, "Location": rt(a.get("phong") or ""),
                  "Notes": rt(a.get("ghi_chu") or "Lịch thi (ghi qua Copilot)"), "Sync Key": rt(f"exam|{c['code']}|{kind}|{day[:10]}")})
        return {"ok": True, "mon": f"{c['code']} {c['name']}", "da_ghi": [f"{name}: {day[:10]}" + (f" {a['gio']}" if a.get("gio") else "") + " — đã vào Lịch; bản tin sẽ nhắc nếu chưa có kế hoạch ôn."]}

    if loai in ("on thi", "on_thi", "ke hoach on"):
        kind = None
        t = norm(a.get("thanh_phan") or "")
        kind = "Midterm" if "giua" in t else "Final" if "cuoi" in t else "Quiz" if ("kiem tra" in t or "quiz" in t) else "Other" if t else None
        if not kind: missing.append("ôn cho thi giữa kỳ, cuối kỳ hay bài kiểm tra")
        if not a.get("ngay"): missing.append("ngày thi")
        if missing: return {"ok": False, "mon": f"{c['code']} {c['name']}", "thieu": missing}
        st = norm(a.get("trang_thai") or "")
        status = "Ready" if ("xong" in st or "san sang" in st) else "Reviewing" if ("dang" in st or "bat dau" in st) else "Not started"
        tt = norm(a.get("lua_chon") or "")
        conf = "Strong" if ("chac" in tt or "tot" in tt) else "Weak" if ("yeu" in tt or "chua" in tt) else "Medium" if tt else None
        vi = {"Midterm": "giữa kỳ", "Final": "cuối kỳ", "Quiz": "kiểm tra", "Other": ""}[kind]
        props = {"Revision Item": title(f"Ôn thi {vi} {c['code']} {c['name']}".replace("  ", " ")), "Exam Date": {"date": {"start": a["ngay"][:10]}},
                 "Exam Type": {"select": {"name": kind}}, "Topic": rt(a.get("luat") or a.get("ghi_chu") or ""), "Status": {"select": {"name": status}}}
        if conf: props["Confidence"] = {"select": {"name": conf}}
        if num(a.get("so_buoi")) is not None: props["Estimated Hours"] = {"number": num(a.get("so_buoi"))}
        old = [r for r in nt.query(cfg.notion("exam_revision")) if c["code"] in (P(r, "Revision Item") or "")
               and (P(r, "Exam Date") or "")[:10] == a["ngay"][:10]]
        if old: nt.patch(old[0]["id"], props)
        else: nt.create(cfg.notion("exam_revision"), props)
        return {"ok": True, "mon": f"{c['code']} {c['name']}", "da_ghi": [("Cập nhật" if old else "Lập") + f" kế hoạch ôn thi {vi} {c['code']} ({a['ngay'][:10]}): {status}" + (f", tự tin {conf}" if conf else "")]}

    if loai in ("vang", "nghi", "muon", "di muon", "chuyen can"):
        n = int(num(a.get("so_buoi")) or 1)
        status = "Late" if "muon" in loai or norm(a.get("trang_thai")) in ("muon", "late") else \
                 "Excused" if norm(a.get("trang_thai")) in ("co phep", "excused") else "Absent"
        day = a.get("ngay") or today()
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", str(day)):
            return {"ok": False, "thieu": ["ngày vắng dạng YYYY-MM-DD (hoặc bỏ trống nếu là hôm nay)"]}
        if not 1 <= n <= 20:
            return {"ok": False, "thieu": ["số buổi vắng (1–20)"]}
        label = {"Absent": "vắng", "Late": "đi muộn", "Excused": "vắng có phép"}[status]
        for i in range(n):
            nt.create(ATTEND, {"Session": title(f"{c['code']} · {label} {day}" + (f" ({i + 1}/{n})" if n > 1 else "")),
                               "Course": {"relation": [{"id": c["id"]}]}, "Date": {"date": {"start": day}},
                               "Status": {"select": {"name": status}}, "Notes": rt(a.get("ghi_chu") or "")})
        st = course_status(nt, c, sem)
        done.append(f"{n} buổi {label} môn {c['code']}")
        if c["max_abs"] is not None:
            left = st["con_duoc_vang"]
            risk = "At Risk" if left <= 0 else "Watch" if left <= 1 else "OK"
            nt.patch(c["id"], {"Attendance Risk": {"select": {"name": risk}}})
            done.append(f"đã vắng {st['vang']}/{int(c['max_abs'])} buổi → còn được vắng {left}" + (" — SẮP/ĐÃ CHẠM GIỚI HẠN" if risk != "OK" else ""))
        else:
            missing.append(f"giới hạn vắng của môn {c['name']} chưa có, nên chưa tính được còn bao nhiêu buổi")
        return {"ok": True, "mon": f"{c['code']} {c['name']}", "da_ghi": done, "con_thieu_trong_luat": missing, "ket_qua": st}

    return {"ok": False, "thieu": ["loại thông tin: luat (luật môn), diem, vang (vắng/muộn), ren_luyen hoặc xem"]}
