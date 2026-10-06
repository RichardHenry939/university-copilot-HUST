# -*- coding: utf-8 -*-
"""Áp dữ liệu chính thức của trường vào Notion (Claude 2026-10-03). Nguyên tắc người dùng: DỮ LIỆU TRƯỜNG LÀ CAO NHẤT —
khác thì sửa thẳng, mọi thay đổi ghi vào 🏫 Đồng bộ trường.

Nguồn: school/latest.json (school_fetch.py đọc qldt + iCTSV). Áp:
  • TKB (qldt Thời khoá biểu → Chi tiết)  → 📅 Academic Timetable qua tkb.run (đúng tuần, phòng, online/offline, mã lớp);
                                            buổi cũ không còn trên qldt → thùng rác Notion (khôi phục được 30 ngày)
  • Vắng (cột Vắng của từng lớp)          → Courses."Vắng (trường)" (tổng các lớp của môn) — dùng cho cảnh báo cấm thi
  • Bảng điểm chi tiết                    → Courses."Điểm thành phần (trường)"
  • Chương trình đào tạo                   → Courses: Credits, "Nhóm HP (trường)", điểm HP / kết quả khi trường đã công bố
  • Bảng điểm tổng hợp (GPA/CPA/ĐRL/TC/Cảnh báo theo kỳ) → Semester Credit Tracker + ⭐ Điểm rèn luyện
  • iCTSV chấm điểm rèn luyện (đang chấm) → Tracker."ĐRL đang chấm (trường)"
  • Khung CTĐT: môn Notion chưa có (bắt buộc lẫn tự chọn) → tạo; kỳ dự kiến của môn bắt buộc CHƯA học → theo khung trường.

LUẬT CỐ ĐỊNH (người dùng 2026-10-04, áp cho MỌI kỳ: 20261, 20262, 20271, … tới hết khoá):
  KHÔNG DỮ LIỆU LOCAL NÀO ĐƯỢC VƯỢT MẶT DỮ LIỆU TRƯỜNG — áp cho trường hợp NOTION THIẾU / LỆCH so với trường:
  trường có mà Notion chưa có → thêm; trường và Notion khác nhau → sửa theo trường (kể cả giá trị bạn hay Copilot nhập tay).
  Thứ tự quyết định: TKB/bảng điểm (lần học thật) > khung CTĐT (kế hoạch) > dữ liệu local.
  KHÔNG áp cho NOTION THỪA: thứ Notion có mà trường không liệt kê (môn Module chưa hiện hết, luật môn GV nói, deadline,
  ghi chú…) → giữ nguyên, không xoá, không báo. Môn tự chọn trong khung cũng cần có (chỉ là kỳ học do bạn chọn).
"""
import uc_config as cfg
import json, re, subprocess, sys, datetime as dt
from pathlib import Path
from academic import Notion, P, rt, title, TZ, COURSES, CONDUCT, course_view

HERE = Path(__file__).resolve().parent
SNAP = HERE / "school" / "latest.json"
STATE_FILE = HERE / "school" / "state.json"
LOG_DB = cfg.notion("school_log")      # 🏫 Đồng bộ trường
TRACKER = cfg.notion("credit_tracker")
KIND = {"LT": "LT", "BT": "BT", "LT+BT": "LT+BT", "TN": "Thực nghiệm", "TH": "Thực hành", "ĐA": "Đồ án", "DA": "Đồ án", "TT": "Thực tập"}
G4 = {"A+": 4.0, "A": 4.0, "B+": 3.5, "B": 3.0, "C+": 2.5, "C": 2.0, "D+": 1.5, "D": 1.0, "F": 0.0}


def _clean(s):
    return str(s or "").replace("\xa0", " ").strip()

def sem_of_code(code):
    """'20261' -> 'S1', '20272' -> 'S4' (năm học bắt đầu 2026)."""
    m = re.match(r"(\d{4})\.?([12])", _clean(code))
    if not m: return None
    k = (int(m.group(1)) - 2026) * 2 + int(m.group(2))
    return f"S{k}" if 1 <= k <= 8 else None

