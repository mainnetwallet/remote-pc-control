# Starts the PIN lock screen (lock_overlay.py) automatically when you sign in to Windows,
# with no visible window. It runs independently of the Remote PC Control server, so the lock
# still shows after a restart even if you haven't started the server yet.
#   .\scripts\install-lock-overlay.ps1            create / update the sign-in task
#   .\scripts\install-lock-overlay.ps1 -Remove    delete it again
param([switch]$Remove)
$ErrorActionPreference = "Stop"
$name = "RemotePCControlLock"

if ($Remove) {
  Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Lock screen sign-in task removed." -ForegroundColor Green
  return
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$pyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) { throw "Run .\scripts\setup.ps1 first." }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$Root\lock_overlay.py`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -Priority 0
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
  -Description "Shows the PIN lock screen at sign-in if the PC is locked" -Force | Out-Null
Write-Host "Done. The PIN lock screen will start hidden when you sign in to Windows." -ForegroundColor Green
Write-Host "Start now (no reboot):  Start-ScheduledTask -TaskName $name"
Write-Host "Set a PIN first if you haven't: .\scripts\set-pin.ps1"
Write-Host "Remove it later:        .\scripts\install-lock-overlay.ps1 -Remove"
