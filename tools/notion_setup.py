# -*- coding: utf-8 -*-
"""🧱 Dựng lại workspace Notion cho University Copilot từ schema rút ra từ code (tools/notion_schema.json).

Cách dùng (PowerShell):
    $env:NOTION_TOKEN = "<token integration Notion của bạn>"
    py tools\\notion_setup.py <id-trang-cha> --dry-run     # chỉ in kế hoạch, KHÔNG gọi mạng, không cần token
    py tools\\notion_setup.py <id-trang-cha>               # tạo thật

Trang cha phải được share cho integration (••• → Connections). Công cụ:
  1. đọc các database / trang con ĐÃ CÓ trên trang cha (dò theo tên) -> chạy lại không tạo trùng;
  2. tạo database còn thiếu (đủ thuộc tính, trừ quan hệ); DB đã có thì chỉ THÊM thuộc tính còn thiếu, không sửa / xoá gì;
  3. khi đã đủ database: thêm các thuộc tính quan hệ (relation);
  4. tạo "dòng mồi" mà code cần sẵn (vd dòng 'Current' của Semester State) — CHỈ khi database đó đang trống;
  5. tạo các trang thường (không phải database) còn thiếu;
  6. in khối "notion": {...} để dán vào config.json, kèm danh sách việc phải làm tay
     (thuộc tính Status, formula / rollup, nhóm của Status…).
Chỉ dùng thư viện chuẩn. Không ghi file nào; ID chỉ in ra màn hình."""
import argparse, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

SCHEMA_FILE = Path(__file__).resolve().parent / 'notion_schema.json'


def load_schema(path=SCHEMA_FILE):
    return json.loads(Path(path).read_text(encoding='utf-8'))

API = 'https://api.notion.com/v1'
VERSION = '2022-06-28'   # bản API mà n8n / UC đang dùng: ID database (không phải data source)
SIMPLE = {'rich_text', 'number', 'date', 'checkbox', 'url', 'email', 'phone_number', 'files', 'people',
          'created_time', 'last_edited_time', 'created_by', 'last_edited_by'}
MANUAL = {'status', 'formula', 'rollup', 'unique_id', 'button'}   # API không tạo được (hoặc không tạo đúng) -> việc làm tay


