﻿# AgentChattr.ps1 — cửa vào DUY NHẤT của Hội đồng AI (AgentChattr). (Claude 2026-10-03, thay Bat-4-ghe-AI.ps1)
#
#   Shortcut "agentchattr - daily" (Desktop): bật máy chủ phòng chat + 4 ghế nếu chưa có -> mở Chrome App.
#                                             Ghế nào đã có thì bỏ qua; cửa sổ ghế tự ẩn khi ghế đã vào phòng.
#   -AtLogon  (Task Scheduler "AgentChattr - 4 ghe AI"): như trên nhưng không mở app, chạy ẩn hoàn toàn.
#   -Show / -Hide : hiện lại (15 phút) / ẩn ngay cửa sổ các ghế — shortcut "Hien ghe AI" trong thư mục này.
#   -NoApp        : bật phòng + ghế nhưng không mở Chrome App (shortcut "Bat 4 ghe AI" trong thư mục này).
#
# 4 ghế: Claude, Codex, Gemini (CLI, cửa sổ console ẩn khỏi màn hình) + Local AI (LM Studio qwen3-14b).
# Bộ giữ ghế: <thư mục agentchattr>\seat_keeper.py — tự bật lại ghế rớt, ghi lý do OFF lên phòng chat.
param([switch]$AtLogon, [switch]$Show, [switch]$Hide, [switch]$NoApp)

$root  = $PSScriptRoot   # thư mục agentchattr (đặt file này trong đó)
$py    = Join-Path $root '.venv\Scripts\python.exe'
$pyw   = Join-Path $root '.venv\Scripts\pythonw.exe'
$pysrv = (Get-Command pythonw.exe).Source
$appId = $env:AC_CHROME_APP_ID   # id Chrome App của phòng chat trên máy bạn (cài trang 127.0.0.1:8300 thành app rồi lấy id ở chrome://apps)
$log   = Join-Path $root 'seat-keeper.log'
$env:PYTHONIOENCODING = 'utf-8'

function Log($m) { Add-Content -LiteralPath $log -Value ("{0} [AgentChattr.ps1] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) -Encoding UTF8 }
function Test-Port([int]$port) {
  $c = New-Object Net.Sockets.TcpClient
  try { $c.Connect('127.0.0.1', $port); $true } catch { $false } finally { $c.Close() }
}

if ($Show) { & $py "$root\seat_keeper.py" --show; exit 0 }
if ($Hide) { & $py "$root\seat_keeper.py" --hide; exit 0 }

# 1) Máy chủ phòng chat (8300). run.py giữ khoá data\server.lock nên bật trùng cũng chỉ 1 bản sống.
if (-not (Test-Port 8300)) {
  Log 'máy chủ phòng chat chưa chạy -> bật'
  Start-Process -FilePath $pysrv -ArgumentList 'launcher_w.py' -WorkingDirectory $root -WindowStyle Hidden
  # lúc mới đăng nhập máy còn nặng: chờ tới 3 phút (bản cũ chỉ chờ 21 s rồi bỏ cuộc, không bật ghế)
  $deadline = (Get-Date).AddMinutes(3)
  while (-not (Test-Port 8300) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
  if (-not (Test-Port 8300)) { Log 'LỖI: máy chủ không lên sau 3 phút (xem ac-stderr.log)'; exit 1 }
}

# 2) Bộ giữ ghế: chưa chạy thì tự khởi động; --kick = quét ghế, ghế thiếu bật NGAY, ghế đã có bỏ qua
Start-Process -WindowStyle Hidden -FilePath $pyw -ArgumentList "`"$root\seat_keeper.py`"", '--kick' -WorkingDirectory $root
Log ("đã gọi bộ giữ ghế (--kick){0}" -f $(if ($AtLogon) { ', lúc đăng nhập' } else { '' }))

# 3) Mở phòng chat bằng Chrome App (cửa sổ riêng, không mở tab Chrome mới)
if (-not $AtLogon -and -not $NoApp) {
  Start-Process 'C:\Program Files\Google\Chrome\Application\chrome_proxy.exe' -ArgumentList '--profile-directory=Default', "--app-id=$appId"
}
