# -*- coding: utf-8 -*-
"""Sơ đồ khối n8n · University Copilot (Claude 2026-10-03).

Vẽ từ KIỂM KÊ TRỰC TIẾP (không vẽ theo trí nhớ):
  • n8n API: mọi workflow, node, trigger (cron / webhook / chat / form), URL gọi ra ngoài
  • Notion API (qua credential n8n, notion_ops.py): toàn bộ database
  • Ma trận đọc/ghi: suy từ node (truy vấn = đọc, tạo/sửa trang = ghi) + bổ sung tay những chỗ ID nằm trong biểu thức
    (công cụ Copilot, module Python ghi qua cổng /copilot-notion)
Chạy lại:  python docs\\gen_n8n_map.py   ->  docs\\Map-n8n.svg
"""
import json, re, sys, os, collections, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from n8napi import api
from notion_ops import NotionOps

OUT = os.path.join(HERE, "Map-n8n.svg")
UNIFIED, LEC_A, LEC_C = "AhMtmx7g4dpZgB5r", "EtG8zlgeGNCZnak8", "df0t4jhikLNbS5HB"

# ------------------------------------------------------------------ kiểm kê
def inventory():
    ws, cur = [], None
    while True:
        r = api("GET", "/workflows?limit=100" + (f"&cursor={cur}" if cur else ""))
        ws += r["data"]; cur = r.get("nextCursor")
        if not cur: break
    full = {w["id"]: api("GET", f"/workflows/{w['id']}") for w in ws}
    with NotionOps() as n:
        dbs = n.run([{"method": "POST", "url": "https://api.notion.com/v1/search",
                      "body": {"filter": {"property": "object", "value": "database"}, "page_size": 100}}])[0]["body"]["results"]
        names = {d["id"].replace("-", ""): "".join(a.get("plain_text", "") for a in d.get("title", [])) for d in dbs}
        counts = {}
        for d in dbs:
            r = n.run([{"method": "POST", "url": f"https://api.notion.com/v1/databases/{d['id']}/query", "body": {"page_size": 100}}])[0]["body"]
            counts[d["id"].replace("-", "")] = (len(r.get("results", [])), bool(r.get("has_more")))
    return full, names, counts

UUID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")

def section_of(name):
    m = re.match(r"^([A-Z]+\d+|[A-Za-zÀ-ỹ ]+?) ·", name)
    return m.group(1).strip() if m else name.split(" ")[0]

def analyse(w, names, per_section=True):
    secs = collections.OrderedDict()
    for nd in w["nodes"]:
        if nd["type"].endswith("stickyNote"): continue
        s = section_of(nd["name"]) if per_section else w["name"].split("— ")[-1]
        S = secs.setdefault(s, {"nodes": 0, "trig": [], "R": set(), "W": set()})
        S["nodes"] += 1
        p = nd.get("parameters", {}); blob = json.dumps(p, ensure_ascii=False)
        if "scheduleTrigger" in nd["type"]:
            iv = ((p.get("rule") or {}).get("interval") or [{}])[0]
            S["trig"].append(("cron", iv.get("expression") or (f"mỗi {iv.get('minutesInterval')} phút" if iv.get("minutesInterval") else
                                                                f"{iv.get('triggerAtHour', 0):02d}:{iv.get('triggerAtMinute', 0):02d} hằng ngày")))
        elif nd["type"].endswith("webhook"): S["trig"].append(("hook", "/" + str(p.get("path"))))
        elif "chatTrigger" in nd["type"]: S["trig"].append(("chat", "chat"))
        elif "formTrigger" in nd["type"]: S["trig"].append(("form", "form"))
        url = str(p.get("url", ""))
        for u in set(UUID.findall(blob)):
            k = u.replace("-", "")
            if k not in names: continue
            if "/query" in url and k in url.replace("-", ""): S["R"].add(k)
            elif "/query" in url: S["R"].add(k)
            else: S["W"].add(k)
    return secs