def sem_of_header(text):
    """'Học kỳ 1 - Năm học 2026-2027' -> 'S1'"""
    m = re.search(r"Học kỳ\s*(\d)\s*-\s*Năm học\s*(\d{4})", _clean(text))
    return f"S{(int(m.group(2)) - 2026) * 2 + int(m.group(1))}" if m else None

def _category(groups):
    g = " ".join(groups).lower()
    return ("Môn Đại cương" if "toán và khoa học" in g or "tiếng anh" in g else "Chính trị" if "chính trị" in g or "quốc phòng" in g else
            "Thể chất" if "thể chất" in g else "Cử nhân" if "tốt nghiệp" in g else "Thực hành" if "thực tập" in g else
            "Kỹ năng mềm" if "bổ trợ" in g else "Môn Cơ sở ngành" if "cơ sở" in g else "Môn Chuyên ngành")


def weeks(text):
    out = []
    for part in re.split(r"[,\s]+", _clean(text)):
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit(): out += list(range(int(a), int(b) + 1))
        elif part.isdigit():
            out.append(int(part))
    return sorted(set(out))


# ------------------------------------------------------------------ đọc bảng
def parse_tkb(t):
    """-> (lop[], vang{code: n}, problems[])"""
    lop, vang, probs = [], {}, []
    for r in t.get("rows", []):
        if len(r) < 6: continue
        head = _clean(r[1])
        m = re.search(r"(\d+)\s*-\s*([A-Z]{2,4}\d{3,4}[A-Z]?)\s*\(([^)]+)\)", head)
        if not m: probs.append(f"Không đọc được lớp: {head[:60]}"); continue
        cls, code, typ = m.groups()
        try: vang[code] = vang.get(code, 0) + int(_clean(r[5]) or 0)
        except ValueError: pass
        sched = _clean(r[4])
        for b in re.split(r"\n(?=(?:Sáng|Chiều|Tối)\s+(?:T[2-8]|CN))", sched):
            lines = [x.strip() for x in b.split("\n") if x.strip()]
            m1 = re.match(r"(?:Sáng|Chiều|Tối)\s+(T[2-8]|CN),\s*Tuần:\s*([\d,\-\s]+)", lines[0]) if lines else None
            tm = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", b)
            if not m1 or not tm: probs.append(f"{code} ({typ}): không đọc được lịch “{lines[0][:40] if lines else ''}”"); continue
            room = next((x for x in lines[1:] if not re.search(r"\d{1,2}:\d{2}|^Kỳ\b", x)), "")
            thu = "cn" if m1.group(1) == "CN" else m1.group(1)[1:]
            lop.append({"mon": code, "loai": KIND.get(typ, typ), "thu": thu, "bat_dau": tm.group(1), "ket_thuc": tm.group(2),
                        "phong": room, "hinh_thuc": "Online" if room.lower() == "online" else "Offline",
                        "tuan": weeks(m1.group(2)), "ghi_chu": f"Mã lớp {cls} (qldt)"})
    return lop, vang, probs

def parse_grouped(t, header_fn):
    """Bảng có dòng tiêu đề nhóm (1 ô) -> [(nhóm, hàng)]"""
    out, grp = [], None
    for r in t.get("rows", []):
        if len(r) == 1: grp = header_fn(r[0]); continue
        out.append((grp, [_clean(x) for x in r]))
    return out


