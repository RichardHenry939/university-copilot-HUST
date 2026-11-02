---
name: uc-notebooklm
description: UC_NotebookLM. Đưa tài liệu trong Uni-Documents (kho tài liệu của University Copilot) vào NotebookLM rồi hỏi đáp trên đó. Dùng khi người dùng muốn "đưa file này vào NotebookLM", "tạo notebook cho môn X", "học / ôn file này bằng NotebookLM", "file trong Inbox nằm ở đâu", hoặc chọn một file từ Google Drive mà UC đã sao lưu. Skill nói rõ thứ tự gọi connector UC và MCP NotebookLM để không bị lạc.
compatibility: Cần connector MCP "uc" (uc_inbox, uc_status) và MCP NotebookLM (notebook_list, notebook_create, source_add_drive_file, source_add, source_wait, source_list, chat_ask, studio_generate). Có connector Google Drive thì tiện cho bước chọn file, nhưng không bắt buộc.
---

# UC_NotebookLM

Mục tiêu: người dùng chọn một (hoặc vài) tài liệu → Claude biết **chính xác** file nằm ở đâu → đưa vào đúng notebook trong NotebookLM → hỏi đáp trên đúng nguồn đó. Làm theo đúng thứ tự dưới đây; không đoán đường dẫn, không đoán id.

## Bước 1. Xác định file

- Người dùng nói tên file, môn, hoặc dán link Google Drive.
- Gọi `uc_inbox`. Mỗi mục có: `name`, `folder` (thư mục trong Uni-Documents), `relPath`, `courseCode`, `driveLink`, `duong_dan` (đường dẫn đầy đủ trên máy của người dùng), `status`.
- Tìm mục khớp tên (không phân biệt hoa thường, bỏ dấu khi cần). Có nhiều mục trùng tên thì liệt kê ngắn (tên, thư mục, ngày nhận) và hỏi người dùng chọn cái nào.
- Bỏ qua mục có `status` là `moved` hoặc `duplicate` nếu có mục `placed` cùng tên ở thư mục mới.
- Nói lại cho người dùng: "File X nằm ở `<duong_dan>` (thư mục `<folder>`)". Đây là chỗ người dùng tự mở file trên máy.
- `uc_inbox` có `"online": false` thì nói rõ máy tính đang tắt và danh sách là bản lúc `lan_cuoi`; vẫn dùng được `driveLink` vì Drive không phụ thuộc máy.

## Bước 2. Chọn đường đưa file vào NotebookLM

1. **Có `driveLink`** (khác rỗng): lấy id file trong link (`/file/d/<id>/`). Đây là đường chính, chạy được cả từ Claude Chat lẫn điện thoại, kể cả khi máy tắt.
2. **Không có `driveLink`** (file chưa sao lưu lên Drive):
   - Nếu đang chạy trên chính máy của người dùng (Claude Code / Cowork) và MCP NotebookLM cho phép đọc thư mục đó: dùng `source_add` với `source_type: "file"`, `path: <duong_dan>`.
   - Nếu không (Claude Chat): nói thẳng là file chưa có bản trên Drive nên chưa đưa vào được; gợi ý người dùng mở UC trên máy để sao lưu, hoặc tự tải file lên NotebookLM.
- Không tự tải file từ nguồn khác, không đoán id Drive.

## Bước 3. Chọn hoặc tạo notebook

- Gọi `notebook_list` (lật trang bằng `offset` khi `has_more` là true).
- Tên notebook chuẩn:
  - File môn học: `<mã môn> <tên môn>`, ví dụ `MI1111 Giải tích I`, `IT1108 Nhập môn lập trình`.
  - File `courseCode` là `HANHCHINH` (thư mục Hành chính): notebook `Hành chính`. **Hành chính không phải môn học**; không gắn nó vào notebook của môn nào.
- Có notebook đúng tên thì dùng lại. Chưa có thì hỏi người dùng một câu xác nhận rồi mới `notebook_create(title=...)`.

## Bước 4. Thêm nguồn và chờ xong

- Đường Drive: `source_add_drive_file(notebook=<tên hoặc id>, document_id=<id Drive>, title=<name>, wait=true)`.
  - Nếu trả lỗi file là Google Doc / Slides / Sheet gốc: dùng `source_add(notebook=..., source_type="drive", document_id=<id>, mime_type="google-doc" | "google-slides" | "google-sheets")`.
- Đường file trên máy: `source_add(notebook=..., source_type="file", path=<duong_dan>, wait=true)`.
- Trước khi thêm, `source_list(notebook=..., detail="compact")` để tránh thêm trùng (cùng tiêu đề đã `ready` thì không thêm lại).
- Sau khi thêm: kết quả phải có nguồn trong `ready`. Nếu `timed_out` thì gọi `source_wait(notebook=..., source=<source_id>)`. Nếu `failed`: báo lỗi nguyên văn, không nói là đã xong.

## Bước 5. Dùng notebook

- Hỏi đáp: `chat_ask(notebook=..., question=..., source_ids=[<source_id vừa thêm>])` để chỉ hỏi trên đúng file đó; bỏ `source_ids` khi người dùng muốn hỏi trên cả notebook. Dẫn trích nguồn (`references`) khi trả lời.
- Tài liệu ôn tập theo yêu cầu: `studio_generate(notebook=..., artifact_type="report" | "flashcards" | "quiz" | "audio" | "mind-map", source_ids=[...])`, rồi theo dõi bằng `studio_status` tới khi `is_complete`.

## Bước 6. Báo lại (ngắn)

- File nào, nằm ở đâu trên máy (`duong_dan`), vào notebook nào, trạng thái nguồn (`ready` / lỗi).
- Phần chưa làm được và lý do (vd thiếu `driveLink`).

## Ranh giới

- UC và skill này **chỉ đọc** dữ liệu trường. Không nộp bài, không làm bài tập, bài kiểm tra hay việc có tính điểm thay người dùng; NotebookLM dùng để người dùng tự học. Câu hỏi là đề bài đang được chấm thì giải thích khái niệm và hướng làm, không đưa đáp án để nộp.
- Không nhập mật khẩu hay đăng nhập thay người dùng. NotebookLM chưa đăng nhập thì nhờ người dùng tự đăng nhập; chỉ mở một cửa sổ đăng nhập NotebookLM tại một thời điểm.
- Không dán nguyên đường dẫn connector UC (có khoá) vào câu trả lời.
