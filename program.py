# -*- coding: utf-8 -*-
"""Chương trình 4 năm cho University Copilot (Claude 2026-10-03): tab Học kỳ (S1..S8 bấm được), học phần tự chọn GDTC,
ĐK tốt nghiệp. Mọi con số tính ở đây (không để AI tự tính); dữ liệu đọc từ Notion qua cổng copilot-notion, đệm như timetable.py.

Hiển thị: S1 → 2026.1, S2 → 2026.2, S3 → 2027.1 … (chỉ trong UC; Notion giữ S1..S8).
GPA kỳ / CPA: trung bình thang 4 theo tín, chỉ môn có tín và đã tổng kết (Pass/Fail có điểm). Môn 0 tín (GDTC, QP-AN) không tính.
Nợ tín: tín các môn Fail chưa học lại qua.
GDTC tự chọn: mở khi PE1014 Lý luận TDTT đạt; cần đạt ≥ 4 học phần; môn đánh số (Bóng chuyền 1 → 2 → 3 …) phải đạt số trước mới học
  số sau (số trước đang học thì cho đăng ký kèm cảnh báo); môn không số học một lần là đủ.
Tốt nghiệp: tín tích luỹ ≥ 128 (khung 128–132) mới mở 2 mục: ngoại ngữ (lấy từ 🎫 Chứng chỉ của tôi — chuẩn đầu ra K70:
  tiếng Anh 4 kỹ năng ≥ Bậc 3, cấp trong 2 năm, còn hạn) và CPA ≥ 2.0.
"""
import uc_config as cfg
import datetime as dt, re, threading, time
from academic import Notion, P, rt, title, TZ, COURSES, GRADES, ATTEND, CONDUCT, STATE, course_view, weighted_gpa, conduct_rank, sem_items, cpa_items, attempt_start, attach_history, past, fail_count, record_attempt, ATTEMPTS

TRACKER = cfg.notion("credit_tracker")
SUMMER = cfg.notion("summer")      # ☀️ Summer Planning
GRAD = cfg.notion("graduation")          # 🎓 Xét tốt nghiệp (Home Dashboard)
PE_GATE = "PE1014"
PE_NEED = 4
GRAD_MIN, GRAD_MAX = 128, 132
R_EXEMPT = "Miễn (R)"   # Result của học phần được miễn (ghi điểm R) — giá trị toàn khoá
CPA_MIN = 2.0   # ngoại ngữ: theo certs.py (chuẩn đầu ra K70: tiếng Anh ≥ Bậc 3, cấp trong 2 năm, còn hạn)
MAX_AGE = 60

RANKS = [(3.6, "Xuất sắc"), (3.2, "Giỏi"), (2.5, "Khá"), (2.0, "Trung bình"), (1.0, "Yếu"), (0.0, "Kém")]   # QCĐT 2025 Đ12.6
DOWN = {"Xuất sắc": "Giỏi", "Giỏi": "Khá"}

def rank_of(x):
    return next(n for t, n in RANKS if x >= t)

def _k(s):
    return int(str(s)[1:]) if s and str(s)[1:].isdigit() else 0

def label(sem):
    """'S3' -> '2027.1'"""
    k = int(str(sem)[1:]) if sem and str(sem)[1:].isdigit() else None
    return f"{2026 + (k - 1) // 2}.{1 if k % 2 else 2}" if k else ""

def _num_level(name):
    m = re.match(r"^(.*?)\s+(\d)$", name or "")
    return (m.group(1), int(m.group(2))) if m else (name, None)


