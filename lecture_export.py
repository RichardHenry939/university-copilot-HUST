# -*- coding: utf-8 -*-
"""📚 Ghi chú bài giảng (Notion · Lecture Notes) -> Uni-Documents (Claude 2026-10-06).

Người dùng: "LectureRecorder ghi vào mỗi Notion, không đưa vào tệp ghi chú bài giảng trên Uni-Documents."
Mỗi ghi chú -> <thư mục ĐÚNG MÔN đã gán>/Ghi chú bài giảng/<YYYY-MM-DD> - <tên bài>.txt (6/10: người dùng — .md không dùng được, phải .txt).
Môn lấy theo quan hệ Course của ghi chú -> mã môn -> thư mục môn (COURSE_FOLDERS + thư mục môn mới tự tạo); thiếu Course thì đoán theo tên môn trong tiêu đề.
Chạy trong vòng cập nhật 5 phút: chỉ xuất ghi chú MỚI hoặc vừa SỬA trên Notion (so last_edited_time). Chỉ đọc Notion, không gọi AI.
Thư mục "Ghi chú bài giảng" không bị luồng Uni-Documents nạp ngược lên Notion / Drive (ghi chú đã ở Notion rồi)."""
import uc_config as cfg
import json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTES_DB = cfg.notion("lecture_notes")   # 📚 Lecture Notes
STATE = HERE / 'school' / 'lecture_export.json'
SUB = 'Ghi chú Bài giảng'   # đúng tên thư mục bạn đã đặt (vd Giải Tích I); thư mục môn đã có tên khác hoa / thường thì dùng tên có sẵn


def _load():
    try: return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception: return {}


def _txt(rt): return ''.join(x.get('plain_text', '') for x in rt or [])


def _blocks(N, bid):
    out, cur = [], None
    while True:
        u = f"https://api.notion.com/v1/blocks/{bid}/children?page_size=100" + (f"&start_cursor={cur}" if cur else '')
        r = N.ops([{"method": "GET", "url": u}])[0]
        out += r.get('results', [])
        if not r.get('has_more'): return out
        cur = r['next_cursor']


def _md(N, blocks, depth=0):
    L, n = [], 0
    pad = '  ' * depth
    for b in blocks:
        t = b['type']; d = b.get(t) or {}; s = _txt(d.get('rich_text'))
        n = n + 1 if t == 'numbered_list_item' else 0
        if t in ('heading_1', 'heading_2', 'heading_3'): L += ['', s.upper() if t == 'heading_1' else s, '-' * min(60, max(10, len(s))), '']
        elif t == 'bulleted_list_item': L.append(f'{pad}- {s}')
        elif t == 'numbered_list_item': L.append(f'{pad}{n}. {s}')
        elif t == 'to_do': L.append(f"{pad}{'☑' if d.get('checked') else '☐'} {s}")
        elif t == 'callout': L += ['', f"{((d.get('icon') or {}).get('emoji') or '')} {s}".strip(), '']
        elif t in ('quote', 'code'): L += ['', s, '']
        elif t == 'equation': L += ['', d.get('expression', ''), '']
        elif t == 'divider': L += ['', '-' * 40, '']
        elif t == 'toggle':   # bản chép lời đầy đủ nằm trong toggle
            L += ['', s, '-' * min(60, max(10, len(s))), '']
            if b.get('has_children'): L += [x for x in _md(N, _blocks(N, b['id'])) ]
            continue
        elif t == 'paragraph': L += [f'{pad}{s}' if s else '']
        if b.get('has_children') and t != 'toggle': L += _md(N, _blocks(N, b['id']), depth + 1)
    return L


def _safe(s): return re.sub(r'\s+', ' ', re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', s)).strip()[:120] or 'Bài giảng'


def run(post):
    import academic, copilot_app as app, teams_files
    N = academic.Notion(post)
    courses = {c['id']: (_txt(c['properties'].get('Code', {}).get('rich_text')), _txt(c['properties'].get('Name', {}).get('rich_text')))
               for c in N.query(academic.COURSES)}
    st = _load(); out = {'written': [], 'kept': 0}
    for r in N.query(NOTES_DB):
        P = r['properties']; nid = r['id']
        title = _txt(P['Lecture']['title']) or 'Bài giảng'
        day = (((P.get('Lecture Date') or {}).get('date') or {}).get('start') or r['created_time'])[:10]
        cs = [courses.get(c['id']) for c in (P.get('Course') or {}).get('relation', []) if courses.get(c['id'])]
        code, cname = cs[0] if cs else ('', '')
        if not code:   # ghi chú chưa gán môn -> đoán theo tên môn có trong tiêu đề (vd "Giải tích I - …")
            hit = [(len(n), c, n) for c, n, _ in teams_files.course_table() if n and teams_files.norm(n) in teams_files.norm(title)]
            if hit: _, code, cname = max(hit)
        folder = teams_files.folder_for(code, cname) if code else SUB + ' (chưa rõ môn)'
        sub = SUB
        if code:
            try: sub = next((d.name for d in (app.UNI / folder).iterdir() if d.is_dir() and d.name.lower() == SUB.lower()), SUB)
            except OSError: pass
        rel = str(Path(folder) / sub / f"{day} - {_safe(title)}.txt") if code else str(Path(folder) / f"{day} - {_safe(title)}.txt")
        old = st.get(nid) or {}
        dest = app.UNI / rel
        if old.get('sig') == r['last_edited_time'] and old.get('rel') == rel and dest.exists():
            out['kept'] += 1; continue
        body = _md(N, _blocks(N, nid))
        head = [title.upper(), '=' * min(70, len(title)), '',
                f"- Môn: {code} {cname}".rstrip() if code else '- Môn: (chưa gán)',
                f"- Ngày học: {day}",
                f"- Ghi chú gốc (Notion): {r.get('url', '')}"]
        if (P.get('Source Audio') or {}).get('url'): head.append(f"- Bản ghi âm: {P['Source Audio']['url']}")
        if _txt((P.get('Summary') or {}).get('rich_text')): head += ['', f"Tóm tắt: {_txt(P['Summary']['rich_text'])}"]
        text = '\n'.join(head + [''] + body).replace('\n\n\n', '\n\n').strip() + '\n'
        dest.parent.mkdir(parents=True, exist_ok=True)
        if old.get('rel') and old['rel'] != rel:   # đổi tên / đổi môn trên Notion -> chuyển file cũ (chỉ file UC đã xuất)
            try: (app.UNI / old['rel']).unlink(missing_ok=True)   # vd bản .md cũ -> .txt
            except Exception: pass
        dest.write_text(text, encoding='utf-8')
        st[nid] = {'sig': r['last_edited_time'], 'rel': rel}
        out['written'].append(rel)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True, **out}


if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(encoding='utf-8')
    import copilot_app as app
    print(json.dumps(run(app._npost), ensure_ascii=False, indent=1))
