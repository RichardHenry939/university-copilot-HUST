# Đánh giá kỹ thuật University Copilot — 10/2026

> Báo cáo review toàn repo theo góc nhìn reviewer cấp cao. **Không sửa dòng code nào**: chỉ có file này.
> Đối chiếu tại commit `da7a3a0` (v1.00.23, `main` ngày 14/10/2026). Mọi `file:dòng` đều theo commit này.

## Cách đọc báo cáo

**Nhãn kiểm chứng.** Mỗi vấn đề có đúng một nhãn:

| Nhãn | Nghĩa |
|---|---|
| **[Chạy]** | Đã chạy thử để chứng minh: script nhỏ chạy trên **bản sao** repo, dữ liệu giả, máy Linux (CPython 3.12). Không chạy trên Windows thật, không gọi trường / Notion / n8n thật. |
| **[Đọc]** | Đã đọc kỹ từng dòng liên quan và lần theo đường gọi; chắc chắn về hành vi của code, nhưng chưa chạy. |
| **[Suy luận]** | Lập luận từ code + hiểu biết về Windows / trình duyệt / phần cứng; **chưa chứng minh**. Số liệu bộ nhớ, thời gian, số lần chạy đều thuộc loại này trừ khi ghi khác. |

**Mức độ.**
- **Cao**: có kịch bản thực tế làm sai hoặc mất dữ liệu học tập, lộ khoá, hoặc hỏng im lặng diện rộng.
- **Vừa**: sai một phần / cần điều kiện cụ thể / có cách thấy được.
- **Thấp**: hiếm, ảnh hưởng nhỏ, hoặc **chỉ là lý thuyết** (được ghi rõ).

**Công sức** là giờ làm ước tính cho một người đã quen repo, gồm cả test hồi quy.

**Giới hạn của lần review này.**
- Không chạy app trên Windows, không đo RAM/CPU thật.
- `gemini_gate.py` (:8350), AgentChattr / `council_relay.py` (:8300/:8310) và các workflow n8n mẫu nằm ngoài repo nên không review được.
- Giao diện `ui/index.html` (79 chỗ `innerHTML`) mới kiểm theo mẫu, chưa duyệt hết từng chỗ (xem B-8).

---

## Tóm tắt: top 10 theo thứ tự nên sửa

Thứ tự = mức độ × khả năng xảy ra ÷ công sức. Hai mục đầu rẻ và nên làm ngay.

| # | Mã | Vấn đề | Mức | Nhãn | Công sức |
|---|---|---|---|---|---|
| 1 | B-1 | Cổng chép lời :8340 gửi khoá `X-Copilot-Key` tới **bất kỳ URL `callback`** nào người gọi đưa vào, không cần xác thực | Cao* | [Đọc] | 1–2 h |
| 2 | D-2 | `copilot_app` bị **nạp hai lần** (chạy dưới tên `__main__`, nơi khác `import copilot_app`): hai khoá `lock`, hai hàng đợi `jobs` → file kéo từ 📥 Notion kẹt "queued", ghi `inbox_state.json` không được bảo vệ | Vừa→Cao | [Chạy] | 0,5 h |
| 3 | D-1 | ~25 file trạng thái JSON ghi **không nguyên tử**, và `load()` gặp file hỏng thì **lặng lẽ trả trạng thái rỗng** → gửi lại toàn bộ thư cho Gemini, nhân đôi trang Notion, mất mọi lựa chọn "Sẽ đi / Bỏ" | Cao | [Chạy] | 4–6 h |
| 4 | R-1 | TKB qldt đổi định dạng **một ô** → môn đó bị đưa buổi học vào thùng rác Notion và hạ về *Planned*, không báo lỗi rõ | Cao | [Chạy] | 3 h |
| 5 | D-3 | Mất cập nhật giữa `mail_events.process` (luồng mail) và `alerts.ack` (nút bấm): lựa chọn "Sẽ đi / Bỏ" của bạn có thể biến mất, hoặc thư đã xử lý bị xử lý lại | Vừa | [Chạy] | 4–6 h |
| 6 | M-1 | Năm nhập học **2026 viết cứng** khi đổi mã kỳ sang S1–S8 → sinh viên khoá khác bị xếp sai kỳ toàn bộ | Vừa→Cao | [Đọc] | 1–2 h |
| 7 | R-2 | Bảng CTĐT qldt chèn thêm một cột → **mọi môn Credits = 0**, rơi khỏi GPA / tín tích luỹ; điểm có thể đọc nhầm cột | Cao | [Chạy] | 2 h |
| 8 | D-4 | Một câu trả lời Gemini "lạ" (ngày `"null"`, `chang` là mảng chuỗi) **chặn vĩnh viễn** việc đọc mọi thư sau đó, không ai thấy | Vừa | [Chạy] | 2–3 h |
| 9 | R-3 | MOOC / FAMI / iCTSV / Teams / Outlook đổi khoá JSON → trả `ok:true` với danh sách rỗng, **ghi đè** dữ liệu tốt; FAMI cờ `"0"` → bài bị đánh *Submitted*; MOOC mất điểm → "Đã làm" bị hạ thành "Bỏ lỡ" | Vừa→Cao | [Chạy] | 8 h |
| 10 | H-1 | Tới **~1.700 lần mở Chrome headless/ngày**, cộng LM Studio giữ 14B (và 8B) thường trú không hạn giờ → đỉnh RAM có thể vượt 32 GB | Vừa | [Đọc] + [Suy luận] | 4–8 h |

\* B-1 là **Cao** nếu một trang web có thể gửi yêu cầu tới 127.0.0.1 (phụ thuộc trình duyệt, xem chi tiết); với tiến trình cục bộ thì không thêm rủi ro, vì tiến trình đó vốn đọc được file khoá.

**Tổng công sức ước tính** cho mọi đề xuất trong báo cáo: khoảng **130–160 h**. Top 10 ở trên: khoảng **30–40 h**.

---

## 1. Bảo mật

**Bức tranh chung [Đọc].**

Mọi cổng HTTP đều chỉ nghe `127.0.0.1`:
- `copilot_app.py:1441`
- `speech-gate/speech_gate.py:571`
- `meeting-lecture-recorder/Program.cs:27`

Cách mỗi cổng chặn người gọi lạ:
- **UC (:8320).** Mọi POST đều qua kiểm tra Origin (`copilot_app.py:1087-1088`, sửa ở v1.00.23). Các endpoint mà n8n gọi còn kiểm thêm `X-Copilot-Key` bằng `hmac.compare_digest` (vd `copilot_app.py:1114-1115`).
- **Lệnh điện thoại.** Có chữ ký HMAC-SHA256 (cắt 96 bit), hạn 48 giờ, chống dùng lại (`phone_link.py:40-52`).
- **Cổng chép lời (:8340) và máy ghi (:5681).** **Không có xác thực nào.**

### B-1. Cổng chép lời gửi khoá chung tới URL do người gọi chọn — **Cao\*** · [Đọc] · 1–2 h

- **Bằng chứng:**
  - `POST /jobs` nhận `callback` từ query string và lưu nguyên vào job, không kiểm tra gì (`speech-gate/speech_gate.py:523-540`). Endpoint không đòi khoá, không kiểm Origin (`:508-557`).
  - Khi job xong **hoặc lỗi** (`:389`, `:447`), hàm `callback` đọc `.copilot-secret` và gửi nó trong header `X-Copilot-Key` tới đúng URL đó (`:451-461`).
  - Audio rác vẫn đi nhánh lỗi, tức là vẫn gọi callback (`:386-389`). Điều kiện duy nhất là body ≥ 1000 byte (`:528`).
- **Kịch bản gây hại:** ai gửi được một POST tới `127.0.0.1:8340` thì nhận được khoá chung. Với khoá đó, họ:
  - gọi được mọi endpoint "dành cho n8n" của UC, tức ghi vào Notion qua công cụ của não chat;
  - **ký được lệnh điện thoại**, vì `phone_link.py:17` dùng cùng khoá.
