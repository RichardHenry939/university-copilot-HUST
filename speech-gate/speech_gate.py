"""Cổng âm thanh -> chữ -> nén (giai đoạn 2 của plan, Claude 2026-10-02).

Mục đích: KHÔNG BAO GIỜ gửi audio cho Gemini. Audio bài giảng được xử lý hết trên máy:
  1. Kiểm tra chất lượng (VAD): quá ít tiếng nói -> "unusable", dừng ngay (0 token, không chép lời).
  2. Chép lời bằng PhoWhisper-large -> transcript có mốc giờ thật. Mặc định chạy trên NPU (OpenVINO INT8,
     ~4.5x realtime, đo 3/10); NPU lỗi/không có -> tự lùi về CPU (faster-whisper int8, ~1x realtime).
  3. Lọc rác: câu bịa kiểu "đăng ký kênh", lặp từ, đoạn model không chắc (logprob thấp / nén bất thường).
  4. Nén bằng LM Studio (qwen3-14b) theo đoạn ~8 phút: giữ nguyên văn công thức/định nghĩa/BTVN/deadline.
  5. Gọi lại n8n (webhook lecture-transcript-ready) với bản nén + thống kê + ảnh slide (nếu có).

HTTP (127.0.0.1:8340, n8n trong Docker gọi qua host.docker.internal):
  POST /jobs?captureId=&startedAt=&endedAt=&markers=&callback=   body = audio (mp3/wav/webm)
  GET  /jobs/<jobId>            GET /jobs?captureId=<id>        GET /health
  POST /slides?captureId=&name= body = ảnh (Copilot tải lên trong giờ học)
"""
import base64, io, json, os, queue, re, threading, time, traceback, urllib.request, uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("SPEECH_GATE_DIR", r"D:\Data\SpeechGate"))
JOBS, SLIDES = ROOT / "jobs", ROOT / "slides"
MODEL_DIR = r"D:\AI\models\phowhisper-large-ct2"
# (Claude 2026-10-03) PhoWhisper tren NPU: IR tao boi export_ov.py + quantize_ov.py (.venv-ov). SPEECH_GATE_STT=cpu de tat.
OV_MODEL_DIR = r"D:\AI\models\phowhisper-large-ov-int8"
OV_CACHE = r"D:\AI\Cache\openvino"          # ban bien dich cho NPU: lan dau ~4.5 phut, sau do ~10 s
STT_DEVICE = os.environ.get("SPEECH_GATE_STT", "NPU").upper()
OV_WIN_SEC = 28.0                              # Whisper xu ly cua so 30 s; ghep cac doan VAD toi da 28 s
LMSTUDIO = "http://127.0.0.1:1234/v1/chat/completions"
LM_MODEL = "qwen3-14b"
SECRET = Path(os.environ.get("UC_SECRET_FILE") or Path(__file__).resolve().parent.parent / ".copilot-secret")   # khoá chung với web app UC
PORT = 8340
SR = 16000
TZ = timezone(timedelta(hours=7))

# Ngưỡng chất lượng (đo trên dữ liệu thật 2/10: bản ghi ngồi xa / trong balo chỉ có 1.5–2.3 phút tiếng nói / 186 phút)
MIN_SPEECH_MIN = 3.0
MIN_SPEECH_RATIO = 0.05
MIN_KEPT_CHARS = 400
CHUNK_SEC = 8 * 60

HALLU = re.compile(r"(subscribe|đăng k[ýí] (cho )?kênh|lalaschool|ghiền mì gõ|cảm ơn các bạn đã (theo dõi|xem)|"
                   r"like (và|and) share|bấm chuông|nhấn chuông|video hấp dẫn|theo dõi kênh)", re.I)

for d in (JOBS, SLIDES):
    d.mkdir(parents=True, exist_ok=True)

_q: "queue.Queue[str]" = queue.Queue()
_lock = threading.Lock()
_model = None


