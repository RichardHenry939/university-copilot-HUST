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


def _ngoai_khoa_inbox():
    """(v1.00.40) Ngoại khoá (iCTSV) và danh sách Inbox: chỉ tên, trạng thái, thư mục, môn. KHÔNG đưa nội dung file lên mây."""
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
        keep = ('name', 'status', 'folder', 'relPath', 'source', 'courseCode', 'reason')
        rows = []
        for it in st.get('items', [])[-200:]:
            r = {k: it.get(k) for k in keep}
            ts = it.get('createdAt')
            if isinstance(ts, (int, float)): r['nhan_luc'] = dt.datetime.fromtimestamp(ts, S.TZ).isoformat(timespec='minutes')
            rows.append(r)
        out["inbox"] = rows
    except Exception as e:
        out["inbox_loi"] = f"{type(e).__name__}: {e}"[:160]
    return out


def snapshot():
    """-> bản tóm tắt (dict) hoặc None khi UC không trả lời. Chỉ đọc /api/today MỘT lần."""
    d, err = S._fetch()
    if d is None: return None
    real = S._fetch
    S._fetch = lambda: (d, None)
    try:
        return {"at": dt.datetime.now(S.TZ).isoformat(timespec="seconds"),
                "today": S.t_today({}),
                "han_tat_ca": [S._deadline_view(x) for x in S._song(d)],
                "bao_cao": S.t_briefing({})["bao_cao"],
                **_ngoai_khoa_inbox()}
    finally:
        S._fetch = real


def push():
    conf = json.loads(CONF.read_text(encoding='utf-8'))
    snap = snapshot()
    if snap is None: return 'UC không chạy, không gửi'
    body = json.dumps(snap, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(conf['push_url'], data=body, method='POST',
                                 headers={'Content-Type': 'application/json', 'X-UC-Push': conf['push_secret']})
    with urllib.request.urlopen(req, timeout=40) as r:
        return f'đã gửi {len(body)} byte, HTTP {r.status}'


if __name__ == '__main__':
    print(push())
