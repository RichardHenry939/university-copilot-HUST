# Khoá giờ ngủ của UC (night lock + nap lock)

Hai khoá là một phần của University Copilot, nhưng chạy **riêng** bằng quyền quản trị (sửa file `hosts` và chính sách trình duyệt — tiến trình UC chạy bằng quyền thường nên không làm được). UC tính lịch, khoá đọc từ UC.

| Khoá | Khi nào | Chặn gì | Đọc gì từ UC |
|---|---|---|---|
| `night-lock.ps1` | 22:00–06:00 mỗi ngày (cố định); ngoài giờ đó: chế độ tập trung của Ví thời gian | Đêm: mọi mạng xã hội + game (IFEO + tắt tiến trình + tải lại tab đang mở). Tập trung: như đêm nhưng chừa YouTube thường và Messenger, chặn Shorts | `school/focus.json` (tín hiệu tập trung, tự hết hạn theo giờ trong file) |
| `nap-lock.ps1` | Phần ngủ trưa (13:00–15:00) mà đồng hồ 24 giờ của UC tô vàng — buổi học / thi chiếm chỗ nào thì mất chỗ đó (lab 12:30–17:30 = không ngủ trưa, không khoá) | Mọi mạng xã hội **kể cả YouTube**, chỉ chừa Messenger; tắt game | `school/nap.json` (UC ghi mỗi phút, `nap.py`) |

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
- Tab mở sẵn trước giờ khoá trưa có thể xem tiếp tới khi tải lại (khoá đêm có tải lại tab, khoá trưa chưa).
