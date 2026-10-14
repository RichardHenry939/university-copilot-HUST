# -*- coding: utf-8 -*-
"""tools/notion_setup.py — bộ dựng workspace Notion. Không gọi mạng: FakeNotion giả API trong bộ nhớ
và KIỂM hình dạng payload (mỗi DB đúng 1 cột tiêu đề, quan hệ trỏ tới DB đã có, không gửi kiểu API không tạo được)."""
import io, json, re, sys, urllib.error, urllib.request
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import notion_setup as ns  # noqa: E402

SCHEMA = ns.load_schema()
PARENT = 'a' * 32


class FakeNotion:
    def __init__(self):
        self.n = 0
        self.children = []            # khối con của trang cha: {'type', 'id', 'title'}
        self.dbs = {}                 # id -> {'title', 'props': {name: payload}}
        self.rows = {}                # id DB -> [properties]
        self.pages = {}
        self.calls = []

    def _id(self):
        self.n += 1; return f'{self.n:032x}'

    def __call__(self, method, path, body=None):
        self.calls.append((method, path))
        if method == 'GET' and path.startswith(f'/blocks/{PARENT}/children'):
            res = [{'type': c['type'], 'id': c['id'], c['type']: {'title': c['title']}} for c in self.children]
            return {'results': res, 'has_more': False}
        if method == 'POST' and path == '/databases':
            assert body['parent'] == {'type': 'page_id', 'page_id': PARENT}
            props = body['properties']
            assert sum(1 for v in props.values() if 'title' in v) == 1, 'mỗi DB đúng 1 cột tiêu đề'
            self._check_props(props)
            i = self._id(); t = body['title'][0]['text']['content']
            self.dbs[i] = {'title': t, 'props': dict(props)}; self.rows[i] = []
            self.children.append({'type': 'child_database', 'id': i, 'title': t})
            return {'id': i}
        m = re.fullmatch(r'/databases/(\w+)', path)
        if m and method == 'GET':
            return {'properties': {k: {'type': next(iter(v))} for k, v in self.dbs[m.group(1)]['props'].items()}}
        if m and method == 'PATCH':
            self._check_props(body['properties'])
            for k in body['properties']: assert k not in self.dbs[m.group(1)]['props'], f'không được sửa thuộc tính đã có: {k}'
            self.dbs[m.group(1)]['props'].update(body['properties']); return {}
        m = re.fullmatch(r'/databases/(\w+)/query', path)
        if m and method == 'POST':
            return {'results': self.rows[m.group(1)][:body.get('page_size', 100)]}
        if method == 'POST' and path == '/pages':
            par = body['parent']
            if par['type'] == 'database_id':
                db = self.dbs[par['database_id']]
                for k in body['properties']: assert k in db['props'], f'dòng mồi ghi cột không có: {k}'
                self.rows[par['database_id']].append(body['properties']); return {'id': self._id()}
            i = self._id(); t = body['properties']['title']['title'][0]['text']['content']
            self.pages[i] = t; self.children.append({'type': 'child_page', 'id': i, 'title': t}); return {'id': i}
        raise AssertionError(f'gọi API không mong đợi: {method} {path}')

    def _check_props(self, props):
        for name, v in props.items():
            (t, conf), = v.items()
            assert t not in ns.MANUAL, f'{name}: API không tạo được kiểu {t}'
            if t == 'relation': assert conf['database_id'] in self.dbs, f'{name}: quan hệ tới DB chưa có'
            if t in ('select', 'multi_select'):
                names = [o['name'] for o in conf['options']]
                assert len(names) == len(set(names)), f'{name}: lựa chọn trùng'


def run(fake):
    return ns.setup(fake, PARENT, SCHEMA, log=lambda *_: None)


# ----------------------------------------------------------------------------- schema
def test_schema_covers_every_notion_key_in_config():
    cfg_keys = set(json.loads((ROOT / 'config.example.json').read_text(encoding='utf-8'))['notion'])
    keys = [db['key'] for db in SCHEMA['databases']] + [pg['key'] for pg in SCHEMA['pages']]
    assert len(keys) == len(set(keys))
    assert set(keys) == cfg_keys


def test_schema_is_well_formed():
    db_keys = {db['key'] for db in SCHEMA['databases']}
    names = [db['name'] for db in SCHEMA['databases']]
    assert len(names) == len(set(names)), 'tên DB phải khác nhau (dò theo tên khi chạy lại)'
    for db in SCHEMA['databases']:
        props = [p['name'] for p in db['properties']]
        assert len(props) == len(set(props)), db['key']
        assert sum(p['type'] == 'title' for p in db['properties']) == 1, db['key']
        for p in db['properties']:
            assert p['certainty'] in ('CODE', 'INFERRED')
            if p['type'] == 'relation': assert p['relation_to'] in db_keys, (db['key'], p['name'])


def test_schema_has_no_real_ids_or_personal_paths():
    raw = (ROOT / 'tools' / 'notion_schema.json').read_text(encoding='utf-8')
    assert not re.search(r'\b[0-9a-f]{32}\b', raw)
    assert not re.search(r'[A-Za-z]:[\\/](Users|Data|AI|Tools)', raw)
    assert '@' not in raw


def test_seed_rows_match_schema():
    for db in SCHEMA['databases']:
        props = {p['name']: p for p in db['properties']}
        for row in db.get('seed', []):
            for k, v in row.items():
                assert k in props, (db['key'], k)
                if props[k]['type'] == 'select': assert v in props[k]['options'], (db['key'], k, v)
                ns.value_payload(props[k], v)   # kiểu được hỗ trợ
    st = next(db for db in SCHEMA['databases'] if db['key'] == 'semester_state')
    assert st['seed'][0]['State'] == 'Current'   # semester.py cần dòng 'Current'
    tr = next(db for db in SCHEMA['databases'] if db['key'] == 'credit_tracker')
    assert ['S' + r['Semester'].split()[-1] for r in tr['seed']] == [f'S{i}' for i in range(1, 9)]