# ------------------------------------------------------------------ ngữ nghĩa (bổ sung tay, có giải thích)
DESC = {
    "Chat": "Cửa chat (n8n hosted + tab Trò chuyện UC qua /copilot-api). Nạp ngữ cảnh hôm nay rồi giao cho Não.",
    "Não": "Gemini 3.5 Flash (LangChain, gọi thẳng Google — không qua cổng). Dự phòng: LM Studio qwen3-8b.",
    "Bản tin": "07:20 / 21:30: chụp dữ liệu → kiểm tra học tập (checks.py) → LM Studio viết → 🗞️ Bản tin. Quá hạn = deadline THẬT của bài; việc nhỏ trượt = dời lại. Tối CN kèm kết luận tuần.",
    "Đánh giá tuần": "CN 21:00: weekly.py nhìn cả tuần (giờ làm theo ngày, ngày dồn, giờ cần tuần sau, deadline thật) → Ổn / Cần tăng tốc / Không ổn + gợi ý ngày camp → 📅 Weekly Reviews.",
    "Gợi ý": "Tab Gợi ý: việc gấp, quá hạn, sắp tới, chờ quyết + tài liệu gợi ý hôm nay.",
    "Nhập file": "Nạp file (tab Inbox UC + đồng bộ Uni-Documents): → Drive (Course Materials Backup) → 📥 University Inbox. Web app bơm A2 tuần tự.",
    "N9": "Mỗi phút: phiên 🏛️ Council có tick Convene → relay :8310 → 4 ghế AgentChattr; nhận biên bản về.",
    "C9": "Copilot mở / chốt phiên hội đồng (/council-convene, /council-finalize).",
    "Bài giảng": "Tab Ghi bài giảng: danh sách phiên + phân tích lại.",
    "Lịch": "Tab Lịch (cũ). Nay web app đọc thẳng qua cổng Notion và đệm (timetable.py).",
    "Học kỳ": "Tab Học kỳ (cũ). Nay web app dùng program.py qua cổng Notion.",
    "Cổng Notion": "Cổng cho web app: chỉ bảng trong danh sách cho phép, KHÔNG xoá. Mọi module Python đi qua đây.",
    "Thùng rác TKB": "Chỉ bỏ vào thùng rác trang Academic Timetable có Kind=Class (nạp TKB).",
    "Trang điện thoại": "Cổng hẹp (04/10): thay TOÀN BỘ nội dung ĐÚNG MỘT trang — 📱 University Copilot (điện thoại), cấp cao nhất. Không nhận id trang khác.",
    "Nghiên cứu": "15 phút + chạy ngay: research.py tìm SearXNG → Gemini Flash-Lite chọn → Results + Inbox.",
    "Chuyển kỳ": "00:15: semester.py — đổi kỳ theo ⚙️ Mốc năm học, chốt môn, học lại, Tết, hè, tín chỉ, hạn chứng chỉ.",
    "A1": "Intake: ➕ Academic Intake → Gemini đọc → Academic Work + sự kiện Lịch + task gốc (Codex).",
    "A2": "University Inbox: khớp môn → 📚 Course Materials (Codex). Giành quyền dòng (khoá + mã lượt chạy) nên không tạo trùng.",
    "A3": "Coursework Breakdown: Academic Work → Academic Tasks theo giờ ước lượng, Gemini (Codex).",
    "A4": "Daily Planning 07:00 + 30 phút: gợi ý 📅 Daily Task theo 🌗 chế độ ngày (đồng bộ qua 🎛️ Control): ⛺ Camp = trần giờ camp, 💤 Rest = không xếp việc mới (Codex + Claude).",
    "S5": "Progress Recorder: snapshot tiến độ (Codex). Không còn cảnh báo lệch ước lượng từng task — gộp vào 📅 Weekly Reviews.",
    "S6": "Material Recommendations 07:10: đánh dấu Suggested Today + lý do trong Course Materials (Codex).",
    "H10": "Health Ping 6 giờ: thử Notion + Gemini, ghi kết quả vào 🎛️ University Control (Freebuff).",
    "R10": "Reconciliation 6 giờ: Academic Work thiếu liên kết → Exception Queue (Freebuff).",
    "QU": "Form Quick Upload: link/file → 📥 University Inbox + 🧾 Automation Log (Freebuff).",
    "Lecture Capture": "Nhận file ghi âm từ companion :5681 → Google Drive.",
    "Lecture Analysis": "5 phút + /lecture-transcript-ready: speech gate (NPU) → văn bản gọn → Gemini → 📚 Lecture Notes + Inbox.",
}
SHORT = {"Bản tin": "bản tin sáng / tối", "N9": "hội đồng: xem phiên Convene", "Nghiên cứu": "tìm tài liệu ngoài",
         "Chuyển kỳ": "đổi kỳ, chốt môn, hạn chứng chỉ", "A1": "Intake → việc + lịch", "A2": "Inbox → kho tài liệu",
         "A3": "chia việc thành task", "A4": "lập kế hoạch ngày / theo dõi tải", "S5": "ghi tiến độ", "S6": "gợi ý tài liệu",
         "H10": "kiểm tra sức khoẻ", "Đánh giá tuần": "Weekly Reviews (CN)", "R10": "đối soát liên kết", "Lecture Analysis": "phân tích bài giảng"}