- **Ai gửi được POST tới cổng này:**
  - **Tiến trình trên máy:** không thêm rủi ro, vì nó vốn đọc được file khoá.
  - **Một trang web bạn đang mở:** POST "đơn giản" (không header lạ) tới 127.0.0.1 không cần preflight CORS. Trình duyệt chỉ chặn nếu đã bật cơ chế chặn trang công khai gọi vào mạng nội bộ (Private / Local Network Access). Cơ chế này đang được triển khai dần và khác nhau theo trình duyệt và phiên bản. **[Suy luận], chưa thử trên trình duyệt thật.**
- **Đề xuất:**
  1. Chỉ nhận `callback` có host thuộc danh sách cho phép (`host.docker.internal` / `127.0.0.1` / `localhost`, cổng 5678, đường dẫn `/webhook/`).
  2. Bắt `POST /jobs` và `/slides` có `X-Copilot-Key`: n8n đã có credential này.
  3. Kiểm Origin như UC.

### B-2. Máy ghi :5681 không xác thực — **Thấp** (phần lớn lý thuyết) · [Đọc] + [Suy luận] · 1 h

- **Bằng chứng:**
  - `/start`, `/stop`, `/marker`, `/extend`, `/retry-upload`, `/command` không kiểm tra gì (`meeting-lecture-recorder/Program.cs:34-44`).
  - Các endpoint có body JSON kiểu (`StartRequest`…) cần `Content-Type: application/json`, nên từ trình duyệt phải qua preflight, mà máy ghi không bật CORS → bị chặn.
  - `/stop` (`:38`) không có body nên **có thể** nhận POST "đơn giản".
- **Kịch bản:** một trang web dừng bản ghi giữa buổi học. Kịch bản này cần cùng điều kiện trình duyệt như B-1. **[Suy luận].**
- **Đề xuất:** kiểm header `X-Copilot-Key` hoặc Origin cho mọi POST; bỏ `/command` cũ nếu không còn dùng.

### B-3. Kiểm tra CSRF sau v1.00.23 — **không còn endpoint POST nào lọt** · [Đọc] + [Chạy]

- `_same_origin()` đứng **đầu** `do_POST` (`copilot_app.py:1087-1088`). Mình đã duyệt mọi nhánh POST bên dưới: không nhánh nào đứng trước nó.
- `Origin: None` (không có header) vẫn được nhận (`copilot_app.py:941-943`). Điều này cố ý, cho n8n/curl. Trình duyệt luôn gửi Origin trên POST khác nguồn, nên không mở lỗ hổng từ web. Chuỗi `"null"` (Origin từ iframe sandbox) **không** bằng `None`, nên bị chặn.
- `do_GET` không kiểm Origin. Các GET hầu hết chỉ đọc (`copilot_app.py:951-1083`). Không có CORS header nên trang lạ không đọc được kết quả.
- **Ngoại lệ nhỏ:** `GET /api/suggest` gọi n8n/LLM (`:971-972`), nên trang lạ có thể khiến UC tốn lượt Gemini. **Thấp.**

### B-4. DNS rebinding đọc được dữ liệu GET — **Thấp, lý thuyết** · [Suy luận] · 1 h

- **Bằng chứng [Đọc]:** không cổng nào kiểm header `Host`. ASP.NET mặc định nhận mọi host.
- **Kịch bản:** một trang trỏ tên miền của nó sang 127.0.0.1 sau khi tải xong. Khi đó trình duyệt coi đó là cùng nguồn và đọc được `/api/study`, `/api/tuition`, `/api/inbox`… (điểm, học phí). POST vẫn bị chặn vì Origin là tên miền lạ.
- **Đề xuất:** từ chối mọi request có `Host` khác `127.0.0.1:<cổng>` / `localhost:<cổng>`. Chỉ cần vài dòng cho mỗi cổng.

### B-5. Chặn `..` trong đường dẫn chỉ tách theo `\` — **Vừa/Thấp** · [Chạy] · 1 h

- **Bằng chứng:**
  - `POST /api/inbox/<id>/assign` kiểm `".." in folder.split("\\")` (`copilot_app.py:1400`).
  - Thư mục dạng dùng `/` (vd `a/../../x`) lọt qua.
  - `place()` ghép thẳng `UNI / rel_folder` rồi `shutil.move` (`copilot_app.py:277-282`). Trên Windows `/` cũng là dấu tách, nên file bị chuyển ra ngoài Uni-Documents.
  - Agent chạy thử qua `do_POST` thật thấy lọt.
- **Ai khai thác được:** trang lạ thì không, vì POST bị chặn Origin. Chỉ còn tiến trình cục bộ (vốn đã có quyền) hoặc lỗi XSS trong giao diện. Vì vậy thực tế là **lỗi đúng đắn hơn là lỗ hổng**.
- **Đề xuất:** `(UNI / folder).resolve()` phải nằm trong `UNI.resolve()` (`is_relative_to`).

### B-6. Tải trang web cho não chat: chặn địa chỉ nội bộ chưa kín — **Thấp** · [Chạy] + [Đọc] · 1–2 h

- **Bằng chứng:**
  - `web_tools.read` kiểm host bằng `_private()` **trước** khi gửi (`web_tools.py:31-49`).
  - urllib tự theo chuyển hướng. Kiểm tra URL sau chuyển hướng (`web_tools.py:50`) chạy **sau** khi request tới đích cuối đã được gửi.
  - `_private` không chặn dải 100.64.0.0/10 (CGNAT / Tailscale) [Chạy].
  - Tên miền được phân giải hai lần (kiểm tra, rồi urlopen), nên còn khe cho DNS rebinding [Suy luận].
- **Ai điều khiển URL:** não chat (LLM), tức là có thể bị nội dung web / thư "mớm" URL.
- **Kịch bản:** một trang công khai chuyển hướng tới `http://127.0.0.1:...` → UC gửi **một GET mù** vào cổng nội bộ. Kết quả bị bỏ, nhưng GET có tác dụng phụ thì đã chạy. GET của UC hầu như chỉ đọc (B-3), nên tác hại thấp.
- **Đề xuất:** tự xử lý chuyển hướng (`HTTPRedirectHandler` kiểm từng bước); kết nối tới IP đã kiểm; thêm 100.64.0.0/10.

### B-7. Lưu bí mật — **Vừa** (gộp) · [Đọc] + [Chạy]

| Bí mật | Nơi lưu | Nhận xét |
|---|---|---|
| Mật khẩu trường | Windows Credential Manager qua `keyring` (`school_cred.py:4`, `:15`) | Tốt. |
| `.copilot-secret` | File thường ở gốc repo, có trong `.gitignore` (`.gitignore:1-16`) | Chấp nhận được cho app cá nhân. Một khoá dùng cho **3 việc**: header n8n, ký link file, ký lệnh điện thoại. Lộ một chỗ (B-1) là lộ cả ba. Nên tách khoá theo mục đích. |
| Credential n8n | Trong n8n; repo chỉ giữ **ID** (`n8napi.py:22-26`) | Tốt. |
| `GEMINI_API_KEY`, `N8N_API_KEY` | Biến môi trường User | Ổn. Khoá Gemini gửi tới cổng :8350 trên máy (`mail_events.py:54-59`), ngoài repo nên không kiểm được tiếp. |
| Topic ntfy | `school/ntfy.json`, server công khai `ntfy.sh` | Ai đoán được topic thì **đọc được thông báo** (hạn nộp, tên sự kiện). Lệnh ngược lại vẫn an toàn nhờ chữ ký. |

**B-7a. `.copilot-secret` đọc bằng hai kiểu mã hoá — Vừa · [Chạy] cho cơ chế, [Suy luận] cho tần suất · 0,5 h**
- **Bằng chứng:**
  - `copilot_app.py:25` và `phone_link.py:17` dùng `read_text()`, tức mã hoá mặc định của Windows (cp1252 nếu không bật UTF-8 mode).
  - `speech-gate/speech_gate.py:457` dùng `utf-8`.