# ------------------------------------------------------------------ áp
def apply(post, snap):
    nt = Notion(post)
    changes, review = [], []
    courses = {c["code"]: c for c in nt.courses()}
    raw = {p["id"]: p for p in nt.query(COURSES)}
    def cprop(c, name): return P(raw.get(c["id"], {}), name) if raw.get(c["id"]) else None
    patches = {}
    def patch(c, key, val, note):
        patches.setdefault(c["id"], {})[key] = val
        changes.append(note)

    # 1) TKB + vắng
    t = snap.get("tkb") or {}
    if t.get("rows"):
        lop, vang, probs = parse_tkb(t)
        review += probs
        sem = sem_of_code(t.get("sem") or "")
        if lop and sem:
            import tkb
            w1 = tkb.week1(dt.date(int(t["sem"][:4]), 10, 1))
            ws = [w for l in lop for w in l["tuan"]]
            start, end = w1 + dt.timedelta(days=(min(ws) - 1) * 7), w1 + dt.timedelta(days=max(ws) * 7 - 1)
            r = tkb.run(post, {"buoc": "ghi", "bat_dau": start.isoformat(), "ket_thuc": end.isoformat(), "ky": sem,
                               "ma_ky": t["sem"], "lop": lop, "nghi": []})
            if not r.get("ok"):
                review.append("TKB chưa ghi được: " + "; ".join(r.get("thieu") or [r.get("loi") or "?"]))
            else:
                n_new = int(re.match(r"(\d+)", r["da_ghi"][0]).group(1)); n_old = int(re.match(r"(\d+)", r["da_ghi"][1]).group(1))
                if n_new or n_old: changes.append(f"TKB {t['sem']}: thêm {n_new} buổi, bỏ {n_old} buổi cũ (thùng rác Notion)")
                courses = {c["code"]: c for c in Notion(post).courses()}   # tkb.run có thể đổi Status/Semester
        for code, n in vang.items():
            c = courses.get(code)
            if c and cprop(c, "Vắng (trường)") != n:
                patch(c, "Vắng (trường)", {"number": n}, f"{code}: vắng theo trường {cprop(c, 'Vắng (trường)') or 0} → {n}")

    # 2) bảng điểm chi tiết
    for grp, r in parse_grouped(snap.get("transcript") or {}, sem_of_header):
        if len(r) < 4 or not re.match(r"[A-Z]{2,4}\d", r[1]): continue
        c = courses.get(r[1])
        if not c: review.append(f"Bảng điểm có {r[1]} {r[2]} ({grp}) nhưng Notion chưa có môn này"); continue
        comp = " · ".join(x for x in r[4:] if x)
        if comp != (cprop(c, "Điểm thành phần (trường)") or ""):
            patch(c, "Điểm thành phần (trường)", rt(comp) if comp else {"rich_text": []}, f"{r[1]}: điểm thành phần “{comp or 'trống'}”")

    # 3) chương trình đào tạo
    prog = {}
    for grp, r in parse_grouped(snap.get("program") or {}, sem_of_header):
        if len(r) < 10 or not re.match(r"[A-Z]{2,4}\d", r[1]): continue
        p = prog.setdefault(r[1], {"sem": grp, "name": r[2], "groups": [], "tc": r[4], "req": r[6] == "X", "grade": r[8], "res": r[9]})
        if r[3] not in p["groups"]: p["groups"].append(r[3])
    for code, p in prog.items():
        c = courses.get(code)
        if not c:   # Notion THIẾU môn của khung trường → tạo (bắt buộc: đặt kỳ theo khung; tự chọn: để bạn chọn kỳ, ghi kỳ gợi ý)
            tc0 = float(p["tc"]) if re.match(r"^\d+(\.\d+)?$", p["tc"] or "") else 0
            props = {"Name": title(p["name"]), "Code": rt(code), "Credits": {"number": tc0}, "Status": {"status": {"name": "Planned"}},
                     "Result": {"select": {"name": "Unknown"}}, "Category": {"select": {"name": _category(p["groups"])}},
                     "Nhóm HP (trường)": rt(" · ".join(p["groups"])),
                     "Course Notes": rt(f"Tạo theo khung CTĐT trên qldt ({dt.datetime.now(TZ):%d/%m/%Y})" + ("" if p["req"] else ", môn tự chọn") + ".")}
            if p["req"] and p["sem"]: props["Semester"] = {"select": {"name": p["sem"]}}
            elif p["sem"]: props["Kỳ gợi ý"] = rt(p["sem"][1:])
            if not p["req"] and any("thể chất" in g.lower() for g in p["groups"]): props["Nhóm tự chọn"] = {"select": {"name": "GDTC"}}
            nt.create(COURSES, props)
            changes.append(f"Thêm {code} {p['name']} ({p['sem'] if p['req'] else 'tự chọn, gợi ý ' + str(p['sem'])}, {tc0:g} TC) theo khung CTĐT")
            continue
        tc = float(p["tc"]) if re.match(r"^\d+(\.\d+)?$", p["tc"] or "") else 0
        if float(c["credits"] or 0) != tc:
            patch(c, "Credits", {"number": tc}, f"{code}: số tín {c['credits']} → {tc:g} (theo CTĐT)")
        groups = " · ".join(p["groups"])
        if groups != (cprop(c, "Nhóm HP (trường)") or ""):
            patch(c, "Nhóm HP (trường)", rt(groups), f"{code}: nhóm HP “{groups[:60]}”")
        m = re.search(r"\b([ABCD]\+?|F)\b", p["grade"] or "")
        if m and not c.get("improve"):
            g4, res = G4[m.group(1)], ("Fail" if m.group(1) == "F" else "Pass")
            if (c["gpa4"], c["result"]) != (g4, res):
                patch(c, "Current GPA 4", {"number": g4}, f"{code}: điểm HP {m.group(1)} ({g4:g}) — {res}")
                patches[c["id"]]["Result"] = {"select": {"name": res}}
        # kỳ dự kiến của môn bắt buộc CHƯA học: theo khung trường (môn đang/đã học thì TKB + bảng điểm quyết, ở bước 1–2)
        if p["req"] and c["status"] == "Planned" and c["result"] not in ("Miễn (R)",) and not c.get("retake") and not c.get("improve") \
                and c["semester"] and p["sem"] and c["semester"] != p["sem"]:
            patch(c, "Semester", {"select": {"name": p["sem"]}}, f"{code}: kỳ dự kiến {c['semester']} → {p['sem']} (theo khung CTĐT)")
    # Notion THỪA (môn trường không liệt kê, vd môn Module chưa hiện hết trên trang) → giữ nguyên, không báo (luật 2026-10-04)

    # 4) tổng hợp theo kỳ + ĐRL
    trk = {"S" + (P(r, "Semester") or "").split()[-1]: r for r in nt.query(TRACKER)}
    s_rows = (snap.get("summary") or {}).get("rows", [])
    heads = (snap.get("summary") or {}).get("heads", [])
    col = {h: i for i, h in enumerate(heads)}
    cond = {P(r, "Semester"): r for r in nt.query(CONDUCT)}
    for r in s_rows:
        if len(r) < len(heads) or "Học kỳ" not in col: continue
        s = sem_of_code(r[col["Học kỳ"]]); row = trk.get(s)
        if not s or not row: continue
        def num(h):
            v = _clean(r[col[h]]) if h in col else ""
            try: return float(v.replace(",", "."))
            except ValueError: return None
        want = {"GPA (trường)": num("GPA"), "CPA (trường)": num("CPA"), "TC tích luỹ (trường)": num("TC tích lũy"),
                "TC nợ (trường)": num("TC nợ trong kỳ")}
        props = {k: {"number": v} for k, v in want.items() if v is not None and P(row, k) != v}
        warn = _clean(r[col["Cảnh báo"]]) if "Cảnh báo" in col else ""
        if warn and warn != (P(row, "Cảnh báo (trường)") or ""): props["Cảnh báo (trường)"] = rt(warn)
        if props:
            nt.patch(row["id"], props); changes.append(f"{s}: " + ", ".join(f"{k} {v.get('number', warn)}" for k, v in props.items()))
        drl = num("Điểm rèn luyện")
        if drl is not None:
            cr = cond.get(s)
            if not cr: nt.create(CONDUCT, {"Kỳ": title(f"Kỳ {s}"), "Semester": {"select": {"name": s}}, "Điểm": {"number": drl}}); changes.append(f"{s}: điểm rèn luyện {drl:g}")
            elif P(cr, "Điểm") != drl: nt.patch(cr["id"], {"Điểm": {"number": drl}}); changes.append(f"{s}: điểm rèn luyện {P(cr, 'Điểm')} → {drl:g}")
    d = snap.get("drl") or {}
    cur = sem_of_code((snap.get("tkb") or {}).get("sem") or "")
    if d.get("sv") is not None and cur in trk:
        txt = f"SV tự chấm {d['sv']} · GV {d['gv'] if d.get('gv') not in (None, '', '0') else 'chưa chấm'}"
        if txt != (P(trk[cur], "ĐRL đang chấm (trường)") or ""):
            nt.patch(trk[cur]["id"], {"ĐRL đang chấm (trường)": rt(txt)}); changes.append(f"{cur}: rèn luyện đang chấm — {txt}")

    if snap.get("drl_error"): review.append("iCTSV (điểm rèn luyện) chưa đọc được lần này: " + snap["drl_error"][:150])
    for cid, props in patches.items(): nt.patch(cid, props)
    return changes, review


