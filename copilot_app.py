"""University Copilot — web app chạy trên máy (127.0.0.1:8320).

  /                       giao diện (ui/index.html): Trò chuyện · Gợi ý · Inbox tài liệu
  POST /api/chat          -> n8n /webhook/copilot-api            (bộ não Gemini + công cụ Notion)
  GET  /api/suggest       -> n8n /webhook/copilot-suggest        (gợi ý theo dữ liệu thật)
  POST /api/upload?name=  -> lưu file vào Uni-Documents\\00 · Inbox, đưa cho agent xếp tài liệu
  GET  /api/inbox         -> danh sách file đã nhận + trạng thái
  POST /api/inbox/<id>/assign {"folder": "..."}  -> bạn chọn thư mục cho file agent chưa chắc
  GET  /api/folders       -> cây thư mục Uni-Documents
  GET  /files/<id>?k=     -> n8n tải file về (có chữ ký HMAC) để sao lưu Drive + đưa vào Notion

Agent xếp tài liệu (luồng nền): Tika đọc nội dung -> LM Studio (qwen3-8b, local) chọn thư mục theo
cấu trúc Uni-Documents -> chuyển file -> n8n: Drive (Course Materials Backup) + University Inbox -> A2.
Chỉ dùng thư viện chuẩn Python.
"""
import uc_config as cfg
import hashlib, hmac, json, mimetypes, os, queue, re, shutil, threading, time, unicodedata, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNI = Path(cfg.path("uni_documents"))
INBOX = UNI / "00 · Inbox"
STATE = HERE / "inbox_state.json"
SECRET = (HERE / ".copilot-secret").read_text().strip()
N8N = "http://127.0.0.1:5678/webhook"
LMSTUDIO = "http://127.0.0.1:1234/v1/chat/completions"
TIKA = "http://127.0.0.1:9998/tika"
SORT_MODEL = "qwen3-14b"   # việc nền: ưu tiên đúng hơn nhanh (8B xếp nhầm Đại số thành Giải tích khi thử)
CONFIDENCE_OK = 0.7
PORT = 8320
ORIGIN = f"http://127.0.0.1:{PORT}"

# Thư mục môn đã có -> mã môn (đối chiếu với Courses trong Notion). Agent dùng để biết "thư mục này là môn gì".
COURSE_FOLDERS = {
    r"Toán Cao Cấp - HUST\Giải tích I+II+III\Giải Tích I": ("MI1111", "Giải tích I"),
    r"Toán Cao Cấp - HUST\Giải tích I+II+III\Giải Tích II": ("MI1121", "Giải tích II"),
    r"Toán Cao Cấp - HUST\Giải tích I+II+III\Giải Tích III": ("", "Giải tích III"),
    r"Toán Cao Cấp - HUST\Đại số Tuyến Tính": ("MI1141", "Đại số"),
    r"Nhập môn Công Nghệ Thông Tin và Truyền Thông": ("IT2000", "Nhập môn CNTT và TT"),
    r"Nhập môn Lập Trình": ("IT1108", "Nhập môn lập trình"),
}
# Chủ đề đặc trưng từng môn: vừa đưa cho model làm gợi ý, vừa chấm điểm từ khoá độc lập để bắt lỗi model.
COURSE_HINTS = {
    "MI1111": ["giới hạn", "đạo hàm", "vi phân", "tích phân", "hàm một biến", "liên tục", "l'hospital", "taylor", "chuỗi", "cực trị"],
    "MI1121": ["hàm nhiều biến", "đạo hàm riêng", "tích phân bội", "tích phân kép", "tích phân đường", "tích phân mặt", "trường vector"],
    "MI1141": ["ma trận", "định thức", "hạng", "hệ phương trình tuyến tính", "cramer", "không gian vector", "ánh xạ tuyến tính",
               "trị riêng", "véc tơ riêng", "dạng toàn phương", "logic mệnh đề", "tập hợp", "số phức"],
    "IT2000": ["website", "wordpress", "iot", "arduino", "firebase", "aws", "tên miền", "internet", "mạng máy tính", "soict"],
    "IT1108": ["lập trình", "thuật toán", "biến", "vòng lặp", "con trỏ", "hàm main", "printf", "scanf", "c++", "mảng", "chương trình"],
}
# Thư mục con chuẩn (theo cách bạn đang đặt tên)
CATEGORIES = ["Slide Bài giảng", "Slide Lý thuyết", "Ghi chú Bài giảng", "Bài tập", "Đề thi - Kiểm tra", "Tài liệu tham khảo", "Lớp Thực Nghiệm"]
SKIP_UNDER = ["Adruino Examples"]   # dự án code: không coi các thư mục con là nơi xếp tài liệu

lock = threading.Lock()
jobs = queue.Queue()


# ----------------------------------------------------------------------------- state
def load_state():
    try:
        return json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {"items": []}

def save_state(st):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(STATE)

def update_item(item_id, **kw):
    with lock:
        st = load_state()
        for it in st["items"]:
            if it["id"] == item_id:
                it.update(kw); it["updatedAt"] = time.time()
                save_state(st); return it
    return None

def get_item(item_id):
    with lock:
        return next((it for it in load_state()["items"] if it["id"] == item_id), None)


# ----------------------------------------------------------------------------- folders
def folder_list():
    out = []
    for p in sorted(UNI.rglob("*")):
        if not p.is_dir():
            continue
        rel = str(p.relative_to(UNI))
        if rel.startswith("00 · Inbox"):
            continue
        parts = rel.split(os.sep)
        if any(s in parts[:-1] for s in SKIP_UNDER) or len(parts) > 4:
            continue
        out.append(rel)
    return out

def all_course_folders():
    """COURSE_FOLDERS + thư mục môn tự tạo cho môn mới (uni_folders.json, teams_files.folder_for)."""
    try: extra = {k: tuple(v) for k, v in json.loads((HERE / "uni_folders.json").read_text(encoding="utf-8")).items()}
    except Exception: extra = {}
    return {**COURSE_FOLDERS, **extra}

def course_of(rel):
    best = None
    for k, v in all_course_folders().items():
        if rel == k or rel.startswith(k + os.sep):
            if not best or len(k) > len(best[0]):
                best = (k, v)
    return best[1] if best else ("", "")


# ----------------------------------------------------------------------------- helpers
def safe_name(name):
    name = unicodedata.normalize("NFC", os.path.basename(name or "file")).strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:150]
    return name or "file"

def unique_path(folder, name):
    p = folder / name
    stem, ext = os.path.splitext(name)
    i = 2
    while p.exists():
        p = folder / f"{stem} ({i}){ext}"; i += 1
    return p

def sign(item_id):
    return hmac.new(SECRET.encode(), item_id.encode(), hashlib.sha256).hexdigest()[:32]

