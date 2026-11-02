# -*- coding: utf-8 -*-
"""(v1.00.52) Tải bù lên Drive các file đã nhập vào UC nhưng chưa có bản Drive (driveLink rỗng).
  python drive_backfill.py              -> chỉ liệt kê, không tải
  python drive_backfill.py --apply [N]  -> tải (tối đa N file nếu có N), vào đúng University/Uni-Documents/<thư mục như máy>, tên thật
Đi qua webhook n8n `copilot-drive-upload` (chỉ tải lên Drive, KHÔNG tạo dòng Notion mới). UC phải đang chạy: n8n tải file từ
http://host.docker.internal:<PORT>/files/<id> có chữ ký. Không qua ổ G:. Không xoá gì.
Giới hạn: dòng 📥 University Inbox cũ của các file này vẫn ghi "Drive: (sao lưu lỗi)" — script không sửa Notion.
"""
import os, sys


def main():
    import copilot_app as C, drive_tree as T
    st = C.load_state()
    todo = []
    for x in st.get('items', []):
        if x.get('notion') != 'done' or x.get('movedTo') or not x.get('relPath'): continue
        if not os.path.exists(x.get('path') or '') or C.drive_id(x.get('driveLink')): continue
        todo.append(x)
    print(f'{len(todo)} file chưa có bản Drive')
    for x in todo: print(' -', x['relPath'])
    if '--apply' not in sys.argv: return
    lim = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)
    ok = bad = 0
    for x in todo[:lim]:
        rel = x['relPath']
        try:
            fid = T.folder_for(C.n8n, os.path.dirname(rel))
            r = C.n8n('copilot-drive-upload', {'folderId': fid, 'fileName': os.path.basename(rel),
                      'downloadUrl': f"http://host.docker.internal:{C.PORT}/files/{x['id']}?k={C.sign(x['id'])}"}, timeout=300)
            r = r[0] if isinstance(r, list) else r
            if not r.get('driveLink'): raise RuntimeError(f'n8n không trả driveLink: {r}')
            C.update_item(x['id'], driveLink=r['driveLink'])
            try: C.backup_log(C.get_item(x['id']), True, r['driveLink'])
            except Exception as e: print('  backup_log:', e)
            ok += 1; print('  đã tải', rel)
        except Exception as e:
            bad += 1; print('  LỖI', rel, e)
    print(f'Đã tải {ok}, lỗi {bad}.')


if __name__ == '__main__':
    main()
