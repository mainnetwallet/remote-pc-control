<#
Registers (or re-registers) the Remote PC Control Credential Provider for the CPUS_UNLOCK_WORKSTATION scenario.
Run as Administrator, AFTER building RemoteUnlockProvider.dll (see CMakeLists.txt) and signing it.

This script does NOT disable any existing credential provider. It only adds one new CLSID under
HKLM\...\Credential Providers so Windows offers an extra tile when (and only when) a request is pending.

    .\register.ps1 -DllPath .\build\Release\RemoteUnlockProvider.dll
#>
param(
    [Parameter(Mandatory=$true)][string]$DllPath,
    [string]$Clsid = "{8F2A6C1E-5B7D-4E39-9A41-6D0C2E7B13F5}"   # must match CLSID_RemoteUnlockProvider in the .cpp
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $DllPath)) { throw "DLL not found: $DllPath" }
$DllPath = (Resolve-Path $DllPath).Path

$clsidKey = "HKLM:\SOFTWARE\Classes\CLSID\$Clsid"
New-Item -Path $clsidKey -Force | Out-Null
New-ItemProperty -Path $clsidKey -Name "(Default)" -Value "Remote PC Control Unlock Provider" -Force | Out-Null
$inproc = New-Item -Path "$clsidKey\InprocServer32" -Force
New-ItemProperty -Path $inproc.PSPath -Name "(Default)" -Value $DllPath -Force | Out-Null
New-ItemProperty -Path $inproc.PSPath -Name "ThreadingModel" -Value "Apartment" -Force | Out-Null

$providerKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$Clsid"
New-Item -Path $providerKey -Force | Out-Null
New-ItemProperty -Path $providerKey -Name "(Default)" -Value "Remote PC Control Unlock Provider" -Force | Out-Null

Write-Host "Registered. Lock the workstation ($([char]0x2318)+L or Win+L) and confirm:"
Write-Host "  1. The normal password tile is still there and still works."
Write-Host "  2. With no pending request, no extra tile appears."
Write-Host "Run uninstall.ps1 any time to remove this provider and go back to stock Windows sign-in."