TOOLS = [  # công cụ của Não Copilot -> đích
    ("them_vao_he_thong", "W ➕ Academic Intake"), ("cap_nhat_viec_hom_nay", "W 📅 Daily Task"), ("cap_nhat_task_goc", "W Academic Tasks"),
    ("dong_ngoai_le", "W ⚠️ Exception Queue"), ("tim_tai_lieu", "R 📚 Course Materials"), ("ghi_hoc_tap", "→ web app academic.py"),
    ("nghien_cuu", "→ web app research.py"), ("doc_ket_qua_nghien_cuu", "R 🌐 Research Results"), ("nhap_tkb", "→ web app tkb.py"),
    ("gui_notebooklm", "W 🧠 NotebookLM Inbox"), ("chay_ngay", "→ webhook /copilot-run-*"), ("hoi_hoi_dong", "→ relay :8310"),
    ("doc_bien_ban_hoi_dong", "→ relay :8310"), ("chot_hoi_dong", "→ /council-finalize"),
]
PY = [  # module Python trong web app :8320 -> bảng (qua cổng /copilot-notion)
    ("academic.py", "ghi_hoc_tap: luật môn, điểm, vắng, rèn luyện, kết quả, lịch thi, ôn thi",
     {"Courses": "RW", "📊 Grades & Transcript": "RW", "🧑‍🏫 Attendance": "RW", "Điểm rèn luyện": "RW", "Semester State": "R",
      "Academic Work": "W", "🗓️ Academic Timetable Events": "W", "📝 Exam Revision": "RW", "Lần học": "RW"}),
    ("semester.py", "chuyển kỳ 00:15", {"Semester State": "RW", "Courses": "RW", "Semester Credit Tracker": "RW", "Academic Tasks": "W", "Lần học": "W",
                                         "⚠️ Exception Queue": "RW", "☀️ Summer Planning": "RW", "⚙️ Mốc năm học": "R"}),
    ("tkb.py", "nạp TKB cả kỳ", {"🗓️ Academic Timetable Events": "RW", "Courses": "RW"}),
    ("research.py", "Research Hub", {"🔍 Research Requests": "RW", "🌐 Research Results": "W", "📥 University Inbox": "W", "Courses": "R"}),
    ("checks.py", "kiểm tra cho bản tin", {"Courses": "R", "📊 Grades & Transcript": "R", "🧑‍🏫 Attendance": "R", "Academic Work": "R",
                                            "📝 Exam Revision": "R", "Semester State": "R"}),
    ("program.py", "tab Học kỳ / GDTC · Kỳ hè · Học lại · Cải thiện / ĐK tốt nghiệp + hạng", {"Courses": "RW", "📊 Grades & Transcript": "R", "🧑‍🏫 Attendance": "R",
                                                        "Semester Credit Tracker": "R", "Điểm rèn luyện": "R", "Semester State": "R", "🎓 Xét tốt nghiệp": "RW",
                                                        "Lần học": "RW", "☀️ Summer Planning": "RW", "⚠️ Exception Queue": "RW"}),
    ("school_sync.py", "🏫 qldt + iCTSV → Notion · 06:30 12:30 18:30 22:30 · dữ liệu trường cao nhất",
     {"🗓️ Academic Timetable Events": "RW", "Courses": "RW", "Semester Credit Tracker": "RW", "Điểm rèn luyện": "RW", "Đồng bộ trường": "W"}),
    ("certs.py", "tab Ngoại ngữ", {"📚 Danh mục chứng chỉ ngoại ngữ (ĐHBK công nhận)": "R", "📏 Quy định miễn học phần ngoại ngữ (K70)": "R",
                                   "🎫 Chứng chỉ ngoại ngữ của tôi": "RW"}),
    ("timetable.py", "tab Lịch (đệm)", {"🗓️ Academic Timetable Events": "R"}),
    ("uni-sync (copilot_app)", "thả file vào Uni-Documents → Drive + Inbox; chống trùng SHA-256, phiên bản (AI phân xử)", {"💾 Backup & Drive Sync": "RW", "📥 University Inbox": "R", "📚 Course Materials": "R"}),
    ("daymode.py", "tab Hôm nay + 🌗 chế độ ngày → 🎛️ Control (A4)", {"🌗 Chế độ ngày": "RW", "🎛️ University Control": "RW", "📅 Daily Task": "RW"}),
    ("mail_events.py", "📡 thư + Teams → sự kiện nhiều chặng · Trước → Nay · đổi phòng / giờ trên Teams → sửa buổi Class",
     {"Sự kiện theo dõi": "RW", "🗓️ Academic Timetable Events": "RW", "Courses": "R"}),
    ("deadlines.py", "hạn 3 mức (agent xếp) · bài tập Teams → Academic Work · tranh chấp → theo trường",
     {"Academic Work": "RW", "🗓️ Academic Timetable Events": "W", "Academic Tasks": "RW", "Courses": "R", "Đồng bộ trường": "W"}),
    ("mooc.py", "🎓 MOOC SoICT soict.daotao.ai: hạn + điểm bài → Academic Work theo luật tối cao (thêm / sửa / có điểm = Hoàn tất / bỏ lỡ = báo)",
     {"Academic Work": "RW", "🗓️ Academic Timetable Events": "W", "Academic Tasks": "RW", "Courses": "R", "Đồng bộ trường": "W"}),
    ("fami.py", "📐 FAMI số hoá (fami.hust.edu.vn/sohoa): thi theo chương học phần MI → Academic Work (bài đang mở / mở trong 7 ngày) theo luật tối cao",
     {"Academic Work": "RW", "Courses": "R", "🗓️ Academic Timetable Events": "W", "Academic Tasks": "RW", "Đồng bộ trường": "W"}),
    ("expired.py", "việc của trường đã hết hạn (Teams + MOOC) → ✅ Academic Tasks: Done + Kết quả hạn (Đã làm / Bỏ lỡ / Không rõ) — không ghi thành hạn",
     {"Academic Tasks": "RW", "Courses": "R"}),
    ("extracurricular.py", "🎯 CTSV (đăng ký, minh chứng, đang mở, học bổng) + mail / Teams → ngoại khoá", {"🎯 Hoạt động ngoại khoá": "RW"}),
    ("dupscan.py", "quét trùng hạn / lịch (khác môn = không trùng) · bỏ bản trùng → thùng rác sau Xác nhận",
     {"Academic Work": "R", "🗓️ Academic Timetable Events": "R", "Academic Tasks": "R", "📅 Daily Task": "R", "Courses": "R"}),
    ("teams_files.py", "Teams ⇄ Uni-Documents ⇄ 📥 Notion · chống trùng SHA · bản Teams thắng khi tranh chấp", {"📥 University Inbox": "R"}),
    ("phone_page.py", "📱 trang điện thoại (gửi /copilot-phone-page) · alerts / phone_sched / phone_link: ntfy", {"Academic Work": "R", "🎯 Hoạt động ngoại khoá": "R", "Sự kiện theo dõi": "R"}),
    ("weekly.py", "📅 Weekly Reviews — đánh giá theo tuần", {"📅 Daily Task": "R", "Academic Tasks": "R", "Academic Work": "R", "🎛️ University Control": "R", "🌗 Chế độ ngày": "R",
                                                            "🧑\u200d🏫 Attendance": "R", "📊 Grades & Transcript": "R", "📅 Weekly Reviews": "RW"}),
]
FIX = {  # ID nằm trong biểu thức nên máy không thấy — sửa tay
    "S6": {"📚 Course Materials": "RW", "📅 Daily Task": "R"},
    "Chat": {"Academic Tasks": "R", "Courses": "R", "⚠️ Exception Queue": "R", "📅 Daily Task": "R", "🗓️ Academic Timetable Events": "R",
             "➕ Academic Intake": "W", "📚 Course Materials": "R", "🌐 Research Results": "R", "🧠 NotebookLM Inbox": "W"},
    "C9": {"🏛️ Council Sessions": "RW"}, "N9": {"🏛️ Council Sessions": "RW"},
    "H10": {"🎛️ University Control": "RW"}, "A4": {"🎛️ University Control": "R", "📅 Daily Task": "RW", "Academic Tasks": "R"},
    "Lecture Capture": {"🎙️ Lecture Sessions": "RW"}, "Lecture Analysis": {"🎙️ Lecture Sessions": "RW", "📚 Lecture Notes": "W",
                                                                          "📥 University Inbox": "W", "🗓️ Academic Timetable Events": "R"},
}
GROUPS = [
    ("Nhập & việc học", ["➕ Academic Intake", "Academic Work", "Academic Tasks", "📅 Daily Task", "🌗 Chế độ ngày", "🗓️ Academic Timetable Events",
                         "📝 Exam Revision", "📈 Progress & Estimate History"]),
    ("Chương trình & học kỳ", ["Courses", "Semester State", "⚙️ Mốc năm học", "Semester Credit Tracker", "📊 Grades & Transcript",
                               "🧑‍🏫 Attendance", "Điểm rèn luyện", "☀️ Summer Planning", "📅 Weekly Reviews", "Lần học"]),
    ("Ngoại ngữ & tốt nghiệp", ["🎫 Chứng chỉ ngoại ngữ của tôi", "📚 Danh mục chứng chỉ ngoại ngữ (ĐHBK công nhận)",
                                "📏 Quy định miễn học phần ngoại ngữ (K70)", "🎓 Xét tốt nghiệp"]),
    ("Tài liệu & tìm kiếm", ["📥 University Inbox", "📚 Course Materials", "🔍 Research Requests", "🌐 Research Results", "🧠 NotebookLM Inbox",
                             "💾 Backup & Drive Sync"]),
    ("Bài giảng", ["🎙️ Lecture Sessions", "📚 Lecture Notes"]),
    ("Theo dõi · ngoại khoá (04/10)", ["Sự kiện theo dõi", "🎯 Hoạt động ngoại khoá"]),
    ("Điều phối & giám sát", ["⚠️ Exception Queue", "🎛️ University Control", "🧾 Automation Log", "🗞️ Bản tin Copilot",
                              "🏛️ Council Sessions", "Đồng bộ trường"]),
]
ORPHAN_NOTE = {
    "Lecture Recorder Control": "bảng cũ — companion v2 thay thế",
    "🤖 Agent Suggestions": "chạy thử đã vô hiệu theo ý bạn",
}
OFF_WHY = {
    "jJEKXFiaNFd5658j": "→ gộp thành A1", "nnIyFww4eY5qdSgM": "→ gộp thành A2", "WyAsZmZOXqR8yibs": "→ gộp thành A3",
    "VsytHV7Cuy21P66F": "→ gộp thành A4", "i1DOTALMrMxYwJOI": "→ gộp thành S5", "7fD3LcYmOr3KMDvx": "→ gộp thành S6",
    "phaseICouncilBridge": "→ gộp thành C9", "phaseHHealthPing1": "→ gộp thành H10", "phaseHRecon00001": "→ gộp thành R10",
    "phaseB0000000001": "→ gộp thành QU", "phaseJConductor001": "thay bằng lịch trong workflow hợp nhất",
    "FEsOtrkuJMkhHXem": "thay bằng companion v2 + tab Ghi bài giảng", "proxyBridge0000001": "thay bằng Cổng Notion",
    "cbTbVGMIeTFytToa": "lưu trữ", "klp1BO7fDUx6cXox": "lưu trữ",
    "phaseEConverter01": "⚠ CHƯA GỘP — đề xuất đã duyệt không được chuyển",
}