def http_json(url, body=None, headers=None, timeout=120, method=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        t = r.read().decode("utf-8")
        return json.loads(t) if t.strip() else {}

def _safe(fn):
    try: return fn()
    except Exception as e: print("bg:", e)

def _npost(path, body):
    return n8n(path, body, timeout=120)

def _tt_refresh():   # làm mới lịch ở luồng nền (sau chat / nạp TKB có thể đã thêm hạn, đổi buổi học)
    def go():
        try:
            import timetable; timetable.refresh(_npost)
        except Exception as e: print("timetable:", e)
        try:
            import program; program.refresh(_npost)   # điểm / vắng / luật môn có thể vừa đổi qua chat
        except Exception as e: print("program:", e)
    threading.Thread(target=go, daemon=True).start()

def n8n(path, body=None, timeout=180):
    return http_json(f"{N8N}/{path}", body, {"X-Copilot-Key": SECRET}, timeout, "POST" if body is not None else "GET")

def n8n_multipart(path, fields, files, timeout=300):
    """files: [(field, filename, mime, bytes)] — n8n đặt tên binary theo tiền tố 'file' + số thứ tự."""
    boundary = "----UniCopilot" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode() + str(v).encode("utf-8") + b"\r\n")
    for field, fname, mime, data in files:
        fq = urllib.parse.quote(fname)
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{fq}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{N8N}/{path}", data=body, method="POST",
                                 headers={"X-Copilot-Key": SECRET, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        t = r.read().decode("utf-8")
        return json.loads(t) if t.strip() else {}

# --- Ghi bài giảng (Claude 2/10): app ghi âm trên máy + cổng chép lời + cổng Gemini
RECORDER = "http://127.0.0.1:5681"     # LectureRecorderCompanion: chỉ ghi khi người dùng bấm Start ở tab này
SPEECH_GATE = "http://127.0.0.1:8340"  # cổng âm thanh -> chữ -> nén
GEMINI_GATE = "http://127.0.0.1:8350"  # cổng Gemini (đếm quota)


def local_json(url, body=None, timeout=15, method=None):
    try:
        return http_json(url, body, None, timeout, method or ("POST" if body is not None else "GET"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "offline": True, "error": str(e)[:200]}


CHAT_FILES = HERE / "chat_files"
VISION_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}

def enqueue_inbox(src_path, name):
    INBOX.mkdir(parents=True, exist_ok=True)
    dest = unique_path(INBOX, safe_name(name))
    shutil.copy2(src_path, dest)
    item = {"id": str(uuid.uuid4()), "name": dest.name, "path": str(dest), "size": dest.stat().st_size, "status": "queued",
            "createdAt": time.time(), "updatedAt": time.time(), "source": "chat"}
    with lock:
        st = load_state(); st["items"].append(item); save_state(st)
    jobs.put(item["id"])
    return item


# ----------------------------------------------------------------------------- sorter agent
def extract_text(path, limit=4000):
    try:
        req = urllib.request.Request(TIKA, data=path.read_bytes(), method="PUT",
                                     headers={"Accept": "text/plain; charset=utf-8", "Content-Type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=90) as r:
            txt = r.read().decode("utf-8", "ignore")
        return re.sub(r"\s+", " ", txt).strip()[:limit]
    except Exception as e:
        return f"(không đọc được nội dung: {e.__class__.__name__})"

def folder_of_code(code):
    return next((rel for rel, (c, _) in all_course_folders().items() if c and c == code), None)

def heuristic(name, text):
    """Mã môn trong tên/nội dung (chắc chắn) hoặc điểm từ khoá chủ đề (gợi ý). Trả (folder, code, strength)."""
    s = (name + " " + text[:1500]).upper()
    for rel, (code, cname) in all_course_folders().items():
        if code and code in s:
            return rel, code, "code"
    low = (name + " " + text).lower()
    scores = {c: sum(low.count(k) for k in kws) for c, kws in COURSE_HINTS.items()}
    best = sorted(scores.items(), key=lambda x: -x[1])
    if best and best[0][1] >= 2 and (len(best) < 2 or best[0][1] >= 2 * max(1, best[1][1])):
        return folder_of_code(best[0][0]), best[0][0], "keywords"
    return None, None, None

def ask_llm(name, text, folders):
    numbered = "\n".join(f"{i}. {f}" + (f"   [môn {course_of(f)[0]} {course_of(f)[1]}]" if course_of(f)[1] else "   [thư mục chung, không phải môn]") for i, f in enumerate(folders))
    hints = "\n".join(f"- {code} {next((n for c, n in COURSE_FOLDERS.values() if c == code), '')}: {', '.join(kws)}" for code, kws in COURSE_HINTS.items())
    prompt = f"""Bạn là thủ thư sắp xếp tài liệu học tập của một sinh viên HUST vào kho Uni-Documents.
Chọn THƯ MỤC phù hợp nhất cho file dưới đây.

Các thư mục hiện có (số. đường dẫn [môn]):
{numbered}

Chủ đề đặc trưng của từng môn (dùng để nhận môn theo NỘI DUNG):
{hints}

Thư mục con chuẩn có thể tạo mới bên trong thư mục môn: {", ".join(CATEGORIES)}.
Luôn chọn thư mục của MỘT MÔN cụ thể (có nhãn [môn ...]), không chọn thư mục chung.

File: {name}
Nội dung trích (có thể thiếu):
{text[:3000]}

Trả về DUY NHẤT một JSON:
{{"folder_index": <số thư mục phù hợp nhất, hoặc null>,
 "new_subfolder": "<tên thư mục con chuẩn nên tạo bên trong thư mục đã chọn nếu chưa có, hoặc rỗng>",
 "course_code": "<mã môn nếu nhận ra, vd MI1111>",
 "category": "<loại tài liệu: slide / bài tập / đề thi / ghi chú / tham khảo / thực hành / khác>",
 "title": "<tên ngắn gọn dễ hiểu cho tài liệu>",
 "summary": "<1 câu mô tả nội dung>",
 "confidence": <0..1>,
 "reason": "<lý do ngắn>"}}
Nếu không chắc là môn nào, đặt confidence thấp (<0.5). /no_think"""
    body = {"model": SORT_MODEL, "temperature": 0, "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}]}
    r = http_json(LMSTUDIO, body, timeout=300)
    out = r["choices"][0]["message"]["content"]
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S)
    m = re.search(r"\{.*\}", out, re.S)
    return json.loads(m.group(0)) if m else {}

def place(item_id, rel_folder, decision, how):
    it = get_item(item_id)
    src = Path(it["path"])
    dest_dir = UNI / rel_folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_path(dest_dir, src.name)
    shutil.move(str(src), str(dest))
    rel = str(dest.relative_to(UNI))
    code, cname = course_of(rel_folder)
    code = decision.get("course_code") or code
    update_item(item_id, status="placed", path=str(dest), relPath=rel, folder=rel_folder, courseCode=code, courseName=cname,
                title=decision.get("title") or it["name"], summary=decision.get("summary", ""), category=decision.get("category", ""),
                placedBy=how)
    if it.get("fromNotion"):   # kéo từ 📥 University Inbox về máy: Notion đã có, không nạp lại
        update_item(item_id, notion="done"); return
    threading.Thread(target=ingest, args=(item_id,), daemon=True).start()

def ingest(item_id):
    it = get_item(item_id)
    try:
        if dedup_gate(item_id) == "stop": return
    except Exception as e:
        print("dedup_gate:", e)
    it = get_item(item_id)
    update_item(item_id, notion="sending")
    try:
        drive_name = it["relPath"].replace(os.sep, " › ")
        r = n8n("copilot-file-ingest", {
            "relPath": it["relPath"], "fileName": os.path.basename(it["relPath"]), "title": it.get("title"),
            "courseCode": it.get("courseCode"), "courseName": it.get("courseName"), "summary": it.get("summary"),
            "category": it.get("category"), "driveName": drive_name,
            "downloadUrl": f"http://host.docker.internal:{PORT}/files/{item_id}?k={sign(item_id)}"}, timeout=300)
        update_item(item_id, notion="done" if r.get("ok") else "error", inboxUrl=r.get("inboxUrl"), driveLink=r.get("driveLink"))
        backup_log(get_item(item_id), bool(r.get("ok")), r.get("driveLink"))
        threading.Thread(target=a2_pump, daemon=True).start()   # A2 xếp vào kho, tuần tự từng dòng
        sup = get_item(item_id).get("supersedes")
        if r.get("ok") and sup: threading.Thread(target=retire_item, args=(sup, item_id), daemon=True).start()
    except Exception as e:
        update_item(item_id, notion="error", notionError=str(e)[:300])
        backup_log(get_item(item_id), False, None, str(e)[:300])

def sort_job(item_id):
    it = get_item(item_id)
    path = Path(it["path"])
    try:   # (4/10) chống trùng TRƯỚC khi xếp: vân tay SHA-256 so với mọi file trong Uni-Documents
        import teams_files
        h = sha256_of(path); same = teams_files.local_index().get(h)
        if same:
            update_item(item_id, status="duplicate", sha=h, dupOf=same, notion="duplicate")
            return
    except Exception as e:
        print("pre-dedup:", e)
    update_item(item_id, status="reading")
    text = extract_text(path)
    folders = folder_list()
    update_item(item_id, status="thinking", excerpt=text[:240])
    decision = {}
    try:
        decision = ask_llm(it["name"], text, folders)
    except Exception as e:
        decision = {"confidence": 0, "reason": f"Model local chưa sẵn sàng ({e.__class__.__name__}) — LM Studio đang tắt?"}
    idx = decision.get("folder_index")
    target = folders[idx] if isinstance(idx, int) and 0 <= idx < len(folders) else None
    sub = (decision.get("new_subfolder") or "").strip()
    if target and sub and sub in CATEGORIES and not (UNI / target / sub).exists() and not target.endswith(sub):
        target = os.path.join(target, sub)
    h_folder, h_code, h_kind = heuristic(it["name"], text)
    conf = float(decision.get("confidence") or 0)
    notes = []
    t_code = course_of(target)[0] if target else ""
    if target and not course_of(target)[1]:
        notes.append("model chọn thư mục chung, không phải thư mục môn"); conf = min(conf, 0.4)
    if decision.get("course_code") and t_code and decision["course_code"] != t_code:
        notes.append(f"model nói môn {decision['course_code']} nhưng chọn thư mục của {t_code}"); conf = min(conf, 0.4)
    if h_folder:
        if not target or not course_of(target)[1]:
            target, conf = h_folder, max(conf, 0.75 if h_kind == "code" else 0.7)
            sub = (decision.get("new_subfolder") or "").strip()
            if sub in CATEGORIES:
                target = os.path.join(target, sub)
        elif not target.startswith(h_folder):
            notes.append(f"từ khoá nội dung nghiêng về {h_code}, model chọn {t_code or 'thư mục khác'}"); conf = min(conf, 0.45)
            decision.setdefault("reason", "")
    if notes:
        decision["reason"] = (decision.get("reason", "") + " — Cần xem lại: " + "; ".join(notes)).strip(" —")
    update_item(item_id, suggestion=target, confidence=round(conf, 2), reason=decision.get("reason", ""),
                title=decision.get("title") or it["name"], summary=decision.get("summary", ""), category=decision.get("category", ""),
                courseCode=decision.get("course_code") or h_code or "", heuristic=f"{h_kind}:{h_code}" if h_kind else "")
    if target and conf >= CONFIDENCE_OK:
        place(item_id, target, decision, "agent")
    else:
        update_item(item_id, status="needs_choice")

# ----------------------------------------------------------------------------- 💾 Backup & Drive Sync (Claude 2026-10-03)
# Thả file thẳng vào Uni-Documents (D:) là tự lên Drive + University Inbox, như tải qua tab Inbox của UC:
#   • file nằm trong thư mục (bạn đã xếp)  -> nạp luôn: Drive "Course Materials Backup" -> 📥 University Inbox -> A2 -> 📚 Course Materials
#   • file thả ở gốc Uni-Documents (chưa xếp) -> agent xếp file như tab Inbox, rồi nạp
#   • bỏ qua: "00 · Inbox" (chỗ làm việc của agent), thư mục dự án code (.git, .gitignore, library.properties…), file tạm/ẩn
#   • chỉ xử lý khi file đã chép xong (kích thước + giờ sửa không đổi qua 2 lần quét, cũ hơn 20 giây)
#   • mọi lần nạp ghi 1 dòng vào 💾 Backup & Drive Sync; sửa file đã đồng bộ -> ghi "Needs review" (bản Drive là bản cũ)
BACKUP_DB = cfg.notion("backup")
SYNC_STATE = HERE / "uni_sync.json"
SYNC_EVERY = 60
SYNC_PER_ROUND = 3
PROJECT_MARKERS = (".git", ".gitignore", "library.properties", "package.json", "CMakeLists.txt", ".vscode", "platformio.ini")
SKIP_FILE = re.compile(r"^(~\$|\.~lock|\.)|\.(tmp|part|crdownload|download|lnk)$|^(desktop\.ini|thumbs\.db)$", re.I)

def backup_log(it, ok, drive_link, err="", status=None):
    try:
        import academic
        rel = it.get("relPath") or it.get("name") or ""
        code = it.get("courseCode") or ""
        notes = rel + (f" · môn {code} {it.get('courseName') or ''}".rstrip() if code else " · chưa rõ môn (A2 sẽ hỏi)") + \
                (" · từ Uni-Documents (tự đồng bộ)" if it.get("source") == "uni-sync" else " · tải qua UC") + ((f" · ghi chú: {err}" if status else f" · lỗi: {err}") if err else "")
        page = academic.Notion(_npost).create(BACKUP_DB, {
            "Item": {"title": [{"text": {"content": (it.get("title") or os.path.basename(rel))[:200]}}]},
            "Type": {"select": {"name": "Course Material"}}, "Status": {"select": {"name": status or ("Synced" if ok else "Needs review")}},
            "SHA-256": {"rich_text": [{"text": {"content": it.get("sha") or ""}}]},
            "Drive URL": {"url": drive_link or None}, "Source URL": {"url": Path(it.get("path") or (UNI / rel)).as_uri()},
            "Last Sync": {"date": {"start": time.strftime("%Y-%m-%dT%H:%M:%S+07:00")}},
            "Notes": {"rich_text": [{"text": {"content": notes[:1900]}}]}})
        if it.get("id"): update_item(it["id"], backupId=page.get("id"))
        return page.get("id")
    except Exception as e:
        print("backup_log:", e)

def _sync_load():
    try: return json.loads(SYNC_STATE.read_text(encoding="utf-8"))
    except Exception: return {"files": {}}

def _sync_save(st):
    SYNC_STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------------- chống trùng (Claude 2026-10-03)
#  • vân tay SHA-256 = căn cước nội dung. Chốt chung ở đầu ingest():
#      trùng vân tay, file cũ còn      -> bản chép: không tải lên, nhật ký "Duplicate"
#      trùng vân tay, file cũ đã mất   -> chuyển chỗ / đổi tên: cập nhật đường dẫn, nhật ký "Moved"
#  • phiên bản gần giống (cùng thư mục, tên gần giống sau khi bỏ final / v3 / (1) / copy…): so NỘI DUNG
#      bản mới chứa trọn bản cũ + thêm nội dung -> nhận bản mới, gỡ tài liệu bản cũ khỏi kho (nhật ký "Superseded")
#      bản mới ít hơn bản cũ                     -> không đưa vào kho (nhật ký "Superseded")
#      khác nhau / không đọc được chữ            -> giữ cả hai
#  • file đã đồng bộ bị sửa trên máy -> ghi đè nội dung CHÍNH file đó trên Drive (Drive giữ lịch sử), nhật ký "Updated"
#  File trên máy KHÔNG bao giờ bị xoá / di chuyển bởi hệ thống.
import hashlib, difflib, unicodedata as _ud

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def drive_id(link):
    m = re.search(r"/d/([A-Za-z0-9_-]{10,})", link or "")
    return m.group(1) if m else None

def _done_items():
    with lock:
        return [x for x in load_state()["items"] if x.get("notion") == "done" and x.get("sha")]

def _stem(name):
    s = _ud.normalize("NFD", Path(name).stem.lower())
    s = "".join(c for c in s if _ud.category(c) != "Mn").replace("đ", "d")
    s = re.sub(r"\(\d+\)|\bcopy\b|\bban\s*(sao|moi|cu)\b|\b(final|new|moi|sua|fix|edited|updated|latest)\b|\bv\d+(\.\d+)?\b|\b20\d\d[._-]?\d\d[._-]?\d\d\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def _shingles(text, k=6):
    w = re.findall(r"\w+", (text or "").lower())
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}

def compare_versions(new_path, old_path):
    """-> 'new_more' | 'old_more' | 'different' | 'unknown' (so chữ trích bằng Tika: phần trăm đoạn 6 từ của bản này nằm trong bản kia)."""
    a, b = extract_text(Path(new_path), 400000), extract_text(Path(old_path), 400000)
    if a.startswith("(không đọc") or b.startswith("(không đọc") or len(a) < 300 or len(b) < 300:
        return "unknown", {}
    A, B = _shingles(a), _shingles(b)
    if not A or not B: return "unknown", {}
    old_in_new, new_in_old = len(A & B) / len(B), len(A & B) / len(A)
    info = {"cu_trong_moi": round(old_in_new, 2), "moi_trong_cu": round(new_in_old, 2), "chu_moi": len(a), "chu_cu": len(b)}
    if old_in_new >= 0.8 and len(A) > len(B) * 1.02: return "new_more", info
    if new_in_old >= 0.8 and len(B) >= len(A): return "old_more", info
    if max(old_in_new, new_in_old) >= 0.5:   # vùng xám: viết lại / sắp xếp lại -> AI cục bộ đọc phần khác nhau rồi phân xử
        v, why = ask_llm_versions(Path(new_path).name, Path(old_path).name, a, b, info)
        info["ai"] = why
        if v: return v, info
    return "different", info

def _sents(t):
    return [x.strip() for x in re.split(r"(?<=[.!?:;])\s+|\s{2,}|•", t or "") if len(x.strip()) > 25]

def ask_llm_versions(new_name, old_name, new_text, old_text, info):
    """LM Studio đọc các câu CHỈ có ở từng bản -> {'chon': 'moi'|'cu'|'giu_ca_hai'}. Lỗi / không chắc -> giữ cả hai."""
    sn, so = _sents(new_text), _sents(old_text)
    setn, seto = set(sn), set(so)
    only_old, only_new = [x for x in so if x not in setn], [x for x in sn if x not in seto]
    pick = lambda xs, k: [xs[int(i * len(xs) / k)] for i in range(min(k, len(xs)))]
    sample_old = "\n".join("- " + x[:170] for x in pick(only_old, 45))
    sample_new = "\n".join("- " + x[:170] for x in pick(only_new, 45))
    prompt = f"""Hai tệp tài liệu học tập cùng tên gần giống trong cùng thư mục. Cần giữ MỘT bản trong kho: bản có NHIỀU NỘI DUNG HƠN so với bản kia
(bản kia chỉ là bản cũ / bản ít hơn). Nếu hai bản là hai tài liệu khác nhau thật (mỗi bản có nội dung quan trọng mà bản kia không có) thì giữ cả hai.

Bản A (cũ): {old_name} — khoảng {info.get('chu_cu')} ký tự
Bản B (mới): {new_name} — khoảng {info.get('chu_moi')} ký tự
Tỉ lệ đoạn văn của A có trong B: {info.get('cu_trong_moi')}; của B có trong A: {info.get('moi_trong_cu')}.

Các câu CHỈ có ở A (mẫu, {len(only_old)} câu):
{sample_old}

Các câu CHỈ có ở B (mẫu, {len(only_new)} câu):
{sample_new}

Lưu ý: câu chỉ khác cách diễn đạt / định dạng thì coi như cùng nội dung. Xét xem phần chỉ có ở A có thực sự bị mất ý trong B không.
Trả về DUY NHẤT JSON: {{"chon": "moi" | "cu" | "giu_ca_hai", "ly_do": "<1–2 câu tiếng Việt>"}} /no_think"""
    try:
        r = http_json(LMSTUDIO, {"model": SORT_MODEL, "temperature": 0, "max_tokens": 400,
                                 "messages": [{"role": "user", "content": prompt}]}, timeout=420)
        out = re.sub(r"<think>.*?</think>", "", r["choices"][0]["message"]["content"], flags=re.S)
        m = re.search(r"\{.*\}", out, re.S)
        d = json.loads(m.group(0)) if m else {}
    except Exception as e:
        return None, f"AI không phân xử được ({e.__class__.__name__}) — giữ cả hai"
    return {"moi": "new_more", "cu": "old_more"}.get(d.get("chon")), (d.get("ly_do") or "")[:300]

def backup_patch(row_id, status=None, note=None, it=None):
    if not row_id: return
    try:
        import academic
        props = {"Last Sync": {"date": {"start": time.strftime("%Y-%m-%dT%H:%M:%S+07:00")}}}
        if status: props["Status"] = {"select": {"name": status}}
        if note: props["Notes"] = {"rich_text": [{"text": {"content": note[:1900]}}]}
        if it:
            props["Source URL"] = {"url": Path(it["path"]).as_uri()}
            if it.get("sha"): props["SHA-256"] = {"rich_text": [{"text": {"content": it["sha"]}}]}
        academic.Notion(_npost).patch(row_id, props)
    except Exception as e:
        print("backup_patch:", e)

def _from_school(rel):
    """File này do UC tải từ Teams (dữ liệu trường)? — teams_files ghi đường dẫn đã tải vào school/teams/files_done.json."""
    try:
        done = json.loads((HERE / "school" / "teams" / "files_done.json").read_text(encoding="utf-8"))
        return any(v.get("rel") == rel and v.get("kq") == "đã tải" for v in done.values())
    except Exception:
        return False

def dedup_gate(item_id):
    it = get_item(item_id)
    p = Path(it["path"])
    h = sha256_of(p)
    update_item(item_id, sha=h)
    it = get_item(item_id)
    others = [x for x in _done_items() if x["id"] != item_id]
    same = [x for x in others if x["sha"] == h]
    for o in same:
        if Path(o["path"]).exists() and Path(o["path"]) != p:   # bản chép
            update_item(item_id, notion="duplicate", dupOf=o.get("relPath"))
            backup_log(get_item(item_id), False, None, status="Duplicate",
                       err=f"trùng nội dung với {o.get('relPath')} — không tải lên; bỏ bản chép vào Thùng rác nếu không cần")
            return "stop"
        if not Path(o["path"]).exists():   # chuyển chỗ / đổi tên
            update_item(o["id"], path=str(p), relPath=it.get("relPath"), folder=it.get("folder"), name=p.name)
            update_item(item_id, notion="moved", movedTo=o["id"])
            backup_patch(o.get("backupId"), "Moved", f"đã chuyển / đổi tên trên máy: {o.get('relPath')} → {it.get('relPath')} (bản Drive giữ nguyên)", get_item(o["id"]))
            return "stop"
    # phiên bản gần giống trong cùng thư mục
    folder, stem = os.path.dirname(it.get("relPath") or ""), _stem(p.name)
    near = [o for o in others if os.path.dirname(o.get("relPath") or "") == folder and Path(o["path"]).exists() and o["sha"] != h
            and stem and re.findall(r"\d+", _stem(o["name"])) == re.findall(r"\d+", stem)   # 1.1 vs 1.2 = phần nối tiếp, không phải phiên bản
            and (_stem(o["name"]) == stem or difflib.SequenceMatcher(None, _stem(o["name"]), stem).ratio() >= 0.85)]
    for o in near:
        verdict, info = compare_versions(p, o["path"])
        if verdict == "old_more" and _from_school(it.get("relPath")):   # LUẬT TỐI CAO: bản giảng viên đăng trên Teams thắng bản cũ trên máy
            verdict, info = "new_more", {**info, "luat_toi_cao": "bản trên Teams (trường) thắng khi tranh chấp"}
        update_item(item_id, versionCheck={"so_voi": o.get("relPath"), "ket_qua": verdict, **info})
        if verdict == "old_more":
            update_item(item_id, notion="skipped", lesserThan=o.get("relPath"))
            backup_log(get_item(item_id), False, None, status="Superseded",
                       err=f"ít nội dung hơn {o.get('relPath')} — không đưa vào kho. {info.get('ai') or info}")
            return "stop"
        if verdict == "new_more":
            update_item(item_id, supersedes=o["id"])
    return "go"

def retire_item(old_id, new_id):
    """Bản mới nhiều nội dung hơn đã nạp xong -> gỡ tài liệu của bản cũ khỏi 📚 Course Materials (thùng rác Notion)."""
    o, n_ = get_item(old_id), get_item(new_id)
    pid = re.search(r"([0-9a-f]{32})$", (o.get("inboxUrl") or "").replace("-", ""))
    removed = 0
    try:
        import academic
        if pid:   # tài liệu trong kho sinh ra từ dòng Inbox của bản cũ (truy vấn bảng — cổng Notion không cho GET trang lẻ)
            mats = academic.Notion(_npost).query(cfg.notion("materials"),
                                                 {"property": "Source Upload", "relation": {"contains": str(uuid.UUID(pid.group(1)))}})
            for rel in mats:
                r = n8n("copilot-material-archive", {"id": rel["id"]}, timeout=60)
                r = r[0] if isinstance(r, list) else r
                removed += 1 if r.get("ok") else 0
    except Exception as e:
        print("retire_item:", e)
    update_item(old_id, notion="superseded", supersededBy=n_.get("relPath"))
    backup_patch(o.get("backupId"), "Superseded",
                 f"{o.get('relPath')} — đã có bản nhiều nội dung hơn: {n_.get('relPath')}; gỡ {removed} tài liệu bản cũ khỏi kho (file trên máy giữ nguyên)")

def update_drive_copy(item_id):
    """File đã đồng bộ bị sửa trên máy -> ghi đè nội dung chính file đó trên Drive."""
    it = get_item(item_id)
    if it.get("movedTo"): item_id, it = it["movedTo"], get_item(it["movedTo"])   # file đã chuyển chỗ: bản gốc giữ link Drive
    fid = drive_id(it.get("driveLink"))
    h = sha256_of(it["path"])
    if h == it.get("sha"): return
    ok = False
    if fid:
        try:
            r = n8n("copilot-file-update", {"fileId": fid, "downloadUrl": f"http://host.docker.internal:{PORT}/files/{item_id}?k={sign(item_id)}"}, timeout=300)
            r = r[0] if isinstance(r, list) else r
            ok = bool(r.get("ok"))
        except Exception as e:
            print("update_drive_copy:", e)
    update_item(item_id, sha=h if ok else it.get("sha"), size=Path(it["path"]).stat().st_size)
    backup_patch(it.get("backupId"), "Updated" if ok else "Needs review",
                 (f"{it.get('relPath')} — đã sửa trên máy, đã ghi đè bản trên Drive (Drive giữ lịch sử phiên bản)" if ok else
                  f"{it.get('relPath')} — đã sửa trên máy nhưng chưa ghi đè được bản Drive"), get_item(item_id) if ok else None)

_a2_pumping = threading.Lock()

def a2_pump():
    """Còn dòng 📥 University Inbox 'Not started' -> kích A2 một lần, chờ 45 s, lặp (tối đa 40 lượt). Một bơm duy nhất."""
    if not _a2_pumping.acquire(blocking=False): return
    try:
        import academic
        nt = academic.Notion(_npost)
        for _ in range(40):
            pend = nt.query(cfg.notion("inbox"), {"property": "Triage Status", "status": {"equals": "Not started"}})
            if not pend: return
            try: n8n("copilot-run-a2", None, timeout=30)
            except Exception as e: print("a2_pump:", e)
            time.sleep(45)
    except Exception as e:
        print("a2_pump:", e)
    finally:
        _a2_pumping.release()

def uni_files():
    for root, dirs, files in os.walk(UNI):
        rp = Path(root)
        rel_root = "" if rp == UNI else str(rp.relative_to(UNI))
        if rel_root.startswith("00 · Inbox") or any(m in dirs or m in files for m in PROJECT_MARKERS):
            dirs[:] = []; continue
        dirs[:] = [d for d in dirs if not d.startswith(".") and not (rel_root == "" and d.startswith("00 · Inbox"))]
        for f in files:
            if not SKIP_FILE.search(f):
                yield os.path.join(rel_root, f) if rel_root else f

def uni_sync_once():
    st = _sync_load(); files = st.setdefault("files", {})
    with lock:
        placed = {it.get("relPath") for it in load_state()["items"] if it.get("relPath")}
    now, done = time.time(), 0
    for rel in uni_files():
        p = UNI / rel
        try: sig = [p.stat().st_size, int(p.stat().st_mtime)]
        except OSError: continue
        f = files.get(rel)
        if rel in placed and (not f or f.get("status") != "synced"):   # do agent xếp / tải qua UC: đã nạp ở luồng đó
            files[rel] = {"sig": sig, "status": "synced", "via": "uc"}; continue
        if not f:
            files[rel] = {"sig": sig, "status": "new", "seen": now}; continue
        if f["status"] in ("synced", "modified"):
            if sig != f["sig"] and now - sig[1] > 20:
                f.update(sig=sig, status="synced")
                iid = f.get("itemId") or next((x["id"] for x in load_state()["items"] if x.get("relPath") == rel), None)
                if iid: threading.Thread(target=update_drive_copy, args=(iid,), daemon=True).start()
            continue
        if sig != f["sig"] or now - sig[1] < 20:   # đang chép / vừa sửa: chờ lượt sau
            f.update(sig=sig); continue
        if done >= SYNC_PER_ROUND or sig[0] > 200 * 1024 * 1024:
            continue
        done += 1
        folder = os.path.dirname(rel)
        if not folder:   # thả ở gốc: để agent xếp như tab Inbox
            INBOX.mkdir(parents=True, exist_ok=True)
            dest = unique_path(INBOX, safe_name(p.name)); shutil.move(str(p), str(dest))
            item = {"id": str(uuid.uuid4()), "name": dest.name, "path": str(dest), "size": sig[0], "status": "queued",
                    "createdAt": now, "updatedAt": now, "source": "uni-sync"}
            with lock:
                s2 = load_state(); s2["items"].append(item); save_state(s2)
            jobs.put(item["id"]); files.pop(rel, None)
            continue
        if folder in all_course_folders():   # (4/10) thả ở gốc thư mục môn: xếp vào thư mục loại (Slide / Bài tập / Đề thi / Tham khảo)
            try:
                import teams_files
                dest_rel = teams_files.category_for(folder, p.name)
                if dest_rel != folder:
                    (UNI / dest_rel).mkdir(parents=True, exist_ok=True)
                    dest = unique_path(UNI / dest_rel, p.name); shutil.move(str(p), str(dest))
                    files.pop(rel, None); rel, p, folder = str(dest.relative_to(UNI)), dest, dest_rel
            except Exception as e:
                print("uni sort:", e)
        code, cname = course_of(folder)
        item = {"id": str(uuid.uuid4()), "name": p.name, "path": str(p), "size": sig[0], "status": "placed", "createdAt": now,
                "updatedAt": now, "source": "uni-sync", "relPath": rel, "folder": folder, "courseCode": code, "courseName": cname,
                "title": p.stem, "category": os.path.basename(folder), "summary": "", "placedBy": "bạn (Uni-Documents)"}
        with lock:
            s2 = load_state(); s2["items"].append(item); save_state(s2)
        files[rel] = {"sig": sig, "status": "synced", "itemId": item["id"], "at": now}
        threading.Thread(target=ingest, args=(item["id"],), daemon=True).start()
    _sync_save(st)

# ---------------------------------------------------------------- 🏫 đồng bộ dữ liệu trường (school_fetch + school_sync)
SCHOOL_SLOTS = tuple(f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 5))   # (6/10) mọi nguồn đúng khung 5 phút, 00:00 … 23:55, cả đêm
SLOT_LATE = 120   # giây: tới khung mà máy đang thức thì chạy; lỡ khung (máy tắt / ngủ) thì bỏ, KHÔNG chạy bù


def _slot_now(now):
    """Khung 5 phút vừa tới (≤ SLOT_LATE giây trước) hoặc None."""
    s = now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0)
    return s if (now - s).total_seconds() <= SLOT_LATE else None
_school = {"running": False, "by": None, "lock": threading.Lock()}

def school_status():
    import school_sync
    st = school_sync.state()
    try:
        import school_cred
        e, p = school_cred.get(); creds = bool(e and p); locked = school_cred.LOCK.exists()
    except Exception:
        creds, locked = False, False
    return {**st, "running": _school["running"], "by": _school["by"], "creds": creds, "locked": locked, "slots": SCHOOL_SLOTS}

def extra_refresh():
    """🎯 dựng lại danh sách ngoại khoá (CTSV + mail/Teams) -> Notion, rồi quét trùng hạn / lịch."""
    try:
        import importlib, extracurricular, dupscan
        for m in (extracurricular, dupscan): importlib.reload(m)
        extracurricular.sync_notion(_npost, extracurricular.build())
        dupscan.scan(_npost)
    except Exception as e:
        print("extra/dups:", e)


def school_start(by):
    """Chạy một lượt đồng bộ ở luồng nền (nếu chưa chạy). -> True nếu vừa bắt đầu."""
    with _school["lock"]:
        if _school["running"]: return False
        _school.update(running=True, by=by)
    def job():
        try:
            import school_sync
            school_sync.run(_npost)
            extra_refresh()
            phone_refresh()
            _safe(lambda: __import__("timetable").refresh(_npost))
            _safe(lambda: __import__("program").refresh(_npost))
        except Exception as e:
            print("school sync:", e)
        finally:
            _school.update(running=False)
    threading.Thread(target=job, daemon=True).start()
    return True

def school_loop():
    """qldt + iCTSV đúng khung 5 phút suốt 24 giờ (6/10). Máy tắt / ngủ đúng khung -> bỏ khung đó, không chạy bù."""
    import datetime as dt
    from academic import TZ
    done = pending = None
    while True:
        now = dt.datetime.now(TZ)
        slot = _slot_now(now)
        if slot and slot != done: pending = slot   # máy thức đúng khung -> khung này phải chạy
        if pending and (now - pending).total_seconds() > 280: pending = None   # lượt mail chiếm hết khung -> khung sau
        if pending and not _school["running"] and not _mail["running"]:
            done, pending = pending, None; school_start(f"lịch {done:%H:%M}")
        time.sleep(15)


# ---------------------------------------------------------------- 📡 mail trường -> sự kiện theo dõi -> cảnh báo (mail_events + alerts)
_mail = {"running": False, "last": None, "lock": threading.Lock()}

def mail_run(by):
    with _mail["lock"]:
        if _mail["running"]: return False
        _mail["running"] = True
    try:
        import importlib, school_mail, mail_events, teams_fetch, teams_files
        for m in (mail_events, teams_fetch, teams_files): importlib.reload(m)
        r = school_mail.fetch()
        try:   # 💬 Teams: bài đăng (lịch lớp, bài tập) + file tài liệu
            r["teams"] = teams_fetch.fetch()
            if r["teams"].get("ok"): r["teams_files"] = [x for x in teams_files.sync_teams()["items"] if x["kq"] != "đã có"]
        except Exception as e: r["teams"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        try:   # 🎓 MOOC SoICT (soict.daotao.ai): hạn + điểm bài tập -> Academic Work theo luật tối cao
            import mooc; importlib.reload(mooc)
            r["mooc"] = mooc.fetch()
            if r["mooc"].get("ok"): r["mooc_sync"] = mooc.sync(_npost)
        except Exception as e: r["mooc"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        try:   # 📐 FAMI số hoá (fami.hust.edu.vn/sohoa): thi theo chương các học phần MI -> Academic Work theo luật tối cao
            import fami; importlib.reload(fami)
            r["fami"] = fami.fetch()
            if r["fami"].get("ok"): r["fami_sync"] = fami.sync(_npost)
        except Exception as e: r["fami"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        try:   # ✉️ phân loại mọi thư: môn học / hành chính / ngoại khoá / thông báo chung / học bổng (luật trước, AI theo lô)
            import mail_kinds; importlib.reload(mail_kinds)
            r["mail_kinds"] = mail_kinds.classify()
        except Exception as e: r["mail_kinds"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        try:   # 📚 cách tính điểm từng môn: bài của giảng viên trên Teams / mail -> grade_rules.json (AI chỉ khi có bài mới)
            import course_detail; importlib.reload(course_detail)
            r["grade_rules"] = course_detail.refresh_rules()
        except Exception as e: r["grade_rules"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        try:   # 🏛️ CTSV nhanh mỗi giờ (5/10): toàn bộ sự kiện (như /danh-sach-su-kien) + Hành chính (thông báo, giấy tờ, đặt vé)
            import ctsv_live; importlib.reload(ctsv_live)
            if ctsv_live.due(): r["ctsv_live"] = ctsv_live.fetch()
        except Exception as e: r["ctsv_live"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        try:
            import expired; importlib.reload(expired)   # việc của trường đã hết hạn -> ✅ Academic Tasks (không ghi thành hạn)
            r["expired"] = expired.record(_npost)
        except Exception as e: r["expired"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        try: r["notion_files"] = teams_files.sync_notion(_npost)["items"]   # 📥 file chỉ có trên Notion -> về máy
        except Exception as e: r["notion_files"] = f"{type(e).__name__}: {e}"[:200]
        if r.get("ok") or (r.get("teams") or {}).get("ok"): r["events"] = mail_events.process(_npost)
        try:   # bài tập Teams -> 📋 Academic Work (Môn học) nếu chưa có
            import deadlines; importlib.reload(deadlines)
            r["deadlines"] = deadlines.upsert_teams(_npost, mail_events.load())
        except Exception as e: r["deadlines"] = f"{type(e).__name__}: {e}"[:200]
        extra_refresh()
        phone_refresh()
        _mail["last"] = {"at": time.strftime("%Y-%m-%d %H:%M"), "by": by, **r}
    except Exception as e:
        _mail["last"] = {"at": time.strftime("%Y-%m-%d %H:%M"), "by": by, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    finally:
        _mail["running"] = False
    print("mail:", json.dumps(_mail["last"], ensure_ascii=False)[:300])
    try:   # (5/10) lưu kết quả từng vòng cập nhật: nguồn nào lỗi / đứng thì đọc school/sync_runs.jsonl là biết (không gọi AI)
        def _brief(v):
            if isinstance(v, dict): return {k: v.get(k) for k in ("ok", "error", "new", "updated", "total", "events", "lops", "added", "fixed") if k in v}
            return str(v)[:200]
        rec = {"at": _mail["last"].get("at"), "by": by, **{k: _brief(v) for k, v in _mail["last"].items() if k not in ("at", "by")}}
        f = HERE / "school" / "sync_runs.jsonl"
        lines = (f.read_text(encoding="utf-8").splitlines() if f.exists() else [])[-500:]
        f.write_text("\n".join(lines + [json.dumps(rec, ensure_ascii=False)]) + "\n", encoding="utf-8")
    except Exception as e:
        print("sync_runs:", e)
    return True

def mail_loop():
    """Mail + Teams + MOOC + FAMI + iCTSV đúng khung 5 phút suốt 24 giờ (6/10). Khung trùng lượt qldt thì chờ lượt đó xong
    (vẫn trong khung); lỡ khung (máy tắt / ngủ) thì bỏ, không chạy bù."""
    import datetime as dt
    from academic import TZ
    done = pending = None
    while True:
        now = dt.datetime.now(TZ)
        s = _slot_now(now)
        if s and s != done: pending = s   # máy thức đúng khung -> khung này phải chạy
        if pending and (now - pending).total_seconds() > 280: pending = None   # chờ qldt quá lâu -> nhường khung sau
        if pending and not _school["running"] and not _mail["running"]:
            done, pending = pending, None; mail_run(f"lịch {done:%H:%M}")
        time.sleep(15)

_sched_lock = threading.Lock()

def _dls(days=21):
    """Hạn đang mở cho banner / vòng nhắc; Notion lỗi -> [] cho lượt này (bộ hẹn ntfy và trang 📱 thì dừng hẳn, không ghi gì)."""
    try:
        import deadlines; return deadlines.open_list(_npost, days=days)
    except Exception as e:
        print("deadlines:", e); return []

def phone_refresh():
    """📱 (4/10) hẹn trước nhắc trên ntfy (phone_sched) + cập nhật trang 📱 UC trên Notion (phone_page). Chạy ngầm, một lượt mỗi lúc."""
    def job():
        if not _sched_lock.acquire(blocking=False): return
        try:
            import importlib, phone_sched, phone_page
            for m in (phone_sched, phone_page): importlib.reload(m)
            try:
                r = phone_sched.reconcile(_npost)
                if r.get("added") or r.get("changed") or r.get("cancelled") or r.get("errors"): print("ntfy hẹn:", r)
            except Exception as e: print("phone_sched:", e)
            try: phone_page.update(_npost)
            except Exception as e: print("phone_page:", e)
        finally:
            _sched_lock.release()
    threading.Thread(target=job, daemon=True).start()


def alert_loop():
    """Mỗi phút: tiết học trước 30/15 phút · hạn nộp mốc 72/48/36/24 giờ · sự kiện leo thang vàng/đỏ/ghim + toast + điện thoại."""
    time.sleep(60)
    while True:
        try:
            import importlib, alerts
            importlib.reload(alerts)
            import timetable
            sent = alerts.tick(classes=timetable.get(_npost)["events"], dls=_dls(400))   # (6/10) mọi hạn mở: hạn mới báo ngay lúc xuất hiện
            if sent: print("toast:", sent)
            alert_loop.n = getattr(alert_loop, "n", 0) + 1
            if alert_loop.n % 5 == 1: phone_refresh()   # mỗi 5 phút: đối chiếu lịch hẹn ntfy + trang 📱 UC
        except Exception as e: print("alerts:", e)
        time.sleep(60)   # mỗi phút: nhắc tiết học đúng mốc 30/15 phút


def uni_sync_loop():
    time.sleep(20)
    while True:
        try: uni_sync_once()
        except Exception as e: print("uni_sync:", e)
        time.sleep(SYNC_EVERY)


def worker():
    while True:
        item_id = jobs.get()
        try:
            sort_job(item_id)
        except Exception as e:
            update_item(item_id, status="error", error=str(e)[:300])
        finally:
            jobs.task_done()


# ----------------------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    server_version = "UniCopilot/1.0"

    def _send(self, code, obj=None, raw=None, ctype="application/json; charset=utf-8"):
        b = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _same_origin(self):
        o = self.headers.get("Origin")
        return o in (None, ORIGIN, f"http://localhost:{PORT}")

    def _body(self, limit=200 * 1024 * 1024):
        n = int(self.headers.get("Content-Length", "0"))
        if n > limit:
            raise ValueError("file quá lớn (>200MB)")
        return self.rfile.read(n)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                page = re.sub(r"\{\{notion:(\w+)\}\}", lambda m: cfg.notion(m.group(1)).replace("-", ""),
                              (HERE / "ui" / "index.html").read_text(encoding="utf-8"))
                return self._send(200, raw=page.encode("utf-8"), ctype="text/html; charset=utf-8")
            if u.path == "/manifest.webmanifest":
                man = {"name": "University Copilot", "short_name": "Uni Copilot", "id": "/", "start_url": "/", "scope": "/",
                       "display": "standalone", "background_color": "#f5f7fa", "theme_color": "#2d55c8", "lang": "vi",
                       "description": "Hậu phương học tập 4 năm: trò chuyện, gợi ý và Inbox tài liệu",
                       "icons": [{"src": "/icons/p192.png", "sizes": "192x192", "type": "image/png"},
                                 {"src": "/icons/p512.png", "sizes": "512x512", "type": "image/png"},
                                 {"src": "/icons/m512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}
                return self._send(200, man, ctype="application/manifest+json; charset=utf-8")
            m = re.match(r"^/icons/([a-z0-9-]+\.(png|ico))$", u.path)
            if m:
                p = HERE / "ui" / "icons" / m.group(1)
                if p.exists():
                    return self._send(200, raw=p.read_bytes(), ctype="image/png" if m.group(2) == "png" else "image/x-icon")
            if u.path == "/api/suggest":
                return self._send(200, n8n("copilot-suggest", timeout=120))
            if u.path == "/api/inbox":
                items = sorted(load_state()["items"], key=lambda x: -x.get("createdAt", 0))[:60]
                return self._send(200, {"items": items})
            if u.path == "/api/folders":
                return self._send(200, {"folders": folder_list(), "categories": CATEGORIES})
            if u.path == "/api/health":
                return self._send(200, {"ok": True, "queue": jobs.qsize()})
            if u.path == "/api/admin":   # 🏛️ tab Hành chính (CTSV + thư hành chính / thông báo chung) — chỉ đọc
                import ctsv_live, mail_kinds
                v = ctsv_live.view()
                import stale_filter   # (5/10) lọc thông báo của năm cũ
                v["mailAdmin"], h1 = stale_filter.split(mail_kinds.by_kind("hanh_chinh", days=800), "at", ("subject", "tom_tat"))
                v["mailGeneral"], h2 = stale_filter.split(mail_kinds.by_kind("thong_bao_chung", days=800), "at", ("subject", "tom_tat"))
                v["mailAdmin"], v["mailGeneral"], v["mailHidden"] = v["mailAdmin"][:40], v["mailGeneral"][:40], h1 + h2
                return self._send(200, v)
            if u.path == "/api/nlm/search":   # 🧠 tìm tài liệu trong Uni-Documents để gửi sang NotebookLM (chỉ đọc)
                import nlm_bridge
                return self._send(200, nlm_bridge.search(q.get("q", [""])[0]))
            if u.path == "/api/nlm/notebooks":
                import nlm_bridge
                return self._send(200, nlm_bridge.notebooks(force=q.get("force", ["0"])[0] == "1"))
            if u.path == "/api/nlm/job":
                import nlm_bridge
                return self._send(200, nlm_bridge.job(q.get("id", [""])[0]))
            if u.path == "/api/course-detail":   # 📚 lớp thành phần + điểm thành phần + cách tính (Teams + qldt + MOOC) — chỉ đọc file
                import course_detail
                return self._send(200, course_detail.view(re.sub(r"[^A-Z0-9]", "", q.get("code", [""])[0].upper())[:10]))
            if u.path == "/api/scholarships":   # 🎓 tab Học bổng
                import scholarships
                return self._send(200, scholarships.view())
            if u.path == "/api/lecture-monitor":   # (Claude 5/10) giám sát chuỗi Ghi bài giảng — không gọi AI
                import lecture_monitor
                return self._send(200, lecture_monitor.view())
            if u.path == "/api/rec/status":
                return self._send(200, local_json(RECORDER + "/health", timeout=5))
            if u.path == "/api/rec/pending":
                p = local_json(RECORDER + "/pending", timeout=5)
                return self._send(200, {"pending": p if isinstance(p, list) else []})
            if u.path == "/api/rec/apps":
                apps = local_json(RECORDER + "/audio-apps", timeout=10)
                return self._send(200, {"apps": apps if isinstance(apps, list) else []})
            if u.path == "/api/lectures":
                data = n8n("copilot-lectures", timeout=60)
                for s in data.get("sessions", []):
                    if s.get("state") in ("Processing", "Uploaded") and s.get("captureId"):
                        j = local_json(SPEECH_GATE + "/jobs?captureId=" + urllib.parse.quote(s["captureId"]), timeout=5)
                        if j.get("status"):
                            s["gate"] = {k: j.get(k) for k in ("status", "stage", "progress", "reason")}
                return self._send(200, data)
            if u.path == "/api/gemini":
                return self._send(200, local_json(GEMINI_GATE + "/status", timeout=5))
            # (Claude 2026-10-03) tab Lịch + tab Học kỳ — chỉ đọc Notion qua n8n
            if u.path == "/api/timetable":
                f, t = q.get("from", [""])[0], q.get("to", [""])[0]
                if not (re.fullmatch(r"\d{4}-\d\d-\d\d", f) and re.fullmatch(r"\d{4}-\d\d-\d\d", t)):
                    return self._send(400, {"error": "from/to phải dạng YYYY-MM-DD"})
                import timetable
                return self._send(200, timetable.window(_npost, f, t))
            if u.path == "/api/timetable/all":   # tab Lịch: lấy 1 lần, giao diện tự vẽ tuần/tháng (timetable.py)
                import timetable
                return self._send(200, timetable.get(_npost, force=q.get("force", [""])[0] == "1"))
            if u.path == "/api/study":   # GPA kỳ, CPA, rèn luyện — tính bằng academic.py
                import academic
                return self._send(200, academic.record(lambda path, body: n8n(path, body, timeout=120), {"loai": "xem"}))
            if u.path == "/api/today":   # tab Hôm nay (Daily Task + 🌗 chế độ ngày)
                import daymode
                import deadlines
                v = daymode.today_view(_npost, refresh=q.get("refresh", [""])[0] == "1")
                try: v["dups"] = __import__("dupscan").load().get("pairs", [])   # ⚠ Có thể trùng
                except Exception: v["dups"] = []
                try: v["deadlines"] = _dls()   # mục "Hạn sắp tới": tích Hoàn tất thì biến mất
                except Exception as e: v["deadlines"] = []; v["deadlinesError"] = str(e)[:200]
                return self._send(200, v)
            if u.path == "/api/program":   # tab Học kỳ / Tự chọn / ĐK tốt nghiệp (program.py, có đệm)
                import program
                return self._send(200, program.get(_npost, force=q.get("force", [""])[0] == "1"))
            if u.path == "/api/extra":   # 🎯 tab Ngoại khoá
                import extracurricular
                d = extracurricular.load()
                return self._send(200, {k: d.get(k) for k in ("at", "items", "ctsv_at")})
            if u.path == "/api/alerts":   # 📡 cảnh báo sự kiện (banner mọi tab)
                import importlib, alerts
                importlib.reload(alerts)
                import timetable
                import deadlines
                return self._send(200, {"alerts": alerts.active(classes=timetable.get(_npost)["events"], dls=_dls()), "mail": {**(_mail["last"] or {}), "running": _mail["running"]}})
            if u.path == "/api/school":   # 🏫 trạng thái đồng bộ dữ liệu trường (qldt + iCTSV)
                return self._send(200, school_status())
            if u.path == "/api/semester":
                d = n8n("copilot-semester", timeout=90)
                return self._send(200, d[0] if isinstance(d, list) else d)
            m = re.match(r"^/files/([0-9a-f-]{36})$", u.path)
            if m:
                it = get_item(m.group(1))
                if not it or not hmac.compare_digest(q.get("k", [""])[0], sign(it["id"])):
                    return self._send(403, {"error": "forbidden"})
                p = Path(it["path"])
                ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                return self._send(200, raw=p.read_bytes(), ctype=ctype)
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(500, {"error": str(e)[:400]})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        # (Claude 2026-10-03) công cụ ghi_hoc_tap của não Copilot (n8n trong Docker) -> logic điểm/luật môn/chuyên cần
        # (Claude 2026-10-05) công cụ doi_han: dời hạn TỰ ĐẶT (Tự luyện / cốt lõi); hạn Môn học của trường bị từ chối
        if u.path == "/api/nlm/add":   # 🧠 bạn bấm (đã xác nhận) -> gửi file sang NotebookLM; không ghi Notion, không gọi AI
            import nlm_bridge
            b = json.loads(self._body(100_000) or b"{}")
            if not b.get("confirmed"): return self._send(200, {"ok": False, "error": "cần xác nhận"})
            try: return self._send(200, nlm_bridge.add(b.get("files"), b.get("notebook") or None, b.get("new_title")))
            except ValueError as e: return self._send(200, {"ok": False, "error": str(e)})
        if u.path == "/api/lecture-monitor/dismiss":   # ẩn một buổi khỏi "Đang tải lên" (chỉ file giám sát trên máy)
            import lecture_monitor
            b = json.loads(self._body(10_000) or b"{}")
            return self._send(200, lecture_monitor.dismiss(str(b.get("captureId", ""))))
        if u.path == "/api/reschedule":
            if not hmac.compare_digest(self.headers.get("X-Copilot-Key", ""), SECRET):
                return self._send(403, {"error": "forbidden"})
            try:
                import reschedule, deadlines
                args = json.loads(self._body(64 * 1024) or b"{}")
                res = reschedule.run(_npost, args, kick_a4=lambda: n8n("copilot-run-a4", None, timeout=60))
                import chat_memory
                if res.get("se_doi"):
                    chat_memory.pending_add("doi_han", {"buoc": "ghi", "work_ids": args.get("work_ids"), "han_moi": args.get("han_moi")},
                                            "dời " + "; ".join(res["se_doi"]))
                if res.get("da_doi"):
                    chat_memory.pending_done("doi_han", args.get("work_ids", ""))
                if args.get("buoc") == "ghi" and res.get("da_doi"):
                    threading.Thread(target=lambda: _safe(lambda: deadlines.refresh(_npost)), daemon=True).start()
                return self._send(200, res)
            except Exception as e:
                return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:400]})
        if u.path == "/api/academic":
            if not hmac.compare_digest(self.headers.get("X-Copilot-Key", ""), SECRET):
                return self._send(403, {"error": "forbidden"})
            try:
                import academic
                args = json.loads(self._body(64 * 1024) or b"{}")
                return self._send(200, academic.record(lambda path, body: n8n(path, body, timeout=120), args))
            except Exception as e:
                return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:400]})
        if u.path == "/api/weekly":   # 📅 Weekly Reviews — n8n Chủ nhật 21:00 (ghi dòng), hoặc xem nhanh
            if not hmac.compare_digest(self.headers.get("X-Copilot-Key", ""), SECRET):
                return self._send(403, {"error": "forbidden"})
            try:
                import importlib, weekly
                importlib.reload(weekly)
                args = json.loads(self._body(4 * 1024) or b"{}")
                return self._send(200, weekly.run(_npost, save_row=bool(args.get("save")), today=args.get("today") or None))
            except Exception as e:
                return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:400]})
        if u.path == "/api/checks":   # bản tin 07:20/21:30: chỉ trả chỗ có vấn đề (checks.py)
            if not hmac.compare_digest(self.headers.get("X-Copilot-Key", ""), SECRET):
                return self._send(403, {"error": "forbidden"})
            try:
                import importlib, checks
                importlib.reload(checks)
                args = json.loads(self._body(4 * 1024) or b"{}")
                return self._send(200, checks.run(lambda path, body: n8n(path, body, timeout=180), args.get("today") or None))
            except Exception as e:
                return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:400], "canh_bao": []})
        if u.path in ("/api/research-request", "/api/research-next", "/api/research-save"):   # Research Hub (research.py)
            if not hmac.compare_digest(self.headers.get("X-Copilot-Key", ""), SECRET):
                return self._send(403, {"error": "forbidden"})
            try:
                import importlib, research
                importlib.reload(research)
                args = json.loads(self._body(4 * 1024 * 1024) or b"{}")
                post = lambda path, body: n8n(path, body, timeout=180)
                if u.path == "/api/research-request":
                    r = research.create_request(post, args)
                    if r.get("ok"):   # chạy ngay, không chờ lượt 15 phút
                        threading.Thread(target=lambda: _safe(lambda: n8n("copilot-run-research", None, timeout=600)), daemon=True).start()
                    return self._send(200, r)
                if u.path == "/api/research-next":
                    return self._send(200, research.next_job(post))
                return self._send(200, research.save(post, args))
            except Exception as e:
                return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:400]})
        if u.path == "/api/tkb":   # công cụ nhap_tkb của Copilot
            if not hmac.compare_digest(self.headers.get("X-Copilot-Key", ""), SECRET):
                return self._send(403, {"error": "forbidden"})
            try:
                import importlib, tkb
                importlib.reload(tkb)
                args = json.loads(self._body(256 * 1024) or b"{}")
                res = tkb.run(lambda path, body: n8n(path, body, timeout=600), args)
                if args.get("buoc") == "ghi": _tt_refresh()
                return self._send(200, res)
            except Exception as e:
                return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:400]})
        if u.path == "/api/semester-tick":   # n8n gọi 00:15 hằng ngày (bộ chuyển kỳ, thay tác vụ ChatGPT)
            if not hmac.compare_digest(self.headers.get("X-Copilot-Key", ""), SECRET):
                return self._send(403, {"error": "forbidden"})
            try:
                import importlib, semester
                importlib.reload(semester)
                args = json.loads(self._body(4 * 1024) or b"{}")
                dry = str(args.get("dry", "")).lower() in ("1", "true", "yes")
                return self._send(200, semester.tick(lambda path, body: n8n(path, body, timeout=180), dry=dry, today=args.get("today") or None))
            except Exception as e:
                return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:400]})
        if not self._same_origin():
            return self._send(403, {"error": "cross-origin blocked"})
        try:
            if u.path == "/api/chat-file":
                name = safe_name(q.get("name", ["file"])[0])
                data = self._body(30 * 1024 * 1024)
                CHAT_FILES.mkdir(exist_ok=True)
                fid = str(uuid.uuid4())
                p = CHAT_FILES / f"{fid}__{name}"
                p.write_bytes(data)
                mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                is_image = mime.startswith("image/")
                return self._send(200, {"fid": fid, "name": name, "mime": mime, "size": len(data), "isImage": is_image})
            if u.path == "/api/certs":   # thêm / sửa / xoá chứng chỉ ngoại ngữ (certs.py)
                import program, certs
                r = certs.save(_npost, json.loads(self._body(16 * 1024) or b"{}"))
                if r.get("ok"):
                    program.refresh_certs(_npost)
                    r["data"] = program.get(_npost)
                return self._send(200, r)
            if u.path in ("/api/day-mode", "/api/daily-done"):   # đặt chế độ ngày · đánh dấu việc hôm nay
                import daymode
                b = json.loads(self._body(8 * 1024) or b"{}")
                try:
                    if u.path == "/api/day-mode" and b.get("confirmed") is not True:   # không bao giờ ghi ngầm
                        return self._send(200, {"ok": False, "loi": "Cần bấm Xác nhận trước khi đổi chế độ."})
                    if u.path == "/api/day-mode":
                        r = daymode.set_mode(_npost, b.get("date"), b.get("mode"), b.get("hours"), b.get("note") or "", "Bạn")
                    else:
                        r = daymode.mark_daily(_npost, str(b.get("id", "")), bool(b.get("done")))
                except Exception as e:
                    return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:300]})
                if r.get("ok"):
                    r["data"] = daymode.today_view(_npost, refresh=True)
                    if u.path == "/api/day-mode" and str(b.get("date"))[:10] == r["data"]["today"]: threading.Thread(target=lambda: _safe(lambda: n8n("copilot-run-a4", None, timeout=30)), daemon=True).start()
                return self._send(200, r)
            if u.path == "/api/event-ack":   # 📡 Sẽ đi / Bỏ / Đã biết — chỉ khi đã Xác nhận
                import alerts
                b = json.loads(self._body(4 * 1024) or b"{}")
                if b.get("confirmed") is not True:
                    return self._send(200, {"ok": False, "loi": "Cần bấm Xác nhận trước."})
                if b.get("choice") not in ("Sẽ đi", "Bỏ", "Đã biết", "Đã nộp", "Tắt nhắc"):
                    return self._send(200, {"ok": False, "loi": "Lựa chọn không hợp lệ."})
                try:
                    r = alerts.ack(str(b.get("eid") or ""), b["choice"], stage=b.get("stage"), change_at=b.get("change_at"), post=_npost)
                except Exception as e:
                    return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:300]})
                import timetable, deadlines
                phone_refresh()
                return self._send(200, {**r, "alerts": alerts.active(classes=timetable.get(_npost)["events"], dls=_dls())})
            if u.path == "/api/dup-plan":   # chỉ đọc: những gì sẽ vào thùng rác nếu bỏ một bản trùng
                import dupscan
                b = json.loads(self._body(4 * 1024) or b"{}")
                pl = dupscan.plan_drop(_npost, str(b.get("pid") or ""), str(b.get("drop_id") or ""))
                return self._send(200, {"ok": bool(pl), "what": (pl or {}).get("what")})
            if u.path == "/api/dup-resolve":   # Giữ cả hai / Bỏ một bản (thùng rác Notion) — chỉ khi đã Xác nhận
                import dupscan, deadlines
                b = json.loads(self._body(4 * 1024) or b"{}")
                if b.get("confirmed") is not True:
                    return self._send(200, {"ok": False, "loi": "Cần bấm Xác nhận trước."})
                try:
                    r = dupscan.keep_both(str(b.get("pid") or "")) if b.get("action") == "keep" else dupscan.drop(_npost, str(b.get("pid") or ""), str(b.get("drop_id") or ""))
                except Exception as e:
                    return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:300]})
                if r.get("ok"): _tt_refresh(); phone_refresh()
                return self._send(200, {**r, "dups": dupscan.load().get("pairs", []), "deadlines": _dls()})
            if u.path == "/api/deadline-done":   # 📋 Hoàn tất một hạn (Status = Submitted) — chỉ khi đã Xác nhận
                import alerts, timetable, deadlines
                b = json.loads(self._body(4 * 1024) or b"{}")
                if b.get("confirmed") is not True:
                    return self._send(200, {"ok": False, "loi": "Cần bấm Xác nhận trước."})
                try: deadlines.complete(_npost, str(b.get("id") or ""))
                except Exception as e: return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:300]})
                dls = _dls(); phone_refresh()
                return self._send(200, {"ok": True, "deadlines": dls, "alerts": alerts.active(classes=timetable.get(_npost)["events"], dls=dls)})
            if u.path == "/api/mail-check":   # 📡 đọc mail trường ngay — chỉ khi đã Xác nhận
                b = json.loads(self._body(4 * 1024) or b"{}")
                if b.get("confirmed") is not True:
                    return self._send(200, {"ok": False, "loi": "Cần bấm Xác nhận trước."})
                threading.Thread(target=mail_run, args=("bạn bấm",), daemon=True).start()
                return self._send(200, {"ok": True, "started": not _mail["running"]})
            if u.path == "/api/school-sync":   # 🏫 đồng bộ trường ngay — chỉ khi đã Xác nhận
                b = json.loads(self._body(4 * 1024) or b"{}")
                if b.get("confirmed") is not True:
                    return self._send(200, {"ok": False, "loi": "Cần bấm Xác nhận trước khi đồng bộ."})
                started = school_start("bạn bấm")
                return self._send(200, {"ok": True, "started": started, **school_status()})
            if u.path in ("/api/summer", "/api/retake", "/api/improve"):   # thanh bên Học kỳ: kỳ hè · học lại — chỉ ghi khi đã Xác nhận
                import program
                b = json.loads(self._body(16 * 1024) or b"{}")
                if b.get("confirmed") is not True:
                    return self._send(200, {"ok": False, "loi": "Cần bấm Xác nhận trước khi ghi."})
                try:
                    if u.path == "/api/summer":
                        r = program.save_summer(_npost, b.get("k"), str(b.get("choice") or ""), str(b.get("company") or ""), str(b.get("position") or ""),
                                                str(b.get("hours") or ""), b.get("credits"), str(b.get("courses") or ""), str(b.get("notes") or ""))
                    elif u.path == "/api/improve":
                        r = (program.cancel_improve(_npost, str(b.get("id") or "")) if b.get("cancel") else
                             program.schedule_improve(_npost, str(b.get("id") or ""), str(b.get("sem") or "")))
                    else:
                        r = program.schedule_retake(_npost, str(b.get("id") or ""), str(b.get("sem") or ""))
                except Exception as e:
                    return self._send(200, {"ok": False, "loi": f"{type(e).__name__}: {e}"[:300]})
                if r.get("ok"):
                    program.refresh(_npost)
                    r["data"] = program.get(_npost)
                return self._send(200, r)
            if u.path == "/api/elective":   # chọn GDTC tự chọn
                import program
                b = json.loads(self._body(16 * 1024) or b"{}")
                r = program.choose_elective(_npost, str(b.get("code", "")), str(b.get("sem") or ""))
                if r.get("ok"):
                    program.refresh(_npost)   # dựng lại để giao diện thấy ngay trạng thái mới
                    r["data"] = program.get(_npost)
                return self._send(200, r)
            if u.path == "/api/chat":
                b = json.loads(self._body(1_000_000) or b"{}")
                text = str(b.get("message", ""))
                bins, notes = [], []
                for f in (b.get("files") or [])[:6]:
                    fid = str(f.get("fid", ""))
                    if not re.fullmatch(r"[0-9a-f-]{36}", fid):
                        continue
                    hit = next(CHAT_FILES.glob(f"{fid}__*"), None)
                    if not hit:
                        continue
                    name = hit.name.split("__", 1)[1]
                    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    note = f"[Tệp đính kèm: {name}]"
                    if mime in VISION_TYPES:
                        bins.append(("file", name, mime, hit.read_bytes()))
                    if mime not in VISION_TYPES or mime == "application/pdf":
                        note += "\nNội dung trích:\n" + extract_text(hit, 12000)
                    if f.get("save"):
                        enqueue_inbox(hit, name); note += "\n(đã lưu vào Uni-Documents — agent xếp tài liệu sẽ tự xếp vào đúng thư mục)"
                    notes.append(note)
                chat_input = (text + ("\n\n" + "\n\n".join(notes) if notes else "")).strip() or "(gửi tệp đính kèm)"
                import chat_memory   # (Claude 5/10) trí nhớ bền: lịch sử phiên + việc đang chờ xác nhận
                sess = str(b.get("sessionId", "web"))[:120]
                fields = {"chatInput": chat_memory.wrap(sess, chat_input), "sessionId": sess}
                r = n8n_multipart("copilot-api", fields, bins) if bins else n8n("copilot-api", fields, timeout=300)
                _safe(lambda: chat_memory.remember(sess, chat_input, r.get("output") or r.get("text") or ""))
                _tt_refresh()
                return self._send(200, {"output": r.get("output") or r.get("text") or ""})
            if u.path in ("/api/rec/start", "/api/rec/stop", "/api/rec/marker", "/api/rec/extend", "/api/rec/retry-upload"):
                b = json.loads(self._body(100_000) or b"{}")
                if u.path == "/api/rec/start":     # chỉ những trường cho phép; mô phỏng chỉ khi có file kiểm thử cục bộ
                    b = {k: b[k] for k in ("mode", "includeMic", "appPid", "appName", "course", "simulateFile") if k in b}
                return self._send(200, local_json(RECORDER + u.path.replace("/api/rec", ""), b,
                                                  timeout=900 if u.path.endswith(("stop", "retry-upload")) else 20))
            if u.path == "/api/rec/slide":
                cap = re.sub(r"[^\w\-]", "", q.get("captureId", [""])[0])
                name = safe_name(q.get("name", ["slide.jpg"])[0])
                data = self._body(25 * 1024 * 1024)
                req = urllib.request.Request(f"{SPEECH_GATE}/slides?captureId={cap}&name={urllib.parse.quote(name)}", data=data,
                                             headers={"Content-Type": "application/octet-stream"}, method="POST")
                with urllib.request.urlopen(req, timeout=60) as r:
                    return self._send(200, json.loads(r.read()))
            m = re.match(r"^/api/lectures/([0-9a-f-]{32,36})/reanalyze$", u.path)
            if m:
                return self._send(200, n8n("copilot-lecture-reanalyze", {"pageId": m.group(1)}, timeout=60))
            if u.path == "/api/upload":
                name = safe_name(q.get("name", ["file"])[0])
                data = self._body()
                INBOX.mkdir(parents=True, exist_ok=True)
                dest = unique_path(INBOX, name)
                dest.write_bytes(data)
                item = {"id": str(uuid.uuid4()), "name": name, "path": str(dest), "size": len(data), "status": "queued",
                        "createdAt": time.time(), "updatedAt": time.time()}
                with lock:
                    st = load_state(); st["items"].append(item); save_state(st)
                jobs.put(item["id"])
                return self._send(200, item)
            m = re.match(r"^/api/inbox/([0-9a-f-]{36})/assign$", u.path)
            if m:
                b = json.loads(self._body(100_000) or b"{}")
                folder = (b.get("folder") or "").strip().strip("\\/")
                if not folder or ".." in folder.split("\\") or ":" in folder:
                    return self._send(400, {"error": "thư mục không hợp lệ"})
                it = get_item(m.group(1))
                if not it or it["status"] not in ("needs_choice", "error"):
                    return self._send(409, {"error": "file không ở trạng thái chờ chọn"})
                place(it["id"], folder, {"title": it.get("title"), "summary": it.get("summary"), "category": it.get("category"),
                                         "course_code": course_of(folder)[0]}, "you")
                return self._send(200, get_item(it["id"]))
            self._send(404, {"error": "not found"})
        except urllib.error.HTTPError as e:
            self._send(502, {"error": f"n8n trả lỗi {e.code}"})
        except Exception as e:
            self._send(500, {"error": str(e)[:400]})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    # file đang dở từ lần chạy trước -> xếp lại
    for it in load_state()["items"]:
        if it.get("status") in ("queued", "reading", "thinking") and Path(it["path"]).exists():
            jobs.put(it["id"])
    threading.Thread(target=worker, daemon=True).start()
    _tt_refresh()   # làm nóng lịch: tab Lịch hiện ngay lần bấm đầu
    threading.Thread(target=uni_sync_loop, daemon=True).start()
    threading.Thread(target=mail_loop, daemon=True).start()    # 📡 mọi nguồn đúng khung 5 phút, 24 giờ
    threading.Thread(target=alert_loop, daemon=True).start()
    threading.Thread(target=lambda: __import__("lecture_monitor").loop(lambda path: n8n(path, timeout=60)), daemon=True).start()   # 🎙️ giám sát Ghi bài giảng mỗi 60 s (0 AI)
    threading.Thread(target=lambda: __import__('phone_link').listen(_npost), daemon=True).start()   # 📱 lệnh từ điện thoại qua ntfy   # 📡 cảnh báo leo thang + toast
    threading.Thread(target=school_loop, daemon=True).start()   # 🏫 qldt + iCTSV -> Notion (dữ liệu trường là cao nhất)
    def _mode_loop():   # 🌗 chế độ HÔM NAY -> 🎛️ University Control (A4 đọc), kể cả lúc qua ngày mới
        while True:
            try:
                import daymode, academic; daymode.sync_control(academic.Notion(_npost))
            except Exception as e: print("mode sync:", e)
            time.sleep(600)
    threading.Thread(target=_mode_loop, daemon=True).start()   # 💾 Uni-Documents -> Drive + University Inbox
    threading.Thread(target=lambda: _safe(lambda: __import__("program").refresh(_npost)), daemon=True).start()   # làm nóng tab Học kỳ
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
