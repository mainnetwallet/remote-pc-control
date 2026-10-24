# Run by the Windows installer (elevated). Sets up everything the packaged RemotePCControl.exe needs, so nothing has
# to be typed in a terminal:
#   - scheduled task "RemotePCControl": starts the exe at sign-in with the HIGHEST run level (Administrator rights),
#     so mouse/keyboard also work in Task Manager, Registry Editor and admin terminals (no UAC prompt at sign-in)
#   - firewall rule "RemotePCControl Tailscale only": TCP 8888 from 100.64.0.0/10 only
#   - starts the agent right away
# -Remove undoes all of it (used by the uninstaller).
param([string]$Exe, [switch]$Remove)
$ErrorActionPreference = "Stop"
$name = "RemotePCControl"
$rule = "RemotePCControl Tailscale only"

if ($Remove) {
  Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
  return
}

if (-not (Test-Path $Exe)) { throw "RemotePCControl.exe not found: $Exe" }
$user = "$env:USERDOMAIN\$env:USERNAME"

Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute $Exe -WorkingDirectory (Split-Path -Parent $Exe)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = "PT10S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
  -Description "Starts Remote PC Control at sign-in with administrator rights" -Force | Out-Null

if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 `
    -RemoteAddress "100.64.0.0/10" -Profile Any | Out-Null
}

Start-ScheduledTask -TaskName $name