- **Kịch bản:**
  - Tạo file bằng PowerShell 5.1 `echo ... > .copilot-secret` thì ra UTF-16. Lưu bằng trình soạn thảo có BOM thì có BOM.
  - Hai phía đọc ra hai khoá khác nhau. UC so với credential n8n thì 403 (lỗi thấy được).
  - Riêng cổng chép lời gặp UTF-16 thì `read_text(encoding="utf-8")` **ném lỗi** ở đúng hàm `callback`, dẫn tới D-9 (luồng xử lý chết).
- **Vì sao CI không thấy:** CI đặt `PYTHONUTF8=1` nên không lộ lỗi này.
- **Đề xuất:** một hàm đọc chung `read_bytes().decode("utf-8-sig").strip()`, báo lỗi rõ nếu không phải ASCII.

### B-8. XSS trong giao diện — **chưa thấy lỗi**, kiểm chưa hết · [Đọc] (một phần)

- `ui/index.html:781` có `esc()`, được gọi 185 lần.
- Mình soát 6 chỗ ghép chuỗi "đáng ngờ" (`:1200`, `:1422`, `:1760`, `:1822`, `:1878`, `:2152`). Chỗ nào ghép dữ liệu từ thư / Notion vào HTML đều đã `esc()`, hoặc chỉ dùng trong `alert()`.
- **Rủi ro còn lại [Suy luận]:**
  - `href="${esc(m.url)}"` (`:1822`) không chặn URL `javascript:`. Nếu Notion chứa URL như vậy thì bấm vào sẽ chạy script trong trang UC, tức vượt qua kiểm tra Origin.
  - 79 chỗ `innerHTML` chưa được duyệt hết.
- **Đề xuất:** chỉ cho `http(s):` trong `href`; thêm header `Content-Security-Policy` cho trang UC (chặn script inline sẽ cần tách JS — xem N-1).

---

## 2. Độ bền khi trường đổi giao diện web

**Điểm tốt [Đọc].**
- `school/latest.json` chỉ ghi khi lượt qldt thành công (`school_fetch.py:372-377`), nên một lượt lỗi **không** đè dữ liệu tốt.
- SIS và iCTSV lỗi riêng, không kéo qldt theo.
- 2FA / captcha / sai mật khẩu được nhận diện đúng và dừng lại.

**Điểm yếu chung [Đọc].**
- **Không có kiểm tra hợp lý nào:** không so số dòng với lượt trước, không kiểm tiêu đề cột, không cảnh báo "0 dòng trong khi lần trước có N". Hầu hết bảng đọc theo **vị trí cột cố định**; chỉ bảng tổng kết dò cột theo tên (`school_sync.py:190`).
- **Lỗi của nguồn thứ cấp không lên giao diện.** Lỗi Teams / MOOC / FAMI / iCTSV / Outlook chỉ vào `_mail["last"]` và log (`copilot_app.py:767-836`). Giao diện chỉ đọc `.alerts` của `/api/alerts` (`ui/index.html:2266`) nên không bao giờ thấy.
- **Không có test nào cho bộ đọc / bộ phân tích** (mục 6).

**Đổi giao diện thì bị báo nhầm là "Cần đăng nhập".**
- qldt được coi là "đã đăng nhập" khi `/api/v1/semesters/current` trả 200 (`school_fetch.py:150`); iCTSV khi trang có chữ "Xin chào" (`:157`).
- Hai dấu hiệu này đổi là ra `NeedLogin`. UI báo "Cần đăng nhập" và UC chạy lại SSO mỗi 5 phút.
- Người dùng sẽ đi nhập lại mật khẩu, trong khi lỗi thật là giao diện đổi.

### R-1. TKB đổi định dạng một ô → buổi học của môn đó vào thùng rác Notion — **Cao** · [Chạy] · 3 h

- **Bằng chứng:**
  - `parse_tkb` bỏ qua lớp có ô lịch không khớp regex, chỉ ghi một dòng `probs` (`school_sync.py:82-86`).
  - Điều kiện chạy chỉ là `if lop and sem` (`school_sync.py:121`), tức **có ít nhất một lớp** đọc được. Sau đó `tkb.run(... "buoc": "ghi" ...)` chạy luôn (`:126-127`).
  - `tkb.run` đưa mọi buổi *Class* trong kỳ **không có trong danh sách mới** vào thùng rác Notion (`tkb.py:126-135`).
  - Môn đang *Taking* mà không có trong danh sách thì bị hạ về *Planned* kèm ghi chú "Không có trong TKB" (`tkb.py:148-151`).
  - Agent chạy thử: một lớp hiện "Sáng Thứ 2" thay vì "Sáng T2" → buổi của môn đó bị lưu trữ, môn bị hạ *Planned*.
- **Hậu quả:**
  - Mất lịch học và nhắc tiết học của môn đó.
  - Trái luật "giữ phần Notion thừa" ghi ở đầu file (`school_sync.py:18-20`).
  - Tín hiệu duy nhất là một dòng review và thùng rác Notion 30 ngày.
- **Đề xuất:**
  1. Có bất kỳ `probs` nào thì **không** chạy bước ghi, hoặc loại các môn lỗi khỏi bước lưu trữ / hạ trạng thái.
  2. `tkb.run` từ chối lưu trữ > 20% số buổi, hoặc toàn bộ một môn, trong một lượt.
  3. Lưu HTML thô khi phân tích lỗi.

### R-2. Bảng CTĐT lệch cột → mọi môn Credits = 0 — **Cao** · [Chạy] · 2 h

- **Bằng chứng:** chương trình đào tạo đọc theo chỉ số cột cố định `r[1]`…`r[9]` (`school_sync.py:151-153`).
  - Tín không phải số thì ghi 0 (`school_sync.py:168-170`).
  - Điểm đọc ở `r[8]` (`:174`).
  - Agent chèn một cột giả: mọi môn bị ghi **Credits = 0**, nhóm HP sai.
- **Hậu quả:**
  - Môn rơi khỏi GPA, tín tích luỹ, danh sách cải thiện (`program.py:96`, `:121`, `:146`).
  - Nếu cột điểm lệch sang một cột khác có chữ A–D, có thể ghi sai GPA / Pass [Suy luận].
  - Chỉ thấy được trong nhật ký thay đổi.
- **Đề xuất:** dò cột theo tên tiêu đề (như `:190`); thiếu cột thì dừng với trạng thái "Lỗi"; tín không phải số thì **bỏ qua**, đừng ghi 0.

### R-3. Các nguồn API trả "rỗng hợp lệ" và ghi đè — **Vừa→Cao** · [Chạy] · 8 h

| Nguồn | Điểm phụ thuộc | Đổi thì sao | Hậu quả |
|---|---|---|---|
| FAMI | cờ `da_co_diem` (`fami.py:79`) | API trả chuỗi `"0"` → `bool("0") == True` [Chạy] | Bài chưa làm bị ghi **Submitted** (`fami.py:100-101`), **tắt nhắc** |
| FAMI | `.get('list', [])` (`fami.py:49`), khoá `extra` (`:73-74`) | đổi tên khoá → 0 bài [Chạy] | Mất hạn bài kiểm tra chương, im lặng |
| MOOC | khoá điểm trong `courseware_summary` (`mooc.py:28-35`) | mất điểm → `earned = 0` [Chạy] | `expired.py:47-50` ghi **"Bỏ lỡ"**, **đè** cả kết quả "Đã làm" |
| MOOC | hình dạng danh sách khoá học, HTTP 403 | trả `ok:true` rỗng [Chạy] | `mooc.json` bị ghi đè rỗng (`mooc.py:65`) |
| iCTSV | khoá danh sách hoạt động (`ctsv_live.py:70`) | `{ok:true, mine:[], open:[]}` [Chạy] | Hoạt động đã đăng ký và hạn nộp minh chứng biến mất, **mất nhắc** (`extracurricular.py:36`, `alerts.py:89`) |
| Teams | `joinedTeams` 403 | `ok:true, teams:[]` [Chạy] | Ghi đè file / phản hồi / OneNote bằng danh sách rỗng (`teams_fetch.py:179-181`) |
| Outlook | REST v2.0 cũ (`school_mail.py:28`), khoá `value` | ngừng dịch vụ → HTTP 410 (thấy được); đổi khoá → `items:[]` nhưng `last_fetch` vẫn cập nhật [Chạy] | Trông như "không có thư mới" |
| ctt-sis học phí | cột cố định (`school_fetch.py:316-326`), `_vnd` (`:298-301`) | thêm cột → tổng **2 đ** vẫn `ok=True`; `"1,5"` → 15.0; `"3.500.000 đ"` → ValueError [Chạy] | Chỉ hiển thị (không ghi Notion), nhưng hiện như **số chính thức của trường** |
| iCTSV ĐRL | regex nhãn "Tổng SV:" (`school_fetch.py:337`) | im lặng `None` [Chạy] | Thiếu ĐRL |

