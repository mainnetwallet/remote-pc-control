# Configures Windows UAC so prompts appear on the normal desktop and automatically elevate for administrators.
# This prevents Windows UIPI from blocking synthetic mouse clicks from phones or remote desktops
# when opening apps like MSI App Player, Task Manager, or installers.
#
# Usage (run in Administrator PowerShell):
#   .\scripts\fix-uac-prompt.ps1            # Allow UAC prompts and clicks from phone
#   .\scripts\fix-uac-prompt.ps1 -Revert    # Restore Windows default UAC behavior

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

if ($Revert) {
  Set-ItemProperty -Path $path -Name "PromptOnSecureDesktop" -Value 1 -Type DWord -Force
  Set-ItemProperty -Path $path -Name "ConsentPromptBehaviorAdmin" -Value 5 -Type DWord -Force
  Write-Host "Restored: UAC Secure Desktop is now ENABLED and prompts are required (Windows default)." -ForegroundColor Yellow
} else {
  Set-ItemProperty -Path $path -Name "PromptOnSecureDesktop" -Value 0 -Type DWord -Force
  Set-ItemProperty -Path $path -Name "ConsentPromptBehaviorAdmin" -Value 0 -Type DWord -Force
  Write-Host "Success: UAC Secure Desktop is DISABLED and auto-elevation is ENABLED for administrators." -ForegroundColor Green
  Write-Host "Apps like MSI App Player will open smoothly without blocking your phone mouse." -ForegroundColor Green
}
