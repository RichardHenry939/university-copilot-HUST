# Khoá giờ ngủ của UC (night lock + nap lock)

Hai khoá là một phần của University Copilot, nhưng chạy **riêng** bằng quyền quản trị (sửa file `hosts` và chính sách trình duyệt — tiến trình UC chạy bằng quyền thường nên không làm được). UC tính lịch, khoá đọc từ UC.

| Khoá | Khi nào | Chặn gì | Đọc gì từ UC |
|---|---|---|---|
| `night-lock.ps1` | 22:00–06:00 mỗi ngày (cố định); ngoài giờ đó: chế độ tập trung của Ví thời gian | Đêm: mọi mạng xã hội + game (IFEO + tắt tiến trình + tải lại tab đang mở). Tập trung: như đêm nhưng chừa Messenger; trang YouTube chặn bằng chính sách trình duyệt, không chặn trong `hosts` để trình phát ẩn của UC (youtube-nocookie.com) chạy được; facebook.com + instagram.com bị chặn hẳn (đường đăng nhập cho Muse đã gỡ ở v1.00.58) | `school/focus.json` (tín hiệu tập trung, tự hết hạn theo giờ trong file) |
| `nap-lock.ps1` | Phần ngủ trưa mà đồng hồ 24 giờ của UC tô vàng: 2 giờ, mặc định 13:00–15:00; buổi học / thi chen vào thì dời sang chỗ trống gần nhất trong 08:00–18:00 (lab 12:30–17:30 = ngủ 10:00–12:00); không còn chỗ thì mất phần bị chiếm | Mọi mạng xã hội **kể cả YouTube**, chỉ chừa Messenger; tắt game | `school/nap.json` (UC ghi mỗi phút, `nap.py`) |

An toàn khi UC tắt: `nap.json` không có / khác ngày / cũ quá 10 phút -> khoá trưa không khoá. Khoá đêm không phụ thuộc UC.
Hai khoá không giẫm nhau: dấu riêng trong `hosts`, mục chính sách trình duyệt riêng (khoá trưa dùng số 501 trở lên).

## Cài

1. Chép hai script vào một thư mục **chỉ bạn biết** (giữ kín: biết chỗ thì lúc nửa đêm rất dễ tự tắt). Nếu đặt ngoài thư mục UC, sửa đường dẫn `focus.json` / `nap.json` trong script.
2. Đổi tên tác vụ, dấu `hosts` (`# UC-NIGHT-LOCK`, `# UC-NAP-LOCK`) và tên mutex thành tên của riêng bạn.
3. Tạo hai tác vụ Task Scheduler: chạy khi đăng nhập, **Run with highest privileges**, hành động
   `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "<thư mục>\night-lock.ps1"` (tương tự cho `nap-lock.ps1`).
4. Thêm đường dẫn game của bạn vào `$KillExact` / `$KillPrefix`; game đặt shortcut trong `Desktop\Game` thì khoá đêm tự nhận.

## Thử không thay đổi gì

```powershell
powershell -ExecutionPolicy Bypass -File night-lock.ps1 -DryRun -FakeTime 23:00 -HostsPath "$env:TEMP\hosts-test"
powershell -ExecutionPolicy Bypass -File nap-lock.ps1 -DryRun -FakeTime 14:00 -HostsPath "$env:TEMP\hosts-test" -NapFile <file nap.json thử>
```

## Giới hạn

- Chỉ chặn trên máy tính. Điện thoại (kể cả máy ảo Android) chưa được chặn — đang là việc tiếp theo.
- Tab mở sẵn trên trang bị chặn: khoá đêm tự tải lại mỗi 5 phút tới 22:30 (tập trung: tab đang hiện, mỗi 30 giây), trong tiến trình con, quá 60 giây thì dừng vì UI Automation không có giới hạn thời gian và từng làm treo cả vòng lặp. Khoá trưa không quét tab (từ v1.00.65). Cần tác vụ chạy trong phiên đăng nhập của người dùng (UI Automation không thấy cửa sổ của phiên khác).
- Chính sách trình duyệt không được ép tải lại: Chrome tự đọc lại theo chu kỳ riêng, nên đầu giờ khoá có thể chậm vài phút. UC không gõ phím vào Chrome.
- `morning-cleanup.sample.ps1` là script mẫu: chạy lúc 06:01 và 06:06 (hai trigger Task Scheduler), kiểm chặn còn sót sau giờ đêm, khởi động lại khoá rồi mới dọn. Không được UC cài, phải sửa tham số theo máy bạn.
