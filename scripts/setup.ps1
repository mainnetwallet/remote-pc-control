$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Install Python 3.11+ x64 first." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Install Node.js/npm first." }
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[test,build]"
Push-Location frontend
npm install
npm run build
Pop-Location
New-Item -ItemType Directory -Force "backend\app\static" | Out-Null
Copy-Item -Recurse -Force "frontend\dist\*" "backend\app\static\"
if (-not (Test-Path ".env")) {
  $bytes = New-Object byte[] 48
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($bytes); $rng.Dispose()
  $token = [Convert]::ToBase64String($bytes).Replace("+","-").Replace("/","_").TrimEnd("=")
  @"
REMOTE_PC_TOKEN=$token
REMOTE_PC_HOST=0.0.0.0
REMOTE_PC_PORT=8788
REMOTE_PC_FPS=10
REMOTE_PC_JPEG_QUALITY=55
REMOTE_PC_MAX_WIDTH=1280
REMOTE_PC_SHOW_CURSOR=1
"@ | Set-Content -Encoding ascii ".env"
  Write-Host "Save this access token securely: $token" -ForegroundColor Yellow
}
try { New-NetFirewallRule -DisplayName "RemotePCControl Tailscale only" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8788 -RemoteAddress "100.64.0.0/10" -Profile Any | Out-Null }
catch { Write-Warning "Run elevated PowerShell to add a firewall rule restricted to 100.64.0.0/10. Never expose publicly." }
Write-Host "Setup complete. Run .\scripts\start.ps1"