def _log(post, status, changes, review):
    now = dt.datetime.now(TZ)
    body = "\n".join("• " + x for x in changes)[:1900]
    Notion(post).create(LOG_DB, {"Lần": title(f"Đồng bộ {now:%d/%m %H:%M}"), "Lúc": {"date": {"start": now.isoformat(timespec="minutes")}},
                                 "Trạng thái": {"select": {"name": status}}, "Số thay đổi": {"number": len(changes)},
                                 "Thay đổi": rt(body) if body else {"rich_text": []},
                                 "Cần bạn xem": rt("\n".join("• " + x for x in review)[:1900]) if review else {"rich_text": []}})


def state():
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception: return {}


def run(post, fetch=True):
    """Đọc trường (school_fetch.py, tiến trình riêng) rồi áp vào Notion. -> state dict (cũng lưu school/state.json)."""
    prev = state()
    st = {"at": dt.datetime.now(TZ).isoformat(timespec="minutes")}
    if fetch:
        try:
            import os   # ống dẫn của tiến trình con mặc định cp1252 -> in tiếng Việt là chết (lỗi 12:30 4/10)
            p = subprocess.run([sys.executable, str(HERE / "school_fetch.py")], cwd=str(HERE), capture_output=True, timeout=420,
                               creationflags=0x08000000, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})   # CREATE_NO_WINDOW
            if p.returncode: st["fetch_error"] = (p.stderr or b"").decode("utf-8", "ignore")[-300:]
        except subprocess.TimeoutExpired:
            st["fetch_error"] = "Đọc trường quá 7 phút"
    try: snap = json.loads(SNAP.read_text(encoding="utf-8"))
    except Exception: snap = {"ok": False, "error": "Chưa có dữ liệu đọc từ trường"}
    try:   # (5/10) trạng thái của LẦN ĐỌC GẦN NHẤT (latest.json giữ lần thành công cuối)
        last = json.loads((HERE / "school" / "fetch_last.json").read_text(encoding="utf-8"))
        if not last.get("ok"): snap = {**snap, "ok": False, "error": last.get("error"), "need_login": last.get("need_login")}
    except Exception: pass
    if not snap.get("ok") or st.get("fetch_error"):
        st.update(status="Cần đăng nhập" if snap.get("need_login") else "Lỗi", error=snap.get("error") or st.get("fetch_error"),
                  last_ok=prev.get("last_ok"), changes=[], review=prev.get("review", []))
        if prev.get("status") != st["status"] or prev.get("error") != st["error"]:   # chỉ ghi nhật ký khi trạng thái đổi
            try: _log(post, st["status"], [], [st["error"] or ""])
            except Exception: pass
    else:
        try:
            changes, review = apply(post, snap)
            st.update(status="Đã đồng bộ" if changes else "Không đổi", last_ok=st["at"], changes=changes, review=review,
                      snap_at=snap.get("at"))
            if changes or review != prev.get("review"): _log(post, st["status"], changes, review)
        except Exception as e:
            st.update(status="Lỗi", error=f"{type(e).__name__}: {e}"[:300], last_ok=prev.get("last_ok"), changes=[], review=prev.get("review", []))
            try: _log(post, "Lỗi", [], [st["error"]])
            except Exception: pass
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return st


def dry(post):
    """Xem trước: chỉ phân tích latest.json, KHÔNG ghi gì."""
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    lop, vang, probs = parse_tkb(snap.get("tkb") or {})
    return {"lop": len(lop), "vang": vang, "probs": probs, "mau": lop[:4]}


if __name__ == "__main__":
    import copilot_app
    if "--dry" in sys.argv: print(json.dumps(dry(copilot_app._npost), ensure_ascii=False, indent=1))
    else: print(json.dumps(run(copilot_app._npost, fetch="--no-fetch" not in sys.argv), ensure_ascii=False, indent=1))
