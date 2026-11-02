# -*- coding: utf-8 -*-
"""(v1.00.34) Gửi bản tóm tắt UC lên connector trên Firebase (uc_mcp/cloud). CHỈ ĐI RA: máy không mở cổng nào.

Chạy định kỳ (Task Scheduler, mỗi 10 phút). UC không chạy -> không gửi gì -> bản trên mây cũ dần ->
connector báo "máy đang tắt" sau 20 phút và trả bản cuối làm báo cáo sơ bộ.

Cấu hình cục bộ (KHÔNG đưa lên repo): uc_mcp/cloud.local.json  {"push_url": "https://<site>.web.app/api/push", "push_secret": "..."}
"""
import datetime as dt, json, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import server as S  # noqa: E402

CONF = HERE / 'cloud.local.json'


def _fitness():
    """(v1.00.52, chủ 02/11 cho phép) Fitness: số đo cơ thể, bước hôm nay, buổi tập hôm nay + 7 ngày qua. Chỉ đọc."""
    try:
        sys.path.insert(0, str(HERE.parent))
        import fitness, walk
        v, w = fitness.view(), walk.view()
        return {"fitness": {"so_do": v.get("profile"), "chi_so": v.get("derived"), "buoi_tap_hom_nay": v.get("plan"),
                            "khung_tap": v.get("slot"), "buoi_gan_day": fitness.recent(v["today"]),
                            "di_bo": {"buoc": w.get("steps"), "muc_tieu": w.get("target"), "dat": w.get("met"), "khung": w.get("slot")}}}
    except Exception as e:
        return {"fitness_loi": f"{type(e).__name__}: {e}"[:160]}


def _ngoai_khoa_inbox():
    """(v1.00.40) Ngoại khoá (iCTSV) và danh sách Inbox: tên, trạng thái, thư mục, môn, link Drive, đường dẫn trên máy. KHÔNG đưa nội dung file lên mây."""
    out = {"ngoai_khoa": [], "inbox": []}
    try:
        sys.path.insert(0, str(HERE.parent))
        import extracurricular as X
        keep = ('key', 'name', 'loai', 'start', 'end', 'han', 'place', 'org', 'type', 'status', 'note')
        out["ngoai_khoa"] = [{k: it.get(k) for k in keep} for it in X.load().get('items', [])][:300]
    except Exception as e:
        out["ngoai_khoa_loi"] = f"{type(e).__name__}: {e}"[:160]
    try:
        st = json.loads((HERE.parent / 'inbox_state.json').read_text(encoding='utf-8'))
        # (02/11) + driveLink (Claude Chat đọc file qua connector Google Drive) + duong_dan (vị trí chính xác trên máy, cho skill UC_NotebookLM)
        keep = ('name', 'status', 'folder', 'relPath', 'source', 'courseCode', 'reason', 'driveLink')
        rows = []
        for it in st.get('items', [])[-200:]:
            r = {k: it.get(k) for k in keep}
            if it.get('path'): r['duong_dan'] = it['path']
            ts = it.get('createdAt')
            if isinstance(ts, (int, float)): r['nhan_luc'] = dt.datetime.fromtimestamp(ts, S.TZ).isoformat(timespec='minutes')
            rows.append(r)
        out["inbox"] = rows
    except Exception as e:
        out["inbox_loi"] = f"{type(e).__name__}: {e}"[:160]
    return out


