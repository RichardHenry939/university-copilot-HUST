# -*- coding: utf-8 -*-
"""(v1.00.51) Dọn Drive một lần: lập bảng file UC đã tải lên -> thư mục đích như trên máy. Mặc định CHỈ LẬP BẢNG.
  python drive_tidy_plan.py           -> ghi plans/drive-tidy-table.md (để chủ duyệt), không chuyển gì
  python drive_tidy_plan.py --apply   -> chuyển theo bảng (qua Drive API, giữ fileId, KHÔNG xoá; không qua ổ G:)
Mục thiếu driveLink: liệt kê riêng (chưa sao lưu), không tự tải ở bước này.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'plans' / 'drive-tidy-table.md'


def rows():
    st = json.loads((HERE / 'inbox_state.json').read_text(encoding='utf-8'))
    import copilot_app as C
    have, miss = [], []
    for x in st.get('items', []):
        if x.get('notion') not in ('done',) or x.get('movedTo') or not x.get('relPath'): continue
        if not Path(x.get('path') or '').exists(): continue   # file không còn trên máy: không đụng bản Drive
        fid = C.drive_id(x.get('driveLink'))
        (have if fid else miss).append((x['relPath'].replace('\\', '/'), fid))
    return sorted(have), sorted(miss)


def main():
    have, miss = rows()
    lines = ['# Bảng dọn Drive (chờ chủ duyệt)', '',
             f'Đích: `University/Uni-Documents/<đường dẫn như trên máy>`. Giữ nguyên fileId (driveLink cũ vẫn đúng). Không xoá file nào.', '',
             f'## Sẽ chuyển ({len(have)} file)', '', '| Thư mục đích | Tên file |', '|---|---|']
    lines += [f"| {Path(r).parent.as_posix() or '(gốc)'} | {Path(r).name} |" for r, _ in have]
    lines += ['', f'## Chưa có bản trên Drive ({len(miss)} file) — chưa sao lưu, bước này không tải', '']
    lines += [f'- {r}' for r, _ in miss]
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Đã lập bảng: {len(have)} file sẽ chuyển, {len(miss)} file chưa có trên Drive -> {OUT}')
    if '--apply' in sys.argv:
        import copilot_app as C, drive_tree as T
        ok = bad = 0
        for r, fid in have:
            try: T.place(C.n8n, fid, r); ok += 1
            except Exception as e: bad += 1; print('lỗi', r, e)
        print(f'Đã chuyển {ok}, lỗi {bad}.')


if __name__ == '__main__':
    main()
