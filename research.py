# -*- coding: utf-8 -*-
"""Research Hub chạy trên máy (Claude 2026-10-03) — thay "Research Agent" ChatGPT (thực tế chưa từng chạy).

Luồng:  Copilot nghien_cuu → POST /api/research-request → tạo 🔍 Research Requests (Not started) + gọi n8n chạy ngay
        n8n "Nghiên cứu" (mỗi 15 phút + webhook copilot-run-research):
          /api/research-next  → lấy 1 yêu cầu, khoá In progress, dựng lời gọi Gemini (Google Search)
          tìm bằng SearXNG trên máy (Docker university-searxng :8888) → Gemini (không tools) chọn + chú thích
          qua cổng :8350 (caller=research; hết quota thì cổng tự chuyển LM Studio)
          /api/research-save  → kiểm link thật (mở được), ghi 🌐 Research Results, yêu cầu → Done,
                                 tối đa 3 kết quả tốt nhất có môn rõ ràng → 📥 University Inbox (A2 xếp vào 📚 Course Materials)
Không bịa: AI chỉ được chọn trong kết quả tìm kiếm thật, và chỉ giữ link mở được (HTTP < 400).
"""
import uc_config as cfg
import datetime as dt, json, re, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from academic import Notion, P, rt, title, TZ

REQUESTS = cfg.notion("research_requests")
RESULTS = cfg.notion("research_results")
INBOX = cfg.notion("inbox")
SOURCES = ["Google Scholar", "Studocu", "Microsoft Learn", "Python Docs", "Stack Overflow"]
TYPES = ["Paper", "Study material", "Official docs", "Q&A", "Tutorial", "Other"]
DOMAIN_SOURCE = {"scholar.google": "Google Scholar", "studocu.com": "Studocu", "learn.microsoft.com": "Microsoft Learn",
                 "docs.python.org": "Python Docs", "stackoverflow.com": "Stack Overflow"}
MAX_TRIES = 3
INBOX_MIN_REL, INBOX_MAX = 70, 3
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UniversityCopilot-Research/1.0"}


def _now():
    return dt.datetime.now(TZ)

def create_request(post, a):
    """Từ công cụ nghien_cuu của Copilot."""
    q = (a.get("cau_hoi") or "").strip()
    if len(q) < 6: return {"ok": False, "thieu": ["Cần tìm gì? Nói rõ chủ đề và môn."]}
    src = [s.strip() for s in str(a.get("nguon") or "").split(",") if s.strip() in SOURCES]
    nt = Notion(post)
    page = nt.create(REQUESTS, {"Query": title(q), "Sources": {"multi_select": [{"name": s} for s in src]},
                                "Status": {"status": {"name": "Not started"}}, "Search Notes": rt("Tạo từ University Copilot")})
    return {"ok": True, "da_ghi": [f"Yêu cầu tìm: {q}"], "id": page.get("id"),
            "ghi_chu": "Đang tìm ngay (thường 1–3 phút). Hỏi lại 'kết quả tìm tài liệu' để xem."}


def _courses(nt):
    return [c for c in nt.courses() if c["status"] in ("Taking", "Planned") and c["code"]]