def _local(path, timeout=60):
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:8320' + path, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _mo_rong():
    """(v1.00.42) Phần mở rộng cho connector: lịch 21 ngày (đã gồm lịch đè Teams), cảnh báo đang hiện trên UC, chứng chỉ, MOOC.
    Chỉ đọc API cục bộ của UC (không gọi Notion thêm). Mỗi phần lỗi riêng thì ghi <phần>_loi, không làm hỏng cả bản."""
    out = {}
    now = dt.datetime.now(S.TZ)
    try:
        lo, hi = (now - dt.timedelta(days=1)).isoformat(), (now + dt.timedelta(days=21)).isoformat()
        ev = [e for e in _local('/api/timetable/all').get('events', []) if lo <= (e.get('start') or '') <= hi]
        out['lich'] = [{'tieu_de': e.get('title'), 'loai': e.get('kind'), 'bat_dau': e.get('start'), 'ket_thuc': e.get('end'),
                        'dia_diem': e.get('location'), 'ghi_chu': (e.get('notes') or '')[:400]} for e in sorted(ev, key=lambda e: e['start'])][:300]
    except Exception as e: out['lich_loi'] = f"{type(e).__name__}: {e}"[:160]
    try:
        out['canh_bao'] = [{k: a.get(k) for k in ('level', 'title', 'text', 'note', 'when')} for a in _local('/api/alerts').get('alerts', [])][:60]
    except Exception as e: out['canh_bao_loi'] = f"{type(e).__name__}: {e}"[:160]
    try:
        pg = _local('/api/program', timeout=90)
        keep = ('muc', 'cert', 'band', 'lvLabel', 'cefr', 'issued', 'expiry', 'daysLeft', 'valid', 'grad', 'exempt', 'lang', 'note')
        out['chung_chi'] = {'danh_sach': [{k: c.get(k) for k in keep} for c in (pg.get('certs') or {}).get('items', [])],
                            'chuan_dau_ra': (pg.get('graduation') or {}).get('cert')}
    except Exception as e: out['chung_chi_loi'] = f"{type(e).__name__}: {e}"[:160]
    try:
        sys.path.insert(0, str(HERE.parent))
        import mooc
        m = json.loads(mooc.OUT.read_text(encoding='utf-8'))
        out['mooc'] = {'doc_luc': m.get('at'), 'chua_co_han': mooc.undated(m),
                       'khoa': {cid: {'ten': c.get('name'), 'bai': [{k: it.get(k) for k in ('name', 'due', 'format', 'earned', 'possible')} for it in c.get('items') or []]}
                                for cid, c in (m.get('courses') or {}).items()}}
    except Exception as e: out['mooc_loi'] = f"{type(e).__name__}: {e}"[:160]
    return out


LAST_ERR = None   # lý do lần snapshot() gần nhất trả None (để push() phân biệt "UC tắt" với "UC lỗi")


def snapshot():
    """-> bản tóm tắt (dict) hoặc None khi UC không trả lời. Chỉ đọc /api/today MỘT lần."""
    global LAST_ERR
    d, err = S._fetch()
    LAST_ERR = err
    if d is None: return None
    real = S._fetch
    S._fetch = lambda: (d, None)
    try:
        return {"at": dt.datetime.now(S.TZ).isoformat(timespec="seconds"),
                "today": S.t_today({}),
                "han_tat_ca": [S._deadline_view(x) for x in S._song(d)],
                "bao_cao": S.t_briefing({})["bao_cao"],
                **_ngoai_khoa_inbox(), **_mo_rong(), **_fitness()}
    finally:
        S._fetch = real


STATUS = HERE / 'push_status.json'   # lần gửi gần nhất: giờ, kết quả, lý do (chỉ trên máy)


def _status(ok, msg):
    try: STATUS.write_text(json.dumps({'at': dt.datetime.now(S.TZ).isoformat(timespec='seconds'), 'ok': ok, 'msg': msg},
                                      ensure_ascii=False), encoding='utf-8')
    except Exception: pass


def push():
    """-> (mã thoát, thông báo). 0 = đã gửi; 1 = UC không chạy; 2 = UC có chạy nhưng lỗi / quá tải.
    (02/11) Trước đây mọi lỗi đều báo "UC không chạy" và thoát 0, nên 01/11 khi /api/today lỗi 500 (n8n mất mạng sau
    khi khởi động lại WSL) connector im lặng gần 1 giờ mà Task Scheduler vẫn báo thành công."""
    conf = json.loads(CONF.read_text(encoding='utf-8'))
    snap = snapshot()
    if snap is None:
        err = LAST_ERR or ''
        down = 'refused' in err.lower() or 'WinError 10061' in err or 'actively refused' in err
        msg = ('UC không chạy, không gửi' if down else 'UC đang chạy nhưng lỗi, không gửi: ' + err)
        _status(False, msg)
        return (1 if down else 2), msg
    body = json.dumps(snap, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(conf['push_url'], data=body, method='POST',
                                 headers={'Content-Type': 'application/json', 'X-UC-Push': conf['push_secret']})
    with urllib.request.urlopen(req, timeout=40) as r:
        msg = f'đã gửi {len(body)} byte, HTTP {r.status}'
        try: reply = json.loads(r.read().decode('utf-8') or '{}')
        except Exception: reply = {}
    x = reply.get('xoa_the_duc')   # (v1.00.49) AI đã xoá khung thể dục hôm nay qua MCP (lý do chính đáng) -> ghi vào UC
    if x and x.get('ngay'):
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent)); import walk
            walk.set_override(x['ngay'], x.get('ly_do', ''), x.get('at', ''), 'mcp'); msg += ' · nhận lệnh xoá thể dục ' + x['ngay']
        except Exception as e: msg += f' · lỗi ghi lệnh xoá thể dục: {e}'
    _status(True, msg)
    return 0, msg


if __name__ == '__main__':
    code, msg = push()
    print(msg)
    sys.exit(code)   # khác 0 thì Task Scheduler hiện "Last Run Result" lỗi, không còn báo thành công giả