def log(msg):
    line = f"{datetime.now(TZ):%Y-%m-%d %H:%M:%S} {msg}"
    try:
        with open(ROOT / "speech-gate.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- jobs
def job_path(jid):
    return JOBS / jid


def load_job(jid):
    try:
        return json.loads((job_path(jid) / "job.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def save_job(job):
    p = job_path(job["jobId"]); p.mkdir(parents=True, exist_ok=True)
    tmp = p / "job.tmp"
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p / "job.json")


def find_by_capture(cap):
    best = None
    for d in JOBS.iterdir():
        j = load_job(d.name)
        if j and j.get("captureId") == cap and (best is None or j["created"] > best["created"]):
            best = j
    return best


def public(job):
    return {k: job.get(k) for k in ("jobId", "captureId", "status", "stage", "progress", "reason", "stats", "created", "finished")}


# ---------------------------------------------------------------- pipeline
def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL_DIR, device="cpu", compute_type="int8", cpu_threads=6)
    return _model


def get_ov():
    """WhisperPipeline tren NPU, hoac None neu tat/khong dung duoc (-> CPU)."""
    if STT_DEVICE == "CPU" or not Path(OV_MODEL_DIR).exists():
        return None
    try:
        import openvino_genai as og
        return og.WhisperPipeline(OV_MODEL_DIR, STT_DEVICE, CACHE_DIR=OV_CACHE)
    except Exception as e:
        log(f"NPU không dùng được ({type(e).__name__}: {e}) -> chép lời bằng CPU")
        return None


class Seg:
    """Doan chep loi cung dang voi faster-whisper de bo loc phia sau dung chung."""
    def __init__(self, start, end, text, compression_ratio, avg_logprob=0.0, no_speech_prob=0.0):
        self.start, self.end, self.text = start, end, text
        self.compression_ratio, self.avg_logprob, self.no_speech_prob = compression_ratio, avg_logprob, no_speech_prob


def ov_windows(ts, max_sec=OV_WIN_SEC, pad=0.2):
    """Ghep cac doan co tieng noi (VAD) thanh cua so <= max_sec. Khoang lang khong bao gio vao model:
    Whisper gap im lang/tap am se bia ra cau (do 3/10: 20 s im lang -> 1 cau vo nghia)."""
    wins, cur = [], None
    for t in ts:
        a, b = t["start"] / SR, t["end"] / SR
        while b - a > max_sec:                      # doan noi lien dai hon cua so -> cat
            if cur: wins.append(cur); cur = None
            wins.append([a, a + max_sec]); a += max_sec
        if cur and b - cur[0] <= max_sec and a - cur[1] < 2.0:
            cur[1] = b
        else:
            if cur: wins.append(cur)
            cur = [a, b]
    if cur: wins.append(cur)
    return [(max(0.0, a - pad), b + pad) for a, b in wins]


def transcribe_ov(pipe, audio, ts):
    import zlib
    for a, b in ov_windows(ts):
        chunk = audio[int(a * SR):int(b * SR)]
        r = pipe.generate(chunk.tolist(), language="<|vi|>", task="transcribe", max_new_tokens=220)
        text = " ".join(r.texts).strip()
        raw = text.encode("utf-8")
        cr = len(raw) / max(1, len(zlib.compress(raw))) if raw else 0.0
        # NPU khong tra logprob (scores luon 1.0) -> thay bang mat do chu: noi that ~10-20 ky tu/giay,
        # bia/lap thuong vuot xa. Danh dau "khong chac" de bo loc chung loai bo.
        cps = len(text) / max(0.5, b - a)
        yield Seg(a, b, text, cr, avg_logprob=-2.0 if cps > 30 else 0.0)


def clean_text(t):
    t = re.sub(r"\b(\w+)(?:\s+\1\b){2,}", r"\1", t, flags=re.I)          # "nằm nằm nằm" -> "nằm"
    t = re.sub(r"((?:\S+\s+){2,6}?\S+)(?:\s+\1){1,}", r"\1", t, flags=re.I)  # cụm 3–7 từ lặp liền
    return t.strip()


def clock(start_iso, off):
    try:
        t0 = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(TZ)
        return (t0 + timedelta(seconds=off)).strftime("%H:%M")
    except Exception:
        m = int(off // 60)
        return f"+{m // 60:d}:{m % 60:02d}"


LM_FALLBACK = "qwen3-8b"   # nhẹ hơn ~5 GB: dùng khi qwen3-14b không nạp được (thiếu bộ nhớ)


def lm(messages, max_tokens=1400):
    """Gọi LM Studio; lỗi (không nạp được model, 400/5xx, mất kết nối) -> chờ rồi thử lại, 2 lần cuối dùng model dự phòng."""
    last = None
    for attempt, model in enumerate([LM_MODEL, LM_MODEL, LM_FALLBACK, LM_FALLBACK]):
        body = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
        req = urllib.request.Request(LMSTUDIO, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                out = json.loads(r.read())["choices"][0]["message"]["content"] or ""
            break
        except Exception as e:
            last = e
            log(f"LM Studio ({model}) lỗi lần {attempt + 1}: {e}")
            time.sleep(45 * (attempt + 1))
    else:
        raise RuntimeError(f"LM Studio lỗi sau 4 lần (qwen3-14b, {LM_FALLBACK}): {last}")
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S)
    return out.split("</think>")[-1].strip()


COMPACT_SYS = """/no_think
Bạn là trợ lý NÉN bản chép lời bài giảng đại học tiếng Việt (chép tự động, có lỗi chính tả/nhận dạng).
Nhiệm vụ: viết lại đoạn được giao thành GHI CHÚ NGẮN GỌN, giữ đủ ý giảng, theo thứ tự thời gian.
Quy tắc:
- GIỮ NGUYÊN VĂN (không diễn giải): công thức, định nghĩa, tên khái niệm/thuật ngữ, ví dụ số, bài tập về nhà, deadline, lời dặn "sẽ thi/kiểm tra".
- BỎ: câu đệm, chào hỏi, điểm danh, chuyện ngoài lề, câu lặp.
- Câu vô nghĩa/không đọc được do lỗi nhận dạng -> bỏ, hoặc ghi "[không rõ]" nếu có vẻ quan trọng. KHÔNG được tự bịa nội dung cho mạch lạc.
- Mỗi ý 1 gạch đầu dòng, mở đầu bằng mốc giờ [HH:MM] lấy từ đoạn chép lời.
- Nếu cả đoạn không có nội dung bài giảng, chỉ trả lời đúng: (không có nội dung giảng)
Chỉ trả về danh sách gạch đầu dòng, không lời dẫn."""


def process(jid):
    job = load_job(jid)
    if not job:
        return
    def upd(**kw):
        job.update(kw); save_job(job)
    try:
        from audio_io import load
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        if job.get("resume") and (job_path(jid) / "transcript.txt").exists():
            return compact_step(job, upd)    # chạy lại: đã chép lời xong -> chỉ nén + gọi lại n8n
        upd(status="running", stage="decode", progress=0.02)
        audio = load(str(job_path(jid) / job["audioFile"]))
        dur = len(audio) / SR
        # 1) chất lượng
        upd(stage="quality", progress=0.05)
        ts = get_speech_timestamps(audio, VadOptions(threshold=0.3, min_silence_duration_ms=800))
        speech = sum(t["end"] - t["start"] for t in ts) / SR
        rms = float(np.sqrt(np.mean(audio ** 2)) + 1e-9)
        stats = {"duration_min": round(dur / 60, 1), "speech_min": round(speech / 60, 1),
                 "speech_ratio": round(speech / max(dur, 1), 3), "mean_db": round(20 * np.log10(rms), 1)}
        if speech / max(dur, 1) < MIN_SPEECH_RATIO:
            return finish(job, "unusable", stats, reason=(
                f"Chỉ có {stats['speech_min']} phút tiếng nói trong {stats['duration_min']} phút "
                f"({stats['speech_ratio']*100:.1f}%) — giọng giảng quá nhỏ/xa (máy để xa hoặc trong balo) hoặc không phải bài giảng. "
                "Không chép lời, không gửi Gemini (0 token)."))
        if speech / 60 < MIN_SPEECH_MIN:
            return finish(job, "unusable", stats, reason=(
                f"Bản ghi quá ngắn: chỉ {stats['speech_min']} phút tiếng nói (cần ít nhất {MIN_SPEECH_MIN:g} phút để thành ghi chú bài giảng). "
                "Không chép lời, không gửi Gemini (0 token)."))
        # 2) chép lời
        upd(stage="transcribe", progress=0.08, stats=stats)
        t0 = time.time()
        pipe = get_ov()
        if pipe is not None:
            stats["stt_backend"] = STT_DEVICE.lower()
            segs = transcribe_ov(pipe, audio, ts)
        else:
            stats["stt_backend"] = "cpu"
            segs, _ = get_model().transcribe(audio, language="vi", beam_size=5, vad_filter=True,
                                             vad_parameters={"threshold": 0.3, "min_silence_duration_ms": 800},
                                             condition_on_previous_text=False)
        kept, dropped, lp = [], 0, []
        for s in segs:
            job["progress"] = round(0.08 + 0.72 * min(1.0, s.end / max(dur, 1)), 3)
            if len(kept) % 20 == 0:
                save_job(job)
            text = clean_text(s.text)
            bad = (not text or HALLU.search(text) or s.compression_ratio > 2.4 or s.avg_logprob < -1.0
                   or (s.no_speech_prob > 0.6 and s.avg_logprob < -0.7))
            if bad:
                dropped += 1
                continue
            if kept and text == kept[-1]["text"]:
                continue
            kept.append({"start": round(s.start, 1), "end": round(s.end, 1), "text": text})
            lp.append(s.avg_logprob)
        pipe = segs = None  # nha NPU/RAM ngay sau khi chep xong (Qwen can RAM cho buoc nen)
        stats.update(stt_min=round((time.time() - t0) / 60, 1), segments=len(kept), dropped_segments=dropped,
                     kept_chars=sum(len(k["text"]) for k in kept),
                     avg_logprob=round(float(np.mean(lp)), 3) if lp else None)
        lines = [f"[{clock(job['startedAt'], k['start'])}] {k['text']}" for k in kept]
        (job_path(jid) / "transcript.txt").write_text("\n".join(lines), encoding="utf-8")
        (job_path(jid) / "kept.json").write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
        if stats["kept_chars"] < MIN_KEPT_CHARS:
            return finish(job, "unusable", stats, reason=(
                f"Sau khi lọc chỉ còn {stats['kept_chars']} ký tự đáng tin ({dropped} đoạn bị loại vì nghe không rõ/bịa). "
                "Không gửi Gemini."))
        # 3) nén bằng LM Studio theo đoạn ~8 phút
        upd(stage="compact", progress=0.82, stats=stats)
        chunks, cur, cur_start = [], [], None
        for k, line in zip(kept, lines):
            if cur_start is None:
                cur_start = k["start"]
            cur.append(line)
            if k["end"] - cur_start >= CHUNK_SEC:
                chunks.append("\n".join(cur)); cur, cur_start = [], None
        if cur:
            chunks.append("\n".join(cur))
        parts = []
        for i, ch in enumerate(chunks):
            job["progress"] = round(0.82 + 0.15 * i / max(1, len(chunks)), 3); save_job(job)
            out = lm([{"role": "system", "content": COMPACT_SYS},
                      {"role": "user", "content": f"Đoạn {i+1}/{len(chunks)} của bản chép lời:\n{ch}"}])
            if out and "không có nội dung giảng" not in out.lower():
                parts.append(out)
        compact = "\n".join(parts).strip()
        # 4) đoạn quanh marker: giữ nguyên văn ±60s
        excerpts = []
        for m in job.get("markers") or []:
            try:
                t = float(m.get("t", m.get("offset", 0)))
            except (TypeError, ValueError):
                continue
            near = [l for k, l in zip(kept, lines) if t - 60 <= k["start"] <= t + 60]
            excerpts.append({"at": clock(job["startedAt"], t), "kind": m.get("kind", ""), "note": m.get("note", ""),
                             "text": " ".join(near)[:1500]})
        stats.update(compact_chars=len(compact), compact_chunks=len(chunks))
        (job_path(jid) / "compact.txt").write_text(compact, encoding="utf-8")
        return finish(job, "done", stats, compact=compact, excerpts=excerpts, transcript="\n".join(lines))
    except Exception as e:
        log(f"job {jid} lỗi: {traceback.format_exc()}")
        job.update(status="error", reason=f"{type(e).__name__}: {e}", finished=time.time()); save_job(job)
        callback(job, {"status": "error", "reason": job["reason"]})


def slides_payload(cap, limit=12):
    from PIL import Image
    out = []
    d = SLIDES / cap
    if not d.exists():
        return out
    for f in sorted(d.iterdir())[:limit]:
        try:
            im = Image.open(f); im = im.convert("RGB"); im.thumbnail((1280, 1280))
            buf = io.BytesIO(); im.save(buf, "JPEG", quality=80)
            out.append({"name": f.name, "mime": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()})
        except Exception:
            continue
    return out


def compact_step(job, upd):
    jid = job["jobId"]; stats = job.get("stats") or {}
    upd(status="running", stage="compact", progress=0.82, reason="")
    kj = job_path(jid) / "kept.json"
    lines = (job_path(jid) / "transcript.txt").read_text(encoding="utf-8").splitlines()
    if kj.exists():
        kept = json.loads(kj.read_text(encoding="utf-8"))
    else:   # job cũ: chỉ có mốc [HH:MM] -> thời gian xấp xỉ theo phút
        kept, base = [], None
        for ln in lines:
            m = re.match(r"\[(\d+):(\d+)\]", ln)
            t = (int(m.group(1)) * 60 + int(m.group(2))) * 60 if m else (kept[-1]["start"] if kept else 0)
            base = t if base is None else base
            kept.append({"start": t - base, "end": t - base + 30, "text": ln})
    chunks, cur, cur_start = [], [], None
    for k, line in zip(kept, lines):
        if cur_start is None:
            cur_start = k["start"]
        cur.append(line)
        if k["end"] - cur_start >= CHUNK_SEC:
            chunks.append("\n".join(cur)); cur, cur_start = [], None
    if cur:
        chunks.append("\n".join(cur))
    parts = []
    for i, ch in enumerate(chunks):
        job["progress"] = round(0.82 + 0.15 * i / max(1, len(chunks)), 3); save_job(job)
        out = lm([{"role": "system", "content": COMPACT_SYS},
                  {"role": "user", "content": f"Đoạn {i+1}/{len(chunks)} của bản chép lời:\n{ch}"}])
        if out and "không có nội dung giảng" not in out.lower():
            parts.append(out)
    compact = "\n".join(parts).strip()
    job.pop("resume", None)
    return finish(job, "done", stats, compact=compact, excerpts=[], transcript="\n".join(lines))


def finish(job, status, stats, reason="", compact="", excerpts=None, transcript=""):
    job.update(status=status, stage="finished", progress=1.0, stats=stats, reason=reason, finished=time.time())
    save_job(job)
    log(f"job {job['jobId']} ({job['captureId']}) -> {status} {json.dumps(stats, ensure_ascii=False)}")
    callback(job, {"status": status, "reason": reason, "stats": stats, "compact": compact, "excerpts": excerpts or [],
                   "transcript": transcript[:90000], "slides": slides_payload(job["captureId"]) if status == "done" else []})


def callback(job, extra):
    url = job.get("callback")
    if not url:
        return
    body = {"jobId": job["jobId"], "captureId": job["captureId"], "startedAt": job.get("startedAt"),
            "endedAt": job.get("endedAt"), **extra}
    key = SECRET.read_text(encoding="utf-8").strip() if SECRET.exists() else ""
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "X-Copilot-Key": key})
            urllib.request.urlopen(req, timeout=60).read()
            job["callbackOk"] = True; save_job(job)
            return
        except Exception as e:
            log(f"callback {job['jobId']} lần {attempt+1} lỗi: {e}")
            time.sleep(15 * (attempt + 1))
    job["callbackOk"] = False; save_job(job)


