# Hỏi đáp & lỗi thường gặp

> Theo code trên nhánh `main`; mỗi mục có `file:dòng` để đối chiếu. Chỗ chưa chắc ghi **⚠️ cần chủ repo xác nhận**.
> Cài đặt: [CAI-DAT.md](CAI-DAT.md) · Kiến trúc: [KIEN-TRUC.md](KIEN-TRUC.md).

**Mẹo chung:** khi có lỗi, đừng chạy bằng `open_copilot.ps1` (script này ẩn cửa sổ và ẩn lỗi: `pythonw.exe` + `$ErrorActionPreference = 'SilentlyContinue'`, `open_copilot.ps1:5`, `:9-10`). Hãy chạy thẳng trong PowerShell để đọc được thông báo:
```powershell
$env:PYTHONUTF8 = "1"     # in tiếng Việt ra console không bị lỗi mã hoá
py copilot_app.py
```
(Chính UC cũng đặt `PYTHONUTF8=1` khi chạy tiến trình con, vì ống dẫn mặc định cp1252 làm hỏng chữ Việt: `school_sync.py:244-246`.)

## Khởi động

**`FileNotFoundError: Thiếu config.json …`**
Chưa có `config.json`. Sao chép `config.example.json` thành `config.json` rồi điền (`uc_config.py:18-19`; [CAI-DAT §3](CAI-DAT.md#3-configjson)).

**`KeyError: 'n8n_workflows'`, tab giám sát Ghi bài giảng trống**
Trên `main`, `config.example.json` thiếu khối `n8n_workflows`, nhưng `lecture_monitor.py` đọc nó ngay khi được nạp (`lecture_monitor.py:18`, `uc_config.py:38-40`). Luồng giám sát chạy trong một thread riêng (`copilot_app.py:1421`) nên web app vẫn lên, chỉ phần giám sát chết. Thêm khối này theo [CAI-DAT §3](CAI-DAT.md#3-configjson).

**`FileNotFoundError: … .copilot-secret`**
Web app và kênh điện thoại đọc khoá ngay khi khởi động (`copilot_app.py:25`, `phone_link.py:17`). Tạo file theo [CAI-DAT §4](CAI-DAT.md#4-khoá-chung-copilot-secret-và-biến-môi-trường).

**Chạy `open_copilot.ps1` mà không có gì xảy ra**
- Script tìm `pythonw.exe` bằng `Get-Command` (`open_copilot.ps1:9`). Nếu Python cài mà `pythonw.exe` không nằm trong `PATH`, biến `$py` rỗng và script im lặng bỏ qua. Kiểm tra bằng `Get-Command pythonw.exe`.
- Chạy `py copilot_app.py` để xem lỗi thật (mẹo ở đầu trang).

**"n8n (cổng 5678) chưa chạy — bật Docker Desktop / n8n."**
In ra từ `open_copilot.ps1:13` khi cổng 5678 không mở. Bật Docker Desktop và container n8n.

**Giao diện báo `{"error": "cross-origin blocked"}` (403)**
Web app chỉ nhận yêu cầu ghi từ chính nó: Origin phải là `http://127.0.0.1:8320` hoặc `http://localhost:8320` (`copilot_app.py:932-934`, `:1196-1197`). Mở giao diện đúng một trong hai địa chỉ này.

**n8n gọi công cụ của UC bị `{"error": "forbidden"}` (403)**
Header `X-Copilot-Key` mà n8n gửi khác nội dung `.copilot-secret` (`copilot_app.py:1103-1104` và các endpoint tương tự tới `:1186`). Kiểm tra credential Header Auth "Copilot web app key" trong n8n ([CAI-DAT §5](CAI-DAT.md#5-docker--n8n)). Nếu bạn vừa đổi `.copilot-secret` thì phải cập nhật cả credential.

## Đăng nhập trường

**"Chỉ nhận email @sis.hust.edu.vn."**
`school_cred.py` chỉ nhận email đuôi `@sis.hust.edu.vn` (`school_cred.py:37-39`).

**UC không tự đăng nhập lại nữa / báo đang khoá**
Lần trước mật khẩu bị từ chối nên UC tạo `school/login.lock` để không thử sai liên tục (`school_cred.py:16`, `school_fetch.py:10`). Chạy lại `py school_cred.py` để nhập lại mật khẩu; lệnh này tự xoá khoá (`school_cred.py:47`). `py school_cred.py --status` cho biết đang khoá hay không (`school_cred.py:29`).

**Gặp xác minh 2 bước / captcha**
UC **dừng và báo**, không tự vượt (`school_fetch.py:10-11`, `:35-36`). Chạy `py school_fetch.py --login` để tự đăng nhập trong cửa sổ Chrome hồ sơ riêng, chọn "Duy trì đăng nhập" (`school_fetch.py:5`).

## Gemini, LM Studio

**Thư mới không thành sự kiện; console in `gemini lỗi …`**
Lỗi khi gọi Gemini (qua cổng :8350) thì UC trả thư về hàng chờ và **dừng lượt đó** để giữ đúng thứ tự thư; lượt 5 phút sau thử lại (`mail_events.py:231-234`). Kiểm tra:
- cổng Gemini :8350 có chạy không (⚠️ không có trong repo, xem [CAI-DAT §0](CAI-DAT.md#0-đọc-trước-repo-hiện-chưa-đủ-để-dựng-lại-toàn-bộ));
- biến `GEMINI_API_KEY` đã đặt cho User chưa (`mail_events.py:54-57`);
- lỗi 429 (hết quota theo phút): UC tự chờ 65 giây rồi 130 giây trước khi bỏ cuộc (`mail_events.py:60-65`).

**File trong tab Inbox đứng ở "Cần chọn thư mục", lý do "Model local chưa sẵn sàng … LM Studio đang tắt?"**
Agent xếp tài liệu không gọi được LM Studio ở `127.0.0.1:1234` (`copilot_app.py:333-335`), nên độ tin cậy = 0 và file chờ bạn chọn tay (`copilot_app.py:366`). Bật server LM Studio và nạp model `qwen3-14b` (`copilot_app.py:29`).

## Ghi bài giảng

**Cổng chép lời không khởi động (lỗi đường dẫn / ổ đĩa)**
Trên `main`, thư mục dữ liệu và đường dẫn model của cổng chép lời viết cứng theo máy của chủ repo (`speech-gate/speech_gate.py:25-30`), và thư mục được tạo ngay khi nạp (`:49-50`). Đặt `SPEECH_GATE_DIR` tới một thư mục có thật; đường dẫn model (`:27-30`) hiện phải sửa trong code. ⚠️ cần chủ repo xác nhận.

**`Start-LectureRecorder.ps1` báo không thấy file `.exe`**
Chưa build máy ghi. Chạy `dotnet build -c Release` trong `meeting-lecture-recorder/` (cần .NET 8 SDK); script chạy `bin\Release\net8.0-windows\LectureRecorderCompanion.exe` (`Start-LectureRecorder.ps1:4`).

**Chế độ Teams: máy ghi báo lỗi im lặng sau 30 giây**
Teams chưa phát ra cáp ảo. Trong Teams chọn loa = `CABLE Input` (VB-CABLE); máy ghi thu `CABLE Output` (`meeting-lecture-recorder/README.md:33-35`).

**Biên bản họp không phân biệt người nói, báo "chưa có token Hugging Face"**
Bước pyannote thoát mã 3 khi chưa đăng nhập Hugging Face (`speech-gate/speech_gate.py:238`, `speech-gate/diarize/diarize.py:5-6`). Chạy `hf auth login` trong venv của `diarize` và đồng ý điều khoản model.

## Thông báo, điện thoại

**Không nhận thông báo trên điện thoại**
- Thiếu `school/ntfy.json` thì UC chỉ hiện toast trên máy (`alerts.py:192-193`). Tạo file theo [CAI-DAT §9](CAI-DAT.md#9-thông-báo-điện-thoại-ntfy--tuỳ-chọn).
- Điện thoại phải đăng ký **đúng** topic trong file đó.

**Nhắc lúc nửa đêm**
Đây là thiết kế: "kệ giờ, phải đúng mốc"; mốc rơi vào nửa đêm vẫn gửi đúng giờ (`README.md:70`). Các mốc theo loại hạn nằm ở `deadlines.py:26-29`.

**Gập máy thì có lỡ nhắc không?**
- Lượt đồng bộ: lỡ khung 5 phút quá 120 giây thì **bỏ, không chạy bù** (`copilot_app.py:689-695`).
- Nhắc trên điện thoại: UC hẹn sẵn trên ntfy các lần nhắc trong 70 giờ tới, nên vẫn tới khi laptop ngủ (`phone_sched.py:1-11`, `:18`).

**Nút trên điện thoại báo "Lệnh hết hạn hoặc chữ ký sai"**
Lệnh có chữ ký chỉ sống 48 giờ và mỗi lệnh dùng một lần (`phone_link.py:18`, `:47-52`, `:140-145`). Nếu bạn vừa đổi `.copilot-secret` thì các nút cũ cũng hết hiệu lực.

## Tính năng khác

**Dịch PDF đứng ở "chờ RAM (còn … GB)"**
Dịch PDF chờ khi RAM trống dưới 2 GB và báo lỗi sau 30 phút (`pdf_translate.py:10`, `:54-55`). Đóng bớt ứng dụng.

**NotebookLM cứ bật cửa sổ đăng nhập Google**
Google bắt đăng nhập tay. Đăng nhập trong cửa sổ đang mở rồi đóng nó lại; muốn tạm dừng thì tạo file `notebooklm-keepalive/TAM-DUNG.txt` (`notebooklm-keepalive/login_loop.ps1:2-3`, `:12`). Nhật ký nằm ở `notebooklm-keepalive/keepalive.log` (`keepalive.ps1:5`).

**Luật học phí năm mới chưa cập nhật**
UC chỉ tự tìm *Quyết định mức học phí* từ tháng 8 tới tháng 11, mỗi ngày tối đa một lần (`tuition_rules.py:141-148`). Ngoài thời gian đó thì chạy tay: `py tuition_rules.py --force` (`tuition_rules.py:176-179`).

## Mã hoá tiếng Việt

- File `.ps1` có tiếng Việt trong repo đều lưu **UTF-8 có BOM** (3 byte đầu `EF BB BF`, vd `open_copilot.ps1`). Windows PowerShell 5.1 cần BOM để đọc đúng chữ Việt, nên khi sửa hãy giữ "UTF-8 with BOM".
- `.copilot-secret` nên là **ASCII thuần, không BOM**: web app và cổng chép lời đọc file này theo hai kiểu mã hoá khác nhau (`copilot_app.py:25` và `speech-gate/speech_gate.py:453`).

## Dữ liệu của tôi nằm ở đâu? Có lên Git không?

Không lên Git: `config.json`, `.copilot-secret`, `school/`, các file trạng thái… đều nằm trong `.gitignore` (`.gitignore:1-16`). Mật khẩu trường nằm trong Windows Credential Manager (`school_cred.py:4`). Chi tiết: [KIEN-TRUC §5](KIEN-TRUC.md#5-dữ-liệu-cục-bộ).