**Đề xuất chung:**
- Mỗi nguồn ghi `school/health.json`: lần ok cuối, số mục, lỗi cuối.
- Cảnh báo lên thanh trạng thái khi lỗi kéo dài > 1 giờ, hoặc số mục **từ >0 về 0**, hoặc giảm > 50%.
- **Không ghi đè snapshot khác rỗng bằng snapshot rỗng.**
- `expired` không bao giờ hạ "Đã làm" thành "Bỏ lỡ".
- FAMI đánh *Submitted* chỉ khi có điểm thật.
- Ưu tiên làm trước (~8 h): R-1, R-2, cờ FAMI, luật không hạ kết quả trong `expired`, chặn ghi đè N→0 cho MOOC / FAMI / iCTSV.

**Lỗi phụ thấy khi rà [Đọc]:**
- `course_detail.py:217` đọc `it['type']` nhưng mục MOOC mang khoá `format` (`mooc.py:35`).
- `tuition.py:76-78` dùng file luật học phí mà không kiểm năm học, nên có thể dùng đơn giá năm cũ.

---

## 3. Đồng thời và toàn vẹn dữ liệu

### D-1. Ghi trạng thái không nguyên tử + đọc lỗi thì lặng lẽ về rỗng — **Cao** · [Chạy] · 4–6 h

- **Bằng chứng:**
  - Khoảng 25 file JSON ghi bằng `write_text` thẳng, không qua file tạm, không fsync. Ví dụ:
    - `mail_events.py:43-44` (`school/events.json`)
    - `alerts.py:26` (ghi lại **mỗi phút**)
    - `phone_link.py:34-36`
    - `school_fetch.py:372-377` (`latest.json`, do tiến trình con ghi trong khi tiến trình cha đọc ở `school_sync.py:250`)
  - Chỉ 3 chỗ ghi nguyên tử: `copilot_app.py:67-70`, `speech-gate/speech_gate.py:82-86`, `teams_files.py:140`.
  - Mọi `load()` nuốt lỗi và trả mặc định (`mail_events.py:38-40`, `alerts.py:21-23`).
- **Kịch bản [Chạy]:** máy tắt điện hoặc bị kill đúng lúc ghi làm `events.json` bị cắt cụt. Lượt sau:
  - `process()` coi như chưa xử lý thư nào, gửi lại **toàn bộ** thư (≤ 400) và bài Teams (≤ 1500) cho Gemini;
  - tạo id sự kiện mới nên **nhân đôi** trang 📡 và lịch trong Notion;
  - mất mọi lựa chọn "Sẽ đi / Bỏ / Đã biết".
  - `alerts.json` hỏng thì mọi cảnh báo đỏ đang hiệu lực **nhắc lại**, và mọi "Tắt nhắc" bị quên.
- **Đề xuất:** module `uc_state.py` dùng chung:
  - ghi file tạm tên riêng → fsync → `os.replace` có thử lại (Windows);
  - giữ `.bak`; đọc lỗi thì dùng `.bak` và **báo to**;
  - `process` từ chối chạy khi trạng thái rỗng bất thường.

### D-2. `copilot_app` bị nạp hai lần — **Vừa** (luôn xảy ra) / tác hại **Cao** khi trùng thời điểm · [Chạy] · 0,5 h

- **Bằng chứng:**
  - App chạy bằng `python copilot_app.py` (`open_copilot.ps1:10`), tức module tên `__main__`.
  - `teams_files.py:60`, `:94`, `:136`, `lecture_export.py:112`, `phone_page.py:152` lại `import copilot_app as app`. Python tạo **bản thứ hai** của module, với `lock` và `jobs` mới (`copilot_app.py:56-57`).
- **Hậu quả:**
  - `teams_files` đẩy file kéo từ 📥 University Inbox vào `app.jobs` (`teams_files.py:204`): hàng đợi **không ai đọc**. File kẹt "queued" tới khi khởi động lại.
  - `with app.lock` (`teams_files.py:175`, `:202`) **không** chặn các luồng ghi thật. Hai bản cùng dùng `inbox_state.tmp`.
  - Agent chạy thử thấy `FileNotFoundError`, mất phần thêm vào, và có lần một JSON dở bị đưa vào chỗ thật. Khi đó `load_state()` về `[]` và lượt ghi kế tiếp **xoá sạch** danh sách Inbox cùng lịch sử chống trùng.
- **Đề xuất:** dòng đầu khối `if __name__ == "__main__":` thêm `sys.modules.setdefault("copilot_app", sys.modules["__main__"])`, hoặc tách phần dùng chung ra module riêng.

### D-3. `mail_events.process` và `alerts.ack` ghi đè nhau (lỗi "mất Sẽ đi / Bỏ") — **Vừa** · [Chạy] · 4–6 h

- **Bằng chứng:**
  - `process` (luồng mail) `load()` ở `mail_events.py:206`, gọi Gemini cho từng thư, rồi `save` ở `:269`, `:271`, `:372-373`.
  - `ack` (luồng HTTP khi bạn bấm nút) `me.load()` ở `alerts.py:159`, `me.save` ở `:167`, rồi `sync_notion` (`:169`).
  - Cả hai đọc–sửa–ghi **toàn bộ** file, **không khoá**.
- **Khe thời gian:**
  - Trong `process`: 5–15 giây cho mỗi thư mới. Gemini có `timeout=180` (`mail_events.py:63`), chờ 65/130 s khi bị 429, và luôn nghỉ 4 s (`:66`).
  - Trong `ack`: 2–5 giây.
  - Bấm nút đúng lúc có thư mới là chuyện **thực tế**, không phải lý thuyết.
- **Kịch bản [Chạy]:**
  1. Bạn bấm "Sẽ đi" giữa lúc `process` đang chờ Gemini → `process` ghi lại bản cũ → lựa chọn mất.
  2. Ngược lại: `ack` ghi bản cũ → mất `processed` của thư vừa xử lý → lượt sau gọi Gemini lại và tạo trang Notion trùng (agent đếm được 4 trang thay vì 2).
- **Đề xuất:**
  - Khoá đặt trong module **không bị `importlib.reload`**: hiện `alerts`, `mail_events`, `deadlines` bị reload mỗi lượt (`copilot_app.py:770`, `:815`), nên khoá đặt trong chúng sẽ bị tạo lại.
  - Gọi Gemini / Notion **ngoài** khoá. Sau đó khoá → đọc lại → gộp → ghi.

### D-4. Dữ liệu Gemini lạ làm tắc vĩnh viễn hàng đợi thư — **Vừa** · [Chạy] · 2–3 h

- **Bằng chứng:**
  - Một chặng đã lưu có `ngay = "null"` (chuỗi) làm `fmt()` (`mail_events.py:87`) ném lỗi trong `tracked_text`. Lỗi này bị bắt như "gemini lỗi" (`:230-234`), nên thư bị trả lại hàng chờ và vòng lặp `break`.
  - Lượt sau gặp lại đúng lỗi đó, tức **mọi thư sau đó không bao giờ được đọc**. Không có báo lỗi lên giao diện.
  - Nếu `chang` là mảng chuỗi thì `s.get(...)` ở `:236-239` ném lỗi **ngoài** try. `mail_run` (`copilot_app.py:813`) không bọc chỗ này, nên lượt đó còn bỏ luôn deadlines / extra_refresh / phone_refresh.