def build(post):
    nt = Notion(post)
    raw = nt.query(COURSES)
    courses = []
    for p in raw:
        c = course_view(p)
        c.update({"group": P(p, "Nhóm tự chọn"), "hint": P(p, "Kỳ gợi ý") or "", "retake": bool(P(p, "Retake")),
                  "risk": P(p, "Attendance Risk")})
        courses.append(c)
    attach_history(courses, nt.attempts())
    grades = nt.query(GRADES)
    att = nt.query(ATTEND)
    tracker = nt.query(TRACKER)
    conduct = nt.query(CONDUCT)
    state = next((r for r in nt.query(STATE) if P(r, "State") == "Current"), None)
    cur_no = P(state, "Semester No.") if state else "1"
    cur_k = int(cur_no) if str(cur_no).isdigit() else 1
    period = P(state, "Period") if state else "Semester"

    by_id = {c["id"]: c for c in courses}
    g_by = {}
    for r in grades:
        for cid in P(r, "Course") or []:
            g_by.setdefault(cid, []).append({"component": P(r, "Component"), "score": P(r, "Score 10"), "sem": P(r, "Semester")})
    a_rows = {}
    for r in att:
        for cid in P(r, "Course") or []:
            a_rows.setdefault(cid, []).append(((P(r, "Date") or "")[:10], P(r, "Status")))
    def a_of(c):   # lần học lại / cải thiện: chỉ đếm buổi vắng từ đầu kỳ của lần đó
        rows, start = a_rows.get(c["id"], []), (attempt_start(c["semester"]) if c["retake"] or c["improve"] else None)
        rows = [x for x in rows if not start or x[0] >= start]
        absent = sum(1 for x in rows if x[1] == "Absent")
        if c.get("abs_school") is not None: absent = int(c["abs_school"])   # điểm danh của trường (qldt) là cao nhất
        return {"absent": absent, "late": sum(1 for x in rows if x[1] == "Late")}
    def g_of(c):
        return [x for x in g_by.get(c["id"], []) if not (c["retake"] or c["improve"]) or x["sem"] == c["semester"]]
    rl = {P(r, "Semester"): {"diem": P(r, "Điểm"), "xep_loai": conduct_rank(P(r, "Điểm")) if P(r, "Điểm") is not None else None} for r in conduct}
    tr = {}
    for r in tracker:
        s = "S" + (P(r, "Semester") or "").split()[-1]
        tr[s] = {"required": P(r, "Required Credits"), "planned": P(r, "Planned Credits"), "check": P(r, "Đối soát") or "",
                 "gpa_s": P(r, "GPA (trường)"), "cpa_s": P(r, "CPA (trường)"), "warn_s": P(r, "Cảnh báo (trường)") or "",
                 "drl_s": P(r, "ĐRL đang chấm (trường)") or ""}

    # nợ tín: môn Fail, hoặc môn học lại chưa đạt — tính vào kỳ đã trượt (Original Semester)
    pend = lambda c: not c["improve"] and (c["result"] == "Fail" or (c["retake"] and c["result"] not in ("Pass", R_EXEMPT)))
    earn = lambda c: c["result"] == "Pass" or c["improve"]   # học cải thiện: tín đã đạt từ lần trước, giữ nguyên
    # kỳ tích luỹ tín = lần ĐẠT đầu tiên; kỳ ghi nợ = lần TRƯỢT đầu tiên (từ 🔁 Lần học)
    earn_sem = lambda c: next((x["sem"] for x in past(c) if x["result"] == "Pass"), c["semester"])
    debt_sem = lambda c: next((x["sem"] for x in past(c) if x["result"] == "Fail" and x["kind"] != "Cải thiện"), c["semester"])
    graded = lambda c: c["credits"] and c["gpa4"] is not None and c["result"] in ("Pass", "Fail")
    sems = []
    for k in range(1, 9):
        s = f"S{k}"
        cs = [c for c in courses if c["semester"] == s]
        upto = cpa_items(courses, k)
        done = sum(c["credits"] for c in courses if earn(c) and earn_sem(c) == s)
        debt = sum(c["credits"] for c in courses if pend(c) and debt_sem(c) == s)
        status = "Đang học" if k == cur_k and period == "Semester" else ("Đã học" if k <= cur_k else "Chưa học")
        g = sem_items(courses, s)
        sems.append({"sem": s, "label": label(s), "status": status,
                     # GPA/CPA: trường công bố (bảng điểm tổng hợp qldt) thì lấy của trường, chưa có thì tự tính theo QCĐT
                     "gpa": (tr.get(s) or {}).get("gpa_s") if (tr.get(s) or {}).get("gpa_s") is not None else (weighted_gpa(g) if g else None),
                     "cpa": (tr.get(s) or {}).get("cpa_s") if (tr.get(s) or {}).get("cpa_s") is not None else (weighted_gpa(upto) if upto and status != "Chưa học" else None),
                     "official": (tr.get(s) or {}).get("gpa_s") is not None, "warn": (tr.get(s) or {}).get("warn_s", ""),
                     "drlLive": (tr.get(s) or {}).get("drl_s", ""),
                     "credits": (tr.get(s) or {}).get("planned", sum(c["credits"] for c in cs)), "done": done, "debt": debt,
                     "required": (tr.get(s) or {}).get("required"), "check": (tr.get(s) or {}).get("check", ""),
                     "conduct": rl.get(s),
                     "courses": [{**{k2: c[k2] for k2 in ("id", "code", "name", "credits", "status", "result", "gpa4", "category", "rule", "w_qt", "max_abs", "notes", "retake", "improve", "prev4", "risk", "group")},
                                  "grades": g_of(c), "abs": a_of(c)} for c in cs]})
    all_graded = cpa_items(courses)
    cpa = weighted_gpa(all_graded) if all_graded else None
    off = [x["cpa"] for x in sems if x["official"] and x["cpa"] is not None]
    if off: cpa = off[-1]   # CPA trường công bố của kỳ gần nhất là cao nhất
    earned = sum(c["credits"] for c in courses if earn(c))
    debt = sum(c["credits"] for c in courses if pend(c))

    # ---------- học lại (thanh bên)
    rt_items = []
    for c in courses:
        if c["improve"] or not (pend(c) or (c["retake"] and c["result"] == "Pass")): continue
        failed = debt_sem(c) or c["semester"]
        fails = [x["sem"] for x in past(c) if x["result"] == "Fail" and x["kind"] != "Cải thiện"] + ([c["semester"]] if c["result"] == "Fail" else [])
        fk = int(failed[1:]) if failed and failed[1:].isdigit() else cur_k
        if c["result"] == "Pass": st, why = "passed", f"Đã qua khi học lại {label(c['semester'])}"
        elif c["retake"] and c["status"] == "Taking": st, why = "taking", f"Đang học lại kỳ {label(c['semester'])}"
        elif c["retake"]: st, why = "planned", f"Học lại kỳ {label(c['semester'])} (dự kiến — TKB kỳ đó xác nhận)"
        elif c["semester"] == f"S{cur_k}" and period == "Semester":
            st, why = "wait", (f"Hết kỳ này hệ thống tự xếp sang {label(f'S{cur_k + 1}')}; sau đó đổi kỳ ở đây được." if cur_k < 8 else "Kỳ cuối — báo Copilot cách xử lý.")
        else: st, why = "unscheduled", "Chưa xếp kỳ học lại"
        opts = [{"sem": f"S{k}", "label": label(f"S{k}")} for k in range(max(fk + 1, cur_k), 9)] if st in ("planned", "unscheduled") else []
        rt_items.append({"id": c["id"], "code": c["code"], "name": c["name"], "credits": c["credits"], "failedIn": ", ".join(label(x) for x in fails) or label(failed), "fails": len(fails),
                         "sem": c["semester"], "semLabel": label(c["semester"]), "state": st, "why": why, "options": opts})
    rt_items.sort(key=lambda i: (i["state"] == "passed", i["code"]))
    retake = {"debt": debt, "items": rt_items}

    # ---------- học cải thiện (Đ5.8): học lại môn đã đạt; điểm lần cao nhất là điểm chính thức
    im_items, im_cands = [], []
    for c in courses:
        if not c["credits"]: continue
        if c["improve"]:
            last = next((x for x in reversed(past(c)) if x["result"] == "Pass"), None)   # lần đạt mà bạn đang cải thiện
            prev4 = last["gpa4"] if last else c["prev4"]
            graded_now = c["gpa4"] is not None and c["result"] in ("Pass", "Fail")
            best = max([x["gpa4"] for x in past(c) if x["gpa4"] is not None] + ([c["gpa4"]] if graded_now else []), default=None)
            if graded_now: st, why = "done", f"Đã học cải thiện {label(c['semester'])}: lần này {c['gpa4']:g} → điểm chính thức {best:g}"
            elif c["status"] == "Taking": st, why = "taking", f"Đang học cải thiện kỳ {label(c['semester'])}"
            else: st, why = "planned", f"Học cải thiện kỳ {label(c['semester'])} (dự kiến — TKB kỳ đó xác nhận)"
            frm = last["sem"] if last else c["orig"]
            ok = max(_k(frm) + 1, cur_k)
            im_items.append({"id": c["id"], "code": c["code"], "name": c["name"], "credits": c["credits"], "prev4": prev4, "gpa4": c["gpa4"] if graded_now else None,
                             "best": best, "from": label(frm), "sem": c["semester"], "semLabel": label(c["semester"]), "state": st, "why": why,
                             "tries": len(past(c)) + 1, "options": [{"sem": f"S{k}", "label": label(f"S{k}")} for k in range(ok, 9)] if st == "planned" else []})
        elif c["result"] == "Pass" and c["gpa4"] is not None and c["gpa4"] < 4 and c["semester"]:
            ok = max(_k(c["semester"]) + 1, cur_k)
            if ok <= 8:
                im_cands.append({"id": c["id"], "code": c["code"], "name": c["name"], "credits": c["credits"], "gpa4": c["gpa4"], "semLabel": label(c["semester"]),
                                 "options": [{"sem": f"S{k}", "label": label(f"S{k}")} for k in range(ok, 9)]})
    im_cands.sort(key=lambda i: (i["gpa4"], -i["credits"]))
    improve = {"items": im_items, "candidates": im_cands, "credits": sum(i["credits"] for i in im_items)}

    # ---------- kỳ hè (thanh bên) — ☀️ Summer Planning, mỗi hè 1 dòng "Hè sau S{k}"
    su_rows = {}
    for r in nt.query(SUMMER): su_rows.setdefault(P(r, "Plan") or "", r)
    summers = []
    for k in (2, 4, 6):
        r = su_rows.get(f"Hè sau S{k}")
        g = (lambda n: P(r, n)) if r else (lambda n: None)
        summers.append({"k": k, "label": f"Hè {2026 + k // 2}", "after": label(f"S{k}"), "rowId": r["id"] if r else None,
                        "choice": g("Choice"), "status": g("Status"), "company": g("Company") or "", "position": g("Position") or "",
                        "hours": g("Work Hours") or "", "credits": g("Credits"), "courses": g("Course Search") or "", "notes": g("Notes") or "",
                        "now": period == "Hè" and cur_k == k, "past": cur_k > k})

    # ---------- GDTC tự chọn
    gate = next((c for c in courses if c["code"] == PE_GATE), None)
    unlocked = bool(gate and gate["result"] == "Pass")
    pool = [c for c in courses if c["group"] == "GDTC"]
    by_chain = {}
    for c in pool:
        base, lv = _num_level(c["name"])
        c["_base"], c["_lv"] = base, lv
        if lv: by_chain.setdefault(base, {})[lv] = c
    passed = [c for c in pool if c["result"] == "Pass"]
    items = []
    for c in sorted(pool, key=lambda c: (c["_base"], c["_lv"] or 0)):
        prev = by_chain.get(c["_base"], {}).get(c["_lv"] - 1) if c["_lv"] and c["_lv"] > 1 else None
        if c["result"] == "Pass": st, why = "passed", "Đã đạt"
        elif c["status"] == "Taking": st, why = "taking", f"Đang học ({label(c['semester'])})"
        elif c["semester"]: st, why = "chosen", f"Đã chọn cho {label(c['semester'])}"
        elif not unlocked: st, why = "locked", "Mở khi đạt Lý luận TDTT (PE1014)"
        elif prev and prev["result"] != "Pass" and prev["status"] != "Taking" and not prev["semester"]:
            st, why = "locked", f"Cần học {prev['name']} trước"
        elif prev and prev["result"] != "Pass":
            st, why = "open", f"Đăng ký được — chờ kết quả {prev['name']}"
        else: st, why = "open", "Đăng ký được"
        items.append({"id": c["id"], "code": c["code"], "name": c["name"], "base": c["_base"], "level": c["_lv"], "hint": c["hint"],
                      "semester": c["semester"], "semLabel": label(c["semester"]), "state": st, "why": why,
                      "prev": prev["code"] if prev else None})
    electives = {"unlocked": unlocked, "gate": {"code": PE_GATE, "name": gate["name"] if gate else "Lý luận TDTT",
                                               "status": gate["status"] if gate else None, "result": gate["result"] if gate else None},
                 "need": PE_NEED, "passed": len(passed), "chosen": len([i for i in items if i["state"] in ("chosen", "taking")]),
                 "items": items, "semesters": [{"sem": f"S{k}", "label": label(f"S{k}")} for k in range(max(cur_k, 1), 9)]}

    # ---------- chứng chỉ ngoại ngữ (certs.py) — nguồn cho mục ngoại ngữ khi xét tốt nghiệp
    import certs
    try: cz = certs.build(nt)
    except Exception as e: cz = {"error": f"{type(e).__name__}: {e}"[:300], "items": [], "catalog": [], "rules": [], "summary": {}}
    # FL1131..FL1135 trong Courses: đã học / đang học / được miễn theo chứng chỉ
    fl = {c["code"]: c for c in courses if c["code"].startswith("FL113")}
    cz["fl"] = [{"code": r["code"], "name": r["name"], "status": (fl.get(r["code"]) or {}).get("status"),
                 "result": (fl.get(r["code"]) or {}).get("result"), "semester": label((fl.get(r["code"]) or {}).get("semester")),
                 "exempt": r["code"] in cz.get("summary", {}).get("exempt", []), "minLv": r["lv"], "when": r["when"],
                 "r": (fl.get(r["code"]) or {}).get("result") == R_EXEMPT}   # điểm R: miễn toàn khoá, không phụ thuộc hạn chứng chỉ
                for r in cz.get("rules", []) if r["code"] != "CHUAN_DAU_RA"]
    # ---------- tốt nghiệp
    gr = next(iter(nt.query(GRAD)), None)
    sm = cz.get("summary", {})
    credit_ok = earned >= GRAD_MIN
    cert, lang_ok = lang_link(cz, credit_ok)
    cpa_ok = cpa is not None and cpa >= CPA_MIN
    # ---------- hạng tốt nghiệp dự kiến (Đ15 + Đ12.6): hạng theo CPA; Giỏi trở lên hạ 1 mức nếu tín phải học lại > 5%
    #            tổng tín tính điểm toàn khoá (không tính học cải thiện) hoặc từng bị kỷ luật từ cảnh cáo trở lên
    retake_cr = sum(c["credits"] * fail_count(c) for c in courses if c["credits"])   # mỗi lần trượt = một lần phải học lại
    base_real = sum(cr for cr, _ in all_graded)
    base = max(base_real, GRAD_MIN)
    thr = round(base * 0.05, 2)
    discipline = bool(P(gr, "Kỷ luật từ cảnh cáo")) if gr else False
    r0 = rank_of(cpa) if cpa is not None else None
    reasons = ([f"tín phải học lại {retake_cr:g} > {thr:g} (5% của {base:g})"] if retake_cr > thr else []) + (["từng bị kỷ luật từ cảnh cáo trở lên"] if discipline else [])
    down = r0 in DOWN and bool(reasons)
    rank = {"cpaRank": r0, "final": DOWN[r0] if down else r0, "down": down, "reasons": reasons, "retakeCr": retake_cr, "threshold": thr,
            "base": base, "baseReal": base_real, "discipline": discipline, "improveCr": improve["credits"],
            "room": round(thr - retake_cr, 2)}
    grad = {"rowId": gr["id"] if gr else None, "rank": rank, "earned": earned, "min": GRAD_MIN, "max": GRAD_MAX, "unlocked": credit_ok,
            "cert": cert, "langOk": lang_ok, "cpa": cpa, "cpaOk": cpa_ok, "pe": {"passed": len(passed), "need": PE_NEED},
            "rules": {"cpa": CPA_MIN, "lang": sm.get("gradNeed") or "Bậc 3"},
            "eligible": credit_ok and lang_ok and cpa_ok}
    return {"current": f"S{cur_k}", "currentLabel": label(f"S{cur_k}"), "period": period, "semesters": sems,
            "overall": {"cpa": cpa, "earned": earned, "debt": debt}, "electives": electives, "graduation": grad, "certs": cz, "summer": summers, "retake": retake, "improve": improve,
            "_grad_row": gr}