# ------------------------------------------------------------------ vẽ
INK, INK2, INK3, PAPER, LINE = "#14263A", "#4B5D70", "#8796A8", "#F7F5EF", "#C9D2DC"
BLUE, GREEN, RED, AMBER, TEAL, VIOLET = "#2D55C8", "#2F7D4F", "#B3122E", "#A86400", "#0E7C86", "#6B4FB8"
FONT = "'Segoe UI', 'Segoe UI Emoji', sans-serif"
HEAD = "Bahnschrift, 'Segoe UI', sans-serif"
out = []
def add(s): out.append(s)
def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def text(x, y, s, size=15, fill=INK, weight=400, font=FONT, anchor="start"):
    add(f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(s)}</text>')
def rect(x, y, w, h, fill="#fff", stroke=INK, sw=1.5, r=6, dash=None):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
def wrap(s, width, size):
    per = max(8, int(width / (size * 0.53)))
    words, lines, cur = str(s).split(), [], ""
    for w_ in words:
        if len(cur) + len(w_) + 1 > per and cur: lines.append(cur); cur = w_
        else: cur = (cur + " " + w_).strip()
    if cur: lines.append(cur)
    return lines
def para(x, y, s, width, size=14, fill=INK2, lh=1.35, weight=400):
    for i, ln in enumerate(wrap(s, width, size)):
        text(x, y + i * size * lh, ln, size, fill, weight)
    return y + len(wrap(s, width, size)) * size * lh