- **Đề xuất:** kiểm hình dạng đầu ra Gemini (kiểu, định dạng ngày/giờ); bắt lỗi theo **từng thư** kèm bộ đếm số lần thử; quá N lần thì bỏ qua thư đó và báo.

### D-5. `alerts.tick` và "Tắt nhắc" — **Thấp/Vừa** · [Chạy] · 1 h

- **Bằng chứng:**
  - `tick` đọc ở `alerts.py:222`, gửi từng cảnh báo (toast tới 60 s, ntfy tới 20 s), rồi ghi ở `:286`.
  - "Tắt nhắc" ghi trong khoảng đó (`:154`, `:157`) bị đè.
- **Hậu quả:** cảnh báo bạn vừa tắt lại nhắc.
- **Đề xuất:** cuối `tick` khoá → đọc lại → chỉ gộp `sent`.

### D-6. Cờ chạy và nút "chạy ngay" — **Thấp** · [Đọc] · 1 h

- `_school` / `_mail` đặt cờ đúng cách dưới khoá riêng.
- Nhưng `/api/mail-check` (`copilot_app.py:1289-1294`) chỉ kiểm cờ của chính nó, nên mail và school có thể chạy song song.
- Hệ quả: `extra_refresh` chạy hai lần cùng lúc → có thể tạo trùng dòng 🎯 trong Notion.
- `pdf_translate._worker` và `deadlines._c` là cờ/bộ đệm không khoá. Hai worker pdf2zh có thể cùng chạy [Suy luận].

### D-7. `inbox_state.json` đọc ngoài khoá — **Thấp/Vừa** · [Chạy] (Linux) + [Suy luận] (Windows) · 1 h

- **Trên Linux:** 0/26.660 lần đọc thấy file dở [Chạy].
- **Trên Windows:** `os.replace` (`copilot_app.py:70`) báo `PermissionError` (WinError 5) nếu đúng lúc đó có tiến trình khác giữ file. Ví dụ: luồng đọc ở `:649`, `:974`, `:1421`, phần mềm diệt virus, indexer, OneDrive [Suy luận].
- **Hậu quả:**
  - một upload thành công bị ghi "error" (`:307`, `:313`);
  - `/api/upload` để lại file trong `00 · Inbox` không ai xử lý.
- **Đề xuất:** thử lại `replace` vài lần, đọc trong khoá, cắt bớt mục cũ (danh sách hiện chỉ tăng, không bao giờ cắt).

---

## 4. Hiệu năng trên laptop yếu (32 GB RAM dùng chung GPU tích hợp)

> Số lần chạy lấy từ code [Đọc]. Số RAM là **ước lượng** [Suy luận], chưa đo trên máy thật.

### H-1. Chrome headless mở 5–6 lần mỗi khung 5 phút, 24/24 — **Vừa** · [Đọc] · 2–6 h

- **Bằng chứng:**
  - Cả `school_loop` và `mail_loop` chạy mọi khung 5 phút suốt ngày (`copilot_app.py:688`).
  - Lượt school chạy `school_fetch.py` như tiến trình con (`school_sync.py:245`). Tiến trình này mở Chrome thật với hồ sơ persistent, headless (`school_fetch.py:42`), mỗi lượt ~7 trang.
  - Lượt mail mở thêm Chrome cho Outlook (`school_mail.py:79`), Teams (`teams_fetch.py:144`), MOOC (`mooc.py:49`) và FAMI (`fami.py:34`).
  - iCTSV (`ctsv_live.py:61`) cũng chạy **mọi lượt** vì `EVERY_MIN = 4` (`ctsv_live.py:20`). Chú thích "mỗi giờ" ở `copilot_app.py:799` đã lỗi thời.
- **Kết quả:** tối đa ~1.700 lần khởi động Chrome mỗi ngày. Mỗi lượt mail còn có ~30 s chờ cố định.
- **Lãng phí thêm [Đọc]:**
  - API hoạt động iCTSV (1000 dòng) bị kéo **hai lần** mỗi khung (`school_fetch.py:345`, `ctsv_live.py:70`).
  - `extra_refresh` chạy 2 lần mỗi khung (`copilot_app.py:728`, `:818`); `phone_refresh` tới 3 lần (`:729`, `:819`, `:903`).
  - `alert_loop` chạy mỗi 60 s với `timetable.MAX_AGE = 60` (`timetable.py:15`), tức ~1.440 truy vấn Notion qua n8n mỗi ngày.
  - Workflow n8n đặt `saveDataSuccessExecution: "all"` (`build.py:1378-1379`), nên **mọi** lời gọi Notion để lại một execution đầy đủ trong n8n/WSL.
- **Đề xuất (theo tác động ÷ công sức):**
  1. **Chu kỳ riêng từng nguồn:**
     - qldt / SIS: 30–60 phút;
     - Outlook / Teams: 5 phút ban ngày, 15–30 phút ban đêm;
     - iCTSV: 30 phút.
     - Nhắc hạn vẫn đúng mốc vì đã hẹn sẵn trên ntfy (`phone_sched.py`). 2–4 h.
  2. `saveDataSuccessExecution: "none"` + bật prune trong n8n. 0,5 h.
  3. Một Chrome cho mỗi khung, mỗi nguồn một tab (gộp 6 khối Playwright giống nhau). 4–6 h.
  4. `MAX_AGE` 600 s cho `alert_loop`; bỏ lần kéo iCTSV trùng; bỏ `importlib.reload` khi chạy thật (`copilot_app.py:770`, `:815`; reload còn xoá cache `deadlines._c`). 2 h.
  5. Giãn chu kỳ khi chạy pin (hiện không kiểm tra pin ở đâu). 1–2 h.

### H-2. Model local giữ thường trú, hai model cùng lúc — **Vừa** · [Đọc] + [Suy luận] · 1–2 h

- **Bằng chứng [Đọc]:**
  - qwen3-14b dùng ở:
    - xếp tài liệu (`copilot_app.py:29`);
    - nén chép lời (`speech-gate/speech_gate.py:38`);
    - dịch PDF `-t 4` (`pdf_translate.py:61-63`);
    - não dự phòng của chat (`build.py:414`).
  - qwen3-8b dùng ở bản tin 07:20 / 21:30 (`build.py:605`) và làm dự phòng của cổng chép lời (`speech_gate.py:177`).
  - Không chỗ nào đặt `ttl` / unload.
  - PhoWhisper giữ trong RAM suốt đời tiến trình (`speech_gate.py:58`, `_model`).
- **Ước lượng [Suy luận]:**

  | Thành phần | RAM ước lượng |
  |---|---|
  | 14B Q4 + KV 16k | ~11–12 GB |
  | 8B | ~7 GB |
  | WSL (số tác giả đo, `addons/low-end-priority/README.md:65`) | ~7 GB |
  | Windows + trình duyệt học | 6–9 GB |
  | PhoWhisper | 1,5–2 GB |

  - Hai model cùng nạp: đỉnh ~33–38 GB, **vượt 32 GB**, nên máy phải dùng swap.
  - Chỉ 14B: ~26–30 GB.
- **Đề xuất:**
  - Một model duy nhất cho mọi việc (đổi bản tin sang 14B, hoặc mọi việc sang 8B).
  - Gửi `"ttl": 600` trong request LM Studio / bật auto-evict.
  - pdf2zh `-t 1`.

### H-3. Docker / WSL / Tika — **Thấp/Vừa** · [Đọc] + [Suy luận] · 2–3 h

- **Bằng chứng [Đọc]:** gợi ý `.wslconfig` (`memory=4GB`, `autoMemoryReclaim`) chỉ nằm trong `addons/low-end-priority/README.md:61-77`, không có ở README chính.
- **Ước lượng [Suy luận]:**
  - Tika bản `-full` chạy JVM, mặc định lấy ~25% RAM của VM.
  - Tika gần như rỗi cả ngày; chỉ dùng khi xếp tài liệu / học phí.
- **Đề xuất:**
  - Đưa `.wslconfig` vào hướng dẫn cài đặt.
  - Đặt `-Xmx768m` cho Tika.
  - Thêm `docker compose` có `mem_limit` cho n8n / Tika / SearXNG.
  - Bật Tika theo nhu cầu (`docker start/stop`).

