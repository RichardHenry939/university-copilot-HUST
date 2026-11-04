# UC PhoneDNS: open UDP 53 only on the Tailscale interface, only for tailnet devices.
# Right-click > Run with PowerShell (it asks for admin). Undo: Remove-NetFirewallRule -DisplayName "UC PhoneDNS"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators')) {
    Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`""; exit
}
Remove-NetFirewallRule -DisplayName "UC PhoneDNS" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "UC PhoneDNS" -Direction Inbound -Protocol UDP -LocalPort 53 -InterfaceAlias Tailscale -RemoteAddress 100.64.0.0/10 -Action Allow | Out-Null
Get-NetFirewallRule -DisplayName "UC PhoneDNS" | Select-Object DisplayName, Enabled, Action
Read-Host "Done. Press Enter to close"
