# -*- coding: utf-8 -*-
"""MCP connector (uc_mcp/server.py): giao thức JSON-RPC và các công cụ chỉ đọc — dữ liệu giả, không gọi mạng."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'uc_mcp'))
import server as S  # noqa: E402

FAKE = {
    'exams': [{'ma_hp': 'MI1111', 'ten_hp': 'Giải tích I', 'ngay': '2026-11-08', 'kip': '8h10-8h50', 'phong': 'D5-101'}],
    'deadlines': [
        {'name': 'Bài 10-35', 'course': 'MI1111', 'kind': 'Tự luyện cốt lõi', 'due': '2026-10-26T23:00:00+07:00', 'minsLeft': 2000,
         'gkExam': True, 'extended': 2, 'self': True},
        {'name': 'Quiz xa', 'course': 'IT1108', 'kind': 'Môn học', 'due': '2026-12-30T23:59:00+07:00', 'minsLeft': 90000, 'gkExam': False},
    ],
    'items': [{'task': 'Ôn chương 1', 'status': 'Not started', 'est': 1.5}],
    'mode': 'Bình thường',
}


def _rpc(method, params=None, mid=1):
    return S.handle({'jsonrpc': '2.0', 'id': mid, 'method': method, 'params': params or {}})


def _call(name, args=None, monkeypatch=None, data=FAKE, err=None):
    monkeypatch.setattr(S, '_fetch', lambda: (data, None) if data is not None else (None, err or 'refused'))
    res = _rpc('tools/call', {'name': name, 'arguments': args or {}})
    return json.loads(res['result']['content'][0]['text'])


def test_initialize_va_tools_list():
    assert _rpc('initialize')['result']['serverInfo']['name'] == 'uc'
    names = [t['name'] for t in _rpc('tools/list')['result']['tools']]
    assert names == ['uc_status', 'uc_today', 'uc_deadlines', 'uc_exams', 'uc_briefing']


def test_thong_bao_khong_co_id_khong_tra_loi():
    assert S.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) is None


def test_khong_co_cong_cu_la_loi_chuan(monkeypatch):
    res = _rpc('tools/call', {'name': 'uc_xoa_tat_ca', 'arguments': {}})
    assert 'error' in res


def test_may_tat_thi_bao_ro_va_huong_dan_notion(monkeypatch):
    out = _call('uc_today', monkeypatch=monkeypatch, data=None, err='refused')
    assert out['online'] is False and 'tắt' in out['thong_bao'] and 'Notion' in out['thong_bao']


def test_status_online_offline(monkeypatch):
    assert _call('uc_status', monkeypatch=monkeypatch)['online'] is True
    assert _call('uc_status', monkeypatch=monkeypatch, data=None)['online'] is False


def test_today_gom_dung_truong(monkeypatch):
    out = _call('uc_today', monkeypatch=monkeypatch)
    assert out['lich_thi_giua_ki'][0]['ma_hp'] == 'MI1111'
    han = out['han_dang_mo'][0]
    assert han['mon_co_thi_giua_ki'] is True and han['tu_gia_han_so_lan'] == 2 and han['tu_luyen'] is True


def test_deadlines_loc_theo_so_ngay(monkeypatch):
    out = _call('uc_deadlines', {'days': 7}, monkeypatch=monkeypatch)
    assert out['so_luong'] == 1 and out['han'][0]['ten'] == 'Bài 10-35'


def test_briefing_co_bao_cao_va_nhac_mon_thi(monkeypatch):
    out = _call('uc_briefing', monkeypatch=monkeypatch)
    assert 'Giải tích I' in out['bao_cao'] and '[môn thi giữa kì]' in out['bao_cao']


def test_briefing_liet_ke_tung_mon_ke_ca_mon_chua_lich(monkeypatch):
    data = dict(FAKE, examStatus=[{'ma_hp': 'MI1111', 'ten_hp': 'Giải tích I', 'trang_thai': 'co_lich', 'ngay': '2026-11-08', 'kip': '8h10', 'phong': 'D5'},
                                  {'ma_hp': 'IT1108', 'ten_hp': 'Nhập môn lập trình', 'trang_thai': 'chua_lich', 'trich': 'chưa thấy lịch'}])
    out = _call('uc_briefing', monkeypatch=monkeypatch, data=data)
    assert 'Thi giữa kỳ từng môn' in out['bao_cao'] and 'Nhập môn lập trình: có thi, chưa có lịch' in out['bao_cao']
    assert _call('uc_exams', monkeypatch=monkeypatch, data=data)['thi_giua_ki_tung_mon'][1]['ma_hp'] == 'IT1108'


def test_push_snapshot_doc_uc_mot_lan(monkeypatch):
    import push
    calls = []
    monkeypatch.setattr(S, '_fetch', lambda: (calls.append(1), (FAKE, None))[1])
    snap = push.snapshot()
    assert len(calls) == 1 and snap['today']['online'] is True and snap['han_tat_ca'][0]['ten'] == 'Bài 10-35' and 'bao_cao' in snap
    monkeypatch.setattr(S, '_fetch', lambda: (None, 'refused'))
    assert push.snapshot() is None


def test_xac_thuc_token_qua_http(monkeypatch):
    import http.client, threading
    from http.server import ThreadingHTTPServer
    monkeypatch.setattr(S.H, 'token', 'bi-mat')
    srv = ThreadingHTTPServer(('127.0.0.1', 0), S.H)
    th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
    try:
        port = srv.server_address[1]
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        c.request('POST', '/mcp', body, {'Content-Type': 'application/json'}); assert c.getresponse().status == 401
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        c.request('POST', '/mcp', body, {'Content-Type': 'application/json', 'Authorization': 'Bearer bi-mat'})
        r = c.getresponse(); assert r.status == 200 and json.loads(r.read())['id'] == 1
    finally:
        srv.shutdown(); srv.server_close()
