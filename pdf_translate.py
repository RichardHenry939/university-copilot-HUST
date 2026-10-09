# -*- coding: utf-8 -*-
"""📄 Dịch tài liệu PDF (Claude 2026-10-07) — PDFMathTranslate (pdf2zh) chạy với LM Studio trên máy, giữ bố cục + công thức.

Người dùng: "sub part dịch tài liệu (giống Google Dịch nhưng cho PDF) cho mục tài liệu"; bản dịch "nạp thẳng vào cả Uni-Documents
và Notion giống 1 file được ném vào Inbox".
  • Tìm PDF trong Uni-Documents -> tích chọn -> bấm Dịch (có xác nhận). Chạy nền, MỘT file mỗi lúc.
  • Ra 2 file đặt cạnh bản gốc, trong thư mục "Bản dịch": "<tên> (VI).pdf" và "<tên> (song ngữ).pdf".
    Luồng Uni-Documents của UC tự nạp chúng như file bạn thả vào thư mục môn: xếp môn, chống trùng SHA, Drive + Notion.
  • Không tốn quota Gemini: dịch bằng model trên máy (qwen3-14b qua LM Studio). Không chạy khi máy đang thi Local AI
    hoặc RAM trống < 2 GB (tự chờ).
pdf2zh: uv tool (AGPL-3.0) — UC chỉ GỌI như công cụ ngoài, không chép mã."""
import ctypes, os, shutil, subprocess, tempfile, threading, time, uuid
from pathlib import Path

PDF2ZH = Path(os.environ.get('APPDATA', '')) / 'uv' / 'tools' / 'pdf2zh' / 'Scripts' / 'pdf2zh.exe'
PROMPT = Path(__file__).resolve().parent / 'tools' / 'pdf-translate' / 'prompt_vi.txt'
LMS = os.environ.get('LMS_EXE', 'lms')
SUB = 'Bản dịch'
LANGS = {'en': 'tiếng Anh', 'zh': 'tiếng Trung', 'ja': 'tiếng Nhật', 'ko': 'tiếng Hàn', 'fr': 'tiếng Pháp', 'de': 'tiếng Đức', 'ru': 'tiếng Nga'}
_jobs, _q, _lk = {}, [], threading.Lock()
_worker = {'t': None}


def _ram_gb():
    class MS(ctypes.Structure):
        _fields_ = [('len', ctypes.c_ulong), ('load', ctypes.c_ulong), ('total', ctypes.c_ulonglong), ('avail', ctypes.c_ulonglong),
                    ('tpf', ctypes.c_ulonglong), ('apf', ctypes.c_ulonglong), ('tv', ctypes.c_ulonglong), ('av', ctypes.c_ulonglong), ('ext', ctypes.c_ulonglong)]
    m = MS(); m.len = ctypes.sizeof(m); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); return m.avail / 1024 ** 3


def _tournament_on():
    try:
        out = subprocess.run([LMS, 'ps'], capture_output=True, text=True, timeout=30, creationflags=0x08000000).stdout
        return 'local-executor-tournament' in out
    except Exception:
        return False


def search(q):
    import nlm_bridge
    r = nlm_bridge.search(q, limit=200)
    items = [i for i in r['items'] if i['name'].lower().endswith('.pdf') and SUB not in Path(i['rel']).parts]
    return {'ok': True, 'total': len(items), 'items': items[:80], 'langs': LANGS}


def _run(jid):
    import nlm_bridge
    j = _jobs[jid]
    src = nlm_bridge._safe(j['rel'])
    if _tournament_on():
        j.update(status='lỗi', error='Máy đang chạy cuộc thi Local AI (model của cuộc thi đang nạp) — để sau khi cuộc thi dừng.'); return
    t0 = time.time()
    while _ram_gb() < 2:
        j['status'] = f'chờ RAM (còn {_ram_gb():.1f} GB)'
        if time.time() - t0 > 1800: j.update(status='lỗi', error='RAM trống dưới 2 GB quá 30 phút — đóng bớt app rồi thử lại.'); return
        time.sleep(20)
    j['status'] = 'đang dịch'
    tmp = Path(tempfile.mkdtemp(prefix='uc-dich-'))
    try:
        work = tmp / 'in.pdf'; shutil.copy2(src, work)   # tên ASCII ngắn: tránh lỗi đường dẫn tiếng Việt / dài trong pdf2zh
        env = {**os.environ, 'OPENAI_BASE_URL': 'http://127.0.0.1:1234/v1', 'OPENAI_API_KEY': 'lm-studio', 'OPENAI_MODEL': 'qwen3-14b',
               'PYTHONIOENCODING': 'utf-8'}
        p = subprocess.run([str(PDF2ZH), str(work), '-li', j['lang'], '-lo', 'vi', '-s', 'openai', '-t', '4', '--prompt', str(PROMPT), '-o', str(tmp)],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=4 * 3600, env=env, creationflags=0x08000000)
        mono, dual = tmp / 'in-mono.pdf', tmp / 'in-dual.pdf'
        if p.returncode or not mono.exists():
            j.update(status='lỗi', error=(p.stderr or p.stdout)[-400:]); return
        dest = src.parent / SUB; dest.mkdir(exist_ok=True)
        out = []
        for f, tag in ((mono, 'VI'), (dual, 'song ngữ')):
            if not f.exists(): continue
            d = dest / f'{src.stem} ({tag}).pdf'
            if d.exists(): d = dest / f'{src.stem} ({tag}) {time.strftime("%Y%m%d-%H%M")}.pdf'
            shutil.move(str(f), str(d)); out.append(str(d.relative_to(nlm_bridge.UNI)))
        j.update(status='xong', out=out, minutes=round((time.time() - t0) / 60, 1))
    except subprocess.TimeoutExpired:
        j.update(status='lỗi', error='quá 4 giờ')
    except Exception as e:
        j.update(status='lỗi', error=f'{type(e).__name__}: {e}'[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _loop():
    while True:
        with _lk:
            jid = _q.pop(0) if _q else None
        if not jid: _worker['t'] = None; return
        _run(jid)


def add(files, lang='en'):
    import nlm_bridge
    if not PDF2ZH.exists(): return {'ok': False, 'error': 'Chưa cài pdf2zh (uv tool install pdf2zh).'}
    if lang not in LANGS: return {'ok': False, 'error': 'ngôn ngữ nguồn không hỗ trợ'}
    files = [str(f) for f in (files or []) if str(f).lower().endswith('.pdf')][:10]
    if not files: return {'ok': False, 'error': 'Chưa chọn file PDF nào.'}
    ids = []
    for rel in files:
        nlm_bridge._safe(rel)
        jid = uuid.uuid4().hex[:10]
        _jobs[jid] = {'id': jid, 'rel': rel, 'lang': lang, 'status': 'đang chờ', 'out': [], 'at': time.strftime('%H:%M')}
        with _lk: _q.append(jid)
        ids.append(jid)
    if not _worker['t']:
        _worker['t'] = threading.Thread(target=_loop, daemon=True); _worker['t'].start()
    return {'ok': True, 'jobs': ids}


def jobs():
    return {'ok': True, 'items': sorted(_jobs.values(), key=lambda j: j['at'], reverse=True)[:30]}
