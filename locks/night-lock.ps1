# UC night lock: from 22:00 to 06:00 block social sites (hosts file + Chrome/Edge policy) and games.
# Games are discovered automatically from every shortcut in Desktop\Game, on every pass.
# Two layers: (1) Image File Execution Options block so the exe exits at launch, (2) kill any running copy.
# Needs admin rights. Install: see locks/README.md (scheduled task at logon, highest privileges).
# Test without changing anything (kills nothing, writes only to -HostsPath):
#   powershell -ExecutionPolicy Bypass -File night-lock.ps1 -DryRun -FakeTime 23:00 -HostsPath "$env:TEMP\hosts-test"

param(
    [switch]$DryRun,
    [string]$Sweep,   # internal: run one tab sweep for this mode, then exit (see Invoke-SweepChild)
    [string]$FakeTime,
    [string]$HostsPath = (Join-Path $env:WINDIR 'System32\drivers\etc\hosts')
)

$BlockFrom = [TimeSpan]'22:00'
$BlockTo   = [TimeSpan]'06:00'
$Marker    = '# UC-NIGHT-LOCK'
$LogFile   = Join-Path $PSScriptRoot 'night-lock.log'
$GameFolder = Join-Path $env:USERPROFILE 'Desktop\Game'
$IfeoRoot  = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options'
$IfeoDebugger = 'cmd.exe /c exit 0'

$Sites = @(
    # Social networks, every one the owner uses or could switch to, except LinkedIn (2026-11-01).
    # Hosts covers each name and www.name; the browser policy also covers every subdomain.
    'facebook.com', 'fb.com', 'fb.watch', 'messenger.com', 'm.facebook.com', 'web.facebook.com', 'mbasic.facebook.com',
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
    'gapo.vn', 'voz.vn',
    'neal.fun',
    'capitalrift.com', 'play.capitalrift.com',
    'buckshotroulette.online'
)
$ExpectedLines = $Sites.Count * 2

