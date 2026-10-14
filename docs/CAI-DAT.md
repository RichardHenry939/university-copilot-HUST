# Cài đặt University Copilot trên Windows

> Hướng dẫn cho **một sinh viên HUST khác** muốn tự dựng hệ thống trên máy mình.
> Viết theo **code đang có trên nhánh `main` (v1.00.23)**; mỗi bước có `file:dòng` để đối chiếu. Chỗ code không đủ để khẳng định ghi **⚠️ cần chủ repo xác nhận**.
> Xem thêm: [KIEN-TRUC.md](KIEN-TRUC.md) (dịch vụ, cổng, luồng dữ liệu) · [HOI-DAP.md](HOI-DAP.md) (lỗi thường gặp).

## 0. Đọc trước: repo hiện CHƯA đủ để dựng lại toàn bộ

README đã nói rõ đây là công cụ cá nhân, "chưa phải sản phẩm cài một lần là chạy" (`README.md:173`). Khi đối chiếu code, các phần sau **không có trong repo**, nên bạn cần chủ repo cung cấp thêm:

| Thiếu | Vì sao cần | Bằng chứng |
|---|---|---|
| **File mẫu workflow n8n** (`<n8n_template_dir>/<ID>.json`) | `python build.py` ghép workflow hợp nhất từ 10 workflow cũ, đọc từng file `<ID>.json` trong thư mục `paths.n8n_template_dir` (ID lấy từ `n8n_legacy_workflows` A1…S6 trong `config.json`). Thiếu file thì `build.py` dừng | `build.py:17`, `build.py:63-74`, `build.py:98-101`, `build.py:1358-1360` |
| **Workflow "Lecture Capture"** | Không có script nào trong repo tạo workflow nhận audio (`lecture-capture-upload`); `lecture_build.py` chỉ **sửa lại** workflow "Lecture Analysis" đã có sẵn (đọc nó bằng `GET /workflows/<id>`) | `meeting-lecture-recorder/Program.cs:75`, `lecture_build.py:19`, `lecture_build.py:362-375` |
| **Cấu trúc 38 database Notion** (tên cột, kiểu cột) | Code đọc/ghi theo tên cột cụ thể (vd `Entry Kind`, `Due`, `Loại hạn`, `Sync Key`…) nhưng repo không có bản xuất / mẫu workspace | `config.example.json:2-41`, vd `deadlines.py:70-75` |
| **Cổng Gemini `gemini_gate.py` (:8350)** | Mọi lời gọi Gemini của UC (đọc thư, phân loại hạn, phân tích bài giảng) đi qua cổng này | `mail_events.py:18`, `lecture_build.py:27`, `open_copilot.ps1:3` |

⚠️ **cần chủ repo xác nhận**: cách lấy 4 thứ trên (đưa vào repo, hay mô tả cách tạo).
Những phần **chạy được ngay** chỉ với repo: web app `copilot_app.py`, đọc dữ liệu trường bằng Chrome (`school_fetch.py`), cổng chép lời, máy ghi, add-on máy yếu.

## 1. Chuẩn bị

| Cần | Ghi chú | Bằng chứng |
|---|---|---|
| Windows 10/11 | Code dùng Windows Credential Manager, toast Windows, `winreg`, PowerShell | `school_cred.py:4`, `alerts.py:173-186`, `mail_events.py:56-57` |
| Python **3.12+** | | `README.md:177` |
| Google Chrome (bản cài thường) | Playwright mở **Chrome thật** (`channel="chrome"`); "Làm bài" gọi `chrome.exe` ở thư mục cài mặc định | `school_fetch.py:42`, `work_open.py:23` |
| Docker Desktop | Chạy n8n (và SearXNG nếu dùng) | `README.md:84`, `open_copilot.ps1:13` |
| Tài khoản `@sis.hust.edu.vn` | Chỉ nhận email đuôi này | `school_cred.py:37-39` |
| Tài khoản Notion, Google (Gemini API key, Google Drive) | n8n giữ credential Notion / Gemini / Drive | `n8napi.py:22-26` |

## 2. Lấy mã nguồn và cài thư viện Python

```powershell
git clone https://github.com/RichardHenry939/university-copilot-HUST.git
cd university-copilot-HUST
py -m pip install playwright keyring
py -m playwright install chrome
```
- Phần lõi chỉ cần `playwright` + `keyring` (`README.md:177`); `copilot_app.py` chỉ dùng thư viện chuẩn (`copilot_app.py:14`).
- Các thư viện nặng (`numpy`, `faster-whisper`, `openvino`, `torch`, `pyannote`…) **chỉ** dành cho cổng chép lời (bước 9).

