# -*- coding: utf-8 -*-
"""Bản đồ kiến trúc Hệ thống University — bản 5 (06/10/2026). Sinh SVG kiểu bản vẽ kỹ thuật."""
import html, sys

W, H = 13800, 3400
OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/Map.svg"

# ---- tokens
PAPER = "#FAFBFC"; GRID = "#E9EEF3"; GRID2 = "#D9E1E9"
INK = "#14263A"; INK2 = "#4B5D70"; INK3 = "#7A8A9B"
RED = "#B3122E"; TEAL = "#0D7377"; HL = "#FFD43B"
Z_N8N = "#F2F5F9"; Z_NOTION = "#F3F5F4"; Z_COUNCIL = "#F4F2F7"; Z_AI = "#EDF6F5"; Z_REC = "#FFFBEA"; Z_FRONT = "#F2F5F9"
F_HEAD = "Bahnschrift, 'Segoe UI', sans-serif"
F_BODY = "'Segoe UI', 'Segoe UI Emoji', sans-serif"
F_MONO = "'Cascadia Mono', Consolas, monospace"

out = []
def add(s): out.append(s)
def esc(t): return html.escape(t, quote=True)

def text(x, y, s, size=18, fill=INK, weight=400, family=F_BODY, anchor="start", italic=False, ls=0):
    st = ' font-style="italic"' if italic else ""
    lsp = f' letter-spacing="{ls}"' if ls else ""
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{st}{lsp}>{esc(s)}</text>')

def wrap(s, width, size):
    cw = size * 0.47
    maxc = max(8, int(width / cw))
    words, lines, cur = s.split(" "), [], ""
    for w_ in words:
        if len(cur) + len(w_) + (1 if cur else 0) <= maxc: cur = (cur + " " + w_).strip()
        else: lines.append(cur); cur = w_
    if cur: lines.append(cur)
    return lines

def para(x, y, s, width, size=18, fill=INK, lh=1.38, weight=400, family=F_BODY):
    for i, ln in enumerate(wrap(s, width, size)):
        text(x, y + i * size * lh, ln, size, fill, weight, family)
    return y + len(wrap(s, width, size)) * size * lh

def rect(x, y, w, h, fill="#fff", stroke=INK, sw=1.5, rx=0, dash=None, op=1):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" fill-opacity="{op}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

def zone(x, y, w, h, num, title, sub, fill, new=False, inline=False):
    rect(x, y, w, h, fill, INK, 2.4)
    # title tab
    tw = 26 * 0.62 * (len(num) + len(title) + 3) + 40
    rect(x, y, tw, 56, INK, INK, 0)
    text(x + 20, y + 38, f"{num}  ·  {title}".upper() if num else title.upper(), 26, "#fff", 600, F_HEAD, ls=1.2)
    if new:
        nx = x + tw + 14
        rect(nx, y + 14, 74, 30, "#fff", RED, 2)
        text(nx + 37, y + 36, "MỚI", 17, RED, 700, F_HEAD, "middle", ls=2)
    if sub and inline:
        text(x + tw + (110 if new else 24), y + 36, sub, 20, INK2, 400)
    elif sub:
        text(x + 22, y + 92, sub, 19, INK2, 400)

BODY = 21
def card_h(w, meta, lines, size=BODY):
    hh = 60 + (28 if meta else 0)
    for ln in lines:
        bullet = not ln.startswith("→")
        n = len(wrap(ln, (w - 54) if bullet else (w - 40), size))
        hh += n * size * 1.38 + 4
    return int(hh + 14)

def card(x, y, w, h, num, title, meta, lines, fill="#fff", accent=INK, size=BODY):
    if h is None: h = card_h(w, meta, lines, size)
    rect(x, y, w, h, fill, accent, 1.6)
    add(f'<rect x="{x}" y="{y}" width="6" height="{h}" fill="{accent}"/>')
    tx = x + 22
    if num:
        text(tx, y + 34, num, 22, accent, 700, F_HEAD)
        nx = tx + len(num) * 13 + 14
    else:
        nx = tx
    text(nx, y + 34, title, 22, INK, 600, F_HEAD)
    yy = y + 60
    if meta:
        text(tx, yy, meta, 15, INK3, 400, F_MONO); yy += 28
    for ln in lines:
        bullet = not ln.startswith("→")
        if bullet:
            add(f'<circle cx="{tx + 4}" cy="{yy - size * 0.36}" r="2.6" fill="{INK2}"/>')
            yy = para(tx + 16, yy, ln, w - 54, size, INK)
        else:
            yy = para(tx, yy, ln, w - 40, size, TEAL, weight=600)
        yy += 4
    return y + h

def chip(x, y, w, label, sub=None, fill="#fff", stroke=INK):
    h = 64 if sub else 44
    rect(x, y, w, h, fill, stroke, 1.6, rx=22)
    text(x + w / 2, y + 28, label, 18, INK, 600, F_HEAD, "middle")
    if sub: text(x + w / 2, y + 51, sub, 14, INK3, 400, F_MONO, "middle")