# (2026-11-01) Focus mode, driven by University Copilot's time wallet (one-way: UC writes, this reads).
# Looser than the night window: Messenger stays open, the YouTube site is blocked by browser policy (not hosts: UC's hidden player needs it),
# games are blocked as at night. Night window and soft lock always win; focus never removes a night block.
# Expiry is the 'until' time inside the file itself, checked every pass, so it ends on time even if UC
# crashes or the machine sleeps (no reliance on a cleanup step at the end of some process).
$FocusFile = Join-Path $PSScriptRoot '..\school\focus.json'   # written by UC's time wallet
$FocusAllowed = @('messenger.com', 'youtube.com', 'youtu.be', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com')
$FocusSites = @($Sites | Where-Object { $FocusAllowed -notcontains $_ })
# (2026-11-06) Focus mode: YouTube plays only through UC's hidden embedded player (youtube-nocookie.com, on the allow list).
$FocusPolicyExtra = @('youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtube.com/shorts', 'm.youtube.com/shorts')
$FocusEmbedAllow = @('youtube-nocookie.com')
# (2026-11-03) Muse (muse.ai, Meta's AI agent, used for work) logs in through facebook.com and instagram.com
# (Meta account sync bounces between them). In focus mode both leave the hosts block (name + www); the browser
# policy still blocks all of facebook.com / instagram.com except these login paths, and the tab sweep reloads
# any other page there. Limit: Chrome/Edge only, other apps can reach both during focus. Night and nap are
# unchanged. Add paths here if Muse needs more (an entry without '/' opens that whole host).
# (2026-11-03, later) Muse is not available in Vietnam, so the opening is removed: both hosts stay blocked in
# focus mode. $FocusPolicyAllow stays only so leftover allow-list entries from the earlier version get cleaned up.
$FocusHostsOpen = @()
$FocusPolicyAllow = @(
    'facebook.com/login', 'facebook.com/aymh', 'facebook.com/dialog', 'facebook.com/checkpoint',
    'facebook.com/ajax', 'facebook.com/api/graphql', 'facebook.com/oidc', 'accountscenter.facebook.com',
    'instagram.com/aymh', 'instagram.com/accounts', 'instagram.com/oauth', 'instagram.com/challenge',
    'instagram.com/ajax', 'instagram.com/api/v1/web/accounts', 'accountscenter.instagram.com', 'youtube-nocookie.com'
)
$FocusMaxHours = 9   # an 'until' further away than this is ignored (bad or hostile file)
$script:mode = $null
$script:blockSites = @()

# Shortcut targets that must never be killed or IFEO-blocked (killing them closes the browser, shell or Explorer)
$SafeTargets = @('explorer.exe', 'chrome.exe', 'chrome_proxy.exe', 'msedge.exe', 'cmd.exe',
                 'powershell.exe', 'pwsh.exe', 'WindowsTerminal.exe', 'rundll32.exe')
# Generic exe names: too common to block by name (IFEO is global by file name)
$GenericExe = @('main.exe', 'launcher.exe', 'setup.exe', 'updater.exe')

# Always blocked, in any folder
$StaticExeNames = @('EtG.exe', 'gta_sa.exe', 'RobloxPlayerBeta.exe', 'steam.exe', 'SoS.exe', 'data.exe', 'stdrt.exe')
$KillNames = @(
    'steam', 'steamwebhelper', 'steamerrorreporter',
    'EtG', 'gta_sa',
    'RobloxPlayerBeta', 'RobloxStudioBeta', 'RobloxStudioInstaller',
    'EpicGamesLauncher'
)
# Exact exe paths that are always killed
$KillExact = @(
    # exact exe paths of your own games
)
# Any exe under these folders is killed (Steam libraries, game installs, Roblox)
$KillPrefix = @(
    # folders whose every exe is killed: your Steam library, game installs, Roblox
    (Join-Path ${env:ProgramFiles(x86)} 'Steam\'),
    (Join-Path $env:LOCALAPPDATA 'Roblox\')
)

$script:state = $null
$script:targets = [pscustomobject]@{ Exe = @(); Titles = @() }
$script:lastSweep = [DateTime]::MinValue
$script:lastHostsCheck = [DateTime]::MinValue
$script:lastTargets = [DateTime]::MinValue
$script:closedAt = @{}

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

# Win32 helpers to find windows by exact title (Chrome app windows share the browser process)
Add-Type -Namespace UcNightLock -Name Win -MemberDefinition @'
public delegate bool EnumWindowsProc(System.IntPtr hWnd, System.IntPtr lParam);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, System.IntPtr lParam);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
public static extern int GetWindowText(System.IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
public static extern int GetWindowTextLength(System.IntPtr hWnd);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool PostMessage(System.IntPtr hWnd, uint Msg, System.IntPtr wParam, System.IntPtr lParam);
'@

function Write-Log([string]$msg) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    if ($DryRun) { Write-Output $line } else { Add-Content -Path $LogFile -Value $line }
}

function Get-Now {
    if ($DryRun -and $FakeTime) { return [TimeSpan]::Parse($FakeTime) }
    return (Get-Date).TimeOfDay
}

# Window crosses midnight: 22:00 -> 06:00
function Test-InWindow([TimeSpan]$now) {
    return ($now -ge $BlockFrom -or $now -lt $BlockTo)
}

function Set-HostsBlock([string[]]$list) {
    $on = ($list.Count -gt 0)
    try {
        $kept = @(Get-Content -Path $HostsPath | Where-Object { $_ -notlike "*$Marker*" })
        if ($on) {
            $add = foreach ($s in $list) { "127.0.0.1 $s $Marker"; "127.0.0.1 www.$s $Marker" }
            $kept = $kept + $add
        }
        if ($DryRun) { Write-Log "would write hosts, block=$on, sites=$($list.Count), lines=$($kept.Count)"; return }
        Set-Content -Path $HostsPath -Value $kept -Encoding Default
        ipconfig /flushdns | Out-Null
        Write-Log "hosts block=$on sites=$($list.Count)"
    } catch {
        Write-Log "hosts write failed: $($_.Exception.Message)"
    }
}

# Reads every shortcut in Desktop\Game. Exe targets are killed/blocked; the rest (Chrome apps) are matched by window title.
function Update-Targets {
    $sh = New-Object -ComObject WScript.Shell
    $exe = @()
    $titles = @()
    if (Test-Path $GameFolder) {
        foreach ($f in @(Get-ChildItem -Path $GameFolder -Filter *.lnk -Recurse -ErrorAction SilentlyContinue)) {
            $target = $sh.CreateShortcut($f.FullName).TargetPath
            $name = [IO.Path]::GetFileName($target)
            if ($target -and ($SafeTargets -notcontains $name)) { $exe += $target }
            elseif ($name -match '^chrome') { $titles += $f.BaseName }
        }
    }
    $script:targets = [pscustomobject]@{ Exe = $exe; Titles = $titles }
}

# Blocks the exe name at launch (exits at once when opened from any place). Only ours are touched.
function Set-IfeoBlock([string]$exeName, [bool]$on) {
    $key = Join-Path $IfeoRoot $exeName
    if ($on) {
        if (-not (Test-Path $key)) {
            if ($DryRun) { Write-Log "would ifeo block $exeName"; return }
            New-Item -Path $key -Force | Out-Null
        }
        $cur = (Get-ItemProperty -Path $key -Name Debugger -ErrorAction SilentlyContinue).Debugger
        if ($cur -eq $IfeoDebugger) { return }
        if ($cur) { return }   # someone else's debugger: leave it alone
        if ($DryRun) { Write-Log "would ifeo block $exeName"; return }
        Set-ItemProperty -Path $key -Name Debugger -Value $IfeoDebugger
        Set-ItemProperty -Path $key -Name UcNightLock -Value 1
        Write-Log "ifeo block $exeName"
    }
}

function Remove-IfeoBlocks {
    Get-ChildItem -Path $IfeoRoot -ErrorAction SilentlyContinue | ForEach-Object {
        $mine = (Get-ItemProperty -Path $_.PSPath -Name UcNightLock -ErrorAction SilentlyContinue).UcNightLock
        if ($mine -eq 1) {
            if ($DryRun) { Write-Log "would ifeo unblock $($_.PSChildName)"; return }
            Remove-Item -Path $_.PSPath -Recurse -Force
            Write-Log "ifeo unblock $($_.PSChildName)"
        }
    }
}

function Stop-Blocked {
    # One CIM query for all paths: reading .Path per process took ~5 s
    $exact = $KillExact + $script:targets.Exe
    foreach ($p in @(Get-CimInstance Win32_Process -Property ProcessId, Name, ExecutablePath -ErrorAction SilentlyContinue)) {
        $path = $p.ExecutablePath
        $name = [IO.Path]::GetFileNameWithoutExtension($p.Name)
        $hit = $KillNames -contains $name
        if (-not $hit -and $path) {
            $hit = ($exact -contains $path) -or ($path -match '\\Temp\\mrt[0-9A-Fa-f]+\.tmp\\stdrt\.exe$') -or
                   [bool]($KillPrefix | Where-Object { $path.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) })
        }
        if ($hit) {
            if ($DryRun) {
                Write-Log "would stop $name ($path)"
            } else {
                Write-Log "stop $name ($path)"
                Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# Closes top-level windows whose title is exactly a Chrome-app game name (WM_CLOSE, not a process kill)
function Close-GameWindows {
    if ($script:targets.Titles.Count -eq 0) { return }
    $titles = $script:targets.Titles
    $hits = New-Object System.Collections.ArrayList
    $cb = [UcNightLock.Win+EnumWindowsProc]{
        param($h, $l)
        $len = [UcNightLock.Win]::GetWindowTextLength($h)
        if ($len -gt 0) {
            $sb = New-Object System.Text.StringBuilder ($len + 1)
            [void][UcNightLock.Win]::GetWindowText($h, $sb, $sb.Capacity)
            $tt = $sb.ToString()
            foreach ($t in $titles) {
                if ($tt.IndexOf($t, [StringComparison]::OrdinalIgnoreCase) -ge 0) { [void]$hits.Add($h); break }
            }
        }
        return $true
    }
    [void][UcNightLock.Win]::EnumWindows($cb, [IntPtr]::Zero)
    foreach ($h in $hits) {
        $key = [string]$h
        if ($script:closedAt.ContainsKey($key) -and ((Get-Date) - $script:closedAt[$key]).TotalSeconds -lt 5) { continue }
        $script:closedAt[$key] = Get-Date
        if ($DryRun) { Write-Log "would close window handle $h" }
        else {
            Write-Log "close game window handle $h"
            [void][UcNightLock.Win]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
        }
    }
}

# Host part of the Chrome address bar text ("facebook.com/x" -> "facebook.com")
function Get-HostFromText([string]$v) {
    if (-not $v) { return '' }
    $h = (($v -replace '^[a-zA-Z]+://', '') -split '[/:?#]')[0]
    return $h.ToLower()
}

function Test-BlockedHost([string]$h) {
    foreach ($s in $script:blockSites) {
        if ($h -eq $s -or $h.EndsWith('.' + $s)) { return $true }
    }
    return $false
}

# Focus mode: the YouTube site is blocked by policy only. A tab already open there keeps playing until reloaded, so reload it.
function Test-BlockedUrl([string]$v) {
    if (Test-BlockedHost (Get-HostFromText $v)) { return $true }
    if ($script:mode -eq 'focus' -and (Get-HostFromText $v) -match '(^|\.)youtube\.com$') { return $true }
    if ($script:mode -eq 'focus' -and (Test-MetaNotLogin $v)) { return $true }
    return $false
}

# Focus mode: facebook.com / instagram.com are out of hosts for Muse's login, so any page there that is not a login path counts as blocked.
function Test-MetaNotLogin([string]$v) {
    $h = Get-HostFromText $v
    $inScope = $false
    foreach ($o in $FocusHostsOpen) { if ($h -eq $o -or $h.EndsWith('.' + $o)) { $inScope = $true } }
    if (-not $inScope) { return $false }
    $path = (($v -replace '^[a-zA-Z]+://', '') -replace '^[^/?#]*', '').ToLower()
    foreach ($a in $FocusPolicyAllow) {
        $i = $a.IndexOf('/')
        $ah = if ($i -ge 0) { $a.Substring(0, $i) } else { $a }
        $p = if ($i -ge 0) { $a.Substring($i) } else { '' }
        if (-not ($h -eq $ah -or $h.EndsWith('.' + $ah))) { continue }
        if ($p -eq '' -or $path -eq $p -or $path.StartsWith($p + '/') -or $path.StartsWith($p + '?') -or $path.StartsWith($p + '.')) { return $false }
    }
    return $true
}

# Every 5 min in the window: reload Chrome tabs already open on a blocked domain (hosts only affects new DNS lookups).
# Reads each tab's address bar and presses that tab's Reload button, then puts the originally shown tab back.
function Invoke-TabSweep([switch]$ActiveOnly) {
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
        # Dry run only reads the tab that is already shown, so it changes nothing
        $toCheck = if ($DryRun -or $ActiveOnly) { @($original) } else { $tabs }
        foreach ($t in $toCheck) {
            if (-not $t) { continue }
            $sp = $null
            if (-not $DryRun -and -not $ActiveOnly) {
                if (-not $t.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$sp)) { continue }
                $sp.Select()
                Start-Sleep -Milliseconds 200
            }
            $bar = $null
            foreach ($e in @($w.FindAll($scope, $editCond))) {
                if ($e.Current.AutomationId -eq 'view_1012' -or $e.Current.Name -match 'Address and search bar|\u0111\u1ECBa ch\u1EC9') { $bar = $e; break }
            }
            if (-not $bar) { continue }
            $vp = $null
            if (-not $bar.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) { continue }
            $h = Get-HostFromText $vp.Current.Value
            if (-not (Test-BlockedUrl $vp.Current.Value)) { continue }
            $reloadBtn = $null
            foreach ($b in @($w.FindAll($scope, $btnCond))) {
                if ($b.Current.Name -match '^(Reload|T\u1EA3i l\u1EA1i)$') { $reloadBtn = $b; break }
            }
            if ($DryRun) { Write-Log "would reload tab on $h"; continue }
            if ($reloadBtn) {
                $ip = $null
                if ($reloadBtn.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$ip)) {
                    $ip.Invoke()
                    Write-Log "reloaded tab on $h"
                }
            }
        }
        # Put back the tab the user had on screen
        if (-not $DryRun -and -not $ActiveOnly -and $original) {
            $sp = $null
            if ($original.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$sp)) { $sp.Select() }
        }
    }
}

# Browser-level block: Chrome and Edge refuse these URLs under policy, independent of DNS cache.
$BrowserKeys = @('HKLM:\SOFTWARE\Policies\Google\Chrome\URLBlocklist', 'HKLM:\SOFTWARE\Policies\Microsoft\Edge\URLBlocklist')
function Set-BrowserBlock([string[]]$list) {
    $managed = @($Sites) + @($FocusPolicyExtra)
    if ($DryRun) { Write-Log "would set browser policy: $($list -join ', ')"; return }
    foreach ($k in $BrowserKeys) {
        try {
            if ($list.Count -gt 0) {
                if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null }
                $i = 1
                foreach ($s in $list) {
                    Set-ItemProperty -Path $k -Name ([string]$i) -Value $s -Type String
                    $i++
                }
            }
            if (Test-Path $k) {
                foreach ($name in @((Get-Item $k).Property)) {
                    if (($name -as [int]) -ge 500) { continue }   # 501+ belong to the nap lock (2026-11-02): never touch them
                    $val = (Get-ItemProperty -Path $k -Name $name).$name
                    if (($managed -contains $val) -and ($list -notcontains $val)) { Remove-ItemProperty -Path $k -Name $name }
                }
            }
        } catch {
            Write-Log "browser policy failed: $($_.Exception.Message)"
        }
    }
}

