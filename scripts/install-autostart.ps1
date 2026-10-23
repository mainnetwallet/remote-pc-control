# Starts Remote PC Control automatically when you sign in to Windows.
#   .\scripts\install-autostart.ps1            create the startup task
#   .\scripts\install-autostart.ps1 -Remove    delete it again
# It runs as YOUR user in the signed-in desktop session (screen capture and input need that),
# so it cannot start before you log in. No administrator rights are needed.
param([switch]$Remove)
$ErrorActionPreference = "Stop"
$name = "RemotePCControl"

if ($Remove) {
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Startup task removed." -ForegroundColor Green
  return
}

$Root = Split-Path -Parent $PSScriptRoot
$start = Join-Path $Root "scripts\start.ps1"
if (-not (Test-Path (Join-Path $Root ".venv\Scripts\python.exe"))) { throw "Run .\scripts\setup.ps1 first." }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$start`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = "PT30S"   # give Tailscale/network 30 s to come up first
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
  -Description "Starts Remote PC Control at sign-in" -Force | Out-Null
Write-Host "Done. Remote PC Control will start 30 seconds after you sign in to Windows." -ForegroundColor Green
Write-Host "Start it now without rebooting:  Start-ScheduledTask -TaskName $name"
Write-Host "Remove it later:                 .\scripts\install-autostart.ps1 -Remove"
