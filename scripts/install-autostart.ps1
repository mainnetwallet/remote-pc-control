# Starts Remote PC Control automatically when you sign in to Windows, with no visible window.
#   .\scripts\install-autostart.ps1            create / update the startup task
#   .\scripts\install-autostart.ps1 -Admin     same, but run elevated (Administrator PowerShell required)
#   .\scripts\install-autostart.ps1 -Remove    delete it again
# It runs as YOUR user in the signed-in desktop session (screen capture and input need that),
# so it cannot start before you log in. No administrator rights are needed (unless you use -Admin).
# -Admin: Windows blocks input from a normal process into elevated windows (Task Manager, Registry Editor, admin
# terminals; UIPI), so with the default level mouse/keyboard do nothing there. -Admin runs the agent at the highest
# level so those windows can be controlled too. Only use it with a strong password; the UAC secure desktop still
# cannot be controlled.
# The runner waits for the network (10 s x 20 tries, then every 60 s) and restarts the server if it stops.
param([switch]$Remove, [switch]$Admin)
$ErrorActionPreference = "Stop"
$name = "RemotePCControl"

if ($Remove) {
  Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Startup task removed." -ForegroundColor Green
  return
}

if ($Admin) {
  $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $isAdmin) { throw "-Admin needs an Administrator PowerShell. Right-click PowerShell > Run as administrator, then run this again." }
}

$Root = Split-Path -Parent $PSScriptRoot
$vbs = Join-Path $Root "scripts\autostart-hidden.vbs"
if (-not (Test-Path (Join-Path $Root ".venv\Scripts\python.exe"))) { throw "Run .\scripts\setup.ps1 first." }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = "PT10S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$runLevel = if ($Admin) { "Highest" } else { "Limited" }
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel $runLevel

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
  -Description "Starts Remote PC Control at sign-in (hidden, waits for network)" -Force | Out-Null
Write-Host "Done. Remote PC Control will start hidden when you sign in to Windows ($runLevel rights)." -ForegroundColor Green
Write-Host "Start now (no reboot):  Start-ScheduledTask -TaskName $name"
Write-Host "Stop it:                Stop-ScheduledTask -TaskName $name     (stopping only the python process makes the runner restart it)"
Write-Host "Log file:               $Root\autostart.log"
Write-Host "Remove it later:        .\scripts\install-autostart.ps1 -Remove"
