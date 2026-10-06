# Giữ phiên Google của NotebookLM (Claude, sửa 05/10):
#  refresh -> lỗi thì login bằng hồ sơ Chrome riêng (đã đăng nhập thì tự đóng ngay) -> vẫn lỗi (Google bắt đăng nhập tay)
#  -> mở login_loop.ps1: thông báo + cửa sổ ở lại đến khi đăng nhập (đóng là mở lại) -> ghi keepalive.log
$N = "$env:APPDATA\uv\tools\notebooklm-py\Scripts\notebooklm.exe"
$dir = $PSScriptRoot; $log = "$dir\keepalive.log"
function Ok { $j = & $N auth check --test --json 2>$null | Out-String; try { ($j | ConvertFrom-Json).checks.token_fetch -eq $true } catch { $false } }
function Toast($title, $text) {
  try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $t = $x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode($title)) | Out-Null; $t.Item(1).AppendChild($x.CreateTextNode($text)) | Out-Null
    $app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))
  } catch {}
}
$how = 'refresh'
& $N auth refresh 2>$null | Out-Null
if (-not (Ok)) {
  $how = 'login (im lặng)'
  & $N login --browser chrome --browser-timeout 45 2>$null | Out-Null     # phiên Chrome còn -> tự lưu, tự đóng
  if (-not (Ok)) {   # Google bắt đăng nhập tay -> vòng đăng nhập riêng (ở lại đến khi xong; mutex: chỉ một bản)
    $how = 'mở vòng đăng nhập (login_loop.ps1)'
    Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'login_loop.ps1')
  }
}
$res = if (Ok) { 'OK' } else { 'LỖI: cần đăng nhập Google lại bằng tay (notebooklm login --browser chrome)' }
Add-Content -Path $log -Value ("{0:yyyy-MM-dd HH:mm} {1} ({2})" -f (Get-Date), $res, $how) -Encoding utf8
$lines = Get-Content $log -Tail 300; Set-Content $log $lines -Encoding utf8