def next_job(post):
    nt = Notion(post)
    rows = nt.query(REQUESTS, {"property": "Status", "status": {"equals": "Not started"}},
                    [{"timestamp": "created_time", "direction": "ascending"}])
    # yêu cầu kẹt In progress quá 30 phút (lượt trước chết giữa chừng) cũng được lấy lại
    stuck = [r for r in nt.query(REQUESTS, {"property": "Status", "status": {"equals": "In progress"}})
             if dt.datetime.fromisoformat(r["last_edited_time"].replace("Z", "+00:00")) < _now() - dt.timedelta(minutes=30)]
    rows = rows + stuck
    if not rows: return {"job": None}
    r = rows[0]
    q = P(r, "Query") or ""
    notes = P(r, "Search Notes") or ""
    tries = int((re.search(r"\[thử (\d+)\]", notes) or [0, 0])[1]) + 1
    if tries > MAX_TRIES:
        nt.patch(r["id"], {"Status": {"status": {"name": "Done"}}, "Search Notes": rt(f"Dừng sau {MAX_TRIES} lần lỗi. {notes}"[:1900])})
        return {"job": None, "bo_qua": q}
    nt.patch(r["id"], {"Status": {"status": {"name": "In progress"}}, "Search Notes": rt(f"[thử {tries}] đang tìm (n8n) {_now():%d/%m %H:%M}")})
    src = P(r, "Sources") or []
    cands = search(q, src)
    if not cands:
        nt.patch(r["id"], {"Status": {"status": {"name": "Not started"}},
                           "Search Notes": rt(f"[thử {tries}] SearXNG không trả kết quả (máy tìm kiếm có thể đang chặn) — thử lại lượt sau")})
        return {"job": None, "loi": "không có kết quả tìm kiếm"}
    cs = _courses(nt)
    course_list = "; ".join(f"{c['code']} {c['name']}" for c in cs if c["status"] == "Taking") or "(chưa có)"
    listing = "\n".join(f"[{i}] {c['title']} — {c['url']}\n    {c['snippet']}" for i, c in enumerate(cands))
    prompt = f"""Bạn là trợ lý chọn tài liệu học tập cho một sinh viên năm 1 Kỹ thuật Máy tính, Đại học Bách khoa Hà Nội.
Yêu cầu: "{q}"
Nguồn ưu tiên: {", ".join(src) if src else "không chỉ định"}.
Môn sinh viên đang học: {course_list}.

Dưới đây là kết quả tìm kiếm thật (đánh số). CHỈ được chọn trong danh sách này, không thêm link khác.
{listing}

Chọn 3–8 kết quả hữu ích nhất cho yêu cầu (bỏ quảng cáo, trang chung chung, mạng xã hội trừ khi thực sự hữu ích).
Trả lời CHỈ một khối JSON:
{{"mon": "<mã môn trong danh sách môn đang học mà yêu cầu thuộc về, hoặc rỗng>",
  "chon": [{{"so": <số trong ngoặc vuông>, "loai": "Paper|Study material|Official docs|Q&A|Tutorial|Other",
            "lien_quan": 0-100, "vi_sao": "1–2 câu tiếng Việt: tài liệu này giúp gì cho yêu cầu"}}]}}"""
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    return {"job": {"id": r["id"], "query": q, "sources": src, "tries": tries, "cands": cands}, "body": body}


SEARX = "http://127.0.0.1:8888/search"
SITE = {"Studocu": "studocu.vn OR site:studocu.com", "Microsoft Learn": "learn.microsoft.com", "Python Docs": "docs.python.org",
        "Stack Overflow": "stackoverflow.com"}

def search(q, src, limit=24):
    """SearXNG (Docker university-searxng, 127.0.0.1:8888): truy vấn chính + truy vấn theo nguồn ưu tiên."""
    qs = [(q, {})]
    for s in src:
        if s == "Google Scholar": qs.append((q, {"categories": "science"}))
        elif s in SITE: qs.append((f"{q} site:{SITE[s]}", {}))
    out, seen = [], set()
    for text, extra in qs:
        try:
            url = SEARX + "?" + urllib.parse.urlencode({"q": text, "format": "json", **extra})
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                res = json.load(r).get("results", [])
        except Exception:
            continue
        for x in res:
            u = x.get("url") or ""
            if u.startswith("http") and u not in seen:
                seen.add(u)
                out.append({"title": (x.get("title") or u)[:160], "url": u, "snippet": re.sub(r"\s+", " ", x.get("content") or "")[:240]})
    return out[:limit]


def _resolve(url, timeout=12):
    """-> link thật (theo chuyển hướng) nếu mở được, None nếu không."""
    if not re.match(r"^https?://", url or ""): return None
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status < 400: return r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429) and method == "GET":   # trang chặn bot nhưng có thật (vd Studocu)
                return e.geturl() or url
        except Exception:
            pass
    return None