---

## 5. Mất mạng và tắt máy giữa chừng

### Khi mất mạng [Đọc]

- **Có add-on network-guard:**
  - Ba vòng school / mail / uni_sync bỏ lượt (`copilot_app.py:755`, `:849`, `:912`).
  - Nhưng `alert_loop`, `phone_refresh`, `lecture_monitor`, worker xếp file và các handler HTTP **vẫn gọi n8n** trong lúc n8n bị `docker pause`. Chúng phải chờ tới hết timeout (120–600 s) [Suy luận].
- **Không có add-on:** mỗi 5 phút vẫn mở Chrome; một lượt có thể kéo > 5 phút, làm đói lượt school. Không spam cảnh báo.
- **Timeout:**
  - Mọi `urlopen` và `page.goto` đều có timeout; fetch trong trang tự huỷ sau 30 s (`teams_fetch.py:30`).
  - Ngoại lệ: `n8napi._key()` chạy PowerShell **không timeout** lúc import (`n8napi.py:4-10`) — **Thấp** (xem L-7).
- **Sau khi khởi động lại lúc offline:** bộ đệm hạn nộp chỉ nằm trong RAM (`deadlines._c`), nên **không có nhắc hạn** cho tới khi có mạng.
  - Nhắc trên điện thoại vẫn tới, vì đã hẹn trên ntfy (`phone_sched.py:1-11`).
  - Lịch học có đệm trên đĩa.

### O-1. Tắt đột ngột → trạng thái hỏng thành rỗng — xem **D-1** (Cao)

### O-2. Upload lên Drive/Notion lỗi thì không bao giờ thử lại — **Vừa** · [Đọc] · 2 h

- **Bằng chứng:**
  - Mục có `notion = "error"` / `"sending"` không có vòng quét thử lại.
  - `uni_sync` đánh dấu file `synced` **trước** khi biết kết quả ingest (`copilot_app.py:683`).
- **Kịch bản:** mất mạng đúng lúc tải lên → tài liệu nằm trên máy nhưng không bao giờ lên Notion/Drive, giao diện vẫn báo đã đồng bộ.
- **Đề xuất:** vòng quét định kỳ cho mục `error` / `sending` cũ hơn 10 phút, có giới hạn số lần.

### O-3. Cổng chép lời: luồng xử lý có thể chết, khởi động lại thì chép từ đầu — **Vừa** · [Đọc] · 2–3 h

- **Bằng chứng:**
  - **Luồng chết:** `worker()` chỉ có `try/finally`, không có `except` (`speech-gate/speech_gate.py:471-480`). Nhánh `except` của `process` lại gọi `save_job` và `callback` (`:386-389`), và `callback` đọc khoá **ngoài** try (`:457`). Lỗi ở đó (đĩa đầy, khoá UTF-16 như B-7a) làm **luồng worker chết vĩnh viễn**, trong khi `/health` vẫn báo `ok`.
  - **Chép lại từ đầu:** khi khởi động lại, job dở được xếp lại **không** đặt `resume` (`:565-568` so với `:290`).
  - **Không gửi lại callback:** `done` được lưu trước callback, và không có cơ chế gửi lại khi `callbackOk = false` (`:468`).
- **Đề xuất:**
  - `except Exception` + log trong `worker`.
  - Đặt `resume` theo sự có mặt của `transcript.txt`.
  - Lúc khởi động, gửi lại callback cho job `done` có `callbackOk = false`.

### O-4. Máy ghi: bản ghi bị kill giữa chừng không gửi lại được — **Vừa** · [Đọc] + [Suy luận] · 2 h

- **Bằng chứng [Đọc]:** file meta `.json` chỉ được ghi lúc Stop (`meeting-lecture-recorder/Program.cs:304`), mà `UploadAsync` cần file đó (`:329`).
- **Suy luận:** sau khi cúp điện, header WAV chưa được chốt.
- **Kịch bản:** laptop hết pin giữa buổi → "Gửi lại" không thấy bản ghi.
- **Đề xuất:** ghi meta ngay lúc Start, cập nhật định kỳ; khi khởi động, sửa header WAV của file dở.

### O-5. Chạy bằng `pythonw` thì mọi `print()` lỗi biến mất — **Vừa** · [Chạy] · 0,5 h

- **Bằng chứng:**
  - `open_copilot.ps1:9-10` chạy bằng `pythonw.exe`, khi đó `sys.stdout` là `None`.
  - Mọi `print("... lỗi", e)` trong vòng lặp nền (vd `copilot_app.py:913`, `mail_events.py:234`) đều mất.
  - Đây là lý do nhiều lỗi ở mục 2–3 trở thành "im lặng".
- **Đề xuất:** đầu `__main__`, nếu `sys.stdout is None` thì chuyển stdout/stderr sang `school/uc.log`, có xoay vòng.

### O-6. Tự hồi phục của các luồng — phần lớn tốt · [Đọc]

- Các vòng `while True` đều bọc `try` và tự chạy tiếp.
- **Ngoại lệ:** worker xếp tài liệu chết nếu `update_item` trong nhánh `except` ném lỗi (`copilot_app.py:918-925`), vd do D-7.
- Không có watchdog tiến trình nếu không cài network-guard. Một phiên Playwright treo sẽ giữ cờ `_mail["running"]`, chặn cả lượt school [Suy luận].
- **Đề xuất:** watchdog đơn giản: lượt chạy quá 15 phút thì ghi log và gỡ cờ. 2 h.

---

## 6. Kiểm thử

- **Tình trạng [Chạy]:** 264 test xanh (~1,3 s), nhưng **độ phủ dòng chỉ ~23%** (8.799 câu lệnh, 6.742 chưa chạy).
- **Phủ tốt:**

  | Module | Độ phủ |
  |---|---|
  | `expired` | 100% |
  | `audio_priority` | 100% |
  | `tuition` | 98% |
  | `tkb` | 95% |
  | `tuition_rules` | 93% |
  | `stale_filter` | 83% |

- **Phủ thấp:**

  | Module | Độ phủ |
  |---|---|
  | `deadlines` | 64% |
  | `school_sync` | 38% |
  | `academic` | 36% |
  | `mail_events` | 18% |
  | `copilot_app` | 12% |

- **Không được import lần nào:** 36 module, cùng toàn bộ `speech-gate/` và `addons/network-guard`.

### T-1. Hàm thuần đáng test trước (rẻ, giá trị cao) — 10–14 h

Agent đã gọi thử các hàm này và **thấy lỗi thật** [Chạy]:

| Hàm | Lỗi thấy được |
|---|---|
| `mail_events.diff_stages` (`mail_events.py:91-101`) | Báo thay đổi giả "giờ 07:05 → 7:05". Bỏ sót phòng "B1-103" → "B1-1035". Không báo khi một chặng hết bị huỷ. |
| `patch_classes` (`mail_events.py:313`) | Giờ dạng `"07:00:00"` ném `ValueError` (xem L-6). |
| `stale_filter.keep` (`stale_filter.py:61-65`) | Thông báo gửi 20/12 ghi "trước 05/01" bị ẩn, vì ngày không ghi năm bị gán năm gửi. Thông báo gửi 31/12 lúc 20:00 UTC (đã là 1/1 ở Việt Nam) bị xếp vào năm cũ. |
| `alerts.py:75` (cùng kiểu ở `:54`, `:97`, `:234`, `phone_sched.py:48`, `:62`) | Hạn chỉ có ngày, chạy trên máy đặt múi giờ UTC → thành 07:00 +07. Trên máy Windows đặt giờ Việt Nam thì không lộ. |
| `dupscan.sim` (`dupscan.py:36`) | "tuần 3" và "tuần 4", "Lab 1" và "Lab 2" giống nhau 1,0. |
| `speech_gate.clean_text` (`speech_gate.py:162`) | "1 1 1 1" thành "1", mất số liệu. |
| `school_fetch._vnd` | Lỗi định dạng số (xem R-3). |
| `web_tools._private` | Lọt 100.64/10 (xem B-6). |

