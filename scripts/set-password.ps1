# Sets your own access password (REMOTE_PC_TOKEN in .env), minimum 4 characters.
# Usage:  .\scripts\set-password.ps1            (asks for it)
#         .\scripts\set-password.ps1 mypass
param([string]$Password)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not $Password) { $Password = Read-Host "New password (min 4 characters)" }
if ($Password.Length -lt 4) { throw "Password must be at least 4 characters." }
if ($Password -match '\s') { throw "Password must not contain spaces." }
if ($Password.Length -lt 12) { Write-Warning "Short password: anyone who finds your link could try to guess it. 12+ characters is much safer." }
$lines = @()
if (Test-Path ".env") { $lines = @(Get-Content ".env") }
$found = $false
$lines = $lines | ForEach-Object { if ($_ -match '^\s*REMOTE_PC_TOKEN\s*=') { $found = $true; "REMOTE_PC_TOKEN=$Password" } else { $_ } }
if (-not $found) { $lines += "REMOTE_PC_TOKEN=$Password" }
Set-Content -Path ".env" -Value $lines -Encoding ascii
Write-Host "Password saved. Restart start.ps1 to use it." -ForegroundColor Green
