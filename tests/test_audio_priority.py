# -*- coding: utf-8 -*-
"""Luật ưu tiên tiến trình (addons/low-end-priority/audio_priority.py) — giả lập kernel32 của Windows để chạy trên mọi OS."""
import ctypes, importlib, io, json, sys

import pytest


class FakeKernel32:
    """Giả các hàm Toolhelp32 + OpenProcess / Get/SetPriorityClass mà audio_priority dùng."""

    def __init__(self, procs, denied=()):
        self.procs = procs                  # [(pid, exe, priority)]
        self.prio = {pid: p for pid, _, p in procs}
        self.denied = set(denied)           # pid tiến trình hệ thống: OpenProcess trả 0
        self.set_calls, self.closed, self.opened = [], [], []
        self._i = 0

    def CreateToolhelp32Snapshot(self, flags, pid):
        assert flags == 0x2                 # TH32CS_SNAPPROCESS
        self._i = 0
        return 999

    def _fill(self, ref):
        if self._i >= len(self.procs): return 0
        e = ref._obj
        assert e.dwSize == ctypes.sizeof(type(e))
        pid, exe, _ = self.procs[self._i]
        e.th32ProcessID, e.szExeFile = pid, exe
        self._i += 1
        return 1

    def Process32FirstW(self, snap, ref): return self._fill(ref)
    def Process32NextW(self, snap, ref): return self._fill(ref)

    def OpenProcess(self, access, inherit, pid):
        self.opened.append(pid)
        return 0 if pid in self.denied else 10_000 + pid

    def GetPriorityClass(self, h): return self.prio[h - 10_000]

    def SetPriorityClass(self, h, cls):
        self.set_calls.append((h - 10_000, cls)); self.prio[h - 10_000] = cls

    def CloseHandle(self, h): self.closed.append(h)


@pytest.fixture
def ap(monkeypatch, tmp_path):
    """Nạp audio_priority với ctypes.windll giả và thư mục cấu hình tạm."""
    fake = FakeKernel32([])
    monkeypatch.setattr(ctypes, 'windll', type('W', (), {'kernel32': fake})(), raising=False)
    sys.modules.pop('audio_priority', None)
    mod = importlib.import_module('audio_priority')
    (tmp_path / 'school').mkdir()
    monkeypatch.setattr(mod, 'CFG', tmp_path / 'school' / 'audio_priority.json')
    yield mod
    sys.modules.pop('audio_priority', None)


def use(mod, monkeypatch, procs, denied=()):
    k = FakeKernel32(procs, denied)
    monkeypatch.setattr(mod, 'k32', k)
    return k


# ----------------------------------------------------------------------------- cấu hình nhóm
def test_groups_creates_default_file(ap):
    g = ap.groups()
    assert g['hoc'] == {'lecturerecordercompanion.exe'}
    assert g['ai'] == {'llama-server.exe'}
    saved = json.loads(ap.CFG.read_text(encoding='utf-8'))
    assert '_ghi_chu' in saved and saved['homelab'] == ['vmmemWSL']


def test_groups_reads_file_lowercases_and_fills_missing_keys(ap):
    ap.CFG.write_text(json.dumps({'ai': ['LM Studio.exe', 'Ollama.EXE'], 'homelab': []}), encoding='utf-8')
    g = ap.groups()
    assert g['ai'] == {'lm studio.exe', 'ollama.exe'}
    assert g['homelab'] == set()                           # danh sách rỗng bạn đặt -> giữ rỗng
    assert g['hoc'] == {'lecturerecordercompanion.exe'}   # khoá thiếu -> mặc định


def test_groups_survives_unwritable_config(ap, monkeypatch, tmp_path):
    monkeypatch.setattr(ap, 'CFG', tmp_path / 'khong-co-thu-muc' / 'x.json')
    assert ap.groups()['binh_thuong'] == {'chrome.exe', 'msedge.exe', 'ms-teams.exe'}


def test_example_config_matches_defaults():
    from pathlib import Path
    ex = json.loads((Path(__file__).resolve().parent.parent / 'addons' / 'low-end-priority' / 'audio_priority.example.json')
                    .read_text(encoding='utf-8'))
    assert {k: v for k, v in ex.items() if not k.startswith('_')} == {
        'hoc': ['LectureRecorderCompanion.exe'], 'binh_thuong': ['chrome.exe', 'msedge.exe', 'ms-teams.exe'],
        'homelab': ['vmmemWSL'], 'ai': ['llama-server.exe']}