def worker():
    while True:
        jid = _q.get()
        try:
            process(jid)
        finally:
            _q.task_done()


# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/health":
            return self._send(200, {"ok": True, "queue": _q.qsize(),
                                    "stt": STT_DEVICE.lower() if STT_DEVICE != "CPU" and Path(OV_MODEL_DIR).exists() else "cpu",
                                    "model": Path(OV_MODEL_DIR if STT_DEVICE != "CPU" else MODEL_DIR).name, "fallback": Path(MODEL_DIR).name})
        if u.path == "/jobs" and "captureId" in q:
            j = find_by_capture(q["captureId"][0])
            return self._send(200 if j else 404, public(j) if j else {"error": "not found"})
        if u.path.startswith("/jobs/"):
            j = load_job(u.path.split("/")[2])
            return self._send(200 if j else 404, public(j) if j else {"error": "not found"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path.startswith("/jobs/") and u.path.endswith("/retry"):
                jid = u.path.split("/")[2]
                job = load_job(jid)
                if not job:
                    return self._send(404, {"error": "not found"})
                if job["status"] in ("queued", "running"):
                    return self._send(200, public(job))
                job.update(status="queued", stage="queued", progress=0, reason="",
                           resume=(job_path(jid) / "transcript.txt").exists())
                save_job(job); _q.put(jid)
                log(f"chạy lại job {jid} ({job['captureId']}) từ {'bước nén' if job['resume'] else 'đầu'}")
                return self._send(200, public(job))
            if u.path == "/jobs":
                cap = q.get("captureId", "").strip()
                if not cap:
                    return self._send(400, {"error": "captureId required"})
                data = self._body()
                if len(data) < 1000:
                    return self._send(400, {"error": "audio body missing"})
                with _lock:
                    prev = find_by_capture(cap)
                    if prev and prev["status"] in ("queued", "running"):
                        return self._send(200, public(prev))      # chống gửi trùng
                    jid = uuid.uuid4().hex[:12]
                    try:
                        markers = json.loads(q.get("markers") or "[]")
                    except ValueError:
                        markers = []
                    job = {"jobId": jid, "captureId": cap, "startedAt": q.get("startedAt", ""), "endedAt": q.get("endedAt", ""),
                           "markers": markers if isinstance(markers, list) else [], "callback": q.get("callback", ""),
                           "status": "queued", "stage": "queued", "progress": 0, "created": time.time(), "audioFile": "audio.bin"}
                    job_path(jid).mkdir(parents=True, exist_ok=True)
                    (job_path(jid) / "audio.bin").write_bytes(data)
                    save_job(job)
                _q.put(jid)
                log(f"nhận job {jid} cho {cap} ({len(data)/1e6:.1f} MB)")
                return self._send(200, public(job))
            if u.path == "/slides":
                cap = re.sub(r"[^\w\-]", "", q.get("captureId", ""))
                name = re.sub(r"[^\w\-.]", "_", q.get("name", "slide.jpg"))[-80:]
                if not cap:
                    return self._send(400, {"error": "captureId required"})
                d = SLIDES / cap; d.mkdir(parents=True, exist_ok=True)
                (d / f"{int(time.time()*1000)}-{name}").write_bytes(self._body())
                return self._send(200, {"ok": True, "count": len(list(d.iterdir()))})
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    for d in JOBS.iterdir():           # chạy lại job dở dang sau khi khởi động lại máy
        j = load_job(d.name)
        if j and j.get("status") in ("queued", "running"):
            j.update(status="queued", stage="queued", progress=0); save_job(j); _q.put(j["jobId"])
    threading.Thread(target=worker, daemon=True).start()
    log("speech gate chạy")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
