# Connector MCP cho University Copilot (1.00.33)

Cho phép Claude đọc tổng quan UC (lịch thi, hạn nộp, việc hôm nay) từ bất kỳ đâu, khi máy tính đang bật.
Chỉ đọc. Không có công cụ ghi.

## Thành phần

| File | Vai trò |
|---|---|
| `server.py` | Máy chủ MCP (JSON-RPC qua HTTP, `POST /mcp`), chỉ thư viện chuẩn. Gọi `/api/today` của UC trên `127.0.0.1:8320`. |
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

## Đưa ra ngoài để Claude (claude.ai, Claude Chat, điện thoại) gọi được

Đây là quyết định của chủ máy, vì nó đưa dữ liệu học tập ra internet. Có hai hướng:

1. **Đường hầm HTTPS** (ví dụ Cloudflare Tunnel) trỏ về `127.0.0.1:8790`, kèm `UC_MCP_TOKEN`. Đăng ký như connector tuỳ chỉnh trong claude.ai. Khi máy tắt, đường hầm không có đích và Claude chuyển sang Notion.
2. **Chỉ trong mạng riêng** (Tailscale): chỉ thiết bị của bạn gọi được. Phù hợp hơn về bảo mật, nhưng Claude.ai không gọi được trực tiếp.

Chưa bật đường hầm nào. Trước khi bật, cần chốt: ai được gọi, token lưu ở đâu, và có chấp nhận rủi ro dữ liệu học tập đi qua máy chủ trung gian không.

## Kiểm thử

`python -m pytest tests/test_uc_mcp.py` (9 test, dữ liệu giả, không gọi mạng). Đã thử thật: UC bật trả báo cáo đầy đủ; UC tắt trả thông báo "máy đang tắt".

## Giới hạn

- Khi UC đang đồng bộ, `/api/today` có thể chậm; server trả "UC đang bận" chứ không kết luận máy tắt.
- Skill chưa được chạy thử đánh giá có đối chứng (chưa đo tỉ lệ đúng khi kích hoạt). Đây là việc làm sau.
