$ErrorActionPreference = 'Stop'

$healthUrl = 'http://127.0.0.1:5681/health'
$recorderExe = Join-Path $PSScriptRoot 'bin\Release\net8.0-windows\LectureRecorderCompanion.exe'

try {
    Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 | Out-Null
    exit 0
}
catch {
    # The companion is not running yet.
}

Start-Process -FilePath $recorderExe `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden
