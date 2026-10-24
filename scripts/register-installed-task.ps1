# Run by the Windows installer (elevated). Sets up everything the packaged RemotePCControl.exe needs, so nothing has
# to be typed in a terminal:
#   - scheduled task "RemotePCControl": starts the exe at sign-in with the HIGHEST run level (Administrator rights),
#     so mouse/keyboard also work in Task Manager, Registry Editor and admin terminals (no UAC prompt at sign-in)
#   - firewall rule "RemotePCControl Tailscale only": TCP 8888 from 100.64.0.0/10 only
#   - starts the agent right away
# -Kind lock registers the PIN lock screen task instead. -Remove undoes it (used by the uninstaller and the control panel).
# -NoFirewall / -NoStart are used by the control panel, which manages those parts itself.
param([string]$Exe, [ValidateSet("agent","lock")][string]$Kind = "agent", [switch]$Remove, [switch]$NoStart, [switch]$NoFirewall)
$ErrorActionPreference = "Stop"
# The installer runs this hidden, so a failure would be invisible. Everything is logged to
# %ProgramData%\RemotePCControl\setup.log (also the place to look when the panel shows autostart or firewall off).
$logDir = Join-Path $env:ProgramData "RemotePCControl"
function Log($m) { try { New-Item -ItemType Directory -Force $logDir | Out-Null; Add-Content -Path (Join-Path $logDir "setup.log") -Value ("{0} {1}" -f (Get-Date -Format s), $m) } catch {} }
try {
  $agentTask = "RemotePCControl"
  $lockTask = "RemotePCControlLock"
  $rule = "RemotePCControl Tailscale only"
  $name = if ($Kind -eq "lock") { $lockTask } else { $agentTask }

  if ($Remove) {
    if (-not $NoStart) { Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue }   # -NoStart: never end a running copy (it may be the one calling this)
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    if ($Kind -eq "agent" -and -not $NoFirewall) { Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue }
    return
  }

  if (-not (Test-Path $Exe)) { throw "RemotePCControl.exe not found: $Exe" }
  $user = "$env:USERDOMAIN\$env:USERNAME"

  if (-not $NoStart) { Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue }
  # --background = start without opening the control panel in the browser
  $arg = if ($Kind -eq "lock") { "--lock-overlay" } else { "--background" }
  $action = New-ScheduledTaskAction -Execute $Exe -Argument $arg -WorkingDirectory (Split-Path -Parent $Exe)
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
  $trigger.Delay = "PT10S"
  $triggers = @($trigger)
  if ($Kind -eq "lock") {   # watchdog: relaunch every minute; a running overlay ignores the extra launch
    $triggers += New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
  }
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Principal $principal `
    -Description "Remote PC Control ($Kind), starts at sign-in with administrator rights" -Force | Out-Null

  if ($Kind -eq "agent" -and -not $NoFirewall) {
    if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
      New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 `
        -RemoteAddress "100.64.0.0/10" -Profile Any | Out-Null
    }
  }

  if (-not $NoStart) { Start-ScheduledTask -TaskName $name }
  Log "ok: kind=$Kind remove=$Remove"
} catch {
  Log "FAILED: kind=$Kind remove=$Remove : $($_.Exception.Message)"
  throw
}