# ----------------------------------------------------------------------------- chạy
def test_dry_run_prints_plan_without_network():
    buf = io.StringIO()
    with redirect_stdout(buf): assert ns.main(['--dry-run']) == 0   # conftest chặn urlopen: gọi mạng là hỏng
    out = buf.getvalue()
    for db in SCHEMA['databases']: assert db['name'] in out
    assert 'kiểu status' in out


def test_setup_creates_everything_then_relations_and_seeds():
    fake = FakeNotion()
    ids, manual, rep = run(fake)
    assert len(rep['created_db']) == len(SCHEMA['databases']) and not rep['reused_db']
    assert len(rep['created_page']) == len(SCHEMA['pages'])
    # mọi DB tạo xong TRƯỚC lần thêm quan hệ đầu tiên
    first_patch = next(i for i, c in enumerate(fake.calls) if c[0] == 'PATCH')
    last_create = max(i for i, c in enumerate(fake.calls) if c == ('POST', '/databases'))
    assert last_create < first_patch
    # đủ thuộc tính (trừ kiểu làm tay) và quan hệ trỏ đúng DB đích
    by_title = {d['title']: d for d in fake.dbs.values()}
    for db in SCHEMA['databases']:
        have = by_title[db['name']]['props']
        for p in db['properties']:
            if p['type'] in ns.MANUAL: assert p['name'] not in have; continue
            assert p['name'] in have, (db['key'], p['name'])
            if p['type'] == 'relation': assert have[p['name']]['relation']['database_id'] == ids[p['relation_to']]
    # dòng mồi
    assert len(fake.rows[ids['credit_tracker']]) == 8 and len(fake.rows[ids['semester_state']]) == 1
    # việc làm tay = đúng các thuộc tính status / formula / rollup
    n_manual = sum(p['type'] in ns.MANUAL for db in SCHEMA['databases'] for p in db['properties'])
    assert len(manual) == n_manual > 0
    block = json.loads(ns.config_block(ids, SCHEMA))['notion']
    assert set(block) == {d['key'] for d in SCHEMA['databases']} | {p['key'] for p in SCHEMA['pages']}
    assert all(re.fullmatch(r'[0-9a-f]{32}', v) for v in block.values())


def test_rerun_creates_nothing_new():
    fake = FakeNotion()
    ids1, _, _ = run(fake)
    n_children, n_rows = len(fake.children), sum(len(r) for r in fake.rows.values())
    ids2, _, rep = run(fake)
    assert ids2 == ids1
    assert not rep['created_db'] and not rep['created_page'] and not rep['added_props'] and not rep['seeded']
    assert len(fake.children) == n_children and sum(len(r) for r in fake.rows.values()) == n_rows


def test_existing_db_only_gets_missing_props_and_type_conflict_is_reported():
    fake = FakeNotion()
    courses = next(db for db in SCHEMA['databases'] if db['key'] == 'courses')
    i = fake._id()
    fake.dbs[i] = {'title': courses['name'], 'props': {'Name': {'title': {}}, 'Credits': {'rich_text': {}}}}
    fake.rows[i] = [{'Name': 'có sẵn'}]
    fake.children.append({'type': 'child_database', 'id': i, 'title': courses['name']})
    ids, _, rep = run(fake)
    assert ids['courses'] == i and 'courses' in rep['reused_db']
    assert fake.dbs[i]['props']['Credits'] == {'rich_text': {}}           # không tự đổi kiểu
    assert any('Credits' in w and 'number' in w for w in rep['warnings'])
    assert 'Code' in fake.dbs[i]['props']                                  # cột thiếu được thêm


def test_seed_skipped_when_db_already_has_rows():
    fake = FakeNotion()
    st = next(db for db in SCHEMA['databases'] if db['key'] == 'semester_state')
    i = fake._id()
    fake.dbs[i] = {'title': st['name'], 'props': {'State': {'title': {}}}}
    fake.rows[i] = [{'State': 'Current'}]
    fake.children.append({'type': 'child_database', 'id': i, 'title': st['name']})
    ids, _, rep = run(fake)
    assert len(fake.rows[i]) == 1 and not any(st['name'] in s for s in rep['seeded'])


# ----------------------------------------------------------------------------- tiện ích
def test_norm_id_accepts_dashed_and_url_and_rejects_garbage():
    raw = '0123456789abcdef0123456789abcdef'
    dashed = f'{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}'
    assert ns.norm_id(dashed) == raw
    assert ns.norm_id(f'https://www.notion.so/Trang-cua-toi-{raw}?pvs=4') == raw
    with pytest.raises(SystemExit): ns.norm_id('khong-phai-id')


def test_http_api_retries_on_429(monkeypatch):
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        assert req.headers['Notion-version'] == ns.VERSION and req.headers['Authorization'] == 'Bearer tok'
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, 'slow down', {'Retry-After': '0'}, io.BytesIO(b'{}'))
        return Resp(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    assert ns.http_api('tok')('GET', '/users/me') == {'ok': True}
    assert len(calls) == 2


def test_main_requires_token(monkeypatch):
    monkeypatch.delenv('NOTION_TOKEN', raising=False)
    with pytest.raises(SystemExit): ns.main([PARENT])
