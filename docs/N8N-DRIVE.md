# Cổng Drive trong n8n (v1.00.51–v1.00.52)

Workflow n8n không nằm trong repo (có id credential, id Notion riêng). Trang này mô tả đủ để tự dựng lại hai cổng mà
`drive_tree.py`, `drive_tidy_plan.py` và `drive_backfill.py` cần. Thêm vào workflow chính "University — Copilot", dùng
cùng credential **Header Auth** của web app (header `X-Copilot-Key` = khoá trong cấu hình UC) và credential **Google Drive OAuth2**.

> Lưu ý: `build.py` sinh lại workflow từ code nhưng **chưa** có hai cổng này. Sinh lại workflow thì phải thêm lại theo trang này.

## Luật chung
- UC chỉ đụng Drive qua API. **Không** ghi / chuyển / xoá file qua ổ Drive for desktop (G:).
- Không có thao tác xoá: cổng chỉ cho GET / POST / PATCH.
- Cây trên Drive: `University/Uni-Documents/<thư mục như Uni-Documents trên máy>/<tên file thật>`.
  `drive_tree.root()` tìm thư mục cha "University" từ thư mục cũ (`OLD_FOLDER` trong `drive_tree.py`) — đổi id này theo Drive của bạn.

## 1. `copilot-drive-api` — gọi Drive v3 `files` (tìm / tạo thư mục, chuyển file giữ fileId)

| Node | Loại | Cấu hình |
|---|---|---|
| Drive API · Webhook | Webhook v2 | POST, path `copilot-drive-api`, Authentication: Header Auth, Respond: *When last node finishes* |
| Drive API · Kiểm | Code | Chặn mọi thứ ngoài `GET/POST/PATCH` và URL bắt đầu bằng `https://www.googleapis.com/drive/v3/files` (xem dưới) |
| Drive API · Gọi | HTTP Request v4 | Method `={{ $json.method }}`, URL `={{ $json.url }}`, Auth: Predefined → Google Drive OAuth2, Send body JSON `={{ JSON.stringify($json.body) }}`, Options → Response → *Never error* |

```js
// Drive API · Kiểm
const b = $json.body || {};
const m = String(b.method || 'GET').toUpperCase();
const u = String(b.url || '');
if (!['GET','POST','PATCH'].includes(m) || !u.startsWith('https://www.googleapis.com/drive/v3/files'))
  throw new Error('UC Drive API: không cho phép ' + m + ' ' + u);
return [{ json: { method: m, url: u, hasBody: m !== 'GET', body: b.body || {} } }];
```

Gửi: `{"method": "GET", "url": "https://www.googleapis.com/drive/v3/files?q=...", "body": {}}` → trả nguyên JSON của Drive.

## 2. `copilot-drive-upload` — tải một file từ máy lên đúng thư mục (không tạo dòng Notion)

Dùng để tải bù file đã nhập nhưng chưa có bản Drive (`python drive_backfill.py --apply`). UC phải đang chạy, vì n8n
tải file từ `http://host.docker.internal:<cổng UC>/files/<id>?k=<chữ ký>`.

| Node | Loại | Cấu hình |
|---|---|---|
| Tải lên Drive · Webhook | Webhook v2 | POST, path `copilot-drive-upload`, Header Auth, Respond: *When last node finishes* |
| Tải lên Drive · Kiểm | Code | Bắt buộc `folderId`, `fileName`, `downloadUrl` bắt đầu bằng `http://host.docker.internal:`; thiếu thì dừng (không đổ vào thư mục mặc định) |
| Tải lên Drive · Tải từ máy | HTTP Request v4 | GET `={{ $json.downloadUrl }}`, Response format *File*, field `data` |
| Tải lên Drive · Tải lên | Google Drive v3 | File → Upload, binary `data`, Name `={{ $('Tải lên Drive · Kiểm').first().json.fileName }}`, Drive *My Drive*, Folder (By ID) `={{ $('Tải lên Drive · Kiểm').first().json.folderId }}` |
| Tải lên Drive · Kết quả | Code | `return [{ json: { ok: !!$json.id, fileId: $json.id, driveLink: 'https://drive.google.com/file/d/' + $json.id + '/view' } }];` |

Gửi: `{"folderId": "<id từ drive_tree.folder_for>", "fileName": "Chap01.pdf", "downloadUrl": "http://host.docker.internal:8320/files/<id>?k=<ký>"}`.

## 3. Sửa node tải lên của luồng nhập file
Node "Nhập file · Sao lưu Drive" (upload): Folder = `={{ $('Nhập file · Web app').first().json.body.folderId || '<thư mục cũ>' }}`,
Name = `={{ $('Nhập file · Web app').first().json.body.fileName || $('Nhập file · Web app').first().json.body.driveName }}`.
`copilot_app.ingest` gửi sẵn `folderId` và `fileName`.

## Kiểm
- `python drive_backfill.py` (chỉ liệt kê) → `0 file chưa có bản Drive` sau khi chạy `--apply`.
- Thả một file vào một thư mục môn trong Uni-Documents → sau ~2 phút `driveLink` có trong `inbox_state.json`, mở link thấy đúng thư mục, đúng tên.
