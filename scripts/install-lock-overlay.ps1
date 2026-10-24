# Starts the PIN lock screen (lock_overlay.py) automatically when you sign in to Windows,
# with no visible window. It runs independently of the Remote PC Control server, so the lock
# still shows after a restart even if you haven't started the server yet.
#   .\scripts\install-lock-overlay.ps1            create / update the sign-in task (safe to re-run)
#   .\scripts\install-lock-overlay.ps1 -Remove    delete it again
#
# Design notes
#  * Runs as a Scheduled Task for the *signed-in user* (LogonType Interactive), NOT as a Windows
#    service: a Tkinter window can only appear on the user's own desktop session.
#  * Idempotent: one task with a fixed name, registered with -Force (replaced, never duplicated).
#    Any other task that launches this project's lock_overlay.py under a different name is removed.
#  * Restart behaviour: (1) Task Scheduler restarts the action if it fails, and (2) a trigger
#    re-launches it every minute. While an overlay is already running those launches are ignored
#    (-MultipleInstances IgnoreNew, plus the overlay's own per-session mutex), so they never create
#    a second window.
#  * Never stops or kills any process. The lock state lives in lock_state.json, so restarting the
#    overlay never changes whether the PC is locked.
param([switch]$Remove, [string]$PythonW)
$ErrorActionPreference = "Stop"
$name = "RemotePCControlLock"

function Remove-OverlayTasks([string]$keepName) {
  Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $_.TaskName -ne $keepName -and ($_.Actions | Where-Object { "$($_.Arguments)" -like "*lock_overlay.py*" })
  } | ForEach-Object {
    Write-Host "Removing duplicate task '$($_.TaskName)'" -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false
  }
}

if ($Remove) {
  Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Remove-OverlayTasks ""
  Write-Host "Lock screen sign-in task removed." -ForegroundColor Green
  return
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$pyw = if ($PythonW) { $PythonW } else { Join-Path $Root ".venv\Scripts\pythonw.exe" }
if (-not (Test-Path $pyw)) { throw "Run .\scripts\setup.ps1 first (or pass -PythonW <path to pythonw.exe>)." }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$Root\lock_overlay.py`"" -WorkingDirectory $Root
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
$watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -Priority 4 `
  -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger @($atLogon, $watchdog) -Settings $settings -Principal $principal `
  -Description "Shows the PIN lock screen if the PC is locked (one instance; restarts itself)" -Force | Out-Null
Remove-OverlayTasks $name

$count = @(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue).Count
if ($count -ne 1) { throw "Expected exactly one '$name' task, found $count." }
Write-Host "Done. The PIN lock screen starts hidden when you sign in and restarts itself if it exits." -ForegroundColor Green
Write-Host "Start now (no reboot):  Start-ScheduledTask -TaskName $name"
Write-Host "Set a PIN first if you haven't: .\scripts\set-pin.ps1"
Write-Host "Remove it later:        .\scripts\install-lock-overlay.ps1 -Remove"
Write-Host "Diagnostics log:        $env:LOCALAPPDATA\RemotePCControl\lock_overlay.log"
