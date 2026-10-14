# Add-on "network-guard": phát hiện mạng tắt / bật (University Copilot)

> Hợp với máy học bằng wifi hay chập chờn, hoặc máy kiêm homelab bán thời gian (lỡ tắt máy rồi bấm Hủy, dịch vụ chết một nửa).

## Add-on làm gì

Kiểm mạng **mỗi 1 phút** (2 yêu cầu rất nhỏ tới Google — gần như không tốn CPU, RAM hay dung lượng):

| Tình huống | Add-on làm |
|---|---|
| **Có mạng** | Dịch vụ UC nào đang tắt (UC, n8n, cổng chép lời, máy ghi, cổng Gemini) → tự chạy `open_copilot.ps1 -NoBrowser` bật lại. Tối đa 1 lần / 5 phút. |
| **Mất mạng 3 phút liên tiếp** | Tạm dừng việc cần mạng: UC bỏ qua các lượt đồng bộ trường / mail / tài liệu (giống lúc máy ngủ); **n8n được đóng băng** (`docker pause`) nguyên trạng. |
| **Có mạng lại** | Gỡ trạng thái mất mạng, n8n chạy tiếp (`docker unpause`) — trong vòng 1 phút. Không mất workflow hay dữ liệu. |

Trong lúc mất mạng **vẫn chạy**: UC, máy ghi bài giảng, model AI trên máy, cổng chép lời (đều chạy trên máy).
Ngưỡng 3 phút để wifi rớt vài giây không làm hệ thống bật/tắt liên tục.

## Cài

1. Chép `netguard.py` vào thư mục UC (cạnh `copilot_app.py` và `open_copilot.ps1`).
2. Tạo task chạy mỗi phút (PowerShell, thay đường dẫn cho đúng máy bạn):

```powershell
$uc = 'C:\duong\dan\toi\university-copilot'
$a = New-ScheduledTaskAction -Execute 'pythonw.exe' -Argument "`"$uc\netguard.py`"" -WorkingDirectory $uc
$t = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName 'UC Mang' -Action $a -Trigger $t -Settings $s
```

3. Khởi động lại UC (UC đọc cờ `OFFLINE.flag` từ v1.00.22 — không có add-on thì cờ không bao giờ xuất hiện, UC chạy như cũ).

Kiểm tra: xem `school/netguard.log` — có dòng mỗi khi mất / có mạng hoặc bật lại dịch vụ.

## Gỡ

`Unregister-ScheduledTask -TaskName 'UC Mang'`, xoá `netguard.py` và `OFFLINE.flag` (nếu còn). Nếu lúc gỡ n8n đang bị đóng băng: `docker unpause n8n`.

## Giới hạn (nói thật)

- Chỉ kiểm "ra được Internet tới Google", **không đo tốc độ**: wifi có mà rất chậm vẫn tính là có mạng.
- Lúc mất mạng, n8n đóng băng **cả** luồng không cần mạng (gần như mọi luồng n8n của UC đều gọi Google / Notion nên chấp nhận).
- Nếu bạn vừa bấm Dừng ghi bài đúng lúc mất mạng, bản ghi gửi sang n8n có thể phải chờ tới khi có mạng lại.
- Đổi vị trí cờ: đặt biến môi trường `UC_OFFLINE_FLAG` giống nhau cho cả UC và task.
