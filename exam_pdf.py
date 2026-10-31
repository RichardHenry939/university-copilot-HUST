"""Read configured local exam PDFs. Never infer a class, date, or room from prose.

Optional dependency: pdfplumber. Configure exam_pdf_config.json with class_name
and sources [{directory, pattern}], e.g. pattern LTGK*.pdf. No user data in code.
"""
import datetime as dt
import hashlib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'exam_pdf_config.json'
OUT = HERE / 'school' / 'exam_pdf.json'
_lock = threading.Lock()


def norm(value):
    value = unicodedata.normalize('NFD', str(value or '').lower()).replace('đ', 'd')
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in value if unicodedata.category(c) != 'Mn'))


def parse_tables(tables, class_name, page=1, slots=None):
    required = ['Mã lớp thi', 'Mã HP', 'Tên học phần', 'Nhóm', 'Ngày thi', 'Kíp thi', 'Phòng thi']
    result = []
    for table in tables:
        columns = None
        for row in table:
            normalized = [norm(x) for x in row]
            if all(norm(h) in normalized for h in required):
                columns = {h: normalized.index(norm(h)) for h in required}
                continue
            if not columns: continue
            def val(h):
                return ' '.join(str(row[columns[h]] or '').split()) if columns[h] < len(row) else ''
            if norm(val('Nhóm')) != norm(class_name): continue
            day = dt.datetime.strptime(val('Ngày thi'), '%d.%m.%Y').date().isoformat()
            code = val('Mã HP')
            if not re.fullmatch(r'[A-Z]{2,4}\d{4}[A-Z]?', code):
                raise ValueError('Mã học phần không hợp lệ ở trang ' + str(page))
            shift = val('Kíp thi')
            slot = re.fullmatch(r'Kíp\s*(\d+)', shift, re.I)
            if slot and slots and slot.group(1) in slots: shift = slots[slot.group(1)]
            result.append(dict(id='pdf-' + val('Mã lớp thi'), ma_hp=code, ten_hp=val('Tên học phần'),
                ngay=day, kip=shift, phong=val('Phòng thi'), lop=val('Mã lớp thi'),
                loai='Theo lịch PDF', nguon='PDF lịch thi', source_page=page))
    return result


def extract(path, class_name):
    try:
        import pdfplumber
    except ImportError:
        import sys
        vendor = HERE / 'vendor'
        if vendor.is_dir(): sys.path.insert(0, str(vendor))
        import pdfplumber
    exams = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''
            if norm(class_name) not in norm(text): continue
            slots = dict(re.findall(r'Kíp\s*(\d+)\s*\((\d{1,2}h\d{2})\)', text, re.I))
            exams.extend(parse_tables(page.extract_tables(), class_name, page_no, slots))
    return exams


def _load():
    try: return json.loads(OUT.read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}


def refresh():
    with _lock:
        if not CONFIG.exists(): return {'ok': False, 'configured': False}
        old = _load()
        try:
            config = json.loads(CONFIG.read_text(encoding='utf-8'))
            target = config['class_name']
            if not norm(target): raise ValueError('Chưa cấu hình lớp')
            candidates = []
            for source in config['sources']:
                root = Path(source['directory']).resolve()
                candidates.extend(p for p in root.glob(source.get('pattern', 'LTGK*.pdf'))
                    if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root))
            if not candidates: raise ValueError('Chưa tìm thấy PDF trong nguồn đã cấu hình')
            path = max(candidates, key=lambda p: p.stat().st_mtime_ns)
            before = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            signature = digest + ':' + norm(target)
            if old.get('signature') == signature and not old.get('error'):
                return {'ok': True, 'cached': True, 'count': len(old.get('exams', []))}
            exams = extract(path, target)
            if not exams: raise ValueError('PDF không có hàng khớp lớp; giữ lịch cũ')
            if (path.stat().st_size, path.stat().st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                raise ValueError('PDF đang thay đổi; sẽ thử lại')
            for e in exams: e['source_file'] = path.name
            state = dict(exams=exams, signature=signature, at=dt.datetime.now().astimezone().isoformat(), source_file=path.name)
            result = dict(ok=True, count=len(exams))
        except Exception as e:
            state = dict(old, error=f'{type(e).__name__}: {e}'[:240], checked_at=dt.datetime.now().astimezone().isoformat())
            result = dict(ok=False, error=state['error'])
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(OUT)
        return result


def merge(fami_exams):
    """Keep FAMI's personalized room when sources agree on course/date; retain provenance."""
    result = [dict(e) for e in fami_exams]
    known = {(e.get('ma_hp'), e.get('ngay')): e for e in result}
    for e in _load().get('exams', []):
        key = e.get('ma_hp'), e.get('ngay')
        if key in known:
            known[key]['pdf_source'] = {'file': e.get('source_file'), 'page': e.get('source_page')}
            if any(known[key].get(k) != e.get(k) for k in ('kip', 'phong')):
                known[key]['source_warning'] = 'PDF và FAMI khác giờ/phòng; đang giữ lịch cá nhân FAMI'
        else:
            result.append(dict(e)); known[key] = result[-1]
    return result


def loop(every=300):
    while True:
        try: refresh()
        except Exception as e: print('exam_pdf:', type(e).__name__)
        time.sleep(every)