# Focus-only allow list (Muse login paths). Never written while the nap lock holds its entries (501+),
# so the nap block on facebook.com is never opened.
$AllowKeys = @('HKLM:\SOFTWARE\Policies\Google\Chrome\URLAllowlist', 'HKLM:\SOFTWARE\Policies\Microsoft\Edge\URLAllowlist')
function Set-BrowserAllow([string[]]$list) {
    $napOn = $false
    foreach ($k in $BrowserKeys) {
        if ((Test-Path $k) -and @((Get-Item $k).Property | Where-Object { ($_ -as [int]) -ge 500 }).Count -gt 0) { $napOn = $true }
    }
    if ($napOn) { $list = @() }
    if ($DryRun) { Write-Log "would set browser allow list: $($list -join ', ')"; return }
    foreach ($k in $AllowKeys) {
        try {
            if ($list.Count -gt 0) {
                if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null }
                $i = 1
                foreach ($s in $list) {
                    Set-ItemProperty -Path $k -Name ([string]$i) -Value $s -Type String
                    $i++
                }
            }
            if (Test-Path $k) {
                foreach ($name in @((Get-Item $k).Property)) {
                    $val = (Get-ItemProperty -Path $k -Name $name).$name
                    if (($FocusPolicyAllow -contains $val) -and ($list -notcontains $val)) { Remove-ItemProperty -Path $k -Name $name }
                }
            }
        } catch {
            Write-Log "browser allow policy failed: $($_.Exception.Message)"
        }
    }
}