## 3. `config.json`

```powershell
Copy-Item config.example.json config.json
```
Mở `config.json` và điền (`uc_config.py:24-47` đọc đúng các khối này):

| Khối | Điền gì | Ai đọc |
|---|---|---|
| `notion` (38 khoá) | ID database / trang Notion tương ứng | `uc_config.py:24-26` |
| `n8n_credentials` | ID của 5 credential trong n8n (bước 5) | `uc_config.py:33-35`, `n8napi.py:22-26` |
| `paths.uni_documents` | Thư mục tài liệu học tập của bạn | `copilot_app.py:22`, `teams_files.py:16`, `nlm_bridge.py:11` |
| `paths.chrome_profile` | Thư mục **trống** cho hồ sơ Chrome riêng đọc dữ liệu trường | `school_fetch.py:20` |
| `paths.chrome_open_profile` | Thư mục **trống** cho cửa sổ Chrome "Làm bài" | `work_open.py:22` |
| `n8n_workflows` | ID 3 workflow đang chạy: `copilot` (University — Copilot), `lecture_capture`, `lecture_analysis` | `uc_config.py:38-40`, `lecture_monitor.py:18`, `lecture_build.py:19` |
| `n8n_legacy_workflows` | ID các workflow cũ: `A1`…`S6` là tên file mẫu mà `build.py` ghép lại (xem §0); các khoá còn lại (`lecture_recorder_v1`, `archive_*`) chỉ dùng cho sơ đồ tài liệu. Còn để `<…>` thì coi như chưa điền | `uc_config.py:43-47`, `build.py:65-70`, `build.py:98-101` |
| `paths.n8n_template_dir` | Thư mục chứa các file mẫu workflow (xem §0) | `build.py:17` |

