# Sets or changes the PC-side unlock PIN (4-12 digits) used by lock_overlay.py.
# Usage:  .\scripts\set-pin.ps1            (asks for it, input hidden)
#         .\scripts\set-pin.ps1 1234       (visible in shell history -- prefer the prompt)
# You can also set/change the PIN from the phone app: POST /api/v1/lock/pin {"pin":"1234"}
# The PIN is passed to Python on stdin, never on a command line, and is never logged.
param([string]$Pin)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not $Pin) {
  $sec = Read-Host "New unlock PIN (4-12 digits)" -AsSecureString
  $Pin = [System.Net.NetworkCredential]::new("", $sec).Password
}
if ($Pin -notmatch '^\d{4,12}$') { throw "PIN must be 4-12 digits, numbers only." }
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\scripts\setup.ps1 first." }
$backend = Join-Path $Root "backend"
$Pin | & $py -c "import sys; sys.path.insert(0, sys.argv[1]); from app import pinlock; pinlock.set_pin(sys.stdin.readline().strip()); print('state file:', pinlock.STATE_PATH)" $backend
if ($LASTEXITCODE -ne 0) { throw "Could not save the PIN." }
Write-Host "PIN saved." -ForegroundColor Green
