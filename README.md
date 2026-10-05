# University Copilot (UC)

> **EN summary:** a personal "copilot" for a HUST student. It reads six official university systems (Outlook mail, Microsoft Teams, eHUST/qldt, iCTSV, the SoICT MOOC and FAMI) in **read-only** mode. It merges everything into one Notion workspace and pushes **time-precise reminders** to the laptop and the phone. AI (Gemini + a local LLM) extracts events from emails and classifies deadlines; n8n orchestrates the Notion side. Built with an AI coding agent: I designed the problem, the rules and the architecture, and tested it on my own semester.

---

## Vấn đề

Là sinh viên Bách khoa, thông tin học tập của tôi nằm rải ở **6 hệ thống khác nhau**:

| Hệ thống | Có gì | Vấn đề |
|---|---|---|
| Outlook (mail trường) | thông báo thi, đổi lịch, sự kiện | thư đính chính chồng lên thư cũ, rất dễ sót |
| Microsoft Teams | bài tập, đổi phòng, tài liệu | phải tự vào từng nhóm lớp để đọc, rồi tải file về tay |
| eHUST (qldt) | thời khoá biểu, điểm | không chủ động nhắc |
| iCTSV | điểm rèn luyện, hoạt động ngoại khoá | tách rời khỏi lịch học |
| MOOC SoICT (daotao.ai) | bài tập có hạn và điểm | không xuất hiện ở đâu khác |
| FAMI số hoá | bài kiểm tra theo chương của các học phần MI | **không được nhắc trên Teams hay bất kỳ đâu** |

App của trường chỉ gửi một thông báo lúc 6h sáng cho cả ngày. Muốn không trễ hạn, tôi phải tự mở cả 6 nơi mỗi ngày.

## Giải pháp

UC chạy trên laptop, cứ 20 phút đọc lại các nguồn (**chỉ đọc**, không bao giờ gửi, xoá hay nộp bài thay tôi). Sau đó nó:

- **Gộp** lịch, hạn, sự kiện vào một workspace Notion và một giao diện web cục bộ.
- **Đọc mail bằng AI**: một sự kiện có nhiều chặng (đăng ký, thi, phúc khảo…). Thư đính chính hiển thị dạng *Trước → Nay*.
- **Nhắc đúng mốc theo mức quan trọng của hạn**, do AI phân loại:
  - *Tự luyện*: 72 / 48 / 36 / 24 giờ trước hạn.
  - *Tự luyện cốt lõi*: thêm 7h, 5h, 3h, 1h, 30', 20', 10'.
  - *Ảnh hưởng điểm môn học*: thêm 10h, 5h, 3h, 1h, 30', 20', 10', 5', 2', 1'.
  - Tiết học: 30 và 15 phút trước, đã tính cả đổi phòng lấy từ Teams.