def card(x, y, w, title, sub, body, color=INK, nodes=None, trig=None, fill="#fff", dash=None):
    lines_sub = wrap(sub, w - 24, 12.5) if sub else []
    lines_body = wrap(body, w - 24, 13.5) if body else []
    h = 34 + len(lines_sub) * 17 + len(lines_body) * 18.5 + (22 if trig else 0) + 10
    rect(x, y, w, h, fill, color, 1.6, 7, dash)
    add(f'<rect x="{x}" y="{y}" width="6" height="{h}" rx="3" fill="{color}"/>')
    text(x + 16, y + 23, title, 16, color, 700, HEAD)
    if nodes: text(x + w - 12, y + 23, f"{nodes} node", 12.5, INK3, 600, FONT, "end")
    yy = y + 42
    for ln in lines_sub: text(x + 16, yy, ln, 12.5, INK3); yy += 17
    for ln in lines_body: text(x + 16, yy, ln, 13.5, INK2); yy += 18.5
    if trig: text(x + 16, yy + 2, trig, 12.5, BLUE, 600); yy += 22
    return y + h

def trig_label(ts):
    out_ = []
    for k, v in ts:
        out_.append({"cron": "⏱ ", "hook": "🌐 ", "chat": "💬 ", "form": "📝 "}[k] + v)
    return " · ".join(dict.fromkeys(out_))

def cron_vi(e):
    m = {"0 0/15 * * * *": ":00/:15/:30/:45", "0 5/15 * * * *": ":05/:20/:35/:50", "0 10/15 * * * *": ":10/:25/:40/:55",
         "0 7/15 * * * *": ":07/:22/:37/:52", "0 20/30 * * * *": ":20/:50", "0 */30 7-22 * * *": "30 phút (7–22h)",
         "0 15 0 * * *": "00:15", "0 20 7 * * *": "07:20", "0 30 21 * * *": "21:30", "0 0 */6 * * *": "0/6/12/18h", "0 30 */6 * * *": "0:30/6:30/12:30/18:30", "0 0 21 * * 0": "CN 21:00 hằng tuần"}
    return m.get(e, e)

