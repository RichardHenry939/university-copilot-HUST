# -*- coding: utf-8 -*-
"""File Zalo -> 00 · Inbox (zalo_files.py): chép, kiểm SHA, rồi mới xoá; trùng thì chỉ xoá; file khác không đụng tới.
Thư mục tạm + copilot_app giả, không gọi mạng."""
import hashlib
import os
import sys
import threading
import time
import types

import zalo_files as Z


class FakeApp(types.SimpleNamespace):
    pass


def _app(tmp_path, items=()):
    st = {'items': list(items)}
    a = FakeApp(INBOX=tmp_path / 'Uni' / '00 · Inbox', lock=threading.Lock(), queued=[])
    a.load_state = lambda: {'items': list(st['items'])}
    a.save_state = lambda s: st.update(items=s['items'])
    a.jobs = types.SimpleNamespace(put=a.queued.append)
    a.safe_name = lambda n: n
    a.unique_path = lambda d, n: d / n
    a.state = st
    return a


def _setup(tmp_path, monkeypatch, files, idx=None, items=(), age=120):
    z = tmp_path / 'Downloads' / 'Zalo-Logistic-Checkpoint'; z.mkdir(parents=True)
    old = time.time() - age
    for name, data in files.items():
        p = z / name; p.write_bytes(data); os.utime(p, (old, old))
    app = _app(tmp_path, items)
    monkeypatch.setitem(sys.modules, 'copilot_app', app)
    import teams_files
    monkeypatch.setattr(teams_files, 'local_index', lambda: dict(idx or {}))
    monkeypatch.setattr(Z, 'ZDIR', z)
    monkeypatch.setattr(Z, 'REG', tmp_path / 'school' / 'zalo' / 'files_done.json')
    return z, app


def test_file_moi_vao_inbox_dung_noi_dung_roi_xoa_ban_zalo(tmp_path, monkeypatch):
    z, app = _setup(tmp_path, monkeypatch, {'BT tuần 7 - Đại số.pdf': b'%PDF bai tap'})
    out = Z.sync_once()
    dest = app.INBOX / 'BT tuần 7 - Đại số.pdf'
    assert dest.read_bytes() == b'%PDF bai tap' and not (z / 'BT tuần 7 - Đại số.pdf').exists()
    it = app.state['items'][0]
    assert it['source'] == 'zalo' and it['status'] == 'queued' and it['sha'] == hashlib.sha256(b'%PDF bai tap').hexdigest()
    assert app.queued == [it['id']] and out[0]['kq'].startswith('đã chuyển vào Inbox')


def test_trung_voi_kho_thi_chi_xoa_khong_nap_lai(tmp_path, monkeypatch):
    h = hashlib.sha256(b'slide').hexdigest()
    z, app = _setup(tmp_path, monkeypatch, {'slide.pdf': b'slide'}, idx={h: 'Đại số\\Slide\\slide.pdf'})
    original = app.INBOX.parent / 'Đại số' / 'Slide' / 'slide.pdf'
    original.parent.mkdir(parents=True); original.write_bytes(b'slide')
    import teams_files
    monkeypatch.setattr(teams_files, 'local_index', lambda: {h: str(original.relative_to(app.INBOX.parent))})
    out = Z.sync_once()
    assert not (z / 'slide.pdf').exists() and app.state['items'] == [] and app.queued == []
    assert out[0]['kq'] == 'trùng, đã xoá bản Zalo' and out[0]['rel'] == 'Đại số\\Slide\\slide.pdf'


def test_trung_voi_file_dang_cho_trong_inbox(tmp_path, monkeypatch):
    h = hashlib.sha256(b'abc').hexdigest()
    z, app = _setup(tmp_path, monkeypatch, {'a.docx': b'abc'}, items=[{'sha': h, 'name': 'a.docx', 'status': 'queued'}])
    app.INBOX.mkdir(parents=True); (app.INBOX/'a.docx').write_bytes(b'abc')
    app.state['items'][0]['path']=str(app.INBOX/'a.docx')
    Z.sync_once()
    assert not (z / 'a.docx').exists() and len(app.state['items']) == 1


