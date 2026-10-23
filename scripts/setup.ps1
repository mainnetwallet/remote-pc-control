param([switch]$Force)   # -Force: reinstall packages and rebuild the dashboard even if nothing changed
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Install Python 3.11+ x64 first." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Install Node.js/npm first." }
if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = ".\.venv\Scripts\python.exe"

# Python packages: install only when missing or when pyproject.toml changed (use -Force to redo).
# The stamp lives inside .venv, so deleting .venv forces a fresh install.
$pyHash = (Get-FileHash "pyproject.toml" -Algorithm SHA256).Hash
$pyStamp = ".venv\.pyproject.sha256"
$pyCurrent = (Test-Path $pyStamp) -and ((Get-Content $pyStamp -Raw).Trim() -eq $pyHash)
if ($Force -or -not $pyCurrent) {
  & $py -m pip install --upgrade pip
  & $py -m pip install -e ".[test,build]"
  if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
  # Optional: much faster screen capture (DXGI). If it cannot be installed the server simply keeps using mss.
  try {
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $py -m pip install --quiet "dxcam>=0.3.0" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warning "Fast capture (dxcam) was not installed; the standard capture is used." }
  } catch { Write-Warning "Fast capture (dxcam) was not installed; the standard capture is used." }
  finally { $ErrorActionPreference = $prevEap }
  Set-Content -Path $pyStamp -Value $pyHash -Encoding ascii
} else {
  Write-Host "Python packages are up to date (use -Force to reinstall)."
}

# Dashboard: npm install only when package files changed, build only when sources are newer than the last build.
$feHash = (Get-FileHash "frontend\package.json" -Algorithm SHA256).Hash
if (Test-Path "frontend\package-lock.json") { $feHash += (Get-FileHash "frontend\package-lock.json" -Algorithm SHA256).Hash }
$feStamp = "frontend\node_modules\.package.sha256"
$feCurrent = (Test-Path $feStamp) -and ((Get-Content $feStamp -Raw).Trim() -eq $feHash)
Push-Location frontend
if ($Force -or -not $feCurrent) {
  npm install
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed." }
  Set-Content -Path "node_modules\.package.sha256" -Value $feHash -Encoding ascii
} else {
  Write-Host "Dashboard packages are up to date."
}
$dist = "dist\index.html"
$needBuild = $Force -or -not (Test-Path $dist)
if (-not $needBuild) {
  $distTime = (Get-Item $dist).LastWriteTime
  $sources = @(Get-ChildItem "src" -Recurse -File) + @(Get-Item "index.html", "package.json", "tsconfig.json", "vite.config.ts")
  $needBuild = [bool]($sources | Where-Object { $_.LastWriteTime -gt $distTime } | Select-Object -First 1)
}
if ($needBuild) {
  npm run build
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm run build failed." }
} else {
  Write-Host "Dashboard is already built."
}
Pop-Location
$static = "backend\app\static"
if ($needBuild -or -not (Test-Path "$static\index.html")) {
  New-Item -ItemType Directory -Force $static | Out-Null
  Copy-Item -Recurse -Force "frontend\dist\*" "$static\"
}
if (-not (Test-Path ".env")) {
  $bytes = New-Object byte[] 48
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($bytes); $rng.Dispose()
  $token = [Convert]::ToBase64String($bytes).Replace("+","-").Replace("/","_").TrimEnd("=")
  @"
REMOTE_PC_TOKEN=$token
REMOTE_PC_HOST=0.0.0.0
REMOTE_PC_PORT=8888
REMOTE_PC_FPS=20
REMOTE_PC_JPEG_QUALITY=55
REMOTE_PC_MAX_WIDTH=1280
REMOTE_PC_SHOW_CURSOR=1
REMOTE_PC_MOTION_QUALITY=70
REMOTE_PC_MOTION_WIDTH=80
REMOTE_PC_CAPTURE=auto
"@ | Set-Content -Encoding ascii ".env"
  Write-Host "Save this access token securely: $token" -ForegroundColor Yellow
}
try { New-NetFirewallRule -DisplayName "RemotePCControl Tailscale only" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 -RemoteAddress "100.64.0.0/10" -Profile Any | Out-Null }
catch { Write-Warning "Run elevated PowerShell to add a firewall rule restricted to 100.64.0.0/10. Never expose publicly." }
Write-Host "Setup complete. Run .\scripts\start.ps1"
