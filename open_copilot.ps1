# Mở University Copilot: bật web app nếu chưa chạy rồi mở giao diện.
# -NoBrowser: dùng cho Task Scheduler lúc đăng nhập Windows (chỉ bật dịch vụ).
# Các dịch vụ phụ (LM Studio :1234, cổng Gemini :8350, n8n :5678 trong Docker) cài riêng — xem README.
param([switch]$NoBrowser)
$ErrorActionPreference = 'SilentlyContinue'
function Up([int]$port) { $c = New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1', $port); $true } catch { $false } finally { $c.Close() } }

if (-not (Up 8320)) {
  $py = (Get-Command pythonw.exe).Source
  Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList (Join-Path $PSScriptRoot 'copilot_app.py') -WorkingDirectory $PSScriptRoot
  foreach ($i in 1..20) { Start-Sleep -Milliseconds 400; if (Up 8320) { break } }
}
if (-not (Up 5678)) { Write-Host 'n8n (cổng 5678) chưa chạy — bật Docker Desktop / n8n.' }
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8320/' }