# Daytime focus lock: lock.dat holds the end time (ISO). Written by the lock window.
function Test-SoftLock {
    $f = Join-Path $PSScriptRoot 'lock.dat'
    if (-not (Test-Path $f)) { return $false }
    try {
        $until = [DateTime]::Parse((Get-Content $f -Raw).Trim(), [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
        return ((Get-Date) -lt $until)
    } catch { return $false }
}

function Test-Focus {
    if (-not (Test-Path $FocusFile)) { return $false }
    try {
        $j = Get-Content $FocusFile -Raw | ConvertFrom-Json
        if (-not $j.focus -or -not $j.until) { return $false }
        $until = [DateTimeOffset]::Parse([string]$j.until, [Globalization.CultureInfo]::InvariantCulture)
        $left = ($until - [DateTimeOffset]::Now).TotalHours
        return ($left -gt 0 -and $left -le $FocusMaxHours)
    } catch { return $false }
}

# (2026-11-05) The tab sweep talks to Chrome through UI Automation, which has no timeout. It once hung right after 22:00
# and froze the whole loop, so 06:00 never unblocked. It now runs in a child process, killed after 60 s.
function Invoke-SweepChild([string]$mode) {
    if ($DryRun) { if ($mode -eq 'focus') { Invoke-TabSweep -ActiveOnly } else { Invoke-TabSweep }; return }
    if ($script:sweepProc -and -not $script:sweepProc.HasExited) {
        if (((Get-Date) - $script:sweepProc.StartTime).TotalSeconds -gt 60) {
            Write-Log "tab sweep stuck over 60 s, killed"
            try { $script:sweepProc.Kill() } catch {}
        }
        return
    }
    $script:sweepProc = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$script:Self`"", '-Sweep', $mode)
}

function Invoke-Pass {
    $now = Get-Date
    $mode = if ((Test-InWindow (Get-Now)) -or (Test-SoftLock)) { 'night' } elseif (Test-Focus) { 'focus' } else { 'off' }
    $on = ($mode -ne 'off')
    $hostList = switch ($mode) { 'night' { @($Sites) } 'focus' { @($FocusSites | Where-Object { $FocusHostsOpen -notcontains $_ }) } default { @() } }
    $allowList = if ($mode -eq 'focus') { $FocusEmbedAllow } else { @() }   # Muse opening removed (2026-11-03); empty list also cleans old allow entries
    $policyList = switch ($mode) { 'night' { @($Sites) } 'focus' { @($FocusSites) + @($FocusPolicyExtra) } default { @() } }
    $script:blockSites = $hostList
    if ($mode -ne $script:mode) { $script:mode = $mode; $script:lastHostsCheck = [DateTime]::MinValue; $script:lastSweep = [DateTime]::MinValue }
    if (($now - $script:lastHostsCheck).TotalSeconds -ge 10) {
        $script:lastHostsCheck = $now
        $count = @(Get-Content -Path $HostsPath | Where-Object { $_ -like "*$Marker*" }).Count
        if ($count -ne $hostList.Count * 2) { Set-HostsBlock $hostList }
        Set-BrowserBlock $policyList
        Set-BrowserAllow $allowList
    }

    if ($on) {
        # Game list and IFEO blocks refresh once a minute, not every second
        if (($now - $script:lastTargets).TotalSeconds -ge 60) {
            $script:lastTargets = $now
            Update-Targets
            $names = @($StaticExeNames) + @($script:targets.Exe | ForEach-Object { [IO.Path]::GetFileName($_) })
            $names = $names | Where-Object { $GenericExe -notcontains $_ } | Sort-Object -Unique
            # Night only: IFEO registry writes can take ~10 s each (seen 01/11 right after boot), which held the
            # first focus pass for minutes so the end of focus was noticed late. Focus relies on the kill below.
            if ($mode -eq 'night') { foreach ($n in $names) { Set-IfeoBlock $n $true } }
        }
        Stop-Blocked
        Close-GameWindows
        $every = if ($mode -eq 'focus') { 0.5 } else { 5 }   # focus: only the tab on screen, every 30 s
        # (2026-11-05) After 22:30 social sites have long been dead: stop sweeping / reloading tabs for the rest of the night
        $lateNight = ($mode -eq 'night') -and (((Get-Now) -ge [TimeSpan]'22:30') -or ((Get-Now) -lt [TimeSpan]'06:00'))
        if (-not $lateNight -and ((Get-Date) - $script:lastSweep).TotalMinutes -ge $every) {
            Invoke-SweepChild $mode
            $script:lastSweep = Get-Date
        }
    }

    if ($mode -ne $script:state) {
        Write-Log "window active=$on mode=$mode"
        if (-not $on) { Remove-IfeoBlocks }
        $script:lastTargets = [DateTime]::MinValue
        $script:state = $mode
    }
}

$script:Self = $PSCommandPath
if ($Sweep) {
    $script:mode = $Sweep
    $script:blockSites = switch ($Sweep) { 'night' { @($Sites) } 'focus' { @($FocusSites | Where-Object { $FocusHostsOpen -notcontains $_ }) } default { @() } }
    try { if ($Sweep -eq 'focus') { Invoke-TabSweep -ActiveOnly } else { Invoke-TabSweep } } catch { Write-Log "tab sweep error: $($_.Exception.Message)" }
    return
}
if ($DryRun) {
    Invoke-Pass
    return
}

# Single instance: a second copy would fight the first (one blocks, the other unblocks)
$createdNew = $false
$script:instanceMutex = New-Object System.Threading.Mutex($true, 'Local\UcNightLockSingleInstance', [ref]$createdNew)
if (-not $createdNew) {
    Write-Log "another instance is running, exiting"
    exit
}

while ($true) {
    try { Invoke-Pass } catch { Write-Log "error: $($_.Exception.Message)" }
    Start-Sleep -Seconds 1
}