# ----------------------------------------------------------------------------- liệt kê + đổi ưu tiên
def test_procs_matches_case_insensitive_with_or_without_exe(ap, monkeypatch):
    k = use(ap, monkeypatch, [(1, 'Chrome.EXE', ap.NORMAL), (2, 'vmmemWSL', ap.NORMAL), (3, 'notepad.exe', ap.NORMAL),
                              (4, 'llama-server.exe', ap.NORMAL)])
    assert ap._procs({'chrome.exe', 'vmmemwsl'}) == [1, 2]
    assert ap._procs({'llama-server'}) == [4]          # tên không có .exe trong cấu hình vẫn khớp
    assert ap._procs(set()) == []
    assert 999 in k.closed                             # snapshot luôn được đóng


def test_set_only_changes_when_different_and_skips_denied(ap, monkeypatch):
    k = use(ap, monkeypatch, [(1, 'a.exe', ap.HIGH), (2, 'b.exe', ap.NORMAL), (3, 'c.exe', ap.NORMAL)], denied={3})
    ap._set([1, 2, 3], ap.HIGH)
    assert k.set_calls == [(2, ap.HIGH)]
    assert k.opened == [1, 2, 3]
    assert sorted(k.closed) == [10_001, 10_002]         # handle mở được thì đóng; tiến trình từ chối -> bỏ qua


def test_tick_applies_four_tiers(ap, monkeypatch):
    k = use(ap, monkeypatch, [
        (10, 'LectureRecorderCompanion.exe', ap.NORMAL),
        (11, 'chrome.exe', ap.IDLE),                    # trình duyệt học bài bị ai đó hạ -> trả về NORMAL
        (12, 'vmmemWSL', ap.NORMAL),
        (13, 'llama-server.exe', ap.HIGH),
        (14, 'explorer.exe', ap.NORMAL)])               # ngoài danh sách -> không đụng
    monkeypatch.setattr(ap, 'recording', lambda: True)
    assert ap.tick() is True
    assert k.prio == {10: ap.HIGH, 11: ap.NORMAL, 12: ap.BELOW, 13: ap.IDLE, 14: ap.NORMAL}
    assert 14 not in k.opened
    assert ap._state['recording'] is True


def test_tick_is_idempotent(ap, monkeypatch):
    k = use(ap, monkeypatch, [(10, 'LectureRecorderCompanion.exe', ap.NORMAL), (13, 'llama-server.exe', ap.NORMAL)])
    monkeypatch.setattr(ap, 'recording', lambda: False)
    ap.tick(); first = list(k.set_calls)
    ap.tick()
    assert k.set_calls == first and len(first) == 2


def test_priority_constants_are_windows_values(ap):
    # HIGH_PRIORITY_CLASS, NORMAL_PRIORITY_CLASS, IDLE_PRIORITY_CLASS, BELOW_NORMAL_PRIORITY_CLASS
    assert (ap.HIGH, ap.NORMAL, ap.IDLE, ap.BELOW) == (0x80, 0x20, 0x40, 0x4000)
    assert [n for n, _ in ap.GROUPS] == ['hoc', 'binh_thuong', 'homelab', 'ai']


# ----------------------------------------------------------------------------- máy ghi đang ghi?
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_recording_reads_recorder_health(ap, monkeypatch):
    seen = []
    monkeypatch.setattr(ap.urllib.request, 'urlopen', lambda url, timeout: seen.append(url) or _Resp(b'{"recording": true}'))
    assert ap.recording() is True and seen == [ap.RECORDER]
    monkeypatch.setattr(ap.urllib.request, 'urlopen', lambda url, timeout: _Resp(b'{"recording": false}'))
    assert ap.recording() is False


def test_recording_false_when_recorder_down(ap, monkeypatch):
    def down(url, timeout): raise ConnectionRefusedError
    monkeypatch.setattr(ap.urllib.request, 'urlopen', down)
    assert ap.recording() is False


def test_release_zip_matches_addon_folder():
    """addons/low-end-priority.zip là bản người dùng tải về: nội dung phải đúng bằng thư mục add-on (bỏ qua CRLF)."""
    import zipfile
    from pathlib import Path
    base = Path(__file__).resolve().parent.parent / 'addons'
    with zipfile.ZipFile(base / 'low-end-priority.zip') as z:
        files = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
    assert files, 'zip rỗng'
    for name, data in files.items():
        src = base / name
        assert src.exists(), f'{name} có trong zip nhưng không có trong thư mục add-on'
        assert data.replace(b'\r\n', b'\n') == src.read_bytes().replace(b'\r\n', b'\n'), f'{name} trong zip khác thư mục'
