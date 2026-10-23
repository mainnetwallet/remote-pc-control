# Stops Windows from locking the PC on its own, so remote control never runs into the lock screen.
# This does NOT and cannot unlock a PC someone has already locked, or bypass sign-in: Windows keeps
# that screen (the "secure desktop") isolated from every process, including admin ones, by design.
#   .\scripts\disable-lock.ps1            turn screen timeout, sleep and the screensaver off
#   .\scripts\disable-lock.ps1 -Restore   put the previous settings back
param([switch]$Restore)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$stamp = Join-Path $Root ".power-settings-backup.json"

function Get-Power {
  # AC (plugged in) values, in seconds; 0 = never.
  $mon  = (powercfg /q SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | Select-String "Current AC Power Setting Index: 0x(\w+)").Matches.Groups[1].Value
  $sleep = (powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "Current AC Power Setting Index: 0x(\w+)").Matches.Groups[1].Value
  [pscustomobject]@{
    MonitorTimeoutSec = [Convert]::ToInt32($mon, 16)
    SleepTimeoutSec   = [Convert]::ToInt32($sleep, 16)
    ScreenSaveActive  = (Get-ItemProperty "HKCU:\Control Panel\Desktop" -Name ScreenSaveActive -ErrorAction SilentlyContinue).ScreenSaveActive
    ScreenSaverIsSecure = (Get-ItemProperty "HKCU:\Control Panel\Desktop" -Name ScreenSaverIsSecure -ErrorAction SilentlyContinue).ScreenSaverIsSecure
  }
}

if ($Restore) {
  if (-not (Test-Path $stamp)) { Write-Host "Nothing to restore (no backup found at $stamp)." -ForegroundColor Yellow; return }
  $prev = Get-Content $stamp -Raw | ConvertFrom-Json
  powercfg /change monitor-timeout-ac ([Math]::Ceiling($prev.MonitorTimeoutSec / 60))
  powercfg /change standby-timeout-ac ([Math]::Ceiling($prev.SleepTimeoutSec / 60))
  if ($null -ne $prev.ScreenSaveActive) { Set-ItemProperty "HKCU:\Control Panel\Desktop" -Name ScreenSaveActive -Value $prev.ScreenSaveActive }
  if ($null -ne $prev.ScreenSaverIsSecure) { Set-ItemProperty "HKCU:\Control Panel\Desktop" -Name ScreenSaverIsSecure -Value $prev.ScreenSaverIsSecure }
  Remove-Item $stamp -Force -ErrorAction SilentlyContinue
  Write-Host "Restored your previous power/screensaver settings." -ForegroundColor Green
  return
}

if (-not (Test-Path $stamp)) { Get-Power | ConvertTo-Json | Set-Content -Path $stamp -Encoding utf8 }

powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0
Set-ItemProperty "HKCU:\Control Panel\Desktop" -Name ScreenSaveActive -Value "0"

Write-Host "Done: this PC (while plugged in) will no longer turn off the screen, sleep, or run a screensaver." -ForegroundColor Green
Write-Host "It can still be locked manually (Win+L) or by Windows Update/policy - those still need a manual unlock at the PC." -ForegroundColor Yellow
Write-Host "Undo later:  .\scripts\disable-lock.ps1 -Restore"