- **Vẫn nhắc khi laptop gập máy**: các lần nhắc được hẹn sẵn trên máy chủ [ntfy](https://ntfy.sh) tới 70 giờ trước, và tự sửa hoặc huỷ khi lịch thay đổi.
- **Đồng bộ tài liệu hai chiều**: Teams ⇄ thư mục tài liệu trên máy ⇄ Notion. Tài liệu được xếp đúng môn, chống trùng bằng SHA-256.
- **Quét trùng**: phát hiện hạn hoặc lịch bị nhập hai lần. Hai mục khác mã môn thì không bao giờ bị coi là trùng.
- **Có trang riêng trên điện thoại** (Notion) và nhận lệnh xem nhanh qua ntfy.

[![Bản đồ hệ thống](docs/Map.png)](docs/Map.svg)

*Bấm vào ảnh để mở bản SVG nét đầy đủ (rộng 11.800 px, phóng to thoải mái).*

## Các quyết định thiết kế

Đây là phần tôi dành nhiều thời gian nhất:

1. **Luật tối cao: dữ liệu của trường thắng.** Mỗi khi dữ liệu trong Notion khác dữ liệu của trường:
   - *thiếu* → thêm vào;
   - *mâu thuẫn* (ví dụ hạn bị dời) → sửa theo trường, kể cả mục đã qua, và báo "Thay đổi";
   - *thừa* (việc tôi tự đặt) → giữ nguyên.
2. **Chỉ đọc nguồn của trường.** Không đổi trạng thái đã đọc của mail, không gửi hay xoá thư, không bao giờ bấm "Làm bài" trên FAMI hay MOOC.
3. **Không ghi ngầm.** Mọi thao tác ghi từ giao diện (Notion, xoá trùng…) đều phải qua bước xác nhận.
4. **Bài đã hết hạn không biến thành hạn mới.** Chúng được ghi vào lịch sử *Academic Tasks* với kết quả *Đã làm / Bỏ lỡ*, nên không nhắc vô ích.
5. **Điện thoại chỉ để xem và xác nhận đã biết.** Nút "Hoàn tất" và "Tắt nhắc" chỉ có trên máy tính, để không lỡ tay tắt một hạn thật.
6. **Mật khẩu không nằm trong code.** Tài khoản trường cất trong Windows Credential Manager. Tự đăng nhập chỉ điền trên trang đăng nhập Microsoft hoặc trang của trường, tối đa một lần mỗi lượt; gặp xác minh 2 bước hoặc captcha thì dừng và báo người dùng.

## Công nghệ

- **Python** (thư viện chuẩn + Playwright): khoảng 8.500 dòng, chia thành các module theo từng nguồn: `school_mail.py`, `teams_fetch.py`, `mooc.py`, `fami.py`, `mail_events.py`, `deadlines.py`, `alerts.py`, `phone_sched.py`…
- **n8n** (Docker): các luồng tự động phía Notion. Workflow được sinh bằng code (`build.py`), không kéo thả tay. Sơ đồ khối: [Map-n8n.svg](docs/Map-n8n.svg) ([ảnh PNG](docs/Map-n8n.png)).
- **Máy ghi bài giảng** (`lecture-recorder/`, C# .NET 8 + NAudio): ghi giảng đường bằng micro, học online bằng âm thanh máy, hoặc riêng cuộc họp Teams qua cáp ảo VB-CABLE → n8n → chép lời trên máy (PhoWhisper, NPU) → Gemini → ghi chú bài giảng trong Notion.
- **Notion API**: nơi lưu dữ liệu.
- **Gemini API** (flash-lite) để đọc mail và phân loại hạn. **LM Studio** (qwen3-8b, chạy local) để xếp tài liệu.
- **ntfy**: thông báo đẩy và lời nhắc hẹn giờ lên điện thoại.
- Giao diện: một trang HTML/JS do `copilot_app.py` phục vụ tại `127.0.0.1:8320`.

## Cách tôi xây dựng dự án

Tôi xây UC **cùng một AI coding agent (Claude Code)**. Phần việc của tôi:

- đặt bài toán từ chính khó khăn của mình;
- quyết định luật và kiến trúc: luật tối cao, ba mức hạn, chỉ đọc nguồn trường, điện thoại không có nút tắt;
- phát hiện lỗi khi dùng thật và yêu cầu sửa, ví dụ:
  - AI lấy nhầm giờ nhận thư làm giờ sự kiện;
  - hai bài "vá hổng chương I" của hai môn khác nhau bị coi là trùng;
  - bài ngầm trên FAMI bị bỏ sót.

Từng thay đổi được kiểm thử trên học kỳ thật của tôi.

## Chạy thử

> Đây là công cụ cá nhân, gắn với tài khoản sinh viên HUST và workspace Notion của tôi. Repo này để tham khảo cách làm, chưa phải sản phẩm cài một lần là chạy.

1. Cài Python 3.12+ và `pip install playwright keyring`, rồi `playwright install chrome`.
2. Sao chép `config.example.json` thành `config.json`, điền ID database Notion, ID credential n8n và các đường dẫn.
3. Đặt biến môi trường `GEMINI_API_KEY` và `N8N_API_KEY`. Tạo file `.copilot-secret` chứa một chuỗi ngẫu nhiên, dùng để ký các liên kết nội bộ.
4. Cất tài khoản trường: `python school_cred.py`. Mật khẩu gõ vào ô ẩn và được lưu trong Windows Credential Manager.
5. Sinh workflow n8n: `python build.py`. Mở giao diện: `open_copilot.ps1`.

## Quyền riêng tư

Repo **không** chứa dữ liệu cá nhân nào: mail, điểm, lịch, ID Notion, kênh ntfy, khoá API hay mật khẩu đều không có. Mọi giá trị riêng nằm trong `config.json`, biến môi trường hoặc Credential Manager, và đều đã nằm trong `.gitignore`.

Đây là công cụ cá nhân, **không liên kết hay được bảo trợ bởi Đại học Bách khoa Hà Nội**. Công cụ chỉ đọc dữ liệu mà chính tài khoản sinh viên của người dùng được phép xem.
