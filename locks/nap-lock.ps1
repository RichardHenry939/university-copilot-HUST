# UC nap lock (2026-11-02): locks the NAP spans that University Copilot paints yellow on its 24h clock.
# UC writes nap.json every minute: {"date":"YYYY-MM-DD","at":"<ISO>","nap_spans":[["13:00","14:25"]],...}
# = 13:00-15:00 minus any class / exam (only blue may cover yellow). A 12:30-17:30 lab leaves no nap, so no lock.
# Mode: between the night lock and focus mode. Blocks every social site INCLUDING YouTube; only Messenger stays open.
# Games are killed (no IFEO registry writes: they took ~10 s each and are not needed for a 2-hour window).
# Safety: no file / other date / 'at' older than 10 min / spans outside 13:00-15:00 -> nothing is locked by this script.
# Independent of the night lock: own hosts marker (# UC-NAP-LOCK), own browser policy value names (501+).
# Needs admin rights (hosts file + HKLM policy). Test without changing anything:
#   powershell -ExecutionPolicy Bypass -File nap-lock.ps1 -DryRun -FakeTime 14:00 -HostsPath "$env:TEMP\hosts-test" -NapFile <json>

param(
    [switch]$DryRun,
    [string]$FakeTime,
    [string]$HostsPath = (Join-Path $env:WINDIR 'System32\drivers\etc\hosts'),
    [string]$NapFile = (Join-Path $PSScriptRoot '..\school\nap.json')
)

$NapFrom = [TimeSpan]'13:00'
$NapTo   = [TimeSpan]'15:00'
$Marker  = '# UC-NAP-LOCK'
$LogFile = Join-Path $PSScriptRoot 'nap-lock.log'
$PolicyBase = 501
$BrowserKeys = @('HKLM:\SOFTWARE\Policies\Google\Chrome\URLBlocklist', 'HKLM:\SOFTWARE\Policies\Microsoft\Edge\URLBlocklist')

# Same list as the night lock, minus Messenger (owner: nap = everything blocked except Messenger)
$Sites = @(
    'facebook.com', 'fb.com', 'fb.watch', 'm.facebook.com', 'web.facebook.com', 'mbasic.facebook.com',
    'youtube.com', 'youtu.be', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com',
    'instagram.com', 'threads.net', 'threads.com',
    'tiktok.com', 'm.tiktok.com', 'vt.tiktok.com', 'douyin.com',
    'twitter.com', 'x.com', 'mobile.twitter.com',
    'reddit.com', 'old.reddit.com', 'redd.it',
    'pinterest.com', 'pin.it', 'tumblr.com', 'snapchat.com',
    'twitch.tv', 'm.twitch.tv', 'kick.com',
    'discord.com', 'discord.gg', 'discordapp.com',
    'bsky.app', 'mastodon.social', 'bereal.com', 'lemon8-app.com',
    'vk.com', 'weibo.com', 'bilibili.com', 'b23.tv', 'xiaohongshu.com',
    '9gag.com', 'imgur.com', 'quora.com',
    'gapo.vn', 'voz.vn', 'neal.fun',
    'capitalrift.com', 'play.capitalrift.com', 'buckshotroulette.online'
)
# Messenger itself lives on facebook.com for some pages; messenger.com stays reachable.

$KillNames = @('steam', 'steamwebhelper', 'steamerrorreporter', 'EtG', 'gta_sa', 'RobloxPlayerBeta', 'RobloxStudioBeta', 'EpicGamesLauncher', 'SoS', 'stdrt')
$KillPrefix = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Steam\'),
    (Join-Path $env:LOCALAPPDATA 'Roblox\')
)

function Write-Log([string]$msg) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    if ($DryRun) { Write-Output $line } else { Add-Content -Path $LogFile -Value $line }
}

function Get-Now { if ($DryRun -and $FakeTime) { return [TimeSpan]::Parse($FakeTime) }; return (Get-Date).TimeOfDay }

function Test-Nap([TimeSpan]$now) {
    if ($now -lt $NapFrom -or $now -ge $NapTo -or -not (Test-Path $NapFile)) { return $false }
    try {
        $j = Get-Content $NapFile -Raw | ConvertFrom-Json
        if ([string]$j.date -ne (Get-Date -Format 'yyyy-MM-dd') -or -not $j.at) { return $false }
        $at = [DateTimeOffset]::Parse([string]$j.at, [Globalization.CultureInfo]::InvariantCulture)
        if (([DateTimeOffset]::Now - $at).TotalMinutes -gt 10) { return $false }
        foreach ($s in @($j.nap_spans)) {
            $a = [TimeSpan]::Parse([string]$s[0]); $b = [TimeSpan]::Parse([string]$s[1])
            if ($a -lt $NapFrom) { $a = $NapFrom }; if ($b -gt $NapTo) { $b = $NapTo }
            if ($now -ge $a -and $now -lt $b) { return $true }
        }
    } catch { }
    return $false
}

function Set-Hosts([bool]$on) {
    try {
        $kept = @(Get-Content -Path $HostsPath | Where-Object { $_ -notlike "*$Marker*" })
        if ($on) { $kept += foreach ($s in $Sites) { "127.0.0.1 $s $Marker"; "127.0.0.1 www.$s $Marker" } }
        if ($DryRun) { Write-Log "would write hosts, block=$on, sites=$(if ($on) { $Sites.Count } else { 0 })"; return }
        Set-Content -Path $HostsPath -Value $kept -Encoding Default
        ipconfig /flushdns | Out-Null
        Write-Log "hosts block=$on"
    } catch { Write-Log "hosts write failed: $($_.Exception.Message)" }
}