def path(pts, color=INK, sw=2.2, dash=None, arrow="end", label=None, lpos=None, lanchor="start", lsize=15, lcolor=None, halo=True):
    d = "M " + " L ".join(f"{a},{b}" for a, b in pts)
    if halo: add(f'<path d="{d}" fill="none" stroke="{PAPER}" stroke-width="{sw + 7}" stroke-linejoin="round"/>')
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    mk = {"end": f' marker-end="url(#a-{color[1:]})"', "both": f' marker-start="url(#s-{color[1:]})" marker-end="url(#a-{color[1:]})"', None: ""}[arrow]
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round"{ds}{mk}/>')
    if label:
        lx, ly = lpos if lpos else pts[len(pts) // 2]
        tw_ = len(label) * lsize * 0.5 + 10
        tx_ = lx - (tw_ if lanchor == "end" else tw_ / 2 if lanchor == "middle" else 0)
        add(f'<rect x="{tx_ - 5}" y="{ly - lsize}" width="{tw_ + 4}" height="{lsize + 7}" fill="{PAPER}" fill-opacity="0.92"/>')
        text(lx, ly, label, lsize, lcolor or color, 600, F_BODY, lanchor)

def hl(pts, w=26):
    d = "M " + " L ".join(f"{a},{b}" for a, b in pts)
    add(f'<path d="{d}" fill="none" stroke="{HL}" stroke-opacity="0.62" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')

def step(x, y, n):
    add(f'<circle cx="{x}" cy="{y}" r="19" fill="{INK}"/>')
    text(x, y + 7, str(n), 20, HL, 700, F_HEAD, "middle")

# ======================================================================
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">')
add("<title>Bản đồ kiến trúc — Hệ thống University (bản 5, 06/10/2026)</title>")
add("<defs>")
for c in (INK, RED, TEAL, INK2):
    add(f'<marker id="a-{c[1:]}" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="11" markerHeight="11" orient="auto-start-reverse"><path d="M1,1 L11,6 L1,11 Z" fill="{c}"/></marker>')
    add(f'<marker id="s-{c[1:]}" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="11" markerHeight="11" orient="auto-start-reverse"><path d="M1,1 L11,6 L1,11 Z" fill="{c}"/></marker>')
add(f'<pattern id="g" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="{GRID}" stroke-width="1"/></pattern>')
add(f'<pattern id="G" width="200" height="200" patternUnits="userSpaceOnUse"><rect width="200" height="200" fill="url(#g)"/><path d="M200 0H0V200" fill="none" stroke="{GRID2}" stroke-width="1.2"/></pattern>')
add("</defs>")
rect(0, 0, W, H, PAPER, PAPER, 0)
rect(40, 40, W - 80, H - 80, "url(#G)", INK, 0)

# ---- drawing frame + reference grid (A–H rows, 1–8 cols)
rect(40, 40, W - 80, H - 80, "none", INK, 4)
rect(64, 64, W - 128, H - 128, "none", INK, 1.5)
cols, rows = 16, 8
for i in range(cols):
    cx = 64 + (W - 128) * (i + 0.5) / cols
    text(cx, 58, str(i + 1), 18, INK2, 600, F_HEAD, "middle"); text(cx, H - 46, str(i + 1), 18, INK2, 600, F_HEAD, "middle")
    if i: add(f'<path d="M{64 + (W - 128) * i / cols} 40V64M{64 + (W - 128) * i / cols} {H - 64}V{H - 40}" stroke="{INK}" stroke-width="1.5"/>')
for j in range(rows):
    cy = 64 + (H - 128) * (j + 0.5) / rows
    L = "ABCDEFGH"[j]
    text(52, cy + 6, L, 18, INK2, 600, F_HEAD, "middle"); text(W - 52, cy + 6, L, 18, INK2, 600, F_HEAD, "middle")
    if j: add(f'<path d="M40 {64 + (H - 128) * j / rows}H64M{W - 64} {64 + (H - 128) * j / rows}H{W - 40}" stroke="{INK}" stroke-width="1.5"/>')

# ---- header
text(100, 150, "Bản đồ kiến trúc · Hệ thống University", 64, INK, 600, F_HEAD, ls=0.5)
text(102, 200, "Một trang nói hết: dữ liệu vào từ đâu, ai xử lý, lưu ở đâu, AI nào chạy ở chỗ nào, nhắc bạn lúc nào, và cái gì không bao giờ được xảy ra. Trạng thái thật 06/10/2026.", 24, INK2)

# user entry chips
text(100, 282, "CỬA VÀO CỦA BẠN", 17, INK2, 600, F_HEAD, ls=3)
cx_ = 100
entries = [("University Copilot", "Chrome App · :8320", 330), ("AgentChattr", "Chrome App · :8300", 290),
           ("Notion · Home Dashboard", "sửa trực tiếp, tick Convene", 360), ("Form Quick Upload", "n8n form", 250),
           ("Google Drive", "Course Materials Backup", 300), ("Lớp học / bài online", "micro · âm thanh app", 310), ("qldt · iCTSV", "dữ liệu trường · tự đồng bộ", 330),
           ("Mail · Teams · MOOC · FAMI", "chỉ đọc · 5 phút/lần", 330), ("Điện thoại · ntfy", "nhắc + nút bấm · cả khi máy ngủ", 360), ("Notion app · 📱 UC", "xem khi laptop ngủ", 290), ("NotebookLM", "nhận tài liệu khi bạn bấm", 300)]
chip_pos = {}
for lab, sub, w in entries:
    chip(cx_, 300, w, lab, sub)
    chip_pos[lab] = (cx_, w)
    cx_ += w + 22

# ======================================================================
# COL A — 0 · Cửa trước Copilot
FA = [("Chat", "POST /webhook/copilot-api · X-Copilot-Key", ["Hỏi bằng lời, đính kèm ảnh / file; ảnh gửi Gemini dạng nhị phân",
                                                                   "Luật trung thực: chỉ nói “đã làm” khi công cụ trả kết quả thật · nhớ hội thoại + việc chờ bạn xác nhận (chat_memory.py)",
                                                                   "Công cụ dời hạn (reschedule.py): chỉ hạn Tự luyện, 2 bước xem trước → ghi; hạn Môn học / của trường từ chối"]),
      ("Hôm nay · Lịch · Ngoại khoá · Hành chính · Học bổng · 🔔", "tab của web app · chuông cạnh tên app · tự tải lại 15 phút/lần", ["Hạn sắp tới (tích Hoàn tất = biến mất) · Có thể trùng · lịch học và lịch ngoại khoá tách riêng", "🔔 gom mọi cảnh báo, không che tab · Gợi ý (Mục 7) · Hành chính / Học bổng → Mục 20"]),
      ("Inbox · xếp file", "Tika → qwen3-14b → từ khoá môn (COURSE_HINTS)", ["Vân tay SHA-256 so với cả Uni-Documents TRƯỚC khi xếp: trùng → không chép thêm", "→ copilot-file-ingest: Drive → 📥 University Inbox → Mục 3·30", "→ gửi tài liệu sang NotebookLM (Mục 20)"]),
      ("Ghi bài giảng", "/api/rec/*  ·  /api/lectures  ·  /api/lecture-monitor", ["Start / Stop / marker / ảnh slide; thanh bên “Gemini hôm nay”",
                                                                             "“Đang tải lên”: giám sát từng chặng ①→⑨ mỗi phút, tự ghi lỗi, lỗi tự hết khi chặng chạy lại được · không tốn quota AI (lecture_monitor.py)"])]
FA_I = len(out)
y = 556
FA_Y = {}
for t, m, ls in FA:
    FA_Y[t] = y
    y = card(108, y, 900, None, "", t, m, ls) + 14
FRONT_BOTTOM = y - 14
Z0_H = FRONT_BOTTOM + 28 - 440
_mark = len(out)
zone(80, 440, 960, Z0_H, "0", "Cửa trước · University Copilot", "copilot_app.py · ui/index.html · 127.0.0.1:8320 — một cửa duy nhất thay cho “buồng lái”", Z_FRONT, new=True)
_z = out[_mark:]; del out[_mark:]; out[FA_I:FA_I] = _z   # vùng nền vẽ TRƯỚC các thẻ

# COL A — 11 · Ghi bài giảng
Z11_Y = 440 + Z0_H + 40
zone(80, Z11_Y, 960, 2380 - Z11_Y, "11", "Ghi bài giảng", "Từ nút Start tới ghi chú trong Notion — bút dạ vàng ①→⑨", Z_REC, new=True)
COMP_Y = Z11_Y + 116
comp_bottom = card(108, COMP_Y, 900, None, "", "LectureRecorderCompanion", "C# .NET 8 · NAudio · 127.0.0.1:5681 · tự bật cùng máy, không tự ghi",
     ["Chỉ ghi khi bạn bấm Start, chỉ dừng khi bạn bấm Stop",
      "Ngắt an toàn 3 h 30 (yêu cầu ≥ 3 h 10), có cảnh báo trước",
      "Nguồn: micro · âm thanh cả máy · âm thanh riêng 1 app · Teams qua cáp riêng VB-CABLE (chỉ bắt Teams, bạn vẫn nghe bình thường) · trộn micro",
      "Im lặng 30 giây → cảnh báo ngay trên UC",
      "16 kHz mono, bơm theo đồng hồ thật → D:\\…\\Documents\\LectureRecorder"])
steps = [
    "Bấm Start ở tab Ghi bài giảng (Copilot)",
    "Companion ghi; marker / ảnh slide gửi kèm trong giờ",
    "Bấm Stop → tải file lên n8n · Lecture Capture",
    "Drive “University Lecture Recordings” + 🎙️ Lecture Sessions",
    "Lecture Analysis v2 (5 phút/lần) gửi audio sang Cổng chép lời",
    "VAD lọc → PhoWhisper trên NPU → lọc câu bịa → Qwen nén",
    "Cổng chép lời gọi lại n8n: lecture-transcript-ready",
    "Gemini đọc CHỮ đã nén + slide (qua cổng hạn mức)",
    "📚 Lecture Notes + 📥 Inbox (môn gán theo TKB) → A2 / A3",
]
sy = comp_bottom + 56
gap_s = (2350 - sy) / len(steps)
for i, s_ in enumerate(steps):
    step(130, sy - 7, i + 1)
    text(166, sy, s_, 20, INK)
    sy += gap_s

# ======================================================================
# COL B — n8n
zone(1080, 440, 1940, 1940, "", "n8n · Docker · localhost:5678", "", Z_N8N)
text(1104, 532, "Workflow hợp nhất “University — Copilot” · 264 nút · sinh từ build.py (sửa code, không sửa trên giao diện)", 20, INK2)
CW, GAP = 455, 20
X = [1104 + i * (CW + GAP) for i in range(4)]
def row(y0, items):
    h = max(card_h(w, m, ls) for (xi, w, n, t, m, ls, acc) in items)
    for (xi, w, n, t, m, ls, acc) in items:
        card(xi, y0, w, h, n, t, m, ls, accent=acc)
    return y0 + h
R1 = 556
e1 = row(R1, [
    (X[0], CW, "1", "Quick Upload", "form · QU", ["Form gửi file / ghi chú nhanh", "→ 📥 University Inbox"], INK),
    (X[1], CW, "2", "Intake TKB · Deadline", "A1 · 15 phút (:00) · Gemini", ["Ảnh TKB, deadline, buổi học trong ➕ Academic Intake", "→ 🗓️ Timetable Events + 📋 Academic Work"], INK),
    (X[2], CW, "3·30", "University Inbox", "A2 · 15 phút (:05) + web app bơm tuần tự", ["Khớp môn (tin môn theo thư mục Uni-Documents), giành quyền dòng — không tạo trùng", "→ 📚 Course Materials · bản lưu Drive"], INK),
    (X[3], CW, "3·40", "Coursework Breakdown", "A3 · 15 phút (:10) · Gemini", ["Đọc đề, ước lượng độ khó / công sức, phân rã", "→ ✅ Academic Tasks (phụ thuộc, mốc)"], INK)])
R2 = e1 + 20
e2 = row(R2, [
    (X[0], CW, "6", "Daily Planning", "A4 · 07:00 + mỗi 30 phút (7–22 h)", ["Gợi ý việc trong ngày (không phán xét theo ngày) · Camp Mode", "→ 📅 Daily Task"], INK),
    (X[1], CW, "5", "Progress Recorder", "S5 · 30 phút → 📅 Weekly Reviews CN 21:00", ["Ghi tiến độ; lệch ước lượng gộp vào đánh giá TUẦN (không cảnh báo từng task)", "Tuần: Ổn / Cần tăng tốc / Không ổn + gợi ý ngày camp"], INK),
    (X[2], CW, "7", "Material Recommendations", "S6 · 07:10", ["Tài liệu liên quan việc hôm nay", "→ “Suggested Today” + lý do"], INK),
    (X[3], CW, "10", "Health · Reconcile", "H10 · R10 · 6 giờ/lần · Gemini", ["Quét Event/Task kẹt, liên kết thiếu, trùng", "→ ⚠️ Exception Queue"], RED)])
R3 = e2 + 20
e3 = row(R3, [
    (X[0], CW * 2 + GAP, "", "Não Copilot", "Chat trigger · copilot-api · LangChain agent + 9 công cụ HTTP",
     ["Đọc ngữ cảnh Notion mới nhất ở mỗi tin nhắn; trả lời và ghi Notion bằng công cụ",
      "Não: Gemini 3.5 Flash (qua cổng :8350) · dự phòng: LM Studio qwen3-8b",
      "Bản tin sáng 07:20 / tối 21:30 → 🗞️ Bản tin Copilot (LM Studio viết)"], TEAL),
    (X[2], CW * 2 + GAP, "9", "Hội đồng ↔ Notion", "N9 · mỗi phút · C9 council-convene / finalize",
     ["Chủ tọa tick Convene → khoá snapshot Source Work → In council → gửi relay",
      "Nhận biên bản (council-transcript) → Awaiting Chair",
      "Góp ý + Convene = vòng mới · Final Decision + Convene = Finalized"], INK)])
N9_Y = (R3 + e3) / 2
R4 = e3 + 20
e4 = row(R4, [
    (X[0], CW * 2 + GAP, "", "Webhook cho web app", "đều cần header X-Copilot-Key",
     ["copilot-suggest · copilot-file-ingest · copilot-lectures · copilot-lecture-reanalyze · copilot-brief",
      "Mỗi agent có thêm webhook “chạy ngay”: copilot-run-a1 … a4, s5, s6"], INK),
    (X[2], CW * 2 + GAP, "", "Đã tắt, giữ làm bản lưu", "16 workflow · sao lưu D:\\Tools\\n8n-temp",
     ["Agent 2/3/4, Service 5/6, Conductor, Council Bridge, Quick Upload, Reconciliation, Health Ping, Suggestion Converter, Create Deadline, TEMP Proxy, 2 bản ARCHIVED",
      "Lecture Recorder Control Bridge — tắt hẳn để chặn tự ghi âm"], INK3)])
# --- Nhịp chạy trong ngày (trục 24 h) trong vùng n8n
TL_Y = e4 + 70
TL_X0, TL_X1 = 1104, 2984
text(1104, TL_Y - 22, "NHỊP CHẠY TRONG NGÀY", 17, INK2, 600, F_HEAD, ls=2.5)
def hx(h): return TL_X0 + (TL_X1 - TL_X0) * h / 24
# lanes: thanh liền, đậm theo tần suất
lanes = [("Mỗi phút", "N9 hội đồng (kiểm Convene)", [(0, 24, 0.55)]),
         ("5 phút", "Lecture Analysis (phiên chờ xử lý)", [(0, 24, 0.42)]),
         ("15 phút", "A1 :00 · A2 :05 · A3 :10", [(0, 24, 0.30)]),
         ("30 phút", "S5 Progress cả ngày · A4 theo dõi tải 7–22 h", [(0, 24, 0.16), (7, 22, 0.34)]),
         ("6 giờ", "H10 Health · R10 Reconcile (00 · 06 · 12 · 18 h)", "6h")]
ly = TL_Y + 20
bx0 = TL_X0 + 640
def bx(h): return bx0 + (TL_X1 - bx0) * h / 24
for nm, desc, spec in lanes:
    text(TL_X0, ly + 18, nm, 16, INK2, 600, F_HEAD)
    text(TL_X0 + 104, ly + 18, desc, 16, INK)
    add(f'<rect x="{bx0}" y="{ly + 4}" width="{TL_X1 - bx0}" height="18" fill="#fff" stroke="{INK3}" stroke-width="1"/>')
    if spec == "6h":
        for h in (0, 6, 12, 18):
            add(f'<rect x="{bx(h) - 3}" y="{ly + 4}" width="7" height="18" fill="{RED}"/>')
    else:
        for (a_, b_, op) in spec:
            add(f'<rect x="{bx(a_)}" y="{ly + 4}" width="{bx(b_) - bx(a_)}" height="18" fill="{INK}" fill-opacity="{op}"/>')
    ly += 34
# fixed-time events
add(f'<path d="M{bx0} {ly + 10}H{TL_X1}" stroke="{INK}" stroke-width="2"/>')
for h in range(0, 25, 3):
    add(f'<path d="M{bx(h)} {ly + 4}V{ly + 16}" stroke="{INK}" stroke-width="1.6"/>')
    text(bx(h), ly + 36, f"{h:02d}:00", 14, INK2, 500, F_MONO, "middle")
events = [(7.0, "07:00 A4 lập kế hoạch"), (7 + 10 / 60, "07:10 S6 gợi ý tài liệu"), (7 + 20 / 60, "07:20 bản tin sáng"), (14.0, "14:00 Gemini reset hạn mức"), (21.5, "21:30 bản tin tối")]
for i, (h, lab) in enumerate(events):
    yy = ly + 60 + (i % 3) * 24
    add(f'<path d="M{bx(h)} {ly + 10}V{yy - 14}" stroke="{TEAL if "Gemini" in lab else INK}" stroke-width="1.4" stroke-dasharray="3 3"/>')
    add(f'<circle cx="{bx(h)}" cy="{ly + 10}" r="5" fill="{TEAL if "Gemini" in lab else INK}"/>')
    text(bx(h) + 6, yy, lab, 15, TEAL if "Gemini" in lab else INK, 600)
text(TL_X0, ly + 22, "Giờ cố định", 16, INK2, 600, F_HEAD)
TL_END = ly + 140
R5 = 2356 - max(card_h(CW, '7 nút · lecture-capture-upload', ['Nhận file sau khi bấm Stop', 'Đặt tên theo định dạng thật (mp3 / wav / webm)', '→ Drive + 🎙️ Lecture Sessions = Uploaded']), 260)
text(1104, R5 - 16, "HAI WORKFLOW RIÊNG CHO BÀI GIẢNG", 17, INK2, 600, F_HEAD, ls=2.5)
CAP_W = CW; ANA_X = X[1]; ANA_W = CW * 3 + GAP * 2
e5 = row(R5, [
    (X[0], CAP_W, "", "Lecture Capture", "7 nút · lecture-capture-upload",
     ["Nhận file sau khi bấm Stop", "Đặt tên theo định dạng thật (mp3 / wav / webm)", "→ Drive + 🎙️ Lecture Sessions = Uploaded"], INK),
    (ANA_X, ANA_W, "", "Lecture Analysis v2", "30 nút · lecture_build.py · mỗi 5 phút + webhook lecture-transcript-ready",
     ["A · phiên Uploaded → tải audio → gửi Cổng chép lời :8340 — audio KHÔNG BAO GIỜ tới Gemini",
      "B · nhận bản nén → khớp môn theo TKB → Gemini đọc chữ + slide → is_lecture? (loại bản ghi không phải bài giảng)",
      "C · ghi 📚 Lecture Notes đầy đủ + 📥 Inbox kèm Detected Course · giải cứu phiên kẹt quá 6 giờ",
      "Ghi âm hỏng / quá ít tiếng nói → đánh dấu unusable, 0 token Gemini"], INK)])
CAP_MID = (R5 + e5) / 2

# ======================================================================
# COL C — Notion
zone(3080, 440, 760, 1940, "", "Notion · nguồn dữ liệu chính", "Mọi agent đọc / ghi ở đây; bạn sửa trực tiếp được", Z_NOTION)
groups = [
    ("Học vụ", ["2️⃣ Courses (+ cột “trường”)", "🔁 Lần học (học lại · cải thiện)", "📋 Academic Work (+ Loại hạn 3 mức)", "🗓️ Academic Timetable Events", "✅ Academic Tasks", "📅 Daily Task · 🌗 Chế độ ngày"]),
    ("Đầu vào · tài liệu", ["➕ Academic Intake", "📥 University Inbox", "📚 Course Materials"]),
    ("Bài giảng", ["🎙️ Lecture Sessions", "📚 Lecture Notes"]),
    ("Điều phối", ["🏛️ Council Sessions", "⚠️ Exception Queue (Mục 8)", "🗞️ Bản tin Copilot", "🎛️ University Control"]),
    ("Nhật ký · duyệt", ["🧾 Automation Log", "📈 Progress & Estimate History", "💾 Backup & Drive Sync (đồng bộ Uni-Documents)", "📅 Weekly Reviews (đánh giá tuần)", "🏫 Đồng bộ trường (nhật ký qldt · iCTSV)"]),
    ("Mới 04/10 · theo dõi · điện thoại", ["📡 Sự kiện theo dõi (mail · Teams)", "🎯 Hoạt động ngoại khoá (CTSV · mail · Teams)", "📱 University Copilot (trang riêng, cổng n8n chỉ ghi trang này)"]),
]
gy = 560
NOTION_ROW = {}
for gname, dbs in groups:
    text(3108, gy + 4, gname.upper(), 16, INK2, 600, F_HEAD, ls=2.5)
    gy += 22
    for db in dbs:
        rect(3108, gy, 704, 50, "#fff", RED if gname.startswith("Mới") else INK, 1.4)
        text(3128, gy + 33, db, 20, INK, 500)
        NOTION_ROW[db] = gy + 25
        gy += 57
    gy += 16
para(3108, gy + 8, "Khoá chống trùng: Processing Key · Sync Key · Breakdown Key · Analysis Key — chạy lại không sinh bản ghi trùng.", 700, 18, INK2)

# ======================================================================
# COL D — Council
zone(3880, 440, 840, 1940, "9", "Hội đồng AI", "AgentChattr · phòng #council · Chrome App", Z_COUNCIL)
cy = card(3908, 556, 784, None, "", "AgentChattr server", "run.py · :8300 · MCP :8200 · data\\server.lock",
     ["Phòng chat nhiều AI; ghế được gọi bằng @tên", "Chỉ một bản server sống (bật trùng tự thoát)"]) + 26
RELAY_Y = cy
cy = card(3908, cy, 784, None, "", "council_relay.py", ":8310 · /council/ask · data/council_sessions.json",
     ["Xếp ghế đang online; 3 ghế đám mây xáo ngẫu nhiên", "Local AI ngồi áp chót (phản biện), ghế cuối tổng hợp",
      "Hồ sơ chỉ có đúng một “@” → gọi từng ghế một"]) + 26
KEEP_Y = cy
cy = card(3908, cy, 784, None, "", "seat_keeper.py", "kiểm 20 s/lần · AgentChattr.ps1 khởi động",
     ["Ghế rớt → bật lại (giãn 2 / 4 / 8 / 10 phút)", "Hết quota / cần đăng nhập → ghế hiện OFF kèm lý do, không biến mất",
      "Tới giờ reset quota → tự khởi động lại ghế; cửa sổ ghế dời ra ngoài màn hình"]) + 30
add(f'<path d="M4300 {RELAY_Y - 26}V{RELAY_Y}M4300 {KEEP_Y - 26}V{KEEP_Y}" stroke="{INK}" stroke-width="2"/>')
seats = [("Claude", "Claude Code CLI"), ("Codex", "gpt-6-luna · khoá model"),
         ("Gemini", "gemini-3.7-flash · khoá model"), ("Local AI", "qwen3-14b · LM Studio · ghế phản biện")]
text(3908, cy + 8, "4 GHẾ", 16, INK2, 600, F_HEAD, ls=3)
cy += 24
for nm, sb in seats:
    col = TEAL if nm == "Local AI" else INK
    rect(3908, cy, 784, 80, "#fff", col, 1.6, rx=40)
    add(f'<circle cx="3950" cy="{cy + 40}" r="15" fill="{col}"/>')
    text(3982, cy + 35, nm, 23, INK, 600, F_HEAD)
    text(3982, cy + 62, sb, 17, INK2)
    cy += 94
yb = para(3908, cy + 24, "Kimi đã rời hội đồng (02/10). Local AI không tích luỹ trí nhớ: mỗi lượt đọc tối đa 40 tin, gói trong khoảng 7.000 token, luôn giữ hồ sơ phiên.", 784, 18, INK2)
para(3908, yb + 20, "Chủ tọa là bạn: AI chỉ đề xuất, quyết định cuối nằm ở 🏛️ Council Sessions.", 784, 19, RED, weight=600)

# ======================================================================
# Row 12 — Tầng AI
AIW = 690
AX = [108 + i * (AIW + 20) for i in range(4)]
AI_Y = 2516
AI_H = max(card_h(AIW, m_, l_) for m_, l_ in [("gemini_gate.py · :8350 · D:/Data/GeminiGate", ["Đếm token theo ngày (giờ PT, reset 14:00 VN), theo model và theo nơi gọi", "Ưu tiên theo việc; chạm 80 % thì hạ cấp", "Flash ↔ Flash-Lite → LM Studio (chỉ văn bản); tool-call nhận 429 để n8n tự lùi"]),("lms · :1234 · model trên D:/AI/Models", ["qwen3-14b trên GPU Arc 140V · khung 16k token", "Dùng cho: xếp file, nén bài giảng, bản tin, ghế Local AI, dự phòng của cổng", "qwen3-8b: dự phòng não Copilot"])])
Z12H = AI_Y - 2440 + AI_H + 70
zone(80, 2440, 2940, Z12H, "12", "Tầng AI · cổng hạn mức", "Gemini miễn phí là tài nguyên khan hiếm: mọi lời gọi đi qua cổng; việc nặng chạy trên máy", Z_AI, new=True, inline=True)
AIW = 690
AX = [108 + i * (AIW + 20) for i in range(4)]
AI_Y = 2516
AI_BOT = row(AI_Y, [
    (AX[0], AIW, "", "Cổng Gemini", "gemini_gate.py · :8350 · D:\\Data\\GeminiGate",
     ["Đếm token theo ngày (giờ PT, reset 14:00 VN), theo model và theo nơi gọi",
      "Ưu tiên theo việc; chạm 80 % thì hạ cấp",
      "Flash ↔ Flash-Lite → LM Studio (chỉ văn bản); tool-call nhận 429 để n8n tự lùi"], RED),
    (AX[1], AIW, "", "Gemini API (miễn phí)", "3.5 Flash · 3.5 Flash-Lite",
     ["Gọi bởi: A1, A3, H10, não Copilot, Lecture Analysis", "Chỉ nhận chữ và ảnh slide — không nhận audio",
      "Ghế Gemini trong hội đồng dùng khoá riêng"], TEAL),
    (AX[2], AIW, "", "LM Studio", "lms · :1234 · model trên D:\\AI\\Models",
     ["qwen3-14b trên GPU Arc 140V · khung 16k token",
      "Dùng cho: xếp file, nén bài giảng, bản tin, ghế Local AI, dự phòng của cổng",
      "qwen3-8b: dự phòng não Copilot"], TEAL),
    (AX[3], AIW, "", "Cổng chép lời", "speech_gate.py · :8340 · D:\\Data\\SpeechGate",
     ["VAD: ≥ 3 phút tiếng nói và ≥ 5 % thời lượng; không đạt → unusable",
      "PhoWhisper-large INT8 trên NPU (~4,5× thời gian thực); NPU lỗi → CPU",
      "Lọc câu bịa, nén bằng Qwen theo đoạn 8 phút"], TEAL)])

# Storage
zone(3080, 2440, 1640, Z12H, "", "Lưu trữ ngoài Notion", "", "#F6F7F9")
row(2526, [
    (3108, 790, "", "Google Drive", "Drive for Desktop · ổ G:",
     ["Course Materials Backup — bản lưu tài liệu (A2, xếp file)", "University Lecture Recordings — audio bài giảng",
      "Ảnh TKB / tài liệu thả vào được Mục 1, 2, 3·30 đọc"], INK),
    (3918, 774, "", "Ổ D: (C: chỉ cho Windows)", "mọi công cụ, model, cache, dữ liệu",
     ["Uni-Documents — tài liệu đã xếp theo môn", "Documents\\LectureRecorder — file ghi âm",
      "D:\\Tools — mã nguồn: university-copilot, agentchattr, speech-gate, gemini-gate",
      "D:\\AI — model + cache (LM Studio, PhoWhisper, OpenVINO)"], INK)])



# ======================================================================
# COL E — 14 · Chương trình & học kỳ ; 15 · Tìm kiếm & học sâu
EX, EW = 4780, 1540
JY_TOP = 2440 + Z12H + 26 - 26
zone(EX, 440, EW, 1180, "14", "Chương trình · học kỳ", "Kế hoạch 4 năm Computer Engineering · S1 → Tết → S2 → Hè → … → S8", "#F6F4EE", new=True)
ey = card(EX + 28, 556, EW - 56, None, "", "Bộ chuyển kỳ · n8n 00:15 → semester.py", "thay tác vụ hằng ngày của ChatGPT (03/10/2026) · mốc ở semester_calendar.json",
     ["Lịch: kỳ lẻ 24/08 → 18/01 · Tết 19/01 → 15/02 · kỳ chẵn 16/02 → 18/07 · hè 19/07 → 23/08 (Tết âm lịch: sửa overrides)",
      "Sang kỳ mới: Pass → Completed; Fail → học lại kỳ sau (Original Semester, Retake, ghi chú); chưa có điểm / chưa học → hỏi",
      "“Đang học” CHỈ lấy từ TKB: Copilot nhận TKB cả kỳ (nhap_tkb · xem trước → ghi) · S5: hỏi chọn Module",
      "Vào Tết: 4 task “Khai xuân” · vào hè: phiếu ☀️ + hỏi học hè / nghỉ / thực tập · mỗi ngày: tính lại tín chỉ",
      "Câu hỏi nằm trong Exception Queue → trả lời bằng lời với Copilot (ghi_hoc_tap: he / module / doi_mon)"], fill="#fff", accent=TEAL) + 20
half = (EW - 56 - 20) // 2
ey2 = row(ey, [
    (EX + 28, half, "", "Dữ liệu (Notion)", "", ["2️⃣ Courses — Semester, Module, Credits, Result, Retake, Học cải thiện, Vắng/Điểm/Nhóm HP (trường)", "🔁 Lần học — mọi lần học đã kết thúc (trượt bao nhiêu lần cũng đủ)",
      "🗓️ Semesters · Semester State", "☀️ Summer Planning", "📊 Grades & Transcript · 🧑‍🏫 Attendance",
      "📝 Exam Revision · 📅 Weekly Reviews · checks.py → bản tin 07:20/21:30 (chỉ báo khi có vấn đề)"], INK),
    (EX + 28 + half + 20, half, "", "Xem · nói với Copilot", "", ["Tab Lịch (tuần + tháng, chọn theo ngày) · tab Học kỳ (2026.1 … 2029.2 bấm được: GPA, CPA, nợ tín, trạng thái)",
      "Thanh bên: GDTC tự chọn · Kỳ hè (học hè ≤ 8 TC / nghỉ / thực tập) · Học lại + Học cải thiện — ghi khi bấm Xác nhận",
      "Tab ĐK tốt nghiệp: ≥ 128 tín → ngoại ngữ + CPA ≥ 2.0 · hạng dự kiến (Giỏi+ hạ 1 mức khi học lại > 5% hoặc kỷ luật)",
      "GPA/CPA theo QCĐT 2025: GPA kỳ gồm cả điểm F · CPA lấy lần điểm cao nhất · trường công bố thì lấy số của trường",
      "Nói tự nhiên: luật môn, điểm, buổi vắng, rèn luyện → ghi_hoc_tap (academic.py tính điểm, không để AI tự tính)",
      "→ Courses là gốc để A1, A2, Lecture Analysis khớp môn"], INK)])
# --- Trục 4 năm (tỉ lệ theo tuần thật)
CY = ey2 + 58
text(EX + 28, CY - 44, "CHƯƠNG TRÌNH 4 NĂM · TỈ LỆ THEO TUẦN", 17, INK2, 600, F_HEAD, ls=2.5)
segs = [("odd", 147), ("tet", 28), ("even", 153), ("he", 36)]      # 24/08–18/01 · 19/01–15/02 · 16/02–18/07 · 19/07–23/08
tot = sum(d for _, d in segs)
cx0, cx1 = EX + 148, EX + EW - 40
for yr in range(4):
    yy = CY + yr * 78
    text(EX + 28, yy + 33, f"Năm {yr + 1}", 19, INK, 600, F_HEAD)
    x = cx0
    for kind, days in segs:
        w = (cx1 - cx0) * days / tot
        fill, lab, fc = {"odd": ("#DCE6F0", f"S{yr * 2 + 1}", INK), "even": ("#DCE6F0", f"S{yr * 2 + 2}", INK),
                         "tet": ("#F3D3D8", "Tết", RED), "he": ("#FFF0B8", "Hè", INK)}[kind]
        rect(x, yy, w - 4, 46, fill, INK3, 1)
        text(x + 12, yy + 31, lab, 19 if kind in ("odd", "even") else 16, fc, 700 if kind in ("odd", "even") else 600, F_HEAD)
        if kind == "odd" and yr == 2:
            text(x + 70, yy + 31, "→ chọn Module 1 / 2 / 3", 16, TEAL, 600)
        if kind == "he" and yr < 3:
            text(x + 6, yy + 62, "học hè / nghỉ / thực tập", 12, INK2)
        x += w
    if yr == 3:
        text(cx1 - 6, yy + 31, "■ dừng", 15, RED, 700, F_HEAD, "end")
# bạn ở đây: 03/10 = ngày 40 kể từ 24/08
hx = cx0 + (cx1 - cx0) * 41 / tot
add(f'<path d="M{hx} {CY - 14}V{CY + 60}" stroke="{RED}" stroke-width="3"/>')
add(f'<circle cx="{hx}" cy="{CY - 14}" r="8" fill="{RED}"/>')
text(hx + 14, CY - 8, "Bạn ở đây · S1 · tuần 5 · 04/10/2026", 16, RED, 700)

zone(EX, 1660, EW, JY_TOP - 1660 - 20, "15", "Tìm kiếm · học sâu", "Ba tầng: tìm trong kho → tìm ngoài Internet → học sâu", "#F6F4EE", new=True)
fy = 1776
fy = row(fy, [
    (EX + 28, half, "", "Tìm trong kho", "Copilot · công cụ tim_tai_lieu",
     ["Lọc 📚 Course Materials theo từ khoá, Course, Type, Summary; kèm Suggested Today + lý do",
      "Hỏi Copilot “tìm tài liệu Giải tích” → não Copilot gọi tim_tai_lieu",
      "File gốc: Uni-Documents (D:) · bản lưu Drive"], INK),
    (EX + 28 + half + 20, half, "", "Tìm ngoài · Research Hub", "n8n 15 phút + chạy ngay · research.py · SearXNG (Docker :8888)",
     ["Copilot nghien_cuu → 🔍 Research Requests → tìm bằng SearXNG trên máy (Google/Bing/…)",
      "Gemini Flash-Lite chỉ CHỌN trong kết quả thật + chú thích (hết quota → LM Studio); link phải mở được",
      "→ 🌐 Research Results · tối đa 3 kết quả tốt nhất của một môn → 📥 University Inbox → A2 → 📚 Course Materials",
      "Đọc lại: doc_ket_qua_nghien_cuu · tim_tai_lieu (URL nằm trong Keywords)"], TEAL)]) + 20
row(fy, [
    (EX + 28, half, "", "Học sâu · NotebookLM", "Notion → Google Drive → NotebookLM",
     ["🧠 NotebookLM Inbox: Copilot gửi bằng gui_notebooklm (kèm link Drive)", "Drive là cầu nối (NotebookLM không có API) · bạn bấm Add source"], INK),
    (EX + 28 + half + 20, half, "", "Hỏi thầy AI · #teaching", "🎓 Hội đồng Giảng dạy · AgentChattr",
     ["Hỏi đáp môn học với các ghế AI theo “casting”; hồ sơ khó chuyển #council",
      "Trang hướng dẫn trong Notion còn ghi Kimi — đã rời hội đồng 02/10"], INK)])

# ======================================================================
# COL F — 16 · Đồng bộ trường (qldt + iCTSV → Notion)
FX, FW = 6360, 1560
zone(FX, 440, FW, 1940, "16", "Đồng bộ trường", "qldt (eHUST web) + iCTSV → Notion · không còn nhập tay TKB, vắng, điểm, rèn luyện", "#F3F6F2", new=True)
gy_ = card(FX + 28, 556, FW - 56, None, "", "Đọc trường · school_fetch.py", "Playwright · Chrome thật · hồ sơ riêng D:\\Tools\\uc-sync\\chrome-profile (không đụng Chrome chính)",
     ["qldt: TKB chi tiết (tuần, tiết, phòng, online), vắng theo điểm danh, bảng điểm chi tiết + tổng hợp, khung CTĐT 8 kỳ",
      "iCTSV: điểm rèn luyện + hoạt động ngoại khoá đã đăng ký, hạn nộp minh chứng, đang mở, học bổng (API JSON của chính trang, chỉ đọc) → Mục 17",
      "qldt: chỉ đọc bảng trang hiển thị — API qldt đã mã hoá, không phá lớp mã hoá",
      "Hết phiên → tự đăng nhập: qldt → e.hust SSO → Microsoft → ADFS (sso / asso.hust.edu.vn) · iCTSV: bấm qua hộp “Phiên đăng nhập đã hết hạn”",
      "Mật khẩu: Windows Credential Manager, bạn tự cất (school_cred.py) · chỉ điền trên 3 trang đăng nhập · 1 lần/lượt · sai → khoá",
      "Xác minh 2 bước / captcha → dừng, báo trên thanh “Dữ liệu trường”"], fill="#fff", accent=TEAL) + 20
gy_ = card(FX + 28, gy_, FW - 56, None, "", "Ghi Notion · school_sync.py", "web app tự chạy đúng khung 5 phút, 00:00 → 23:55 (máy tắt thì bỏ khung, không chạy bù) · nút Đồng bộ ngay cần Xác nhận",
     ["TKB → 🗓️ Timetable qua tkb.run (khoá Sync Key) · buổi không còn trên qldt → thùng rác Notion",
      "Vắng → Courses “Vắng (trường)” → cảnh báo cấm thi · điểm thành phần, điểm HP, kết quả → Courses",
      "GPA / CPA / TC tích luỹ / TC nợ / cảnh báo theo kỳ → Tracker · điểm rèn luyện → ⭐ Rèn luyện",
      "Khung CTĐT → thêm môn Notion thiếu (cả môn tự chọn) · kỳ dự kiến môn bắt buộc chưa học",
      "Mọi thay đổi → 🏫 Đồng bộ trường · thanh “🏫 Dữ liệu trường” ở tab Học kỳ"], fill="#fff", accent=INK) + 20
LAW_T1 = "Không dữ liệu local nào vượt mặt trường (qldt · iCTSV · thư trường · Teams). THIẾU → thêm theo trường. TRANH CHẤP / trùng thông tin → trường thắng, kể cả giá trị bạn hay Copilot nhập tay, kể cả hạn đã qua (vd Quiz 04: 11/10 → 7/10 theo Teams)."
LAW_T2 = "THỪA (môn Module chưa hiện hết, luật môn, deadline tự đặt, ghi chú) → giữ nguyên. Thứ tự: TKB / bảng điểm / thông báo GV mới nhất > khung CTĐT > local. Áp từ 20261 tới hết khoá."
law_h = 86 + len(wrap(LAW_T1, FW - 110, 19)) * 19 * 1.38 + 10 + len(wrap(LAW_T2, FW - 110, 18)) * 18 * 1.38 + 6
rect(FX + 28, gy_, FW - 56, law_h, "#fff", RED, 2.6)
rect(FX + 28, gy_, 430, 48, RED, RED, 0)
text(FX + 48, gy_ + 33, "LUẬT TỐI CAO · MỌI KỲ", 20, "#fff", 700, F_HEAD, ls=1.5)
ly_ = para(FX + 52, gy_ + 86, LAW_T1, FW - 110, 19, INK, weight=600)
para(FX + 52, ly_ + 10, LAW_T2, FW - 110, 18, INK2)
gy_ += law_h + 26
gy_ = card(FX + 28, gy_, FW - 56, None, "", "Thao tác ghi luôn hỏi lại", "không ghi ngầm (04/10/2026)",
     ["Đổi chế độ ngày ⛺ / 💤 · chọn kỳ hè · xếp học lại · học cải thiện · đồng bộ ngay: hiện việc sẽ xảy ra → Xác nhận / Hủy",
      "Máy chủ từ chối mọi yêu cầu ghi thiếu confirmed: true"], fill="#fff", accent=INK) + 40
# luồng dữ liệu trường → UC
text(FX + 28, gy_, "LUỒNG MỘT LƯỢT ĐỒNG BỘ", 17, INK2, 600, F_HEAD, ls=2.5)
flow = [("qldt · iCTSV", "trang web của trường (Office 365 / ADFS)", "#fff", INK),
        ("Chrome hồ sơ đồng bộ", "mở → tự đăng nhập nếu hết phiên → đọc bảng → đóng", "#fff", TEAL),
        ("school/latest.json", "ảnh chụp dữ liệu (giữ 30 bản) · lượt lỗi chỉ ghi fetch_last.json, không đè bản tốt", "#fff", INK2),
        ("school_sync.py", "so với Notion theo luật tối cao · không đổi thì không ghi", "#fff", RED),
        ("Notion", "Timetable · Courses · Tracker · ⭐ Rèn luyện · 🏫 Đồng bộ trường · 🎯 Ngoại khoá", "#fff", INK),
        ("University Copilot", "tab Lịch · Học kỳ · Hôm nay · Ngoại khoá · cảnh báo cấm thi · bản tin", "#fff", INK)]
bx, bw, bh, gap_ = FX + 120, FW - 240, 62, 30
yy_ = gy_ + 26
for i, (t_, sub_, fl, ac) in enumerate(flow):
    rect(bx, yy_, bw, bh, fl, ac, 2)
    add(f'<rect x="{bx}" y="{yy_}" width="6" height="{bh}" fill="{ac}"/>')
    text(bx + 22, yy_ + 27, t_, 20, INK, 600, F_HEAD)
    text(bx + 22, yy_ + 51, sub_, 16, INK2)
    if i < len(flow) - 1:
        path([(bx + bw / 2, yy_ + bh), (bx + bw / 2, yy_ + bh + gap_)], INK, 2.2)
    yy_ += bh + gap_

# ======================================================================
# COL G — 17 · Thư trường · Teams · Ngoại khoá ; 18 · Nhắc · điện thoại   (04/10 chiều)
GX, GW = 7960, 1760
Z17_H = 1110
zone(GX, 440, GW, Z17_H, "17", "Thư · Teams · Ngoại khoá", "Đọc thay bạn mọi kênh của trường — chỉ đọc, đúng khung 5 phút suốt 24 giờ, cùng một hồ sơ Chrome", "#F3F6F2", new=True)
gh = (GW - 56 - 20) // 2
g1 = row(556, [
    (GX + 28, gh, "", "Thư trường · school_mail.py", "Outlook REST bằng token của chính trang",
     ["Không mở thư → không đổi “đã đọc”; không gửi / xoá / di chuyển", "→ school/mail/inbox.json (giữ 400 thư)"], INK),
    (GX + 28 + gh + 20, gh, "", "Teams · teams_fetch.py", "Graph bằng token trang Teams web",
     ["Mọi lớp, cả kênh ẩn: bài đăng (mỗi lần SỬA bài = 1 phiên bản), thẻ Assignments (hạn), file trong kênh + Shared Documents",
      "MOOC soict.daotao.ai (mooc.py, “Đăng nhập bằng HUST”): hạn + ĐIỂM bài → thêm / sửa hạn, có điểm = Hoàn tất, quá hạn 0 điểm = báo bỏ lỡ"], INK)]) + 20
g2 = card(GX + 28, g1, GW - 56, None, "", "Trích sự kiện · mail_events.py", "Gemini Flash-Lite (cổng :8350, caller mail) CHỈ trích dữ liệu · code so sánh",
     ["Thư / bài sửa cùng chủ đề → dòng “Trước → Nay” (so chữ, không AI) — vd phòng 2 “101-200 → 101-205”",
      "Nhóm học tập / ngoại khoá · bạn tham gia (đã đăng ký, bắt buộc) hay lời mời chung (chỉ gợi ý, không đẩy điện thoại)",
      "Lịch lớp (lop-MÃ): đổi phòng / giờ trên Teams → sửa thẳng buổi Class trong lịch (vd IT2000 1/10 → B1-504)",
      "Bài tập (bt-MÃ) → 📋 Academic Work “Môn học” · hạn tranh chấp → sửa theo Teams + lịch + việc con, báo “Thay đổi” (luật tối cao)",
      "Mốc “ngày mai” tính theo giờ ĐĂNG gốc, giờ gửi thư không bao giờ là giờ diễn ra"], fill="#fff", accent=TEAL) + 20
g3 = row(g2, [
    (GX + 28, gh, "", "Tài liệu hai chiều · teams_files.py", "chống trùng bằng SHA-256 cả Uni-Documents",
     ["Teams → đúng thư mục môn / loại (đặt cạnh file cùng tên)", "📥 Notion → máy (không nạp lại) · file thả ở gốc môn → tự vào thư mục loại",
      "Tranh chấp phiên bản: bản trên Teams (trường) luôn thắng, bản cũ rời kho — file trên máy giữ cả hai"], INK),
    (GX + 28 + gh + 20, gh, "", "Ngoại khoá · extracurricular.py", "CTSV + mail / Teams → 🎯 · tab Ngoại khoá",
     ["Đã đăng ký (Chờ / Đã xác nhận) · hạn nộp minh chứng (điểm rèn luyện)",
      "Một danh sách “có thể đăng ký”: CTSV + thư / Teams, xếp theo ngày công bố, ghi nguồn, link đăng ký thẳng · trùng → giữ bản CTSV",
      "Lịch tuần + tháng riêng, KHÔNG lẫn vào lịch học / hạn học tập"], INK)]) + 20
G17_END = card(GX + 28, g3, GW - 56, None, "", "Quét trùng · dupscan.py", "sau mỗi lượt đồng bộ trường + mỗi lượt thư / Teams",
     ["Hạn còn mở lệch ≤ 2 giờ + tên giống · dòng lịch cùng ngày · sự kiện trùng buổi học",
      "Gắn 2 môn khác nhau = 2 việc thật, không bao giờ là trùng (vd “Vá hổng Chương I” của MI1111 và MI1141)",
      "Không tự xoá: tab Hôm nay “Có thể trùng” → Giữ cả hai / Bỏ bản này → Xác nhận (liệt kê đủ) → thùng rác Notion"], fill="#fff", accent=RED)

Z18_Y = 440 + Z17_H + 40
zone(GX, Z18_Y, GW, 2380 - Z18_Y, "18", "Nhắc · điện thoại", "alerts.py mỗi phút · toast Windows + 🔔 UC + ntfy · LUẬT: kệ giờ, phải đúng mốc · hạn mới báo NGAY khi xuất hiện, rồi theo mốc", "#FFF6F6", new=True)
# bảng mốc nhắc
ty = Z18_Y + 120
text(GX + 28, ty, "MỐC NHẮC", 17, INK2, 600, F_HEAD, ls=2.5)
tbl = [("Tiết học (TKB)", "30 · 15 phút trước — giờ + phòng (đã đổi theo Teams)", INK),
       ("Hạn · Tự luyện", "72 · 48 · 36 · 24 giờ", INK),
       ("Hạn · Tự luyện cốt lõi", "+ 7 · 5 · 3 · 1 giờ · 30 · 20 · 10 phút", "#B26A00"),
       ("Hạn · Môn học", "+ 10 · 5 · 3 · 1 giờ · 30 · 20 · 10 · 5 · 2 · 1 phút", RED),
       ("Sự kiện bạn tham gia", "≤72 h vàng · ≤24 h đỏ · trong ngày ghim tới khi “Sẽ đi / Bỏ”", INK),
       ("Đính chính (Trước → Nay)", "đỏ ngay, tới khi “Đã biết”", RED),
       ("Ngoại khoá đã đăng ký", "24 giờ · 2 giờ trước · hạn minh chứng như tự luyện cốt lõi", INK)]
ty += 14
for k_, v_, c_ in tbl:
    rect(GX + 28, ty, GW - 56, 38, "#fff", INK3, 1)
    add(f'<rect x="{GX + 28}" y="{ty}" width="6" height="38" fill="{c_}"/>')
    text(GX + 48, ty + 26, k_, 18, c_, 700, F_HEAD)
    text(GX + 420, ty + 26, v_, 17, INK)
    ty += 43
para(GX + 28, ty + 18, "Loại hạn do agent (Gemini) xếp theo định nghĩa của bạn, ghi vào Notion; bạn sửa tay thì giữ. Tích Hoàn tất ở tab Hôm nay → hạn biến mất; “Tắt nhắc” chỉ tắt thông báo.", GW - 56, 17, INK2)
g4 = row(ty + 64, [
    (GX + 28, gh, "", "Điện thoại · ntfy", "kênh thông báo + kênh lệnh riêng",
     ["Nút Sẽ đi / Bỏ / Đã biết: lệnh có chữ ký HMAC, dùng 1 lần, luôn hỏi Xác nhận",
      "KHÔNG có Hoàn tất / Tắt nhắc trên điện thoại",
      "Gõ / bấm “hôm nay” · “mai” · “hạn” → UC trả lời (máy phải thức)"], TEAL),
    (GX + 28 + gh + 20, gh, "", "Khi laptop ngủ", "phone_sched.py · phone_page.py",
     ["Máy thức: hẹn sẵn trên ntfy mọi lần nhắc 70 giờ tới (mỗi lần 1 mã → sửa / huỷ được)",
      "📱 University Copilot — trang Notion riêng, cấp cao nhất, dựng giống UC (ô màu, bảng tiết học, hạn, ngoại khoá, tuần này); chỉ ghi khi nội dung đổi",
      "Notion lỗi → giữ nguyên lịch hẹn, không huỷ nhầm"], TEAL)])

# ======================================================================
# COL H — 19 · Nguồn thông tin của UC: trang nào, đọc gì, bằng cách nào, có tự động không (04/10)
HX, HW = 9760, 1960
zone(HX, 440, HW, 1940, "19", "Nguồn thông tin của UC", "UC TỰ đọc các trang này — bạn không phải mở, chép hay báo lại. Tất cả CHỈ ĐỌC.", "#F2F4FA", new=True)
SRC = [  # (trang, đọc gì, cách đọc, đăng nhập, nhịp, mức tự động, màu)
    ("qldt.hust.edu.vn", "TKB chi tiết (phòng, tuần, online) · vắng · bảng điểm · khung CTĐT", "đọc bảng trên trang (API trường mã hoá)",
     "e.hust SSO → Microsoft → ADFS, tự điền từ Credential Manager", "khung 5 phút, 24 giờ", "Tự động", TEAL),
    ("ctsv.hust.edu.vn (iCTSV)", "điểm rèn luyện · hoạt động (1000 dòng) · hạn minh chứng · học bổng · thông báo · giấy tờ · thủ tục · đặt vé", "API JSON của chính trang",
     "bấm qua “Phiên hết hạn” → ADFS asso", "5 phút", "Tự động · công nợ: chỉ link", TEAL),
    ("Outlook · thư trường", "thư gửi bạn: lịch thi, đính chính, xác nhận đăng ký, thông báo", "Outlook REST bằng token của trang",
     "phiên Microsoft của hồ sơ Chrome", "khung 5 phút, 24 giờ", "Tự động · không đổi “đã đọc”", TEAL),
    ("Teams", "bài đăng mọi lớp, cả kênh ẩn (sửa bài = phiên bản mới) · thẻ bài tập (hạn) · file + Shared Documents (công thức điểm)", "Microsoft Graph bằng token của trang",
     "phiên Microsoft", "5 phút", "Tự động", TEAL),
    ("soict.daotao.ai (MOOC)", "hạn + ĐIỂM bài trước lớp / lab → biết đã làm hay bỏ lỡ · khoá Sinh hoạt công dân", "API Open edX (progress)",
     "“Đăng nhập bằng HUST” → phiên Microsoft", "5 phút", "Tự động", TEAL),
    ("fami.hust.edu.vn/sohoa (FAMI)", "học phần mã MI: thi theo chương (CĐ1…10, mở / đóng theo tuần), điểm danh, điểm QT — bài ngầm, không có trên Teams / MOOC", "API của chính trang (Bearer của trang)",
     "“Đăng nhập bằng Microsoft Teams” → phiên Microsoft", "5 phút", "Tự động", TEAL),
    ("Notion · 📥 University Inbox", "file bạn tải thẳng lên Notion → kéo về Uni-Documents", "Notion API qua n8n",
     "tích hợp n8n", "5 phút", "Tự động", TEAL),
    ("Uni-Documents (ổ D:)", "file bạn thả vào → xếp môn / loại, chống trùng, lên Drive + Notion", "quét thư mục",
     "—", "mỗi phút", "Tự động", TEAL),
    ("Điện thoại · kênh lệnh ntfy", "nút Sẽ đi / Bỏ / Đã biết (có chữ ký) · lệnh hôm nay / mai / hạn", "ntfy stream",
     "—", "liên tục khi máy thức", "Tự động · ghi luôn hỏi Xác nhận", INK)]
sy_ = 556
cw_ = [330, 560, 330, 360, 240]
heads = ["Trang", "Đọc gì", "Cách đọc", "Đăng nhập", "Bao lâu"]
xx_ = HX + 28
for hd, w_ in zip(heads, cw_):
    text(xx_ + 10, sy_ + 26, hd.upper(), 15, INK2, 700, F_HEAD, ls=1.5); xx_ += w_
sy_ += 40
for (pg_, what, how, login, when, auto, col) in SRC:
    cells = [pg_, what, how, login, when]
    lines = [wrap(c, w_ - 24, 16 if i else 17) for i, (c, w_) in enumerate(zip(cells, cw_))]
    rh = max(len(l) for l in lines) * 23 + 42
    rect(HX + 28, sy_, HW - 56, rh, "#fff", INK3, 1)
    add(f'<rect x="{HX + 28}" y="{sy_}" width="6" height="{rh}" fill="{col}"/>')
    xx_ = HX + 28
    for i, (ls_, w_) in enumerate(zip(lines, cw_)):
        for j, ln in enumerate(ls_):
            text(xx_ + 14, sy_ + 26 + j * 23, ln, 17 if i == 0 else 16, INK if i else col, 700 if i == 0 else 400, F_HEAD if i == 0 else F_BODY)
        xx_ += w_
    text(HX + 42, sy_ + rh - 10, "● " + auto, 14, TEAL if auto.startswith("Tự động") else INK2, 600)
    sy_ += rh + 8
# mức tự động
sy_ += 18
auto_box = [("Tự động hoàn toàn", "đọc 9 nguồn trên · tự đăng nhập lại khi hết phiên · ghi Notion theo luật tối cao · nhắc toast + 🔔 + điện thoại · hẹn trước khi laptop ngủ · quét trùng", TEAL),
            ("Cần bạn", "Microsoft hỏi xác minh 2 bước / captcha (UC dừng, báo) · đổi mật khẩu trường (chạy school_cred.py) · tích Hoàn tất bài tự đặt · chọn khi “Có thể trùng” · Sẽ đi / Bỏ sự kiện", RED),
            ("Chỉ chạy khi", "laptop thức (gập máy = ngủ): nhắc đã hẹn vẫn tới qua ntfy ≤ 3 ngày; thư / Teams / MOOC mới đọc lại khi máy thức", INK2)]
for k_, v_, c_ in auto_box:
    hh_ = len(wrap(v_, HW - 400, 17)) * 24 + 26
    rect(HX + 28, sy_, HW - 56, hh_, "#fff", c_, 2)
    text(HX + 48, sy_ + 30, k_, 19, c_, 700, F_HEAD)
    para(HX + 330, sy_ + 30, v_, HW - 400, 17, INK)
    sy_ += hh_ + 12
SRC_END = sy_
# một lượt 5 phút (mail_run) — chuỗi tự động
text(HX + 28, sy_ + 20, "MỘT LƯỢT 5 PHÚT · KHÔNG CẦN BẠN", 17, INK2, 600, F_HEAD, ls=2.5)
chain = [("Thư", "school_mail"), ("Teams", "teams_fetch"), ("File Teams", "teams_files"), ("MOOC", "mooc"), ("FAMI · MI", "fami"), ("Hết hạn → ✅ Tasks", "expired"),
         ("📥 Notion → máy", "teams_files"), ("Trích sự kiện", "mail_events"), ("Phân loại thư", "mail_kinds"), ("Bài tập → 📋", "deadlines"), ("Công thức điểm", "course_detail"),
         ("CTSV nhanh", "ctsv_live"), ("🎯 Ngoại khoá", "extracurricular"), ("Quét trùng", "dupscan"), ("Hẹn ntfy · 📱", "phone_sched / page")]
per = 4; bw_ = (HW - 56 - (per - 1) * 46) / per; bh_ = 64
cy0 = sy_ + 40
for i, (t_, m_) in enumerate(chain):
    r_, c_ = divmod(i, per)
    if r_ % 2: c_ = per - 1 - c_   # chạy rắn: hàng chẵn trái→phải, hàng lẻ phải→trái
    x_ = HX + 28 + c_ * (bw_ + 46); y_ = cy0 + r_ * (bh_ + 40)
    rect(x_, y_, bw_, bh_, "#fff", TEAL if i < 7 else INK, 1.8, rx=8)
    text(x_ + 16, y_ + 28, t_, 18, INK, 700, F_HEAD)
    text(x_ + 16, y_ + 51, m_ + ".py" if "/" not in m_ else m_, 14, INK3, 400, F_MONO)
    if i < len(chain) - 1:
        r2, c2 = divmod(i + 1, per)
        if r2 % 2: c2 = per - 1 - c2
        if r2 == r_:
            a_ = x_ + bw_ if c2 > c_ else x_; b_ = a_ + 46 if c2 > c_ else a_ - 46
            path([(a_, y_ + bh_ / 2), (b_, y_ + bh_ / 2)], INK, 2, halo=False)
        else:
            path([(x_ + bw_ / 2, y_ + bh_), (x_ + bw_ / 2, y_ + bh_ + 40)], INK, 2, halo=False)
SRC_END = cy0 + ((len(chain) - 1) // per + 1) * (bh_ + 40)

# ======================================================================
# COL I — 20 · Hành chính · Học bổng · Học phần · NotebookLM   (05–06/10)
IX, IW = 11760, 1960
zone(IX, 440, IW, 1940, "20", "Hành chính · Học bổng · Học phần", "Phần hành chính của trường gom về UC — chỉ đọc, link dẫn thẳng tới trang đăng ký · UC không làm giảng viên", "#F6F3FA", new=True)
ih = (IW - 56 - 20) // 2
iy = card(IX + 28, 556, IW - 56, None, "", "CTSV nhanh · ctsv_live.py", "mở /thong-bao một lần rồi gọi API của chính trang · 5 phút/lần · chỉ đọc",
     ["Sự kiện / hoạt động 1000 dòng (như /danh-sach-su-kien): mô tả, tiêu chí điểm rèn luyện, link đăng ký thẳng",
      "Thông báo gửi riêng · giấy tờ đã xin + trạng thái · thủ tục có thể xin (bấm là mở form)",
      "Đặt vé: sự kiện sắp tới + vé của bạn (đọc lại phản hồi trang, không giữ mã phiên) · vé tự ẩn khi sự kiện đã qua",
      "Công nợ có reCAPTCHA → chỉ đưa link, không tự tra, không vượt captcha"], fill="#fff", accent=TEAL) + 20
iy = card(IX + 28, iy, IW - 56, None, "", "Phân loại thư · mail_kinds.py", "luật trước (0 quota) → còn lại gom lô 30 thư / 1 lần Gemini Flash-Lite",
     ["môn học → Lịch · ngoại khoá → Ngoại khoá · hành chính + thông báo chung → Hành chính · học bổng → Học bổng",
      "Thư tự động của Teams (được thêm vào nhóm, được nhắc tên) → thông báo chung, không phải hoạt động"], fill="#fff", accent=INK) + 20
iy = row(iy, [
    (IX + 28, ih, "", "Tab Hành chính", "CTSV + thư hành chính + thông báo chung",
     ["Thủ tục, giấy tờ, thông báo, đặt vé — mỗi mục có link đính kèm dẫn thẳng tới trang đăng ký"], INK),
    (IX + 28 + ih + 20, ih, "", "Tab Học bổng · scholarships.py", "tách khỏi Ngoại khoá (05/10)",
     ["Đang mở / đã đóng theo ngày công bố thật · giá trị · liên hệ · mô tả"], INK)]) + 20
iy = card(IX + 28, iy, IW - 56, None, "", "Lọc thông báo cũ · stale_filter.py", "luật của bạn (05/10) · không gọi AI",
     ["Có ghi ngày → chỉ giữ khi còn ít nhất một ngày chưa qua (ngày không ghi năm lấy năm của thông báo)",
      "Không ghi ngày → cũ hơn 90 ngày thì ẩn · năm n không hiện thông báo năm n-1 (trừ khi hạn kéo sang năm n)",
      "Áp cho thông báo CTSV, thư Hành chính và thông báo thư / Teams ở Ngoại khoá · số mục bị ẩn hiện ngay trên tab"], fill="#fff", accent=RED) + 20
iy = card(IX + 28, iy, IW - 56, None, "", "Chi tiết học phần · course_detail.py", "tab Học kỳ → bấm một môn",
     ["Lớp thành phần (LT / BT / TN) + điểm thành phần từ bảng điểm qldt",
      "Công thức điểm cho MỌI môn, tự động mọi kỳ: bài đăng + trả lời trong luồng ở mọi kênh, Class Notebook, trang được dẫn tới, NỘI DUNG mọi slide / đề cương / file (Tika đọc, mỗi file một lần) → Gemini chỉ đọc lại khi nguồn đổi",
      "Nguồn từng thành phần theo tên: liên tục → FAMI · giữa kỳ / thực hành → qldt · MOOC → bài tuần · chuyên cần",
      "Cuối kỳ cần bao nhiêu điểm cho từng mức A+ … D"], fill="#fff", accent=INK) + 20
card(IX + 28, iy, IW - 56, None, "", "Gửi tài liệu sang NotebookLM · nlm_bridge.py", "tab Inbox · chỉ chạy khi bạn bấm, luôn hỏi Xác nhận",
     ["Tìm trong Uni-Documents → tích chọn → thêm vào notebook có sẵn hoặc tạo notebook mới",
      "UC dừng ở đó: không tạo task ôn, không ghi Notion, không gọi AI — UC lo hành chính, việc học bạn làm trong NotebookLM",
      "Phiên Google: tác vụ “NotebookLM keepalive” 20 phút/lần; Google bắt đăng nhập tay → cửa sổ Chrome ở lại tới khi đăng nhập (đóng là mở lại)"], fill="#fff", accent=TEAL)

# ======================================================================
# Hành trình bản 1 -> bản 2
JY = 2440 + Z12H + 26
JH = 3000 - JY
rect(80, JY, W - 160, JH, "#fff", INK, 2.4)
rect(80, JY, 340, JH, INK, INK, 0)
text(100, JY + 44, "HÀNH TRÌNH", 26, "#fff", 600, F_HEAD, ls=2)
text(100, JY + 74, "bản 1 → bản 5", 19, "#C9D3DD")
miles = [("08/2026", "Bản 1 (Codex): 10 mục, 6 agent rời rạc, hội đồng 5 ghế có Kimi"),
         ("01–02/10", "Gộp 16 workflow thành 1 “Copilot hợp nhất” + web app một cửa"),
         ("02/10", "Kimi rời hội đồng · Local AI (qwen3-14b) vào ghế phản biện · bộ giữ ghế"),
         ("02/10", "Xoá 8 bản ghi âm tự động · recorder v2 chỉ ghi khi bấm · cổng chép lời + cổng Gemini"),
         ("03/10", "PhoWhisper lên NPU (nhanh ~4,6×) · Local AI khung 16k, ngân sách token"),
         ("03/10", "AgentChattr một cửa khởi động, chặn server trùng"),
         ("03/10", "Bản 2: tầng học kỳ, tìm kiếm ngoài n8n, chế độ ngày, đánh giá tuần")
         ,("03/10", "Theo QCĐT 2025: lần học, học lại / cải thiện, hạng tốt nghiệp, mọi ghi đều hỏi lại")
         ,("04/10 sáng", "Bản 3: đồng bộ qldt + iCTSV, dữ liệu trường là cao nhất")
         ,("04/10 trưa", "Đọc thư trường + Teams · đính chính = Trước → Nay · nhắc leo thang, toast + điện thoại")
         ,("04/10 chiều", "Bản 4: hạn 3 mức · nhắc tiết học · ngoại khoá CTSV · quét trùng · nhắc cả khi laptop ngủ")
         ,("04/10 tối", "MOOC SoICT + FAMI (thi theo chương MI) · việc hết hạn → Academic Tasks · bản đồ nguồn (Mục 19)")
         ,("05/10 trưa", "Chat trung thực + nhớ hội thoại · dời hạn tự đặt · ghi Teams qua cáp riêng · giám sát Ghi bài giảng")
         ,("05/10 tối", "Tab Hành chính + Học bổng · phân loại thư · CTSV 1000 dòng · mọi nguồn 5 phút/lần")
         ,("06/10", "Bản 5: chi tiết điểm học phần · gửi tài liệu sang NotebookLM · lọc thông báo hết hạn")]
mx0, mx1 = 460, W - 110
step_w = (mx1 - mx0) / len(miles)
add(f'<path d="M{mx0} {JY + 30}H{mx1}" stroke="{INK}" stroke-width="2"/>')
for i, (d_, t_) in enumerate(miles):
    xx = mx0 + i * step_w
    add(f'<circle cx="{xx + 8}" cy="{JY + 30}" r="8" fill="{RED if i == len(miles) - 1 else INK}"/>')
    text(xx + 26, JY + 37, d_, 19, INK, 700, F_HEAD)
    para(xx + 8, JY + 66, t_, step_w - 40, 17, INK2, lh=1.3)
# ======================================================================
# Row 13 — Nền máy
zone(80, 3020, 2280, 300, "13", "Nền máy", "", "#F6F7F9", new=True)
row(3092, [
    (108, 1110, "", "Khởi động cùng Windows", "Task Scheduler · lúc đăng nhập",
     ["“University Copilot - khoi dong” → open_copilot.ps1: LM Studio, phòng chat, relay, web app, 2 cổng, companion, Docker",
      "“AgentChattr - 4 ghe AI” (+60 s) → AgentChattr.ps1: server + seat_keeper; shortcut “agentchattr - daily” làm y hệt rồi mở app"], INK),
    (1238, 1094, "", "Intel Core Ultra 7 258V", "32 GB RAM · pagefile 16 GB trên D:",
     ["CPU: n8n (Docker / WSL), web app, các cổng · GPU Arc 140V: qwen3-14b",
      "NPU AI Boost: PhoWhisper — chép lời không giành GPU với Qwen"], INK)])

# Constraints
rect(2400, 3020, 1200, 300, "#fff", RED, 2.6)
rect(2400, 3020, 360, 48, RED, RED, 0)
text(2420, 3053, "RÀNG BUỘC TOÀN HỆ THỐNG", 20, "#fff", 700, F_HEAD, ls=1.5)
cons = ["Chỉ ghi âm khi bấm Start, chỉ dừng khi bấm Stop (ngắt an toàn 3 h 30)",
        "Audio không bao giờ tới Gemini; mọi lời gọi Gemini qua cổng :8350",
        "Không chắc → ⚠️ Exception Queue, không đoán · khoá chống trùng ở mọi bước ghi",
        "Webhook nội bộ cần X-Copilot-Key · workflow sinh từ code (build.py)",
        "Chủ tọa quyết định cuối · C: chỉ cho hệ điều hành",
        "Luật tối cao: thiếu → thêm · tranh chấp → trường thắng · thừa → giữ",
        "Ghi trên UI luôn hỏi Xác nhận · mật khẩu chỉ ở Credential Manager · không tự xoá, chỉ thùng rác",
        "Nguồn trường chỉ đọc · bài hết hạn không ghi thành hạn (→ Academic Tasks) · điện thoại không Hoàn tất / Tắt nhắc",
        "UC lo hành chính, không làm giảng viên: không tạo task ôn · chat chỉ báo “đã làm” khi có kết quả thật",
        "Nhắc: kệ giờ, phải đúng mốc · cập nhật cả đêm để không lỡ mốc · hạn mới báo ngay khi xuất hiện"]
cy_ = 3090
for c in cons:
    add(f'<rect x="2424" y="{cy_ - 12}" width="9" height="9" fill="{RED}"/>')
    text(2446, cy_, c, 15, INK); cy_ += 22.5


# Ai chạy cái gì
rect(3640, 3020, W - 1160 - 40 - 3640, 300, "#fff", INK, 2.6)
rect(3640, 3020, 300, 48, INK, INK, 0)
text(3660, 3053, "AI CHẠY CÁI GÌ", 20, "#fff", 700, F_HEAD, ls=1.5)
whos = [("n8n · máy bạn (Docker)", "Mục 1–10, não Copilot, bản tin, hội đồng N9, 2 workflow bài giảng", INK),
        ("Dịch vụ máy bạn", "web app :8320 (trường · thư · Teams · CTSV 5 phút/lần · nhắc + giám sát bài giảng mỗi phút · Chrome hồ sơ riêng), cổng Gemini :8350, chép lời :8340, SearXNG, AgentChattr, LM Studio", INK),
        ("NotebookLM · Google", "nhận tài liệu UC gửi khi bạn bấm — việc ôn bạn tự làm trong đó; phiên giữ bởi tác vụ keepalive 20 phút", TEAL),
        ("ntfy.sh", "đưa nhắc tới điện thoại, giữ hộ lần nhắc đã hẹn (≤ 3 ngày) khi laptop ngủ — không chạy logic", TEAL),
        ("ChatGPT · đám mây", "không còn việc nào — chuyển kỳ, nghiên cứu, kiểm tra ôn thi đã về n8n (03/10/2026)", TEAL),
        ("Notion", "chỉ lưu và hiển thị: database, view, form — tự nó không chạy logic", INK2)]
wy = 3094
for k_, v_, c_ in whos:
    text(3664, wy, k_, 18, c_, 700, F_HEAD)
    text(3664 + 330, wy, v_, 18, INK)
    wy += 37

# Title block
rect(W - 1160, 3020, 1080, 300, "#fff", INK, 2.6)
add(f'<path d="M{W - 1160} 3110H{W - 80}M{W - 1160} 3170H{W - 80}M{W - 1160} 3230H{W - 80}M{W - 1160} 3280H{W - 80}M{W - 620} 3110V3280" stroke="{INK}" stroke-width="1.3"/>')
text(W - 1138, 3058, "HỆ THỐNG UNIVERSITY", 30, INK, 700, F_HEAD, ls=2)
text(W - 1138, 3094, "Bản đồ kiến trúc toàn hệ thống", 19, INK2)
for (x_, y_, k, v) in [(W - 1138, 3150, "Phiên bản", "5 · 06/10/2026"), (W - 600, 3150, "Thay cho", "bản 4 · 04/10/2026 chiều"),
                       (W - 1138, 3210, "Vẽ", "Claude Code"), (W - 600, 3210, "Nguồn", "n8n · Notion · qldt · iCTSV · Teams · mã nguồn"),
                       (W - 1138, 3266, "Tỉ lệ", "không theo tỉ lệ"), (W - 600, 3266, "Tờ", "1 / 1")]:
    text(x_, y_ - 18, k.upper(), 12, INK3, 600, F_HEAD, ls=2)
    text(x_, y_ + 6, v, 19, INK, 500)
text(W - 1138, 3306, "Mục 1–10 giữ số bản 1 · 0, 11–20 là phần mới (17–19 ngày 04/10, 20 ngày 05–06/10)", 15, INK3)

# Legend
LX, LY = 6400, 268
text(LX, LY + 14, "KÝ HIỆU", 17, INK2, 600, F_HEAD, ls=3)
path([(LX, LY + 50), (LX + 90, LY + 50)], INK, 2.2, halo=False); text(LX + 104, LY + 56, "dữ liệu / lời gọi", 16, INK)
path([(LX + 300, LY + 50), (LX + 390, LY + 50)], TEAL, 2.2, halo=False); text(LX + 404, LY + 56, "gọi AI", 16, INK)
path([(LX + 520, LY + 50), (LX + 610, LY + 50)], INK2, 2, "9 7", halo=False); text(LX + 624, LY + 56, "lưu file", 16, INK)
add(f'<path d="M{LX} {LY + 92}H{LX + 90}" stroke="{HL}" stroke-opacity="0.62" stroke-width="22" stroke-linecap="round"/>'); text(LX + 104, LY + 98, "đường bài giảng ①→⑨", 16, INK)
rect(LX + 300, LY + 80, 26, 26, "#fff", RED, 2.2); text(LX + 340, LY + 98, "cổng chặn / ràng buộc", 16, INK)
rect(LX + 580, LY + 80, 60, 26, "#fff", RED, 2); text(LX + 610, LY + 99, "MỚI", 13, RED, 700, F_HEAD, "middle"); text(LX + 652, LY + 98, "phần mới", 16, INK)

# ======================================================================
# CONNECTORS
ANA_BOT = e5
COMP_MID = COMP_Y + 120
L1 = [(1008, COMP_MID), (1048, COMP_MID), (1048, CAP_MID), (X[0], CAP_MID)]
L2 = [(X[0] + CAP_W, CAP_MID), (ANA_X, CAP_MID)]
SG_X1, SG_X2 = AX[3] + 230, AX[3] + 290
L5 = [(SG_X1, ANA_BOT), (SG_X1, AI_Y)]
L7 = [(SG_X2, AI_Y), (SG_X2, ANA_BOT)]
GEM = [(ANA_X + 160, ANA_BOT), (ANA_X + 160, 2408), (AX[0] + 420, 2408), (AX[0] + 420, AI_Y)]
L9 = [(ANA_X + ANA_W, CAP_MID + 40), (3052, CAP_MID + 40), (3052, NOTION_ROW["📚 Lecture Notes"]), (3108, NOTION_ROW["📚 Lecture Notes"])]
for seg in (L1, L2, L5, L7, GEM, L9):
    hl(seg)
path([(960, FRONT_BOTTOM), (960, COMP_Y)], INK, 2.4, label="① Start / Stop", lpos=(944, (FRONT_BOTTOM + COMP_Y) / 2 - 20), lanchor="end")
path(L1, INK, 2.4, label="③", lpos=(1052, CAP_MID - 16), lsize=18)
path(L2, INK, 2.4, label="④", lpos=(X[0] + CAP_W + 6, CAP_MID - 16), lsize=18)
path(L5, INK, 2.4, label="⑤ audio", lpos=(SG_X1 - 10, ANA_BOT + 44), lanchor="end")
path(L7, INK, 2.4, label="⑦ bản nén", lpos=(SG_X2 + 10, ANA_BOT + 44))
path(GEM, TEAL, 2.6, label="Gemini: A1 · A3 · H10 · não Copilot · ⑧ bài giảng", lpos=(AX[0] + 440, 2402), lsize=16)
path(L9, INK, 2.4, label="⑨", lpos=(3030, CAP_MID + 28), lsize=18, lanchor="end")
path([(1008, FA_Y["Chat"] + 60), (1104, FA_Y["Chat"] + 60)], INK, 2.4)
for yy in (R1 + 70, R2 + 70, R3 + 70):
    path([(3022, yy), (3106, yy)], INK, 2.4, arrow="both")
path([(X[2] + CW * 2 + GAP, N9_Y), (3040, N9_Y), (3040, 418), (3862, 418), (3862, RELAY_Y + 40), (3906, RELAY_Y + 40)], INK, 2.2, arrow="both",
     label="council/ask  ⇄  council-transcript", lpos=(3300, 412), lsize=15)
path([(AX[0] + AIW, AI_Y + 120), (AX[1], AI_Y + 120)], TEAL, 2.4)
path([(AX[0] + 300, AI_BOT), (AX[0] + 300, AI_BOT + 34), (AX[2] + 200, AI_BOT + 34), (AX[2] + 200, AI_BOT)], TEAL, 2, label="hết hạn mức → chạy local", lpos=(AX[1] + 160, AI_BOT + 30), lsize=14)
path([(AX[3], AI_Y + 120), (AX[2] + AIW, AI_Y + 120)], TEAL, 2.4, label="nén", lpos=(AX[3] - 8, AI_Y + 108), lanchor="end", lsize=15)
path([(X[0] + 120, e5), (X[0] + 120, 2424), (3500, 2424), (3500, 2526)], INK2, 1.8, dash="9 7",
     label="audio → Drive", lpos=(X[0] + 132, 2420), lsize=14)

add("</svg>")
open(OUT, "w", encoding="utf-8").write("\n".join(out))
print("written", OUT, len("\n".join(out)), "bytes")