# ----------------------------------------------------------------------------- gọi API
def http_api(token):
    """-> hàm call(method, path, body) gọi Notion thật (thử lại khi 429 / 5xx)."""
    def call(method, path, body=None):
        data = json.dumps(body).encode('utf-8') if body is not None else None
        for attempt in range(5):
            req = urllib.request.Request(API + path, data=data, method=method, headers={
                'Authorization': f'Bearer {token}', 'Notion-Version': VERSION, 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read().decode('utf-8') or '{}')
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(float(e.headers.get('Retry-After') or 2 * (attempt + 1))); continue
                raise RuntimeError(f'{method} {path} -> {e.code}: {e.read().decode("utf-8", "replace")[:400]}')
    return call


def norm_id(x):
    """Nhận ID dạng 32 ký tự, có gạch, hoặc nguyên URL trang Notion -> 32 ký tự hex."""
    s = str(x or '').strip().split('?')[0].rstrip('/').split('/')[-1].split('-')[-1] if 'notion.so' in str(x) else str(x or '').strip()
    s = s.replace('-', '').lower()
    if len(s) != 32 or any(c not in '0123456789abcdef' for c in s):
        raise SystemExit(f'ID trang cha không hợp lệ: cần 32 ký tự hex (có thể có gạch), nhận "{x}"')
    return s


# ----------------------------------------------------------------------------- dựng payload
def prop_payload(p, ids=None):
    """Một thuộc tính trong schema -> payload API (None nếu phải làm tay / chưa đủ DB đích)."""
    t = p['type']
    if t == 'title': return {'title': {}}
    if t in SIMPLE: return {t: {'format': 'number'}} if t == 'number' else {t: {}}
    if t in ('select', 'multi_select'): return {t: {'options': [{'name': o} for o in p.get('options') or []]}}
    if t == 'relation':
        target = (ids or {}).get(p['relation_to'])
        return {'relation': {'database_id': target, 'single_property': {}}} if target else None
    return None


def value_payload(p, v):
    """Giá trị của một ô trong dòng mồi -> payload API."""
    t = p['type']
    if t in ('title', 'rich_text'): return {t: [{'type': 'text', 'text': {'content': str(v)}}]}
    if t == 'select': return {'select': {'name': str(v)}}
    if t in ('number', 'checkbox', 'url'): return {t: v}
    if t == 'date': return {'date': {'start': v}}
    raise ValueError(f"dòng mồi không hỗ trợ kiểu {t} ({p['name']})")


def seed_payload(db, dbid, row):
    props = {p['name']: p for p in db['properties']}
    return {'parent': {'type': 'database_id', 'database_id': dbid},
            'properties': {k: value_payload(props[k], v) for k, v in row.items()}}


def db_payload(db, parent):
    props = {p['name']: prop_payload(p) for p in db['properties'] if p['type'] not in MANUAL | {'relation'}}
    body = {'parent': {'type': 'page_id', 'page_id': parent}, 'title': [{'type': 'text', 'text': {'content': db['name']}}],
            'properties': props}
    if db.get('icon'): body['icon'] = {'type': 'emoji', 'emoji': db['icon']}
    return body


def manual_steps(schema):
    out = []
    for db in schema['databases']:
        for p in db['properties']:
            if p['type'] in MANUAL:
                opt = f" — lựa chọn: {', '.join(p['options'])}" if p.get('options') else ''
                out.append(f"{db['name']} → thêm thuộc tính “{p['name']}” kiểu {p['type']}{opt}")
    return out


# ----------------------------------------------------------------------------- đọc trang cha
def children(call, parent):
    """Database và trang con đang có trên trang cha: (dict tên -> id DB, dict tên -> id trang)."""
    dbs, pages, cursor = {}, {}, None
    while True:
        r = call('GET', f'/blocks/{parent}/children?page_size=100' + (f'&start_cursor={cursor}' if cursor else ''))
        for b in r.get('results', []):
            if b.get('type') == 'child_database': dbs.setdefault(b['child_database'].get('title', ''), b['id'].replace('-', ''))
            if b.get('type') == 'child_page': pages.setdefault(b['child_page'].get('title', ''), b['id'].replace('-', ''))
        if not r.get('has_more'): return dbs, pages
        cursor = r.get('next_cursor')


# ----------------------------------------------------------------------------- chạy
def plan(schema):
    """Kế hoạch đọc được (không gọi mạng)."""
    lines = []
    for db in schema['databases']:
        kinds = {}
        for p in db['properties']: kinds[p['type']] = kinds.get(p['type'], 0) + 1
        rels = [f"{p['name']}→{p['relation_to']}" for p in db['properties'] if p['type'] == 'relation']
        lines.append(f"[DB] {db.get('icon') or ''} {db['name']} (notion.{db['key']}): {len(db['properties'])} thuộc tính "
                     f"({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))})" + (f"; quan hệ: {', '.join(rels)}" if rels else ''))
    for db in schema['databases']:
        if db.get('seed'): lines.append(f"[Dòng mồi] {db['name']}: {len(db['seed'])} dòng (chỉ khi DB trống)")
    for pg in schema.get('pages', []):
        lines.append(f"[Trang] {pg.get('icon') or ''} {pg['name']} (notion.{pg['key']})")
    return lines


def setup(call, parent, schema, log=print):
    """Tạo / bổ sung workspace. -> (ids: key -> id, manual: list việc làm tay, report: dict thống kê)."""
    dbs_have, pages_have = children(call, parent)
    ids, report = {}, {'created_db': [], 'reused_db': [], 'added_props': [], 'created_page': [], 'reused_page': [], 'warnings': []}
    by_key = {db['key']: db for db in schema['databases']}
    # 1) database (không quan hệ)
    for db in schema['databases']:
        if db['name'] in dbs_have:
            dbid = dbs_have[db['name']]; ids[db['key']] = dbid; report['reused_db'].append(db['key'])
            have = call('GET', f'/databases/{dbid}').get('properties', {})
            add = {}
            for p in db['properties']:
                if p['type'] in MANUAL | {'relation'}: continue
                if p['name'] in have:
                    if have[p['name']].get('type') != p['type']:
                        report['warnings'].append(f"{db['name']}.{p['name']}: đang là {have[p['name']].get('type')}, schema cần {p['type']} — không tự sửa")
                    continue
                if p['type'] == 'title':
                    report['warnings'].append(f"{db['name']}: cột tiêu đề phải tên “{p['name']}” — đổi tên tay"); continue
                add[p['name']] = prop_payload(p)
            if add:
                call('PATCH', f'/databases/{dbid}', {'properties': add}); report['added_props'] += [f"{db['name']}.{k}" for k in add]
            log(f"= {db['name']}: đã có" + (f", thêm {len(add)} thuộc tính" if add else ''))
        else:
            r = call('POST', '/databases', db_payload(db, parent))
            ids[db['key']] = r['id'].replace('-', ''); report['created_db'].append(db['key'])
            log(f"+ {db['name']}: tạo mới")
    # 2) quan hệ — sau khi đã đủ database
    for db in schema['databases']:
        rel = [p for p in db['properties'] if p['type'] == 'relation']
        if not rel: continue
        have = call('GET', f"/databases/{ids[db['key']]}").get('properties', {})
        add = {}
        for p in rel:
            if p['name'] in have: continue
            if p['relation_to'] not in by_key:
                report['warnings'].append(f"{db['name']}.{p['name']}: DB đích “{p['relation_to']}” không có trong schema"); continue
            add[p['name']] = prop_payload(p, ids)
        if add:
            call('PATCH', f"/databases/{ids[db['key']]}", {'properties': add}); report['added_props'] += [f"{db['name']}.{k}" for k in add]
            log(f"~ {db['name']}: thêm {len(add)} quan hệ")
    # 3) dòng mồi — chỉ khi database đang trống (chạy lại không tạo trùng)
    report['seeded'] = []
    for db in schema['databases']:
        if not db.get('seed'): continue
        if call('POST', f"/databases/{ids[db['key']]}/query", {'page_size': 1}).get('results'): continue
        for row in db['seed']:
            call('POST', '/pages', seed_payload(db, ids[db['key']], row))
        report['seeded'].append(f"{db['name']} ({len(db['seed'])} dòng)"); log(f"+ {db['name']}: tạo {len(db['seed'])} dòng mồi")
    # 4) trang thường
    for pg in schema.get('pages', []):
        if pg['name'] in pages_have:
            ids[pg['key']] = pages_have[pg['name']]; report['reused_page'].append(pg['key']); continue
        body = {'parent': {'type': 'page_id', 'page_id': parent},
                'properties': {'title': {'title': [{'type': 'text', 'text': {'content': pg['name']}}]}}}
        if pg.get('icon'): body['icon'] = {'type': 'emoji', 'emoji': pg['icon']}
        r = call('POST', '/pages', body); ids[pg['key']] = r['id'].replace('-', ''); report['created_page'].append(pg['key'])
        log(f"+ trang {pg['name']}: tạo mới")
    return ids, manual_steps(schema), report


def config_block(ids, schema):
    keys = [db['key'] for db in schema['databases']] + [pg['key'] for pg in schema.get('pages', [])]
    return json.dumps({'notion': {k: ids.get(k, '<chưa tạo>') for k in sorted(keys)}}, ensure_ascii=False, indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Dựng workspace Notion cho University Copilot (xem docs/NOTION-SCHEMA.md).')
    ap.add_argument('parent', nargs='?', help='ID (hoặc URL) trang Notion cha, đã share cho integration')
    ap.add_argument('--dry-run', action='store_true', help='chỉ in kế hoạch, không gọi mạng')
    a = ap.parse_args(argv)
    schema = load_schema()
    if a.dry_run:
        print('KẾ HOẠCH (không gọi mạng):'); print('\n'.join(plan(schema)))
        print('\nViệc phải làm tay sau khi tạo:'); print('\n'.join('  - ' + x for x in manual_steps(schema)) or '  (không có)')
        return 0
    if not a.parent: ap.error('cần ID trang cha (hoặc dùng --dry-run)')
    token = os.environ.get('NOTION_TOKEN')
    if not token: raise SystemExit('Thiếu biến môi trường NOTION_TOKEN (token integration Notion).')
    ids, manual, rep = setup(http_api(token), norm_id(a.parent), schema)
    print(f"\nTạo {len(rep['created_db'])} DB, dùng lại {len(rep['reused_db'])} DB, thêm {len(rep['added_props'])} thuộc tính, "
          f"tạo {len(rep['created_page'])} trang.")
    for w in rep['warnings']: print('⚠', w)
    print('\nDán khối sau vào config.json (thay khối "notion" cũ):'); print(config_block(ids, schema))
    print('\nViệc phải làm tay:'); print('\n'.join('  - ' + x for x in manual) or '  (không có)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
