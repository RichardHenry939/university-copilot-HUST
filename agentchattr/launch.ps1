param([switch]$NoBrowser)
# AgentChattr launcher: start server neu chua chay -> doi port -> mo browser UI.
$root = $PSScriptRoot
$pyw  = (Get-Command pythonw.exe).Source

function Test-Port([int]$port) {
  $c = New-Object Net.Sockets.TcpClient
  try { $c.Connect('127.0.0.1', $port); $true } catch { $false } finally { $c.Close() }
}

if (-not (Test-Port 8300)) {
  Start-Process -FilePath $pyw -ArgumentList 'launcher_w.py' -WorkingDirectory $root -WindowStyle Hidden
  $ok = $false
  foreach ($i in 1..30) {
    Start-Sleep -Milliseconds 700
    if (Test-Port 8300) { $ok = $true; break }
  }
  if (-not $ok) { exit 1 }
}

# (Claude 2026-10-02) Mo bang Chrome App "agentchattr" (cua so rieng), khong mo tab Chrome moi.
if (-not $NoBrowser) { Start-Process 'C:\Program Files\Google\Chrome\Application\chrome_proxy.exe' -ArgumentList '--profile-directory=Default', "--app-id=$env:AC_CHROME_APP_ID" }