function Set-Policy([bool]$on) {
    if ($DryRun) { Write-Log "would set browser policy block=$on"; return }
    foreach ($k in $BrowserKeys) {
        try {
            if (-not (Test-Path $k)) { if (-not $on) { continue }; New-Item -Path $k -Force | Out-Null }
            foreach ($name in @((Get-Item $k).Property)) { if (($name -as [int]) -ge $PolicyBase) { Remove-ItemProperty -Path $k -Name $name } }
            if ($on) { $i = $PolicyBase; foreach ($s in $Sites) { Set-ItemProperty -Path $k -Name ([string]$i) -Value $s -Type String; $i++ } }
        } catch { Write-Log "browser policy failed: $($_.Exception.Message)" }
    }
}

function Stop-Games {
    foreach ($p in @(Get-CimInstance Win32_Process -Property ProcessId, Name, ExecutablePath -ErrorAction SilentlyContinue)) {
        $name = [IO.Path]::GetFileNameWithoutExtension($p.Name); $path = $p.ExecutablePath
        $hit = ($KillNames -contains $name) -or ($path -and [bool]($KillPrefix | Where-Object { $path.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) }))
        if ($hit) { if ($DryRun) { Write-Log "would stop $name" } else { Write-Log "stop $name"; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } }
    }
}

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-HostFromText([string]$v) {
    if (-not $v) { return '' }
    return ((($v -replace '^[a-zA-Z]+://', '') -split '[/:?#]')[0]).ToLower()
}

function Test-BlockedUrl([string]$v) {
    $h = Get-HostFromText $v
    foreach ($s in $Sites) { if ($h -eq $s -or $h.EndsWith('.' + $s)) { return $true } }
    return $false
}

# (v1.00.52) Same as the night lock: tabs already open on a blocked site keep working until reloaded
# (hosts only affects new DNS lookups). At the start of the nap span and every 5 min after, reload Chrome/Edge
# tabs on a blocked site, then put back the tab the user had on screen.
# Limit: needs the task to run in the user's desktop session (UI Automation cannot see another session's windows).
function Invoke-TabSweep {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $winCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, 'Chrome_WidgetWin_1')
    $tabCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::TabItem)
    $editCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
    $btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
    $scope = [System.Windows.Automation.TreeScope]::Descendants
    foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, $winCond)) {
        $tabs = @($w.FindAll($scope, $tabCond))
        if ($tabs.Count -eq 0) { continue }
        $original = $null
        foreach ($t in $tabs) {
            $sp = $null
            if ($t.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$sp) -and $sp.Current.IsSelected) { $original = $t }
        }
        # Dry run only reads the tab already on screen, so it changes nothing
        $toCheck = if ($DryRun) { @($original) } else { $tabs }
        foreach ($t in $toCheck) {
            if (-not $t) { continue }
            $sp = $null
            if (-not $DryRun) {
                if (-not $t.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$sp)) { continue }
                $sp.Select(); Start-Sleep -Milliseconds 200
            }
            $bar = $null
            foreach ($e in @($w.FindAll($scope, $editCond))) {
                if ($e.Current.AutomationId -eq 'view_1012' -or $e.Current.Name -match 'Address and search bar|\u0111\u1ECBa ch\u1EC9') { $bar = $e; break }
            }
            if (-not $bar) { continue }
            $vp = $null
            if (-not $bar.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) { continue }
            if (-not (Test-BlockedUrl $vp.Current.Value)) { continue }
            $h = Get-HostFromText $vp.Current.Value
            if ($DryRun) { Write-Log "would reload tab on $h"; continue }
            foreach ($b in @($w.FindAll($scope, $btnCond))) {
                if ($b.Current.Name -match '^(Reload|T\u1EA3i l\u1EA1i)$') {
                    $ip = $null
                    if ($b.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$ip)) { $ip.Invoke(); Write-Log "reloaded tab on $h" }
                    break
                }
            }
        }
        if (-not $DryRun -and $original) {
            $sp = $null
            if ($original.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$sp)) { $sp.Select() }
        }
    }
}

$script:state = $null
$script:lastSweep = [DateTime]::MinValue
function Invoke-Pass {
    $on = Test-Nap (Get-Now)
    $hostsCount = @(Get-Content -Path $HostsPath | Where-Object { $_ -like "*$Marker*" }).Count
    $started = $on -and ($script:state -ne $true)
    if ($on -ne $script:state -or $hostsCount -ne $(if ($on) { $Sites.Count * 2 } else { 0 })) {
        Set-Hosts $on; Set-Policy $on
        if ($on -ne $script:state) { Write-Log "nap lock active=$on" }
        $script:state = $on
    }
    if ($on) {
        Stop-Games
        if ($started -or ((Get-Date) - $script:lastSweep).TotalMinutes -ge 5) {
            try { Invoke-TabSweep } catch { Write-Log "tab sweep error: $($_.Exception.Message)" }
            $script:lastSweep = Get-Date
        }
    }
}

if ($DryRun) { Invoke-Pass; return }

$createdNew = $false
$script:mutex = New-Object System.Threading.Mutex($true, 'Local\UcNapLockSingleInstance', [ref]$createdNew)
if (-not $createdNew) { Write-Log 'another instance is running, exiting'; exit }

while ($true) {
    try { Invoke-Pass } catch { Write-Log "error: $($_.Exception.Message)" }
    Start-Sleep -Seconds 5
}