def lang_link(cz, unlocked):
    """Cổng DUY NHẤT nối 🎫 Chứng chỉ -> ĐK tốt nghiệp (yêu cầu người dùng 2026-10-03):
    • chưa đủ 128 tín -> KHÔNG nối: không đọc chứng chỉ, không đánh dấu ngoại ngữ (tránh tự tính 'đạt' khi chưa xét tốt nghiệp);
    • đủ tín -> chỉ nhận chứng chỉ mục 'Đã có', còn hạn tại hôm nay, đạt Bậc 3, cấp trong 2 năm — không bao giờ lấy mục 'Đã hết hạn'."""
    need = (cz.get("summary") or {}).get("gradNeed") or "Bậc 3"
    if not unlocked:
        return {"linked": False, "name": None, "need": need, "best": None}, False
    today = dt.datetime.now(TZ).date().isoformat()
    ok = [x for x in cz.get("items", []) if x.get("muc") == "Đã có" and x.get("valid") and x.get("grad")
          and (x.get("expiry") is None or x["expiry"] >= today)]
    best = max(ok, key=lambda x: x.get("lvn") or 0, default=None)
    have = [x for x in cz.get("items", []) if x.get("muc") == "Đã có" and x.get("valid") and x.get("english")
            and (x.get("expiry") is None or x["expiry"] >= today)]
    top = max(have, key=lambda x: x.get("lvn") or 0, default=None)
    return ({"linked": True, "name": best and f"{best['cert']} {best.get('band') or ''}".strip(), "need": need,
             "best": top and {"cert": top["cert"], "lv": top["lvLabel"]}}, bool(best))


