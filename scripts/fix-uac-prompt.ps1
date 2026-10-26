# Configures Windows UAC so prompts appear on the normal desktop instead of the Secure Desktop.
# This allows remote control / phone screen to view and interact with UAC prompts
# (e.g., "Do you want to allow this app to make changes to your device?").
#
# Usage (run in Administrator PowerShell):
#   .\scripts\fix-uac-prompt.ps1            # Allow UAC prompts to show on phone screen
#   .\scripts\fix-uac-prompt.ps1 -Revert    # Restore Windows default (Secure Desktop enabled)

param([switch]$Revert)
$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  Write-Host "Requesting Administrator privileges..." -ForegroundColor Yellow
  $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  if ($Revert) { $argList += " -Revert" }
  Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
  return
}

$path = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
$val = if ($Revert) { 1 } else { 0 }

Set-ItemProperty -Path $path -Name "PromptOnSecureDesktop" -Value $val -Type DWord -Force

if ($Revert) {
  Write-Host "Restored: UAC Secure Desktop is now ENABLED (Windows default)." -ForegroundColor Yellow
} else {
  Write-Host "Success: UAC Secure Desktop is now DISABLED." -ForegroundColor Green
  Write-Host "UAC prompts will now appear directly on your desktop and stream to your phone screen." -ForegroundColor Green
}