def _parse(resp):
    cand = (resp.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    m = re.search(r"\{.*\}", text, re.S)
    data = {}
    if m:
        try: data = json.loads(m.group(0))
        except Exception: data = {}
    chunks = [c.get("web", {}) for c in (cand.get("groundingMetadata") or {}).get("groundingChunks", [])]
    return data, chunks, text

def _source(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    for d, s in DOMAIN_SOURCE.items():
        if d in host: return s
    return None

def save(post, a):
    job, status, resp = a.get("job") or {}, int(a.get("status") or 0), a.get("resp") or {}
    if not job.get("id"): return {"ok": False, "loi": "thiếu job"}
    nt = Notion(post)
    if status != 200 or not resp.get("candidates"):
        msg = ((resp.get("error") or {}).get("message") or f"HTTP {status}")[:300]
        nt.patch(job["id"], {"Status": {"status": {"name": "Not started"}},
                             "Search Notes": rt(f"[thử {job.get('tries', 1)}] Gemini lỗi: {msg} — thử lại lượt sau")})
        return {"ok": False, "loi": msg}
    data, _, raw = _parse(resp)
    cands = job.get("cands") or []
    items = []
    for x in (data.get("chon") or []):
        try: c = cands[int(x.get("so"))]
        except Exception: continue
        items.append({"tieu_de": c["title"], "url": c["url"], "loai": x.get("loai"), "lien_quan": x.get("lien_quan"), "vi_sao": x.get("vi_sao")})
    with ThreadPoolExecutor(8) as ex:
        real = list(ex.map(_resolve, [x["url"] for x in items]))
    kept, seen = [], set()
    for x, u in zip(items, real):
        if u and u not in seen:
            seen.add(u); kept.append({**x, "url": u})
    cs = {c["code"]: c for c in _courses(nt)}
    course = cs.get(str(data.get("mon") or "").strip().upper())
    created, inbox = [], 0
    for x in sorted(kept, key=lambda x: -(int(x.get("lien_quan") or 0))):
        rel = max(0, min(100, int(x.get("lien_quan") or 0)))
        typ = x.get("loai") if x.get("loai") in TYPES else "Other"
        props = {"Result": title(x.get("tieu_de") or x["url"]), "URL": {"url": x["url"][:1900]}, "Type": {"select": {"name": typ}},
                 "Relevance": {"number": rel}, "Why Relevant": rt(x.get("vi_sao") or ""), "Request": {"relation": [{"id": job["id"]}]}}
        src = _source(x["url"])
        if src: props["Source"] = {"select": {"name": src}}
        page = nt.create(RESULTS, props)
        created.append(page["id"])
        if course and rel >= INBOX_MIN_REL and inbox < INBOX_MAX:
            kind = {"Paper": "paper", "Official docs": "tài liệu chính thức", "Tutorial": "hướng dẫn", "Q&A": "hỏi đáp"}.get(typ, "đọc thêm")
            ctx = " | ".join([f"🌐 Tài liệu ngoài (Research Hub) — reading, {kind}", f"Môn: {course['code']} {course['name']}",
                              f"URL: {x['url']}", f"Vì sao: {x.get('vi_sao') or ''}", f"Yêu cầu: {job.get('query', '')}",
                              f"Độ liên quan: {rel}/100"])[:1900]
            nt.create(INBOX, {"Upload": title(x.get("tieu_de") or x["url"]), "Context": rt(ctx),
                              "Triage Status": {"status": {"name": "Not started"}}})
            inbox += 1
    note = (f"{_now():%d/%m %H:%M} · {len(created)} kết quả có link mở được"
            + (f" · {inbox} vào University Inbox ({course['code']})" if inbox else "")
            + ("" if course else " · không rõ môn nên không đưa vào Inbox")
            + (f" · bỏ {len(items) - len([1 for u in real if u])} link không mở được" if items else ""))
    if not created and not raw.strip():
        note = "Gemini không trả kết quả."
    nt.patch(job["id"], {"Status": {"status": {"name": "Done"}}, "Results Found": {"number": len(created)},
                         "Results": {"relation": [{"id": i} for i in created]}, "Search Notes": rt(note)})
    return {"ok": True, "ket_qua": len(created), "inbox": inbox, "mon": course["code"] if course else None, "ghi_chu": note}