# ---------------------------------------------------------------- đệm
_lock = threading.Lock()
_st = {"data": None, "at": 0.0, "busy": False, "error": None}

def _sync_grad_row(post, d):
    """Ghi kết quả engine vào 🎓 Xét tốt nghiệp (Home Dashboard) khi có thay đổi."""
    g, row = d["graduation"], d.pop("_grad_row", None)
    if not row: return
    concl = ("ĐỦ điều kiện xét tốt nghiệp." if g["eligible"] else
             f"Chưa đủ tín: {g['earned']}/{g['min']}." if not g["unlocked"] else
             "Đủ tín; còn: " + ", ".join(x for x, ok in (("chứng chỉ ngoại ngữ", g["langOk"]), (f"CPA ≥ {CPA_MIN}", g["cpaOk"])) if not ok) + ".")
    k = g["rank"]
    hang = (("Chưa có CPA" if k["final"] is None else k["final"] + (f" (hạ từ {k['cpaRank']}: " + "; ".join(k["reasons"]) + ")" if k["down"] else ""))
            + f" · học lại {k['retakeCr']:g}/{k['threshold']:g} tín")
    want = {"Tín tích luỹ": g["earned"], "CPA": g["cpa"], "Đủ tín": g["unlocked"], "Đủ ngoại ngữ": g["langOk"], "Đủ CPA": g["cpaOk"], "Kết luận": concl,
            "Tín phải học lại": k["retakeCr"], "Ngưỡng 5% (tín)": k["threshold"], "Bị hạ hạng": k["down"], "Hạng tốt nghiệp dự kiến": hang}
    if all(P(row, n) == v for n, v in want.items()): return
    props = {n: ({"checkbox": v} if isinstance(v, bool) else rt(v) if isinstance(v, str) else {"number": v}) for n, v in want.items()}
    props["Cập nhật"] = {"date": {"start": dt.datetime.now(TZ).isoformat(timespec="minutes")}}
    Notion(post).patch(row["id"], props)