**Chưa có test** (mình chưa thấy lỗi ở đây, nhưng nên có):
- `phone_link.make` / `verify` / `handle` (`phone_link.py:40-52`, `:137`);
- `phone_sched.plan` (`phone_sched.py:34`): các khoá nó tạo phải khớp với khoá `alerts.tick` kiểm (`alerts.py:243-282`). Nên có một test hợp đồng giữa hai bên.

### T-2. Đồ giả quá dày nên không bắt được lỗi thật — [Đọc]

| Đồ giả | Bỏ qua điều gì | Lỗi lọt qua (ví dụ) |
|---|---|---|
| `FakeN8n` (`tests/conftest.py:50-80`) | Luật của cổng n8n thật (`build.py:1075-1088`: ≤ 60 thao tác/lô, danh sách DB cho phép, cấm lưu trữ) | Đổi lô `tkb.py:140` từ 50 lên 100 vẫn xanh, chạy thật thì hỏng |
| `FakeN8n` | Bộ lọc và phân trang; trang vừa tạo không xuất hiện ở lần truy vấn sau; PATCH id lạ vẫn 200 | Không kiểm được truy vấn đúng, hay chạy lại có an toàn không |
| `mail_events_stub` | Chỉ kiểm `when_of` khớp module thật | Đổi hình dạng trạng thái mà `load()` trả về sẽ không bị phát hiện |
| `test_copilot_app_origin.py` | Vá `Path.read_text` toàn cục | Che lỗi crash khi thiếu `.copilot-secret` lúc import và lỗi mã hoá B-7a. Các "spy" kiểm stub **được gọi**, không kiểm endpoint **làm gì**. `do_GET` và chữ ký `/files` chưa có test. |
| `FakeKernel32` (`tests/test_audio_priority.py`) | Không bao giờ lỗi (handle -1, `GetPriorityClass` trả 0) | Đoạn giữ AI ở IDLE 120 s sau khi dừng ghi (`audio_priority.py:85`) chưa được test qua một lần dừng, dù độ phủ báo 100% |

### T-3. Thiếu cả nhóm test — [Đọc]

- **Test hợp đồng cho bộ đọc trường:** chưa có HTML/JSON mẫu đã lưu cho qldt / SIS / iCTSV / FAMI / MOOC / Teams. Đây là cách duy nhất để R-1…R-3 bị bắt trước khi lên Notion.
- **Test đồng thời:** D-3 cần một test có luồng song song chứng minh lựa chọn "Sẽ đi" còn nguyên.
- **Test múi giờ:** quanh 00:00 GMT+7 (17:00 UTC) và chuyển năm; chạy dưới `TZ=UTC` và một múi giờ khác.
- **CI** (`.github/workflows/tests.yml`) chỉ chạy pytest. Còn thiếu:
  - lint (ruff), `python -m compileall -W error`;
  - kiểm `'\S'` không hợp lệ ở `speech-gate/export_ov.py:2` và `quantize_ov.py:2`, hiện chỉ là cảnh báo, sẽ thành lỗi ở Python bản mới [Chạy];
  - ngưỡng độ phủ;
  - `dotnet build` cho máy ghi;
  - PSScriptAnalyzer cho `.ps1`;
  - một lượt chạy **không** đặt `PYTHONUTF8`.

### Kế hoạch test đề xuất (~34 h)

| # | Việc | Giờ |
|---|---|---|
| 1 | Test bảo mật: chữ ký / hết hạn / dùng lại lệnh điện thoại, `_private`, đường dẫn `assign`, chữ ký `/files`, `safe_name` (tên `CON`, `NUL`) | 4 |
| 2 | `FakeN8n` chặt: luật cổng, truy vấn theo bộ lọc, đọc lại được trang vừa ghi, 404 id lạ | 5 |
| 3 | `alerts` với đồng hồ đóng băng quanh 23:59/00:00 GMT+7, hợp đồng khoá với `phone_sched` | 6 |
| 4 | Bảng test cho `diff_stages` / `rooms` / `text_diff` | 3 |
| 5 | Bộ test múi giờ / chuyển năm | 3 |
| 6 | Test bộ phân tích bằng dữ liệu mẫu đã lưu (FAMI, iCTSV, `_vnd` + bảng SIS, MOOC, `course_detail`) | 6 |
| 7 | Test luồng song song cho `events.json` / `alerts.json` (đi kèm sửa D-1 / D-3) | 4 |
| 8 | CI: ruff, `compileall -W error`, ngưỡng độ phủ tăng dần từ 23%, `dotnet build`, PSScriptAnalyzer, lượt không UTF-8 mode | 3 |

---

## 7. Nợ kỹ thuật

### N-1. File quá dài, trộn trách nhiệm — **Vừa** · [Đọc] · 30–40 h (không gấp)

**`copilot_app.py` (1.441 dòng):**

| Dòng | Trách nhiệm |
|---|---|
| 16–58 | Cấu hình + dữ liệu cá nhân viết cứng |
| 60–84 | Kho trạng thái Inbox |
| 86–114 | Danh mục thư mục |
| 116–209 | Tiện ích HTTP |
| 211–366 | Agent xếp tài liệu |
| 368–615 | Sao lưu, chống trùng, LLM so phiên bản |
| 617–685 | Theo dõi Uni-Documents |
| 687–853 | Đồng bộ trường + mail |
| 855–926 | Các vòng nền |
| 928–1413 | Handler HTTP: ~65 route viết thành chuỗi `if` dài ~485 dòng |
| 1416–1441 | Khởi động 10 luồng |

- **Đề xuất tách:** `inbox_store`, `sorter`, `backup_sync`, `scheduler` (một hàm `slot_loop` chung thay hai vòng gần như giống hệt ở `copilot_app.py:745-758` và `:838-852`), `routes/` dạng bảng route, `settings`. 18–22 h.
- **`build.py` (1.404 dòng):** ~12 khối JavaScript nhúng thành chuỗi Python, gộp vào một workflow khổng lồ. Nên tách JS ra file riêng để lint/test được. 8–10 h.
- **`ui/index.html` (2.322 dòng):** CSS (`ui/index.html:16-532`) và JS (`:779-2320`) viết inline. Tách file là điều kiện để bật CSP (B-8). 6–8 h.

### N-2. Code trùng lặp — **Thấp/Vừa** · [Đọc]

| Nhóm trùng | Vị trí | Rủi ro |
|---|---|---|
| Định nghĩa `TZ = UTC+7` | 21 bản (vd `academic.py:23`, `fami.py:19`, `deadlines.py:21`, `mooc.py:19`, `speech_gate.py:42`) | Thấp |
| `norm()` giống hệt | `academic.py:37`, `deadlines.py:35`, `dupscan.py:25`, `mail_events.py:27`, `teams_files.py:25` | Sửa một chỗ, quên chỗ khác |
| Client Tika | `copilot_app.py:212`, `course_detail.py:46-50`, `tuition_rules.py:68` | Thấp |
| Đọc `.copilot-secret` | 3 cách khác nhau (`copilot_app.py:25`, `phone_link.py:17`, `speech_gate.py:457`) | **Đã gây B-7a** |
| Đọc biến môi trường User | `winreg` (`mail_events.py:56`) và PowerShell (`n8napi.py:7`) | Thấp |
| `_load` / `_save` JSON | ~12 / ~7 bản, chỉ 3 bản nguyên tử | **Gốc của D-1** |
| Khởi động Playwright | 6 bản (`school_fetch.py:356`, `school_mail.py:78`, `teams_fetch.py:143`, `mooc.py:48`, `fami.py:33`, `ctsv_live.py:60`) | Gốc của H-1 |
| File trùng | `speech-gate/audio_io.py` = `speech-gate/bakeoff/audio_io.py`; `addons/*.zip` = thư mục bên cạnh (chỉ khác CRLF) | Lệch nhau khi sửa |

### N-3. Giá trị viết cứng — **Vừa** · [Đọc]

