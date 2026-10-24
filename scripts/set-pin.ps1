# Sets or changes the PC-side unlock PIN (4-12 digits) used by lock_overlay.py.
# Usage:  .\scripts\set-pin.ps1            (asks for it)
#         .\scripts\set-pin.ps1 1234
# You can also set/change the PIN from the phone app: POST /api/v1/lock/pin {"pin":"1234"}
param([string]$Pin)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not $Pin) { $Pin = Read-Host "New unlock PIN (4-12 digits)" }
if ($Pin -notmatch '^\d{4,12}$') { throw "PIN must be 4-12 digits, numbers only." }
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\scripts\setup.ps1 first." }
& $py -c "import sys; sys.path.insert(0,'backend'); from app import pinlock; pinlock.set_pin('$Pin')"
if ($LASTEXITCODE -ne 0) { throw "Could not save the PIN." }
Write-Host "PIN saved." -ForegroundColor Green
