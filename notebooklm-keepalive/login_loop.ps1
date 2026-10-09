# Google bắt đăng nhập tay (Claude 05/10; viết lại 09/10 sáng và 09/10 chiều).
# QUY TẮC (chủ dự án): cùng một lúc CHỈ CÓ 1 cửa sổ đăng nhập. Khi số cửa sổ về 0 mới mở lại đúng 1 (sau 60 giây), không bao giờ dồn nhiều cửa sổ.
# Tạm dừng: tạo file TAM-DUNG.txt cạnh script này (vd lúc chưa đăng nhập được vì xác thực hai bước) -> không mở cửa sổ nào cho tới khi xoá file.
#
# Vì sao không dùng "notebooklm login" để chờ người: Google đổi sang notebook.google.com, trang mở được cả khi CHƯA đăng nhập, nên lệnh in
# "Already logged in." sau ~4 giây rồi lưu phiên không hợp lệ. Cách làm: TỰ mở Chrome thật, đúng hồ sơ notebooklm, tại trang đăng nhập Google;
# khi cửa sổ đóng thì chạy "login" MỘT lần (lúc này có cookie thật nên lưu được phiên hợp lệ).
# Bài học 09/10: mở Chrome nhiều lần vào cùng hồ sơ = thêm cửa sổ vào tiến trình cũ; tắt Chrome bằng Stop-Process = lần sau nó KHÔI PHỤC lại các cửa sổ cũ
# (đã gặp 9 cửa sổ chồng nhau) -> chỉ đóng cửa sổ bằng WM_CLOSE, mở Chrome với --disable-background-mode và các cờ chống khôi phục.
$N = "$env:APPDATA\uv\tools\notebooklm-py\Scripts\notebooklm.exe"
$log = Join-Path $PSScriptRoot 'keepalive.log'
$pause = Join-Path $PSScriptRoot 'TAM-DUNG.txt'
$profileDir = "$env:USERPROFILE\.notebooklm\profiles\default\browser_profile"
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
$signin = 'https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fnotebooklm.google.com%2F'   # (service=notebooklm trả HTTP 400)
$m = New-Object System.Threading.Mutex($false, 'Local\UC_NotebookLM_Login')
if (-not $m.WaitOne(0)) { exit }   # đã có vòng đăng nhập đang chạy
Add-Type @"
using System; using System.Text; using System.Collections.Generic; using System.Runtime.InteropServices;
public class NlmWin {
  delegate bool EP(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EP p, IntPtr l);
  [DllImport("user32.dll")] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  // cửa sổ Chrome đang hiện thuộc các pid cho trước, từ trên xuống dưới theo thứ tự z
  public static List<IntPtr> Of(HashSet<uint> pids) {
    var r = new List<IntPtr>();
    EnumWindows((h, l) => { uint pid; GetWindowThreadProcessId(h, out pid); if (!pids.Contains(pid) || !IsWindowVisible(h)) return true;
      var c = new StringBuilder(64); GetClassName(h, c, 64); var t = new StringBuilder(8); GetWindowText(h, t, 8);
      if (c.ToString().StartsWith("Chrome_WidgetWin") && t.Length > 0) r.Add(h); return true; }, IntPtr.Zero);
    return r; }
  public static void Close(IntPtr h) { PostMessage(h, 0x0010, IntPtr.Zero, IntPtr.Zero); }
}
"@
function Ok { $j = & $N auth check --test --json 2>$null | Out-String; try { ($j | ConvertFrom-Json).checks.token_fetch -eq $true } catch { $false } }
function Toast {
  try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $t = $x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode('NotebookLM cần đăng nhập Google lại')) | Out-Null
    $t.Item(1).AppendChild($x.CreateTextNode('Đăng nhập trong cửa sổ Chrome đang mở rồi đóng nó lại. Chưa đăng nhập được: tạo file TAM-DUNG.txt.')) | Out-Null
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show([Windows.UI.Notifications.ToastNotification]::new($x))
  } catch {}
}
function ProfileChrome { @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -match [regex]::Escape($profileDir) -and $_.CommandLine -notmatch '--type=' }) }
function LoginWindows { $ids = New-Object 'System.Collections.Generic.HashSet[uint32]'; foreach ($p in (ProfileChrome)) { [void]$ids.Add([uint32]$p.ProcessId) }; if ($ids.Count) { @([NlmWin]::Of($ids)) } else { @() } }
function Note($s) { Add-Content $log ("{0:yyyy-MM-dd HH:mm} {1}" -f (Get-Date), $s) -Encoding utf8 }
$asked = $false; $reopen = $false
try {
  while (-not (Ok)) {
    if (Test-Path $pause) { Start-Sleep -Seconds 30; continue }   # đang tạm dừng: không mở gì
    $w = LoginWindows
    if ($w.Count -eq 0) {
      if ($reopen) { Start-Sleep -Seconds 60; if ((Ok) -or (Test-Path $pause)) { continue } }   # vừa đóng hết: chờ 1 phút rồi mới mở lại đúng 1
      Start-Process $chrome -ArgumentList "--user-data-dir=`"$profileDir`"", '--no-first-run', '--disable-background-mode', '--hide-crash-restore-bubble', '--disable-session-crashed-bubble', '--new-window', $signin
      $reopen = $true; Start-Sleep -Seconds 8
      if (-not $asked) { $asked = $true; Toast; Note 'CHỜ: Google bắt đăng nhập tay — đã mở đúng 1 cửa sổ Chrome; đăng nhập xong thì đóng nó (chưa đăng nhập được: tạo file TAM-DUNG.txt)' }
    }
    $t1 = Get-Date
    while ((LoginWindows).Count -ge 1) {
      $w = LoginWindows; for ($i = 1; $i -lt $w.Count; $i++) { [NlmWin]::Close($w[$i]) }   # thừa -> đóng nhẹ (WM_CLOSE), giữ đúng 1 cửa sổ trên cùng
      if (Test-Path $pause) { foreach ($h in (LoginWindows)) { [NlmWin]::Close($h) } }       # tạm dừng -> đóng nốt, không mở lại
      Start-Sleep -Seconds 4
    }
    if (((Get-Date) - $t1).TotalSeconds -ge 30 -and -not (Test-Path $pause)) {   # cửa sổ sống đủ lâu = bạn đã thao tác -> lưu phiên (cần hồ sơ Chrome đã đóng hẳn)
      for ($i = 0; $i -lt 10 -and (ProfileChrome).Count; $i++) { Start-Sleep -Seconds 3 }
      if (-not (ProfileChrome).Count) { & $N login --browser chrome --browser-timeout 120 2>$null | Out-Null }
    }
    Start-Sleep -Seconds 2
  }
  Note ("OK ({0})" -f $(if ($asked) { 'bạn đã đăng nhập lại' } else { 'tự khôi phục, không cần bạn' }))
} finally { $m.ReleaseMutex() }