| Giá trị | Vị trí | Hậu quả |
|---|---|---|
| **M-1. Năm nhập học 2026** | `school_sync.py:43`, `:49` | Sinh viên khoá khác bị đổi mã kỳ sai toàn bộ (hoặc ra `None` ngoài S1–S8), nên kỳ của môn, TKB (`:122`), CTĐT đều lệch. **Chặn việc dùng cho người khác.** Đưa vào `config.json` (`"khoa": 2026`). 1–2 h |
| **L-5. Máy chủ ntfy** | `phone_link.py:58`, `:158`; `phone_sched.py:99`, `:107` viết cứng `https://ntfy.sh`, trong khi `phone_link.py:82` và `alerts.py:198` đọc khoá `server` | Ai tự dựng ntfy riêng thì **hỏng một nửa**: thông báo thường đi server riêng, còn nút bấm, lịch hẹn và kênh lệnh vẫn đi `ntfy.sh` |
| Tên model | `copilot_app.py:29`, `speech_gate.py:38`, `:177`, `pdf_translate.py:61`, `build.py:412`, `:414`, `:562`, `:605`, `mail_events.py:51` | Đổi model phải sửa 9 chỗ |
| Cổng dịch vụ | :5678 viết hai kiểu (`127.0.0.1` ở `copilot_app.py:26`; `localhost` ở `n8napi.py:3`); :1234, :9998, :8888, :8340, :8350, :9333 | Thấp |
| Dữ liệu môn học cá nhân | `copilot_app.py:35-54` (`COURSE_FOLDERS`, `COURSE_HINTS`, `SKIP_UNDER`) | Người khác phải sửa code |
| Đường dẫn Windows | `work_open.py:23` (`C:\Program Files\...chrome.exe`), `pdf_translate.py:15` | Thấp |
| User-Agent | `school_fetch.py:24` (`Chrome/140`) | Có thể bị trường chặn khi UA quá cũ |
| Hằng số chu kỳ | 280 s, `SLOT_LATE` 120, `SYNC_EVERY` 60, `EVERY_MIN` 4, `MAX_AGE` 60, timeout 420 | Nên gom vào `config.schedule` |

### N-4. Chú thích lỗi thời, code chết — **Thấp** · [Đọc] + [Chạy]

- **Chú thích sai với code:**
  - `copilot_app.py:12` ghi model xếp tài liệu là `qwen3-8b`, code dùng `qwen3-14b` (`:29`).
  - `copilot_app.py:799` và `ctsv_live.py:2` ghi "CTSV mỗi giờ", thực tế mỗi lượt (H-1).
  - `addons/low-end-priority/audio_priority.py:10` ghi "trả về NORMAL", code đặt BELOW_NORMAL; `:11` nhắc `ram_gate`, không có trong repo.
  - Docstring đầu `copilot_app.py:1-10` liệt kê 7 trong ~65 endpoint.
- **Sơ đồ:** `docs/gen_map.py:241`, `:381` ghi chat dự phòng là qwen3-8b (code: 14B, `build.py:414`), nên `docs/Map.svg` / `Map.png` sai theo.
- **Code chết [Chạy]:**
  - `stale_filter._years()` (`stale_filter.py:16`) không được gọi ở đâu;
  - `build.py:143-144` có vòng `for ...: pass`;
  - `speech-gate/bakeoff/*` là script thử một lần, có ngày viết cứng.
- **Dữ liệu chỉ tăng:** `inbox_state.json` (`items`) và `mail_events` (`processed`) không bao giờ cắt bớt; mỗi lần cập nhật một mục lại ghi lại toàn bộ file.

---

## 8. Kiểm lại danh sách "chưa sửa" của PR #2

| # | Vấn đề | Kết luận | Mức | Nhãn | Chi tiết | Công sức |
|---|---|---|---|---|---|---|
| L-1 | Race nút bấm: `process` và `ack` | **Có thật**, khe vài giây | Vừa | [Chạy] | D-3 | 4–6 h |
| L-2 | Race `tick` và `ack` | **Có thật** | Thấp/Vừa | [Chạy] | D-5 | 1 h |
| L-3 | `inbox_state.json` đọc ngoài khoá | Linux: không tái hiện được. Windows: có thể `PermissionError` | Thấp/Vừa | [Chạy] + [Suy luận] | D-7. **Lỗi nạp hai lần D-2 nặng hơn và chắc chắn hơn** | 1 h |
| L-4 | `.copilot-secret` hai kiểu mã hoá | **Có thật** khi file có BOM / UTF-16. Làm chết worker cổng chép lời | Vừa | [Chạy] cơ chế | B-7a, O-3 | 0,5 h |
| L-5 | ntfy viết cứng | **Có thật**, chỉ ảnh hưởng người tự dựng ntfy | Thấp | [Đọc] | N-3 | 1 h |
| L-6 | Giờ `HH:MM:SS` | **Có thật**: `"07:00:00"` ném `ValueError` ở `mail_events.py:313`. Đổi phòng của cùng chặng không được ghi, chặng không bao giờ "xong" nên thử lại mỗi 5 phút. `diff_stages` báo thay đổi giả "07:00 → 07:00:00" thành cảnh báo đỏ | Thấp/Vừa | [Chạy] | Chuẩn hoá `gio` / `ngay` ngay khi đọc đầu ra Gemini | 1 h |
| L-7 | Thiếu timeout `N8N_API_KEY` | **Có thật** nhưng hiếm: chỉ khi PowerShell treo, lúc import `n8napi` (`n8napi.py:4-10`). Module này chỉ được dùng bởi script build và `lecture_monitor` (import trong hàm) | Thấp | [Đọc] | Thêm `timeout=15`, đọc bằng `winreg` như `mail_events.py:56` | 0,25 h |
| L-8 | Chặn `..` | **Có thật** (lọt dấu `/`), nhưng trang lạ không khai thác được | Vừa/Thấp | [Chạy] | B-5 | 1 h |
| L-9 | SSRF qua chuyển hướng | **Có thật**, nhưng chỉ là GET mù | Thấp | [Chạy] + [Đọc] | B-6 | 1–2 h |

### Thêm `sort_job`, đã nêu ở PR #2 dưới dạng nghi vấn — **Có thật**, **Vừa** · [Chạy] · 1 h

- **Bằng chứng:**
  - `copilot_app.py:339`: thư mục con `new_subfolder` **bị bỏ qua khi đã tồn tại**, nên file rơi vào gốc thư mục môn.
  - `copilot_app.py:355`: so chuỗi `target.startswith(h_folder)`, nên "…Giải Tích II" được coi là **nằm trong** "…Giải Tích I". Agent chạy thử: file có từ khoá MI1111 bị xếp vào Giải Tích II ở độ tin cậy 0,8, không có ghi chú cảnh báo. I/III và II/III cũng vậy.
- **Đề xuất:**
  - `target == h or target.startswith(h + os.sep)`;
  - luôn ghép thư mục con loại tài liệu nếu hợp lệ.

---

## Phụ lục: tổng công sức theo nhóm (ước tính)

| Nhóm | Giờ |
|---|---|
| 1. Bảo mật (B-1 … B-8) | 8–12 |
| 2. Độ bền khi trường đổi giao diện (R-1 … R-3 + giám sát sức khoẻ nguồn) | 20–40 |
| 3. Đồng thời / dữ liệu (D-1 … D-7) | 14–20 |
| 4. Hiệu năng (H-1 … H-3) | 8–14 |
| 5. Mất mạng / tắt máy (O-2 … O-6) | 8–10 |
| 6. Kiểm thử (kế hoạch 8 mục) | ~34 |
| 7. Nợ kỹ thuật (N-1 … N-4) | 35–45 |
| 8. Danh sách cũ (đã tính trong các nhóm trên) | — |

**Cách làm review này:**
- Năm phạm vi được rà song song (bảo mật; độ bền; đồng thời + mất mạng; hiệu năng + nợ kỹ thuật; kiểm thử).
- Các phát hiện ở top 10 và các mục **Cao** đã được đọc lại trực tiếp trong code trước khi đưa vào báo cáo.
- Script thử nghiệm chạy trên bản sao repo với cấu hình và khoá giả; không script nào nằm trong repo.