`lecture_monitor.py` đọc `n8n_workflows` ngay khi được nạp (`lecture_monitor.py:18`). Thiếu khối này thì phần giám sát Ghi bài giảng lỗi `KeyError` (xem [HOI-DAP](HOI-DAP.md#khởi-động)).

## 4. Khoá chung `.copilot-secret` và biến môi trường

1. **`.copilot-secret`**: một chuỗi ngẫu nhiên ở thư mục gốc repo. Đây là khoá dùng để ký link nội bộ, làm header `X-Copilot-Key` khi gọi n8n và ký lệnh từ điện thoại (`copilot_app.py:25`, `:131`, `:160`; `phone_link.py:17`). Hãy tạo file **ASCII thuần, không BOM**:
   ```powershell
   [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N') | Set-Content -NoNewline -Encoding ascii .copilot-secret
   ```
   (Web app đọc file bằng mã hoá mặc định của Windows, còn cổng chép lời đọc bằng UTF-8: `copilot_app.py:25` và `speech-gate/speech_gate.py:457`. Dùng ASCII thì hai bên luôn đọc ra cùng một khoá.)
2. **Biến môi trường User** (UC đọc cả từ registry nếu tiến trình mở trước khi đặt biến, `mail_events.py:54-57`, `n8napi.py:5-8`):
   ```powershell
   [Environment]::SetEnvironmentVariable('GEMINI_API_KEY', '<khoá Gemini của bạn>', 'User')
   [Environment]::SetEnvironmentVariable('N8N_API_KEY',    '<API key của n8n>',    'User')
   ```
   `GEMINI_API_KEY` được gửi qua cổng Gemini :8350 (`mail_events.py:58-59`). `N8N_API_KEY` dùng để gọi API quản trị của n8n (`n8napi.py:12-15`).

## 5. Docker + n8n

1. Cài Docker Desktop, chạy n8n ở cổng **5678** (UC gọi `http://127.0.0.1:5678/webhook/...`, `copilot_app.py:26`). Chủ repo dùng **n8n 2.36.7** (chủ repo xác nhận). Lệnh gợi ý, viết theo tài liệu chính thức của n8n:
   ```powershell
   docker run -d --name n8n --restart unless-stopped -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n:2.36.7
   ```
   Giữ tên container là `n8n`, vì add-on network-guard gọi `docker pause n8n` (§12). ⚠️ cần chủ repo xác nhận: các biến môi trường n8n đang dùng. Workflow tự đặt múi giờ `Asia/Ho_Chi_Minh` (`build.py:21`, `build.py:1378`).
2. n8n trong Docker gọi ngược về máy qua `host.docker.internal` (`build.py:443-491`, `lecture_build.py:25-27`). Docker Desktop có sẵn tên này.
3. Trong n8n: **Settings → n8n API** tạo API key, rồi đặt vào `N8N_API_KEY` (bước 4).
4. Tạo **5 credential** rồi chép ID của từng cái vào `config.json → n8n_credentials` (`n8napi.py:22-26`):

| Khoá trong `config.json` | Loại credential n8n | Tên code dùng | Ghi chú |
|---|---|---|---|
| `notionApi` | Notion API | `Notion account` | Integration Notion phải được **share** vào các database |
| `googlePalmApi` | Google Gemini (PaLM) API | `Google Gemini(PaLM) Api account` | |
| `httpHeaderAuth` | Header Auth | `Copilot web app key` | Suy ra từ code: Name = `X-Copilot-Key`, Value = nội dung `.copilot-secret` (`copilot_app.py:160`, `speech-gate/speech_gate.py:461`, `build.py:361-362`) |
| `googleDriveOAuth2Api` | Google Drive OAuth2 | `Google Drive account` | |
| `openAiApi` | OpenAI API trỏ tới LM Studio | `LM Studio (local)` | ⚠️ cần chủ repo xác nhận Base URL (dự đoán `http://host.docker.internal:1234/v1`, xem `build.py:514`) |

5. Sinh workflow hợp nhất (cần các file mẫu ở §0): `py build.py`, rồi `py build.py --activate` để bật (`build.py:8-9`, `:1381-1399`). Lệnh in ra ID workflow và lưu ID vào `state.json` (`build.py:1395-1397`).

## 6. LM Studio

- Bật **server** của LM Studio ở cổng **1234** (`copilot_app.py:27`).
- Model mà code gọi theo tên (chủ repo xác nhận model xếp tài liệu là `qwen3-14b`): **`qwen3-14b`** (xếp tài liệu `copilot_app.py:29`, nén bản chép lời `speech-gate/speech_gate.py:38`, dịch PDF `pdf_translate.py:61`, não dự phòng của chat `build.py:414`) và **`qwen3-8b`** (dự phòng khi thiếu bộ nhớ `speech-gate/speech_gate.py:177`).
- Dịch PDF còn gọi lệnh `lms` (CLI của LM Studio) để kiểm tra model đang nạp; đổi đường dẫn bằng biến `LMS_EXE` (`pdf_translate.py:17`, `:33`).

## 7. Notion

1. Tạo integration Notion, nối nó vào n8n (credential `notionApi` ở bước 5).
2. Tạo các database tương ứng với **38 khoá** trong `config.example.json:2-41` và share chúng cho integration. ⚠️ cần chủ repo xác nhận: cấu trúc cột của từng database (xem §0).
3. Lấy ID database (32 ký tự hex trong URL) và điền vào `config.json → notion`.

## 8. Tài khoản trường và lần đăng nhập đầu

```powershell
py school_cred.py            # nhập email @sis.hust.edu.vn + mật khẩu (ô ẩn) -> Windows Credential Manager
py school_cred.py --status   # kiểm tra đã cất chưa (không in mật khẩu)
py school_fetch.py --login   # mở Chrome hồ sơ riêng để BẠN tự đăng nhập Office 365 một lần
```
- Mật khẩu cất trong Credential Manager, mục `uc-school-sync`; không ghi ra file (`school_cred.py:2-9`, `:15`, `:45-46`).
- Sau đó mỗi lượt đọc, nếu hết phiên thì UC **tự đăng nhập lại**, chỉ điền trên trang Microsoft / ADFS của trường, tối đa 1 lần mỗi lượt. Gặp xác minh 2 bước / captcha thì dừng và báo bạn (`school_fetch.py:8-11`).

## 9. Thông báo điện thoại (ntfy) — tuỳ chọn

1. Cài app **ntfy** trên điện thoại, đăng ký một topic **khó đoán** (topic trên `ntfy.sh` là công khai: ai biết tên đều đọc được).
2. Tạo `school/ntfy.json`:
   ```json
   { "topic": "<tên-topic-khó-đoán>" }
   ```
   UC đọc `topic` (`alerts.py:192-194`, `phone_sched.py:21`) và tự sinh thêm `cmd_topic` cho chiều điện thoại → UC (`phone_link.py:21-25`).
3. Không có file này thì UC chỉ gửi toast trên máy (`alerts.py:192-193`).

## 10. Chạy

```powershell
powershell -ExecutionPolicy Bypass -File .\open_copilot.ps1
```
- Script bật `copilot_app.py` bằng `pythonw.exe` (ẩn cửa sổ) nếu cổng 8320 chưa mở, nhắc nếu n8n (5678) chưa chạy, rồi mở `http://127.0.0.1:8320/` (`open_copilot.ps1:8-14`).
- Tự chạy khi đăng nhập Windows: tạo tác vụ Task Scheduler gọi `open_copilot.ps1 -NoBrowser` (`open_copilot.ps1:2`).
- Lần đầu nên chạy `py copilot_app.py` trong cửa sổ PowerShell để **thấy lỗi** nếu có (script trên ẩn lỗi vì `$ErrorActionPreference = 'SilentlyContinue'`, `open_copilot.ps1:5`).

## 11. Thành phần tuỳ chọn

### 11.1. Cổng chép lời (`speech-gate/`, cổng 8340)
- Chạy: `py speech-gate\speech_gate.py` (`speech-gate/speech_gate.py:564-571`).
- Đường dẫn đọc từ biến môi trường, có mặc định (`speech-gate/speech_gate.py:26-34`):
  - `UC_DATA_DIR` (mặc định `%USERPROFILE%\uc-data`) và `UC_AI_DIR` (mặc định `%USERPROFILE%\AI`) là hai thư mục gốc (`:27-28`);
  - thư mục dữ liệu cổng: `SPEECH_GATE_DIR`, mặc định `<UC_DATA_DIR>\SpeechGate` (`:29`);
  - model PhoWhisper CPU: `PHOWHISPER_CT2_DIR`, mặc định `<UC_AI_DIR>\models\phowhisper-large-ct2` (`:31`);
  - model NPU: `PHOWHISPER_OV_DIR`, mặc định `<UC_AI_DIR>\models\phowhisper-large-ov-int8` (`:33`); cache OpenVINO: `OPENVINO_CACHE_DIR` (`:34`).
- Chép lời mặc định chạy trên **NPU** (OpenVINO INT8), đặt `SPEECH_GATE_STT=cpu` để dùng CPU (`speech-gate/speech_gate.py:32`, `:35`). Chuyển model sang OpenVINO bằng `export_ov.py` + `quantize_ov.py` (`speech-gate/README.md:31-33`).
- Thư viện: `numpy`, `faster-whisper`, `openvino-genai`, `Pillow`, `av` (theo `import` trong `speech-gate/speech_gate.py`, `speech-gate/audio_io.py`). ⚠️ cần chủ repo xác nhận danh sách phiên bản.
- Phân biệt người nói (chế độ Họp): chạy `diarize/diarize.py` bằng một venv riêng, mặc định `speech-gate/diarize/.venv/Scripts/python.exe`, đổi bằng `DIARIZE_PY` (`speech-gate/speech_gate.py:219`). Cần token Hugging Face (`hf auth login`) và đồng ý điều khoản model pyannote (`speech-gate/diarize/diarize.py:5-6`).

### 11.2. Máy ghi bài giảng / cuộc họp (`meeting-lecture-recorder/`, cổng 5681)
- Cần **.NET 8 SDK** (`LectureRecorderCompanion.csproj:3`, gói `NAudio 2.2.1` `:14`). Build:
  ```powershell
  cd meeting-lecture-recorder
  dotnet build -c Release
  ```
  `Start-LectureRecorder.ps1` chạy file `bin\Release\net8.0-windows\LectureRecorderCompanion.exe` (`Start-LectureRecorder.ps1:4`, `:14-16`).
- Thư mục lưu bản ghi: `LRC_RECORDING_DIR`; nếu không đặt thì dùng `<UC_DATA_DIR>\LectureRecorder`, với `UC_DATA_DIR` mặc định là `%USERPROFILE%\uc-data` (`Program.cs:73`).
- Chế độ Teams cần **VB-CABLE**: trong Teams chọn loa = `CABLE Input`, máy ghi thu `CABLE Output` (`meeting-lecture-recorder/README.md:31-35`).

### 11.3. Các dịch vụ ngoài khác
| Tính năng | Cần | Bằng chứng |
|---|---|---|
| Đọc chữ PDF/Office (xếp tài liệu, học phí, chi tiết học phần) | Apache Tika ở cổng 9998, chạy bằng Docker image `apache/tika:4.0.0-1-full` (chủ repo xác nhận), vd `docker run -d --name tika --restart unless-stopped -p 127.0.0.1:9998:9998 apache/tika:4.0.0-1-full` | `copilot_app.py:28`, `tuition_rules.py:22` |
| Chat tìm web, Research Hub | SearXNG ở `127.0.0.1:8888`, chạy bằng Docker (container "university-searxng", chủ repo xác nhận) | `web_tools.py:13`, `research.py:97` |
| Dịch PDF | `pdf2zh` cài bằng `uv tool` (`%APPDATA%\uv\tools\pdf2zh\...`) | `pdf_translate.py:15` |
| Gửi tài liệu sang NotebookLM | `notebooklm-py` cài bằng `uv tool`; giữ phiên bằng `notebooklm-keepalive/refresh.vbs`, tạo tác vụ Task Scheduler chạy **mỗi 20 phút và lúc đăng nhập Windows** (chủ repo xác nhận) | `nlm_bridge.py:12`, `notebooklm-keepalive/refresh.vbs:4` |
| Hội đồng AI | AgentChattr (:8300) + `council_relay.py` (:8310). Cả hai nằm ngoài repo (chủ repo xác nhận); tuỳ chọn | `ui/index.html:555`, `build.py:777` |

## 12. Add-on "máy yếu" (`addons/low-end-priority`)

Chỉ cài khi máy yếu / tầm trung (học online + ghi bài + AI cùng máy). Máy mạnh thì **không cài** (`addons/low-end-priority/README.md:3-4`). Các bước (`addons/low-end-priority/README.md:41-45`):
1. Giải nén `addons/low-end-priority.zip`.
2. Chép `audio_priority.py` vào thư mục UC (cạnh `copilot_app.py`).
3. Chép `audio_priority.example.json` thành `school/audio_priority.json` (sửa danh sách tiến trình nếu muốn).
4. Tạo file rỗng `speech-gate/low_end.flag`.
5. Khởi động lại UC và cổng chép lời.

Cách hoạt động: UC thấy `audio_priority.py` thì cứ 5 giây đặt 4 bậc ưu tiên CPU: học = HIGH, web học tập = NORMAL, homelab = BELOW_NORMAL; riêng AI = IDLE khi máy ghi đang ghi (và thêm 2 phút sau khi dừng), lúc khác = BELOW_NORMAL (`copilot_app.py:881-889`, `addons/low-end-priority/audio_priority.py:15-18`, `:24-27`, `:75`, `:80-85`). Cổng chép lời thấy `low_end.flag` thì hoãn bước nén trong lúc máy ghi đang ghi (`speech-gate/speech_gate.py:180-199`). Gỡ: xoá hai file đó rồi khởi động lại (`addons/low-end-priority/README.md:49-52`).

### Add-on "mạng chập chờn" (`addons/network-guard`)

Dành cho máy học bằng wifi hay rớt (`addons/network-guard/README.md:3`). Không cài thì UC chạy như cũ (`copilot_app.py:739-742`).
- `netguard.py` chạy mỗi phút bằng Task Scheduler, kiểm mạng bằng `https://www.google.com/generate_204` (`addons/network-guard/netguard.py:33-36`; lệnh tạo task: `addons/network-guard/README.md:20-29`).
- Mất mạng 3 phút liên tiếp → đặt cờ `OFFLINE.flag` cạnh `copilot_app.py` và `docker pause n8n` (`addons/network-guard/netguard.py:21`, `:25`, `:71`). Khi có cờ, UC bỏ qua các lượt đồng bộ trường / mail / tài liệu (`copilot_app.py:755`, `:849`, `:912`).
- Có mạng lại → gỡ cờ, `docker unpause n8n`; dịch vụ nào ở các cổng 8320 / 5678 / 8340 / 5681 / 8350 đang tắt thì chạy `open_copilot.ps1 -NoBrowser`, tối đa 1 lần / 5 phút (`addons/network-guard/netguard.py:24-25`, `:59`, `:62-65`).
- Lệnh `docker pause/unpause n8n` cần container tên **`n8n`**, đúng như lệnh `docker run --name n8n` ở bước 5. Đổi vị trí cờ bằng `UC_OFFLINE_FLAG`, đặt giống nhau cho UC và task (`addons/network-guard/README.md:44`).

## 13. Kiểm tra nhanh

| Kiểm | Cách | Mong đợi |
|---|---|---|
| Web app | mở `http://127.0.0.1:8320/api/health` | `{"ok": true, "queue": …}` (`copilot_app.py:978-979`) |
| Cổng chép lời | `http://127.0.0.1:8340/health` | JSON trạng thái (`speech-gate/README.md:28`) |
| Máy ghi | `http://127.0.0.1:5681/health` | JSON trạng thái (`meeting-lecture-recorder/README.md:14`) |
| Tài khoản trường | `py school_cred.py --status` | "Đã có tài khoản …" (`school_cred.py:26-30`) |
| Bộ test (không cần mạng, Notion, n8n) | `py -m pip install -r requirements-dev.txt` rồi `py -m pytest` | tất cả test xanh (`pytest.ini:2`, `.github/workflows/tests.yml`) |