def test_file_dang_ghi_do_va_file_tam_khong_dung_toi(tmp_path, monkeypatch):
    z, app = _setup(tmp_path, monkeypatch, {'dang-tai.pdf': b'x', 'b.crdownload': b'y', '~$nhap.docx': b'z'}, age=1)
    for n in ('b.crdownload', '~$nhap.docx'):
        os.utime(z / n, (time.time() - 300, time.time() - 300))
    assert Z.sync_once() == []
    assert sorted(p.name for p in z.iterdir()) == ['b.crdownload', 'dang-tai.pdf', '~$nhap.docx']


def test_chep_hong_thi_giu_nguyen_ban_zalo(tmp_path, monkeypatch):
    z, app = _setup(tmp_path, monkeypatch, {'de.pdf': b'dung'})
    monkeypatch.setattr(Z.shutil, 'copy2', lambda src, dst: open(dst, 'wb').write(b'sai'))
    out = Z.sync_once()
    assert (z / 'de.pdf').read_bytes() == b'dung' and app.state['items'] == [] and 'giữ bản Zalo' in out[0]['kq']
    assert not any(app.INBOX.iterdir())


def test_doc_thu_muc_con_trong_checkpoint_va_thieu_thu_muc_thi_thoi(tmp_path, monkeypatch):
    z, app = _setup(tmp_path, monkeypatch, {})
    (z / 'con').mkdir(); (z / 'con' / 'x.pdf').write_bytes(b'x'); os.utime(z / 'con' / 'x.pdf', (time.time() - 300,) * 2)
    assert len(Z.sync_once()) == 1 and not (z / 'con' / 'x.pdf').exists()
    assert (app.INBOX/'x.pdf').read_bytes()==b'x'
    monkeypatch.setattr(Z, 'ZDIR', tmp_path / 'khong-co')
    assert Z.sync_once() == []


def test_stale_index_does_not_delete_only_copy(tmp_path, monkeypatch):
    h=hashlib.sha256(b'only copy').hexdigest()
    z, app=_setup(tmp_path,monkeypatch,{'a.pdf':b'only copy'},idx={h:'missing.pdf'})
    Z.sync_once()
    assert (app.INBOX/'a.pdf').read_bytes()==b'only copy'
    assert len(app.state['items'])==1


def test_two_identical_files_in_same_batch_are_queued_once(tmp_path,monkeypatch):
    z,app=_setup(tmp_path,monkeypatch,{'a.pdf':b'abc','b.pdf':b'abc'})
    Z.sync_once()
    assert len(app.queued)==1 and len(app.state['items'])==1
    assert not list(z.iterdir())


def test_persistence_failure_keeps_source_and_does_not_queue(tmp_path,monkeypatch):
    z,app=_setup(tmp_path,monkeypatch,{'a.pdf':b'abc'})
    def fail(state): raise OSError('disk full')
    app.save_state=fail
    Z.sync_once()
    assert (z/'a.pdf').read_bytes()==b'abc' and not app.queued
    assert not list(app.INBOX.iterdir())


def test_source_changes_during_copy_keeps_new_source(tmp_path,monkeypatch):
    z,app=_setup(tmp_path,monkeypatch,{'a.pdf':b'old'})
    copy=Z.shutil.copy2
    def changed(src,dst):
        copy(src,dst); src.write_bytes(b'new content')
    monkeypatch.setattr(Z.shutil,'copy2',changed)
    Z.sync_once()
    assert (z/'a.pdf').read_bytes()==b'new content' and not app.queued


def test_needs_choice_verified_copy_is_deduplicated(tmp_path,monkeypatch):
    h=hashlib.sha256(b'abc').hexdigest()
    z,app=_setup(tmp_path,monkeypatch,{'a.pdf':b'abc'},items=[dict(sha=h,name='old.pdf',status='needs_choice')])
    app.INBOX.mkdir(parents=True); dest=app.INBOX/'old.pdf'; dest.write_bytes(b'abc')
    app.state['items'][0]['path']=str(dest)
    Z.sync_once()
    assert not (z/'a.pdf').exists() and not app.queued and dest.exists()
