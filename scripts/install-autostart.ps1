# Starts Remote PC Control automatically when you sign in to Windows, with no visible window.
#   .\scripts\install-autostart.ps1            create / update the startup task
#   .\scripts\install-autostart.ps1 -Remove    delete it again
# It runs as YOUR user in the signed-in desktop session (screen capture and input need that),
# so it cannot start before you log in. No administrator rights are needed.
# The runner waits for the network (10 s x 20 tries, then every 60 s) and restarts the server if it stops.
param([switch]$Remove)
$ErrorActionPreference = "Stop"
$name = "RemotePCControl"

if ($Remove) {
  Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Startup task removed." -ForegroundColor Green
  return
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
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
  -Description "Starts Remote PC Control at sign-in (hidden, waits for network)" -Force | Out-Null
Write-Host "Done. Remote PC Control will start hidden when you sign in to Windows." -ForegroundColor Green
Write-Host "Start now (no reboot):  Start-ScheduledTask -TaskName $name"
Write-Host "Stop it:                Stop-ScheduledTask -TaskName $name     (stopping only the python process makes the runner restart it)"
Write-Host "Log file:               $Root\autostart.log"
Write-Host "Remove it later:        .\scripts\install-autostart.ps1 -Remove"