def refresh(post):
    with _lock:
        if _st["busy"]: return
        _st["busy"] = True
    try:
        d = build(post)
        try: _sync_grad_row(post, d)
        except Exception as e: print("grad row:", e)
        d.pop("_grad_row", None)
        _st.update({"data": d, "at": time.time(), "error": None})
    except Exception as e:
        _st["error"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        _st["busy"] = False

def get(post, force=False):
    if _st["data"] is None:
        refresh(post)
    elif force or time.time() - _st["at"] > MAX_AGE:
        threading.Thread(target=refresh, args=(post,), daemon=True).start()
    return {**(_st["data"] or {}), "fetchedAt": int(_st["at"]), "refreshing": _st["busy"], "error": _st["error"]}


# ---------------------------------------------------------------- thao tác từ giao diện
def _data(post):
    """Bản đệm nếu còn mới (≤ 5 phút) — tránh dựng lại 10 s mỗi lần bấm; không có thì dựng."""
    if _st["data"] and time.time() - _st["at"] < 300: return _st["data"]
    d = build(post); d.pop("_grad_row", None); return d

def choose_elective(post, code, sem):
    """sem = 'S2'.. để chọn, '' để bỏ chọn."""
    d = _data(post)
    el = d["electives"]
    it = next((i for i in el["items"] if i["code"] == code), None)
    if not it: return {"ok": False, "loi": "Không có học phần này trong nhóm tự chọn GDTC."}
    nt = Notion(post)
    if not sem:
        if it["state"] not in ("chosen",): return {"ok": False, "loi": "Chỉ bỏ được môn đã chọn mà chưa học."}
        nt.patch(it["id"], {"Semester": {"select": None}, "Status": {"status": {"name": "Planned"}}})
        return {"ok": True, "da_ghi": f"Bỏ chọn {code} {it['name']}"}
    if not re.fullmatch(r"S[1-8]", sem): return {"ok": False, "loi": "Kỳ không hợp lệ."}
    if it["state"] not in ("open", "chosen"): return {"ok": False, "loi": it["why"]}
    if int(sem[1:]) < int(d["current"][1:]): return {"ok": False, "loi": "Không chọn được cho kỳ đã qua."}
    if it["prev"]:
        prev = next(i for i in el["items"] if i["code"] == it["prev"])
        if prev["state"] in ("chosen", "taking") and prev["semester"] and int(prev["semester"][1:]) >= int(sem[1:]):
            return {"ok": False, "loi": f"{prev['name']} phải học ở kỳ trước {label(sem)}."}
    status = "Taking" if sem == d["current"] and d["period"] == "Semester" else "Planned"
    nt.patch(it["id"], {"Semester": {"select": {"name": sem}}, "Status": {"status": {"name": status}}})
    return {"ok": True, "da_ghi": f"Chọn {code} {it['name']} cho {label(sem)}"}


def refresh_certs(post):
    """Sau khi thêm/sửa chứng chỉ: chỉ tính lại phần chứng chỉ (~3 s) rồi ghép vào bản đệm; phần còn lại làm mới ngầm."""
    import certs
    d = _st.get("data")
    if not d:
        refresh(post); return
    cz = certs.build(Notion(post))
    ex = set(cz.get("summary", {}).get("exempt", []))
    cz["fl"] = [{**f, "exempt": f["code"] in ex} for f in (d.get("certs") or {}).get("fl", [])]
    sm = cz.get("summary", {})
    g = dict(d["graduation"])
    cert, lang_ok = lang_link(cz, g["unlocked"])
    g.update({"cert": cert, "langOk": lang_ok})
    g["eligible"] = g["unlocked"] and g["langOk"] and g["cpaOk"]
    _st["data"] = {**d, "certs": cz, "graduation": g}
    threading.Thread(target=refresh, args=(post,), daemon=True).start()


# ---------------------------------------------------------------- thanh bên: kỳ hè · học lại (ghi sau khi bạn bấm Xác nhận)
SUMMER_CHOICES = {"Study Summer": "Học hè", "Relax": "Nghỉ", "Internship": "Thực tập"}

def _rtx(s):
    s = str(s or "").strip()
    return {"rich_text": [{"type": "text", "text": {"content": s[:1900]}}] if s else []}

def save_summer(post, k, choice, company="", position="", hours="", credits=None, courses="", notes=""):
    try: k = int(k)
    except (TypeError, ValueError): return {"ok": False, "loi": "Hè không hợp lệ."}
    if k not in (2, 4, 6): return {"ok": False, "loi": "Hè không hợp lệ."}
    if choice not in SUMMER_CHOICES: return {"ok": False, "loi": "Chọn Học hè, Nghỉ hoặc Thực tập."}
    d = _data(post)
    if int(d["current"][1:]) > k: return {"ok": False, "loi": "Hè này đã qua."}
    if choice == "Internship" and not str(company or "").strip(): return {"ok": False, "loi": "Thực tập: điền tên công ty."}
    cr = None
    if choice == "Study Summer" and credits not in (None, ""):
        try: cr = float(credits)
        except ValueError: return {"ok": False, "loi": "Số tín phải là số."}
        if not 1 <= cr <= 8: return {"ok": False, "loi": "Học kỳ hè đăng ký tối đa 8 tín (QCĐT 2025, Đ10)."}
    intern, study = choice == "Internship", choice == "Study Summer"
    props = {"Choice": {"select": {"name": choice}}, "Status": {"status": {"name": "Done" if choice == "Relax" else "In progress"}},
             "Company": _rtx(company if intern else ""), "Position": _rtx(position if intern else ""), "Work Hours": _rtx(hours if intern else ""),
             "Credits": {"number": cr}, "Course Search": _rtx(courses if study else ""), "Notes": _rtx(notes)}
    nt = Notion(post)
    rows = [r for r in nt.query(SUMMER) if P(r, "Plan") == f"Hè sau S{k}"]
    if rows: nt.patch(rows[0]["id"], props)
    else: nt.create(SUMMER, {"Plan": title(f"Hè sau S{k}"), **props})
    import semester
    semester._close_eq(nt, f"semester:summer:S{k}", SUMMER_CHOICES[choice] + " (chọn trên UC)")
    return {"ok": True, "da_ghi": f"Hè {2026 + k // 2}: {SUMMER_CHOICES[choice]}"}

def schedule_retake(post, cid, sem):
    d = _data(post)
    it = next((i for i in d.get("retake", {}).get("items", []) if i["id"] == cid), None)
    if not it: return {"ok": False, "loi": "Môn này không nằm trong danh sách học lại."}
    if it["state"] not in ("planned", "unscheduled"): return {"ok": False, "loi": it["why"]}
    if sem not in [o["sem"] for o in it["options"]]: return {"ok": False, "loi": "Kỳ học lại không hợp lệ."}
    if it["state"] == "planned" and sem == it["sem"]: return {"ok": True, "da_ghi": "Không đổi."}
    nt = Notion(post)
    from academic import course_view
    c = next((course_view(p) for p in nt.query(COURSES) if p["id"] == cid), None)
    if not c: return {"ok": False, "loi": "Không đọc được môn trong Courses."}
    note = (c["notes"] + " | " if c["notes"] else "") + f"Học lại: xếp sang {sem} (UC)"
    props = {"Semester": {"select": {"name": sem}}, "Retake": {"checkbox": True}, "Status": {"status": {"name": "Planned"}}, "Course Notes": rt(note)}
    if it["state"] == "unscheduled":
        record_attempt(nt, c)   # lưu lần trượt vào 🔁 Lần học
        props.update({"Result": {"select": {"name": "Unknown"}}, "Current GPA 4": {"number": None}, "Remaining Credits": {"number": c["credits"]},
                      "GPA 4 lần trước": {"number": c["gpa4"] if c["gpa4"] is not None else 0}})   # giữ điểm F cho GPA kỳ trượt + CPA
        if not c["orig"] and c["semester"]: props["Original Semester"] = {"select": {"name": c["semester"]}}
    nt.patch(cid, props)
    return {"ok": True, "da_ghi": f"{it['code']} học lại kỳ {label(sem)}"}


def schedule_improve(post, cid, sem):
    """Đăng ký học cải thiện môn đã đạt (hoặc đổi kỳ của lần cải thiện đang dự kiến)."""
    d = _data(post)
    im = d.get("improve", {})
    cand = next((i for i in im.get("candidates", []) if i["id"] == cid), None)
    cur = next((i for i in im.get("items", []) if i["id"] == cid), None)
    it = cand or cur
    if not it: return {"ok": False, "loi": "Môn này không học cải thiện được (chỉ môn đã đạt, có điểm, dưới 4.0)."}
    if cur and cur["state"] != "planned": return {"ok": False, "loi": cur["why"]}
    if sem not in [o["sem"] for o in it["options"]]: return {"ok": False, "loi": "Kỳ học cải thiện không hợp lệ."}
    nt = Notion(post)
    c = next((course_view(p) for p in nt.query(COURSES) if p["id"] == cid), None)
    if not c: return {"ok": False, "loi": "Không đọc được môn trong Courses."}
    note = (c["notes"] + " | " if c["notes"] else "") + f"Học cải thiện: xếp sang {sem} (UC)"
    props = {"Semester": {"select": {"name": sem}}, "Status": {"status": {"name": "Planned"}}, "Course Notes": rt(note)}
    if cand:
        record_attempt(nt, c)   # lưu lần đạt vào 🔁 Lần học
        props.update({"Học cải thiện": {"checkbox": True}, "GPA 4 lần trước": {"number": c["gpa4"]},
                      "Result": {"select": {"name": "Unknown"}}, "Current GPA 4": {"number": None}})
        if not c["orig"]: props["Original Semester"] = {"select": {"name": c["semester"]}}
    nt.patch(cid, props)
    return {"ok": True, "da_ghi": f"{it['code']} học cải thiện kỳ {label(sem)}"}

def cancel_improve(post, cid):
    """Huỷ lần cải thiện chưa học: trả môn về kỳ cũ với điểm đạt cũ."""
    d = _data(post)
    cur = next((i for i in d.get("improve", {}).get("items", []) if i["id"] == cid), None)
    if not cur or cur["state"] != "planned": return {"ok": False, "loi": "Chỉ huỷ được lần cải thiện đang dự kiến (chưa học)."}
    nt = Notion(post)
    c = next((course_view(p) for p in nt.query(COURSES) if p["id"] == cid), None)
    rows = [r for r in nt.query(ATTEMPTS, {"property": "Course", "relation": {"contains": cid}})
            if P(r, "Kết quả") == "Pass" and P(r, "Loại") != "Đã huỷ"]
    last = max(rows, key=lambda r: (_k(P(r, "Semester")), r.get("created_time", "")), default=None)
    sem0, g0 = (P(last, "Semester"), P(last, "GPA 4")) if last else ((c or {}).get("orig"), (c or {}).get("prev4"))
    if not c or not sem0 or g0 is None: return {"ok": False, "loi": "Thiếu kỳ hoặc điểm lần trước — sửa tay trong Notion."}
    note = (c["notes"] + " | " if c["notes"] else "") + "Huỷ học cải thiện (UC)"
    props = {"Semester": {"select": {"name": sem0}}, "Status": {"status": {"name": "Completed"}}, "Result": {"select": {"name": "Pass"}},
             "Current GPA 4": {"number": g0}, "Học cải thiện": {"checkbox": False}, "GPA 4 lần trước": {"number": None}, "Course Notes": rt(note)}
    if not c["retake"] and c["orig"] == sem0: props["Original Semester"] = {"select": None}
    nt.patch(cid, props)
    if last: nt.patch(last["id"], {"Loại": {"select": {"name": "Đã huỷ"}}})   # lần đạt quay lại thành lần hiện tại trên Courses
    return {"ok": True, "da_ghi": f"Huỷ học cải thiện {cur['code']}"}
