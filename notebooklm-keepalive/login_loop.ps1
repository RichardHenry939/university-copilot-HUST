# Google bắt đăng nhập tay (Claude 05/10, theo yêu cầu): cửa sổ đăng nhập Chrome Ở LẠI đến khi đăng nhập xong hoặc tắt máy.
# Bị đóng -> mở lại ngay. Chỉ một bản chạy cùng lúc (mutex), nên lượt giữ phiên 20 phút không mở thêm cửa sổ.
$N = "$env:APPDATA\uv\tools\notebooklm-py\Scripts\notebooklm.exe"
$log = Join-Path $PSScriptRoot 'keepalive.log'
$m = New-Object System.Threading.Mutex($false, 'Local\UC_NotebookLM_Login')
if (-not $m.WaitOne(0)) { exit }   # đã có vòng đăng nhập đang chạy
function Ok { $j = & $N auth check --test --json 2>$null | Out-String; try { ($j | ConvertFrom-Json).checks.token_fetch -eq $true } catch { $false } }
try {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
  $x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  $t = $x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode('NotebookLM cần đăng nhập Google lại')) | Out-Null
  $t.Item(1).AppendChild($x.CreateTextNode('Cửa sổ Chrome sẽ ở lại (đóng là mở lại) cho đến khi bạn đăng nhập.')) | Out-Null
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show([Windows.UI.Notifications.ToastNotification]::new($x))
} catch {}
Add-Content $log ("{0:yyyy-MM-dd HH:mm} CHỜ: Google bắt đăng nhập tay — đã mở cửa sổ, chờ đến khi đăng nhập" -f (Get-Date)) -Encoding utf8
try {
  while (-not (Ok)) {
    & $N login --browser chrome --browser-timeout 86400 2>$null | Out-Null   # trả về khi đăng nhập xong / cửa sổ bị đóng
    Start-Sleep -Seconds 2
  }
  Add-Content $log ("{0:yyyy-MM-dd HH:mm} OK (bạn đã đăng nhập lại)" -f (Get-Date)) -Encoding utf8
} finally { $m.ReleaseMutex() }
