# Sample watchdog for the night lock: run it at 06:01 and again at 06:06 (two Task Scheduler triggers, highest privileges).
# Why: a hung lock loop once left social sites blocked after 06:00. This looks at what is really on the machine:
#   - 06:01 pass: if the night block is still there, restart the lock task and let it clean up by itself.
#   - 06:06 pass (-Final): if it is STILL there, remove only the lines / entries the lock owns, and log it.
# It never touches anything during the night (exits before 06:00) or while focus mode is valid (the block is wanted then).
# Limit: this is a template, not installed by UC. Set -TaskName, -Marker and -FocusFile to match your own install.
# Test without changing anything:
#   powershell -ExecutionPolicy Bypass -File morning-cleanup.sample.ps1 -DryRun -Final -HostsPath "$env:TEMP\hosts-test"

param(
    [switch]$DryRun,
    [switch]$Final,
    [string]$TaskName = 'YourNightLockTask',
    [string]$Marker = '# UC-NIGHT-LOCK',
    [string]$HostsPath = (Join-Path $env:WINDIR 'System32\drivers\etc\hosts'),
    [string]$FocusFile = (Join-Path $PSScriptRoot '..\school\focus.json'),
    [string]$LogFile = (Join-Path $PSScriptRoot 'morning-cleanup.log')
)

function Write-Log([string]$msg) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    if ($DryRun) { Write-Output $line } else { Add-Content -Path $LogFile -Value $line }
}

$now = (Get-Date).TimeOfDay
if (-not $DryRun -and ($now -ge [TimeSpan]'22:00' -or $now -lt [TimeSpan]'06:00')) { Write-Log 'night window, nothing to do'; exit }

try {
    $j = Get-Content $FocusFile -Raw -ErrorAction Stop | ConvertFrom-Json
    if ($j.focus -and $j.until -and [DateTimeOffset]::Parse([string]$j.until, [Globalization.CultureInfo]::InvariantCulture) -gt [DateTimeOffset]::Now) { Write-Log 'focus mode valid, block is wanted'; exit }
} catch { }

$lines = @(Get-Content -Path $HostsPath)
$left = @($lines | Where-Object { $_ -like "*$Marker*" }).Count
if ($left -eq 0) { Write-Log 'clean: no hosts lines left'; exit }
Write-Log "still blocked after 06:00: $left hosts lines"

if (-not $Final) {
    if ($DryRun) { Write-Log "would restart task $TaskName"; exit }
    try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop; Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop; Write-Log 'lock task restarted' }
    catch { Write-Log "restart failed: $($_.Exception.Message)" }
    exit
}

if ($DryRun) { Write-Log 'would remove the marked hosts lines and flush DNS'; exit }
Set-Content -Path $HostsPath -Value @($lines | Where-Object { $_ -notlike "*$Marker*" }) -Encoding Default
ipconfig /flushdns | Out-Null
Write-Log "removed $left hosts lines"
