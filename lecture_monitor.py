# -*- coding: utf-8 -*-
"""Giám sát chuỗi Ghi bài giảng (Claude 2026-10-05) — TỰ ĐỘNG, KHÔNG gọi AI nào (0 quota).

Mỗi 60 giây chỉ ĐỌC trạng thái: máy ghi :5681 -> n8n "Lecture Capture" (nhận, Drive, phiên Notion) ->
cổng chép lời :8340 (chép lời, nén bằng LM Studio) -> n8n "Lecture Analysis" (Gemini, ghi chú) -> phiên Notion.
Ra: school/lecture_pipeline.json (từng buổi: 8 bước) + school/lecture_errors.log (mọi lỗi, mỗi lỗi 1 lần,
đủ để đem đi sửa mà không phải đọc lại nhật ký n8n). Tab Ghi bài giảng → mục "Đang tải lên" đọc /api/lecture-monitor."""
import uc_config as cfg
import datetime as dt, json, re, threading, time, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'lecture_pipeline.json'
ERRLOG = HERE / 'school' / 'lecture_errors.log'
RECORDER = 'http://127.0.0.1:5681'
GATE = 'http://127.0.0.1:8340'
GATE_LOG = Path(r'D:\Data\SpeechGate\speech-gate.log')
WF_CAPTURE, WF_ANALYSIS = cfg.n8n_workflow("lecture_capture"), cfg.n8n_workflow("lecture_analysis")
TZ = dt.timezone(dt.timedelta(hours=7))
STEPS = [('rec', 'Ghi âm'), ('upload', 'Gửi n8n'), ('drive', 'Lưu Drive'), ('session', 'Phiên Notion'),
         ('stt', 'Chép lời trên máy'), ('compact', 'Nén (LM Studio)'), ('gemini', 'Gemini phân tích'), ('note', 'Ghi chú Notion')]
_lock = threading.Lock()


def _now(): return dt.datetime.now(TZ).isoformat(timespec='seconds')


def _get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r: return json.loads(r.read().decode('utf-8'))


def load():
    try: return json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return {'captures': {}, 'errors': [], 'seen': {}, 'gateLogPos': 0}


def _save(st): OUT.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')


def _cap(st, cid, **info):
    c = st['captures'].setdefault(cid, {'captureId': cid, 'steps': {}, 'first': _now()})
    for k, v in info.items():
        if v: c[k] = v
    return c


def _step(st, cid, step, state, detail=''):
    """state: run | ok | err | wait. Không lùi từ ok về run (trừ khi chạy lại)."""
    c = _cap(st, cid)
    old = c['steps'].get(step) or {}
    if old.get('state') == state and old.get('detail') == detail: return
    c['steps'][step] = {'state': state, 'detail': detail[:300], 'at': _now()}
    c['updated'] = _now()
    if state == 'ok':
        for e in st['errors']:
            if e.get('captureId') == cid and e.get('step') == step and not e.get('resolved'): e['resolved'] = _now()


def _err(st, source, cid, message, detail='', step=None):
    key = f"{source}|{cid}|{message[:160]}"
    if any(e['key'] == key for e in st['errors']): return
    e = {'key': key, 'at': _now(), 'source': source, 'captureId': cid or '', 'message': message[:500], 'detail': detail[:1500], 'step': step}
    st['errors'].append(e); st['errors'] = st['errors'][-300:]
    with ERRLOG.open('a', encoding='utf-8') as f:
        f.write(f"{e['at']} | {source} | {cid or '-'} | {message}\n" + (f"    {detail}\n" if detail else ''))


def _n8n_execs(api, wid, limit=25):
    return api('GET', f'/executions?workflowId={wid}&limit={limit}').get('data', [])


def tick(n8n_get):
    """n8n_get(path) -> json: webhook n8n của UC (copilot_app.n8n)."""
    from n8napi import api
    with _lock:
        st = load()
        seen = st.setdefault('seen', {})
        # 1) máy ghi
        try:
            h = _get(RECORDER + '/health', 5)
            cid = h.get('captureId')
            if cid:
                _cap(st, cid, startedAt=h.get('startedAt'), course=h.get('course'), device=h.get('device'))
                if h.get('recording'):
                    _step(st, cid, 'rec', 'run', f"{int(h.get('elapsedSec') or 0) // 60} phút · {h.get('levelDb')} dB")
                elif (st['captures'][cid]['steps'].get('rec') or {}).get('state') == 'run':
                    _step(st, cid, 'rec', 'ok')
                if h.get('lastError'):
                    _err(st, 'Máy ghi', cid, h['lastError'])
                for ev in h.get('events') or []:
                    if 'Đã gửi bản ghi' in ev: _step(st, cid, 'rec', 'ok'); _step(st, cid, 'upload', 'ok', ev[:8])
        except Exception as e:
            _err(st, 'Máy ghi', '', f'Không đọc được máy ghi :5681 ({type(e).__name__})')
        # 2) n8n Lecture Capture: nhận -> Drive -> phiên Notion
        try:
            for ex in reversed(_n8n_execs(api, WF_CAPTURE)):
                eid = str(ex['id'])
                if eid in seen or ex.get('status') in ('running', 'waiting', 'new'): continue
                d = api('GET', f'/executions/{eid}?includeData=true')
                rd = d['data']['resultData']; run = rd.get('runData', {})
                recv = (run.get('Receive Lecture Audio') or [{}])[0]
                q = (((recv.get('data') or {}).get('main') or [[{}]])[0][0].get('json') or {}).get('query') or {}
                cid = q.get('captureId')
                if not cid: seen[eid] = 1; continue
                _cap(st, cid, startedAt=q.get('startedAt'), endedAt=q.get('endedAt'))
                _step(st, cid, 'rec', 'ok'); _step(st, cid, 'upload', 'ok', f"n8n #{eid}")
                for node, step in (('Upload Lecture Audio to Drive', 'drive'), ('Create Lecture Session', 'session')):
                    for r in run.get(node, []):
                        if r.get('executionStatus') == 'error' or r.get('error'):
                            msg = (r.get('error') or {}).get('message') or 'lỗi'
                            _step(st, cid, step, 'err', msg); _err(st, 'n8n · ' + node, cid, msg, f'execution #{eid}', step)
                        else:
                            _step(st, cid, step, 'ok', f"n8n #{eid}")
                if ex.get('status') == 'error' and rd.get('error') and not any(run.get(n) for n in ('Upload Lecture Audio to Drive',)):
                    _err(st, 'n8n · Lecture Capture', cid, rd['error'].get('message', 'lỗi'), f'execution #{eid}')
                seen[eid] = 1
        except Exception as e:
            _err(st, 'Giám sát', '', f'Không đọc được n8n Lecture Capture ({type(e).__name__}: {e})')
        # 3) n8n Lecture Analysis: chỉ đọc chi tiết lần chạy LỖI và lần nhận bản chép lời (webhook)
        try:
            for ex in reversed(_n8n_execs(api, WF_ANALYSIS, 40)):
                eid = str(ex['id'])
                if eid in seen or ex.get('status') in ('running', 'waiting', 'new'): continue
                if ex.get('status') != 'error' and ex.get('mode') != 'webhook': seen[eid] = 1; continue
                d = api('GET', f'/executions/{eid}?includeData=true')
                rd = d['data']['resultData']; run = rd.get('runData', {})
                body = ((((run.get('Nhận bản chép lời') or [{}])[0].get('data') or {}).get('main') or [[{}]])[0][0].get('json') or {}).get('body') or {}
                cid = body.get('captureId') or ''
                if cid:
                    if any(run.get(n) for n in ('Gemini phân tích (Flash-Lite)', 'Gemini phân tích (Flash dự phòng)')):
                        ok = any(r.get('executionStatus') == 'success' for n in ('Gemini phân tích (Flash-Lite)', 'Gemini phân tích (Flash dự phòng)') for r in run.get(n, []))
                        _step(st, cid, 'gemini', 'ok' if ok else 'err', f"n8n #{eid}")
                    if run.get('Hoàn tất phiên') or run.get('Ghi nội dung ghi chú'): _step(st, cid, 'note', 'ok', f"n8n #{eid}")
                    if run.get('Ghi: audio không dùng được'): _step(st, cid, 'note', 'err', 'audio không dùng được')
                    if run.get('Ghi: không phải bài giảng'): _step(st, cid, 'note', 'err', 'Gemini: không phải bài giảng')
                if ex.get('status') == 'error':
                    err = rd.get('error') or {}
                    node = (rd.get('lastNodeExecuted') or (err.get('node') or {}).get('name') or 'Lecture Analysis')
                    _err(st, 'n8n · ' + str(node), cid, err.get('message', 'lỗi'), f'execution #{eid}', 'gemini')
                    if cid: _step(st, cid, 'gemini', 'err', err.get('message', 'lỗi'))
                seen[eid] = 1
        except Exception as e:
            _err(st, 'Giám sát', '', f'Không đọc được n8n Lecture Analysis ({type(e).__name__}: {e})')
        # 4) cổng chép lời: từng buổi chưa xong phần trên máy
        for cid, c in st['captures'].items():
            if (c['steps'].get('compact') or {}).get('state') == 'ok' or (c['steps'].get('session') or {}).get('state') != 'ok': continue
            try:
                j = _get(GATE + '/jobs?captureId=' + urllib.parse.quote(cid), 5)
            except Exception:
                continue
            if not j.get('status'): continue
            s, stg, pg = j['status'], j.get('stage'), int((j.get('progress') or 0) * 100)
            if s == 'queued': _step(st, cid, 'stt', 'wait', 'xếp hàng')
            elif s == 'running' and stg in ('decode', 'quality', 'transcribe'): _step(st, cid, 'stt', 'run', f'{stg} {pg}%')
            elif s == 'running' and stg == 'compact': _step(st, cid, 'stt', 'ok'); _step(st, cid, 'compact', 'run', f'{pg}%')
            elif s == 'done': _step(st, cid, 'stt', 'ok'); _step(st, cid, 'compact', 'ok')
            elif s == 'unusable': _step(st, cid, 'stt', 'err', j.get('reason') or 'không dùng được')
            elif s == 'error':
                step = 'compact' if stg == 'compact' else 'stt'
                _step(st, cid, step, 'err', j.get('reason') or 'lỗi'); _err(st, 'Cổng chép lời · ' + (stg or ''), cid, j.get('reason') or 'lỗi', f"job {j.get('jobId')}", step)
        # 5) nhật ký cổng chép lời: lỗi LM Studio / callback (đọc phần mới)
        try:
            size = GATE_LOG.stat().st_size; pos = st.get('gateLogPos', 0)
            if pos > size: pos = 0
            with GATE_LOG.open('r', encoding='utf-8', errors='replace') as f:
                f.seek(pos); new = f.read(); st['gateLogPos'] = f.tell()
            lines = new.splitlines()
            for i, ln in enumerate(lines):
                if not re.match(r'\d{4}-\d{2}-\d{2}', ln) or not re.search(r'lỗi|error', ln, re.I): continue
                msg = ln[20:400]
                if 'Traceback' in ln:   # lấy dòng lỗi thật cuối traceback
                    tail = [x for x in lines[i + 1:i + 60] if x and not x.startswith((' ', '	')) and not re.match(r'\d{4}-', x)]
                    if tail: msg = ln[20:ln.find('Traceback')] + tail[-1][:300]
                m = re.search(r'(lecture-\d+)', ln); jm = re.search(r'job (\w{12})', ln)
                cid = m.group(1) if m else ''
                if not cid and jm:
                    try: cid = _get(GATE + '/jobs/' + jm.group(1), 5).get('captureId') or ''
                    except Exception: pass
                _err(st, 'Cổng chép lời (nhật ký)', cid, msg)
        except Exception:
            pass
        # 6) phiên Notion (qua n8n copilot-lectures — không phải AI)
        try:
            for x in n8n_get('copilot-lectures').get('sessions', []):
                cid = x.get('captureId')
                if not cid: continue
                _cap(st, cid, title=x.get('title'), notionUrl=x.get('url'), noteUrl=x.get('noteUrl'), state=x.get('state'))
                _step(st, cid, 'session', 'ok')
                if x.get('state') == 'Completed': _step(st, cid, 'note', 'ok', 'Xong')
                if x.get('state') == 'Needs review' and x.get('notes'):
                    _err(st, 'Phiên Notion: Cần xem lại', cid, x['notes'], step='note')
        except Exception as e:
            _err(st, 'Giám sát', '', f'Không đọc được danh sách phiên ({type(e).__name__})')
        # dọn: giữ 20 buổi gần nhất, "seen" 2000 id
        caps = sorted(st['captures'].values(), key=lambda c: c.get('startedAt') or c.get('first') or '', reverse=True)
        st['captures'] = {c['captureId']: c for c in caps[:20]}
        if len(seen) > 2000: st['seen'] = dict(list(seen.items())[-1500:])
        st['updated'] = _now()
        _save(st)


def dismiss(cid):
    with _lock:
        st = load()
        if cid in st['captures']:
            st['captures'][cid]['dismissed'] = _now()
            for e in st['errors']:
                if e.get('captureId') == cid and not e.get('resolved'): e['resolved'] = _now(); e['dismissed'] = True
            _save(st)
    return {'ok': True}


def view():
    st = load()
    caps = sorted([c for c in st['captures'].values() if not c.get('dismissed')], key=lambda c: c.get('startedAt') or c.get('first') or '', reverse=True)[:10]
    for c in caps:
        c['line'] = [{'key': k, 'label': lb, **(c['steps'].get(k) or {'state': 'wait'})} for k, lb in STEPS]
    return {'updated': st.get('updated'), 'captures': caps, 'errors': list(reversed(st['errors'][-60:])),
            'errorLog': str(ERRLOG)}


def loop(n8n_get):
    while True:
        try: tick(n8n_get)
        except Exception as e:
            try:
                with ERRLOG.open('a', encoding='utf-8') as f: f.write(f"{_now()} | Giám sát | - | vòng giám sát lỗi: {type(e).__name__}: {e}\n")
            except Exception: pass
        time.sleep(60)