def main():
    full, names, counts = inventory()
    n2id = {v: k for k, v in names.items()}
    uni = analyse(full[UNIFIED], names)
    la = analyse(full[LEC_A], names, False); lc = analyse(full[LEC_C], names, False)
    active = [w for w in full.values() if w.get("active")]
    total_nodes = sum(len([n for n in w["nodes"] if not n["type"].endswith("stickyNote")]) for w in active)
    W, Hh = 6000, 4300
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" width="{W}" height="{Hh}">')
    add(f'<rect width="{W}" height="{Hh}" fill="{PAPER}"/>')
    for gx in range(0, W, 100): add(f'<path d="M{gx} 0V{Hh}" stroke="#EAE6DC" stroke-width="1"/>')
    for gy in range(0, Hh, 100): add(f'<path d="M0 {gy}H{W}" stroke="#EAE6DC" stroke-width="1"/>')
    rect(30, 30, W - 60, Hh - 60, "none", INK, 3, 0)
    # tiêu đề
    text(70, 108, "SƠ ĐỒ KHỐI n8n · UNIVERSITY COPILOT", 46, INK, 800, HEAD)
    today = dt.date.today().strftime("%d/%m/%Y")
    text(70, 150, f"Kiểm kê trực tiếp từ n8n API và Notion API ngày {today}: {len(full)} workflow ({len(active)} đang chạy, {len(full) - len(active)} đã lưu trữ) · "
                  f"{total_nodes} node đang chạy · {len(names)} bảng Notion. Sinh bởi docs/gen_n8n_map.py — chạy lại để vẽ lại.", 19, INK2)
    # chú giải
    lx = 4300
    for i, (c, lab) in enumerate(((BLUE, "Copilot & web app"), (TEAL, "Agent nền Codex (gộp)"), (VIOLET, "Nền mới Claude"),
                                  (AMBER, "Hội đồng & giám sát Freebuff"), (GREEN, "Bài giảng (workflow riêng)"), (RED, "Vấn đề / đã chết"))):
        add(f'<rect x="{lx + (i % 3) * 540}" y="{78 + (i // 3) * 34}" width="22" height="16" rx="3" fill="{c}"/>')
        text(lx + 32 + (i % 3) * 540, 92 + (i // 3) * 34, lab, 16, INK)

    # ===== Cột 1: cửa vào + đồng hồ
    X1, W1, Y0 = 70, 640, 210
    text(X1, Y0, "① CỬA VÀO", 22, INK, 800, HEAD)
    y = Y0 + 20
    for t, s in (("Bạn nói", "Tab Trò chuyện UC (/copilot-api) hoặc chat n8n (đăng nhập n8n)"),
                 ("Bạn bấm", "Web app UC :8320 — Hôm nay (Hạn sắp tới, Có thể trùng), Lịch, Ngoại khoá, 🔔 chuông, Gợi ý, Inbox, Học kỳ, Ngoại ngữ, ĐK tốt nghiệp, GDTC, Ghi bài giảng"),
                 ("Trường gửi", "Mail trường + Teams + MOOC SoICT + FAMI (20 phút) · qldt + iCTSV (4 lần/ngày) — UC tự đọc, chỉ đọc"),
                 ("Điện thoại", "ntfy: nhắc + nút Sẽ đi / Bỏ / Đã biết (có chữ ký, hỏi Xác nhận) · lệnh hôm nay / mai / hạn · app Notion: trang 📱"),
                 ("Bạn sửa Notion", "Tick Convene ở 🏛️ Council · ⚙️ Mốc năm học · danh mục / quy định ngoại ngữ · form Quick Upload"),
                 ("Thiết bị", "Companion ghi âm :5681 (chỉ khi bấm Start) → /lecture-capture-upload")):
        y = card(X1, y + 12, W1, t, None, s, BLUE)
    text(X1, y + 54, "② ĐỒNG HỒ (giờ Việt Nam)", 22, INK, 800, HEAD)
    clock = []
    for s, v in uni.items():
        for k, e in v["trig"]:
            if k == "cron": clock.append((cron_vi(e), s))
    for k, e in la["Lecture Analysis"]["trig"]:
        if k == "cron": clock.append((e, "Lecture Analysis"))
    y += 70
    for when, who in clock:
        rect(X1, y, W1, 30, "#fff", LINE, 1, 4)
        short = SHORT.get(who, "")
        text(X1 + 12, y + 21, when, 14.5, BLUE, 700); text(X1 + 250, y + 21, who + (" — " + short if short and short != who else ""), 13.5, INK2)
        y += 34

    # ===== Cột 2-3: workflow hợp nhất
    X2, W2 = 760, 2240
    frame_at = len(out); add("")   # khung vẽ sau khi biết chiều cao nội dung
    text(X2, Y0, f"③ WORKFLOW HỢP NHẤT · {full[UNIFIED]['name']} · {sum(v['nodes'] for v in uni.values())} node · id {UNIFIED}", 22, INK, 800, HEAD)
    colw = (W2 - 40) // 3
    # 3a Não + công cụ
    xa, ya = X2, Y0 + 30
    chat = uni.get("Chat", {"nodes": 0, "trig": []})
    ya = card(xa, ya, colw, "Chat · Não Copilot", "Gemini 3.5 Flash (gọi thẳng) · dự phòng LM Studio qwen3-8b · nhớ hội thoại theo phiên",
              DESC["Chat"] + " Hard rule: chỉ ghi điểm/vắng/luật khi sinh viên báo; không đổi tín chỉ.", BLUE,
              chat["nodes"] + 3 + len(TOOLS), trig_label(chat["trig"]))
    text(xa, ya + 34, f"{len(TOOLS)} công cụ của Não", 17, BLUE, 700, HEAD)
    ya += 46
    for name, tgt in TOOLS:
        rect(xa, ya, colw, 28, "#fff", LINE, 1, 4)
        text(xa + 10, ya + 19, name, 13.5, INK, 600); text(xa + colw - 10, ya + 19, tgt, 13, BLUE if tgt.startswith("→") else INK2, 500, FONT, "end")
        ya += 31
    # 3b cổng web app
    ya += 26
    text(xa, ya, "Cổng cho web app UC (webhook, X-Copilot-Key)", 17, BLUE, 700, HEAD)
    ya += 10
    for s in ("Gợi ý", "Nhập file", "Cổng Notion", "Thùng rác TKB", "Trang điện thoại", "Lịch", "Học kỳ", "Bài giảng"):
        if s in uni: ya = card(xa, ya + 10, colw, s, None, DESC.get(s, ""), BLUE, uni[s]["nodes"], trig_label(uni[s]["trig"]))
    # 3c agent Codex
    xb, yb = X2 + colw + 20, Y0 + 30
    text(xb, yb + 4, "Agent nền Codex (gộp từ 6 workflow cũ)", 17, TEAL, 700, HEAD)
    yb += 14
    for s in ("A1", "A2", "A3", "A4", "S5", "S6"):
        if s in uni:
            yb = card(xb, yb + 10, colw, s, None, DESC[s], TEAL, uni[s]["nodes"], trig_label([(k, cron_vi(e)) if k == "cron" else (k, e) for k, e in uni[s]["trig"]]))
    yb += 30
    text(xb, yb, "Nền mới (Claude, 10/2026)", 17, VIOLET, 700, HEAD)
    yb += 4
    for s in ("Bản tin", "Đánh giá tuần", "Chuyển kỳ", "Nghiên cứu"):
        if s in uni:
            yb = card(xb, yb + 10, colw, s, None, DESC[s], VIOLET, uni[s]["nodes"] + (1 if s == "Bản tin" else 0),
                      trig_label([(k, cron_vi(e)) if k == "cron" else (k, e) for k, e in uni[s]["trig"]]))
    # 3d hội đồng + giám sát
    xc, yc = X2 + 2 * (colw + 20), Y0 + 30
    text(xc, yc + 4, "Hội đồng & giám sát (Freebuff, gộp)", 17, AMBER, 700, HEAD)
    yc += 14
    for s in ("N9", "C9", "H10", "R10", "QU"):
        if s in uni:
            yc = card(xc, yc + 10, colw, s, None, DESC[s], AMBER, uni[s]["nodes"], trig_label([(k, cron_vi(e)) if k == "cron" else (k, e) for k, e in uni[s]["trig"]]))
    # workflow bài giảng
    yc += 40
    text(xc, yc, "Workflow bài giảng (chạy riêng)", 17, GREEN, 700, HEAD)
    for wid, sec in ((LEC_C, lc), (LEC_A, la)):
        k = list(sec)[0]
        yc = card(xc, yc + 12, colw, k, f"{full[wid]['name']} · id {wid}", DESC.get(k, ""), GREEN, sec[k]["nodes"], trig_label(sec[k]["trig"]))
    # vấn đề
    yc += 40
    text(xc, yc, "Ghi chú kiểm kê", 17, RED, 700, HEAD)
    yc = card(xc, yc + 12, colw, "Chạy thử: đã vô hiệu (chủ ý)", "Dry Run A1/A2/A3 ở 🎛️ University Control — công tắc còn sót, không tác dụng",
              "Bạn đã yêu cầu bỏ chế độ chạy thử; các agent luôn ghi thẳng. 🤖 Agent Suggestions đã vào thùng rác Notion, Suggestion Converter (Phase E) đã archive (04/10).", INK2, None, None, "#F1EFE8", "6 4")
    yc = card(xc, yc + 12, colw, "Khung Codex 23/08 — nay đã xây", None,
              "📅 Weekly Reviews: ĐÃ XÂY 03/10 (đánh giá theo tuần, thay giám sát theo ngày). 💾 Backup & Drive Sync: ĐÃ XÂY 03/10 (đồng bộ Uni-Documents). "
              "Lecture Recorder Control: bảng cũ, companion v2 đã thay — đã vào thùng rác Notion (04/10).", GREEN, None, None, "#F2F8F3")
    # tắt
    ybot = max(ya, yb, yc) + 50
    text(X2, ybot, f"Workflow đã lưu trữ (archive 04/10 — gộp vào Copilot, còn bản JSON) · {len(full) - len(active)}", 17, INK2, 700, HEAD)
    ybot += 14
    offs = [(wid, w) for wid, w in full.items() if not w.get("active")]
    cw = (W2 - 40) // 3
    for i, (wid, w) in enumerate(offs):
        cx_, cy_ = X2 + (i % 3) * (cw + 20), ybot + (i // 3) * 64
        why = OFF_WHY.get(wid, "")
        rect(cx_, cy_, cw, 56, "#FFF5F5" if why.startswith("⚠") else "#F1EFE8", RED if why.startswith("⚠") else LINE, 1.2, 5,
             None if why.startswith("⚠") else "6 4")
        text(cx_ + 12, cy_ + 22, w["name"].replace("University — ", "")[:58], 13.5, INK, 600)
        text(cx_ + 12, cy_ + 43, f"{len(w['nodes'])} node · {why}", 12.5, RED if why.startswith("⚠") else INK3)
    ybot += ((len(offs) + 2) // 3) * 64
    out[frame_at] = (f'<rect x="{X2 - 20}" y="{Y0 - 32}" width="{W2 + 40}" height="{ybot - Y0 + 50}" rx="10" fill="#FBFAF6" '
                     f'stroke="{INK}" stroke-width="2.2"/>')

    # ===== Cột 4: dịch vụ trên máy
    X4, W4 = 3060, 560
    text(X4, Y0, "④ DỊCH VỤ TRÊN MÁY", 22, INK, 800, HEAD)
    y4 = Y0 + 20
    svc = [("Web app UC :8320", "copilot_app.py — giao diện; Uni-Documents mỗi phút; thư + Teams 20 phút; nhắc mỗi phút (toast + ntfy); trường 4 lần/ngày; module Python: " + ", ".join(m for m, _, _ in PY) + ". Ghi Notion qua /copilot-notion.", BLUE),
           ("Cổng Gemini :8350", "Đếm quota, ưu tiên (chat > agent > bài giảng), Flash ↔ Flash-Lite, hết quota → LM Studio (lời gọi chỉ có chữ). Dùng bởi A1, A3, H10, Nghiên cứu, Lecture Analysis.", VIOLET),
           ("LM Studio :1234", "qwen3-8b (Não dự phòng, Thợ viết bản tin), qwen3-14b (xếp file, ghế local). Vulkan trên Arc 140V.", VIOLET),
           ("SearXNG :8888 (Docker)", "Máy tìm kiếm tự host cho Nghiên cứu (Gemini free không có quota tìm kiếm).", VIOLET),
           ("Speech gate :8340", "PhoWhisper trên NPU (OpenVINO) → lọc ảo giác → LM Studio rút gọn → /lecture-transcript-ready.", GREEN),
           ("Companion :5681", "Ghi âm bài giảng (chỉ khi bấm Start/Stop), tải lên qua Lecture Capture.", GREEN),
           ("Council relay :8310 → AgentChattr :8300", "4 ghế: Claude, Codex, Gemini, local (qwen3-14b). Biên bản → /council-transcript.", AMBER),
           ("ntfy.sh", "Thông báo điện thoại + kênh lệnh có chữ ký HMAC; giữ hộ các lần nhắc hẹn trước (≤ 3 ngày, sửa / huỷ theo mã) khi laptop ngủ.", VIOLET),
           ("Microsoft 365 · iCTSV (chỉ đọc)", "Outlook REST + Teams Graph + API iCTSV + Open edX (MOOC SoICT) bằng phiên / token của chính trang trong Chrome hồ sơ đồng bộ (khoá chrome.lock); không gửi / sửa gì.", INK2),
           ("Google Drive", "Course Materials Backup (file) · thư mục ghi âm bài giảng.", INK2),
           ("Gemini API (Google)", "Não Copilot gọi thẳng; các agent gọi qua cổng :8350.", INK2)]
    for t, s, c in svc: y4 = card(X4, y4 + 12, W4, t, None, s, c)
    # Python modules
    y4 += 40
    text(X4, y4, "Module Python (ghi qua Cổng Notion)", 17, BLUE, 700, HEAD)
    for m, d, tbl in PY:
        y4 = card(X4, y4 + 10, W4, m, d, "Bảng: " + ", ".join(f"{k} ({v})" for k, v in tbl.items()), BLUE)

    # ===== Cột 5: Notion
    X5, W5 = 3680, 2250
    text(X5, Y0, f"⑤ NOTION · {len(names)} bảng (số dòng hiện có)", 22, INK, 800, HEAD)
    y5 = Y0 + 24
    gcols = 2; gw = (W5 - 30) // gcols
    colY = [y5, y5]
    for gi, (g, members) in enumerate(GROUPS):
        ci = 0 if colY[0] <= colY[1] else 1
        gx, gy = X5 + ci * (gw + 30), colY[ci]
        h = 46 + len(members) * 34
        rect(gx, gy, gw, h, "#fff", INK, 1.6, 8)
        text(gx + 14, gy + 28, g, 17, INK, 700, HEAD)
        yy = gy + 46
        for m in members:
            k = n2id.get(m)
            cnt = counts.get(k, (0, False)) if k else (None, False)
            dead = m in ORPHAN_NOTE
            if dead: rect(gx + 8, yy - 2, gw - 16, 30, "#FFF5F5", RED, 1, 4, "5 3")
            text(gx + 16, yy + 18, m if k else m + " (không thấy)", 14, RED if dead else INK, 600 if not dead else 500)
            right = ORPHAN_NOTE.get(m) or (f"{cnt[0]}{'+' if cnt[1] else ''} dòng" if cnt[0] is not None else "")
            text(gx + gw - 16, yy + 18, right, 12.5, RED if dead else INK3, 500, FONT, "end")
            yy += 34
        colY[ci] = gy + h + 22
    listed = {m for _, ms in GROUPS for m in ms}
    extra = [v for v in names.values() if v not in listed]
    if extra:
        ci = 0 if colY[0] <= colY[1] else 1
        para(X5 + ci * (gw + 30), colY[ci] + 20, "Bảng chưa xếp nhóm (mới tạo?): " + ", ".join(extra), gw, 14, RED)

    # ===== Ma trận đọc/ghi
    rows = []
    for s in ("Chat", "Bản tin", "Đánh giá tuần", "Gợi ý", "Nhập file", "Lịch", "Học kỳ", "Bài giảng", "Thùng rác TKB", "Nghiên cứu", "Chuyển kỳ",
              "A1", "A2", "A3", "A4", "S5", "S6", "N9", "C9", "H10", "R10", "QU"):
        if s not in uni: continue
        m = {names[k]: "R" for k in uni[s]["R"]}
        for k in uni[s]["W"]: m[names[k]] = "RW" if m.get(names[k]) == "R" else "W"
        m.update(FIX.get(s, {}))
        if s in ("Chuyển kỳ", "Nghiên cứu", "Đánh giá tuần"): m = {}
        rows.append((s, "n8n", m))
    for wid, sec in ((LEC_C, lc), (LEC_A, la)):
        k = list(sec)[0]; m = {names[x]: "R" for x in sec[k]["R"]}
        for x in sec[k]["W"]: m[names[x]] = "RW" if m.get(names[x]) == "R" else "W"
        m.update(FIX.get(k, {})); rows.append((k, "n8n", m))
    for mod, _, tbl in PY: rows.append((mod, "py", tbl))
    cols = [m for _, ms in GROUPS for m in ms] + extra
    MY = max(ybot, y4, max(colY)) + 90
    text(70, MY, "⑥ MA TRẬN ĐỌC / GHI — khối nào chạm bảng Notion nào (R đọc · W ghi · RW cả hai)", 24, INK, 800, HEAD)
    text(70, MY + 30, "Hàng n8n suy từ node; hàng .py là module web app ghi qua Cổng Notion (Nghiên cứu, Chuyển kỳ chỉ gọi web app nên xem hàng research.py, semester.py). "
                      "Cột đỏ = bảng không ai chạm.", 15, INK2)
    lab_w, cw_ = 260, (W - 140 - 260) / len(cols)
    gx0, gy0 = 70 + lab_w, MY + 60
    # tiêu đề cột (xoay)
    for j, c in enumerate(cols):
        x = gx0 + j * cw_ + cw_ / 2
        dead = c in ORPHAN_NOTE
        add(f'<text transform="translate({x + 5},{gy0 + 250}) rotate(-60)" font-family="{FONT}" font-size="13.5" font-weight="600" fill="{RED if dead else INK}">{esc(c[:40])}</text>')
    gy0 += 262
    used = collections.Counter()
    for i, (r, kind, m) in enumerate(rows):
        y = gy0 + i * 30
        add(f'<rect x="70" y="{y}" width="{W - 140}" height="30" fill="{"#FFFFFF" if i % 2 else "#F1EFE8"}"/>')
        text(80, y + 20, r, 14, BLUE if kind == "py" else INK, 600)
        for j, c in enumerate(cols):
            v = m.get(c)
            if not v: continue
            used[c] += 1
            x = gx0 + j * cw_ + 4
            col = {"R": BLUE, "W": RED, "RW": VIOLET}[v]
            add(f'<rect x="{x}" y="{y + 5}" width="{cw_ - 8}" height="20" rx="4" fill="{col}" opacity="{0.18 if v == "R" else 0.28}"/>')
            text(x + (cw_ - 8) / 2, y + 20, v, 12.5, col, 700, FONT, "anchor")
    for j, c in enumerate(cols):
        if used[c] == 0:
            add(f'<rect x="{gx0 + j * cw_ + 2}" y="{gy0}" width="{cw_ - 4}" height="{len(rows) * 30}" fill="{RED}" opacity="0.08"/>')
    end = gy0 + len(rows) * 30 + 40
    text(70, end, "Nguồn sự thật: n8n API + Notion API lúc vẽ. Phần mô tả công việc (DESC, FIX, PY) sửa trong gen_n8n_map.py khi thêm khối mới.", 14, INK3)
    add("</svg>")
    svg = "\n".join(out).replace('text-anchor="anchor"', 'text-anchor="middle"')
    # khít chiều cao
    svg = re.sub(r'viewBox="0 0 (\d+) \d+" width="(\d+)" height="\d+"', f'viewBox="0 0 {W} {int(end + 60)}" width="{W}" height="{int(end + 60)}"', svg, count=1)
    svg = svg.replace(f'<rect width="{W}" height="{Hh}"', f'<rect width="{W}" height="{int(end + 60)}"', 1)
    svg = svg.replace(f'<rect x="30" y="30" width="{W - 60}" height="{Hh - 60}"', f'<rect x="30" y="30" width="{W - 60}" height="{int(end)}"', 1)
    open(OUT, "w", encoding="utf-8").write(svg)
    print("written", OUT, f"{len(svg)} bytes · cao {int(end + 60)}px · {len(rows)} hàng × {len(cols)} cột")

if __name__ == "__main__":
    main()
