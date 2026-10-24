<#
Fully removes the Remote PC Control Credential Provider and restores stock Windows unlock. Run as Administrator.
Safe to run even if registration partially failed or the DLL was already deleted.
#>
param([string]$Clsid = "{8F2A6C1E-5B7D-4E39-9A41-6D0C2E7B13F5}")
$ErrorActionPreference = "SilentlyContinue"
Remove-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$Clsid" -Recurse -Force
Remove-Item -Path "HKLM:\SOFTWARE\Classes\CLSID\$Clsid" -Recurse -Force
Write-Host "Removed. Windows will use only its built-in credential providers from now on."
Write-Host "If you are locked out for any other reason, use Windows' normal recovery options (Safe Mode, a recovery drive, or another admin account) - this script only ever adds/removes a registry entry, it does not touch account passwords or BitLocker."
