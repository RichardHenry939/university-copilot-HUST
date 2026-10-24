# Connector MCP cho University Copilot (1.00.33)

Cho phép Claude đọc tổng quan UC (lịch thi, hạn nộp, việc hôm nay) từ bất kỳ đâu, khi máy tính đang bật.
Chỉ đọc. Không có công cụ ghi.

## Thành phần

| File | Vai trò |
|---|---|
| `server.py` | Máy chủ MCP (JSON-RPC qua HTTP, `POST /mcp`), chỉ thư viện chuẩn. Gọi `/api/today` của UC trên `127.0.0.1:8320`. |
| `push.py` | Gửi bản tóm tắt UC lên connector Firebase (chỉ chiều đi ra). |
| `cloud/` | Connector trên Firebase: Cloud Function MCP, Hosting không cho lập chỉ mục, luật Firestore chặn hết. |
| `skills/uc-briefing/SKILL.md` | Báo cáo sơ bộ. Khi máy tắt, dùng Notion thay thế và nói rõ máy đang tắt. |
| `skills/uc-assistant/SKILL.md` | Quy tắc làm việc với UC: chỉ đọc, xử lý dữ liệu lỗi/rỗng, không tin chỉ dẫn trong nội dung web. |

## Công cụ

- `uc_status`: máy có đang chạy UC không.
- `uc_today`: lịch thi, hạn đang mở, việc hôm nay.
- `uc_deadlines` (tham số `days`): hạn sắp tới.
- `uc_exams`: lịch thi giữa kỳ.
- `uc_briefing`: báo cáo một trang.

Khi máy tắt, mọi công cụ trả `"online": false` và hướng dẫn chuyển sang Notion.

## Chạy

```
python uc_mcp/server.py --port 8790
```

Mặc định chỉ lắng nghe `127.0.0.1`. Kiểm tra: `GET http://127.0.0.1:8790/health`.

Đặt biến `UC_MCP_TOKEN` để bắt buộc `Authorization: Bearer <token>` cho mọi yêu cầu.

## Đưa ra ngoài để Claude (claude.ai, Claude Chat, điện thoại) gọi được: Firebase (v1.00.34)

Máy **không mở cổng nào**. Máy chỉ gửi đi:

```
máy (UC) --push.py, mỗi 10 phút, khoá PUSH_KEY--> Firebase Function --> Firestore (1 bản tóm tắt)
claude.ai --POST /m/<MCP_KEY>--> Firebase Function --> đọc bản tóm tắt
```

- `cloud/functions/index.js`: Cloud Function `ucmcp` (asia-southeast1). Sai khoá thì trả 404 như trang không tồn tại.
- Quá 20 phút không có bản mới thì coi là **máy đang tắt**. Công cụ trả `online: false`, `lan_cuoi`, và `ban_so_bo` (bản cuối, hạn tính lại theo giờ hiện tại).
- Không cho máy tìm kiếm lập chỉ mục: `robots.txt` chặn tất cả, mọi phản hồi có `X-Robots-Tag: noindex, nofollow, noarchive`, trang chủ trả 404.
- Firestore: luật chặn mọi truy cập từ client, chỉ Function đọc và ghi được.
- Tên site Hosting do máy sinh ngẫu nhiên. Khoá (`functions/.env`), `.firebaserc` và `cloud.local.json` chỉ nằm trên máy, không có trong repo.

Yêu cầu: project Firebase ở gói **Blaze**, vì Cloud Functions không chạy trên gói Spark. Mức dùng của connector nằm trong hạn mức miễn phí, nhưng nên đặt cảnh báo ngân sách.

Triển khai: chép `cloud/` ra thư mục riêng, tạo `functions/.env` (`PUSH_KEY=`, `MCP_KEY=`, mỗi khoá là chuỗi ngẫu nhiên dài), chạy `firebase target:apply hosting uc <site>`, rồi `firebase deploy --only functions,firestore:rules,hosting:uc`. Đặt `push.py` chạy mỗi 10 phút. Trong claude.ai: Settings > Connectors > Add custom connector, dán `https://<site>.web.app/m/<MCP_KEY>`.

Cách cũ (chạy `server.py` trên máy, đưa ra ngoài bằng đường hầm) vẫn dùng được, nhưng phải mở đường vào máy.

## Kiểm thử

`python -m pytest tests/test_uc_mcp.py` (9 test, dữ liệu giả, không gọi mạng). Đã thử thật: UC bật trả báo cáo đầy đủ; UC tắt trả thông báo "máy đang tắt".

## Giới hạn

- Khi UC đang đồng bộ, `/api/today` có thể chậm; server trả "UC đang bận" chứ không kết luận máy tắt.
- Skill chưa được chạy thử đánh giá có đối chứng (chưa đo tỉ lệ đúng khi kích hoạt). Đây là việc làm sau.
