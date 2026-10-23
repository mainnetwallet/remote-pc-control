param([switch]$Force, [string]$GistToken = "", [string]$GistId = "")   # -Force: reinstall packages and rebuild the dashboard even if nothing changed; -GistToken/-GistId: save them to .env without asking
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
$example = Join-Path $Root ".env.example"
if (-not (Test-Path ".env")) {
  $bytes = New-Object byte[] 48
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($bytes); $rng.Dispose()
  $token = [Convert]::ToBase64String($bytes).Replace("+","-").Replace("/","_").TrimEnd("=")
  if (Test-Path $example) {
    # New .env = the full .env.example (every setting with its default and comments) with a fresh random password.
    Get-Content $example | ForEach-Object { if ($_ -match '^\s*REMOTE_PC_TOKEN\s*=') { "REMOTE_PC_TOKEN=$token" } else { $_ } } | Set-Content -Encoding ascii ".env"
  } else {
    @"
REMOTE_PC_TOKEN=$token
REMOTE_PC_HOST=0.0.0.0
REMOTE_PC_PORT=8888
REMOTE_PC_FPS=20
REMOTE_PC_JPEG_QUALITY=55
REMOTE_PC_MAX_WIDTH=1280
REMOTE_PC_SHOW_CURSOR=1
REMOTE_PC_MOTION_QUALITY=100
REMOTE_PC_MOTION_WIDTH=100
REMOTE_PC_CAPTURE=auto
"@ | Set-Content -Encoding ascii ".env"
  }
  Write-Host "Save this access token securely: $token" -ForegroundColor Yellow
} elseif (Test-Path $example) {
  # Existing .env: add settings that .env.example gained since (e.g. after git pull). Existing values are never changed,
  # the password is never touched, and a setting you commented out yourself is not added again.
  $have = @{}
  foreach ($line in Get-Content ".env") { if ($line -match '^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') { $have[$Matches[1].ToUpper()] = $true } }
  $missing = @()
  foreach ($line in Get-Content $example) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
      $key = $Matches[1].ToUpper()
      if ($key -ne "REMOTE_PC_TOKEN" -and -not $have[$key]) { $missing += $line }
    }
  }
  if ($missing.Count -gt 0) {
    Add-Content -Path ".env" -Value (@("", "# added by setup.ps1 from .env.example") + $missing) -Encoding ascii
    $names = ($missing | ForEach-Object { ($_ -split '=')[0].Trim() }) -join ", "
    Write-Host "Added new settings to .env: $names" -ForegroundColor Green
  } else {
    Write-Host ".env already has every setting from .env.example."
  }
}
# Optional: lets the Android app find the tunnel link by itself. Needs a GitHub *classic* token with ONLY the "gist" scope.
$envText = Get-Content ".env" -Raw
if ($envText -notmatch '(?m)^\s*GIST_TOKEN\s*=') {
  if (-not $GistToken -and [Environment]::UserInteractive) {
    Write-Host ""
    Write-Host "Optional: GIST_TOKEN lets the Android app find the tunnel link by itself." -ForegroundColor Cyan
    Write-Host "Create a classic token with ONLY the 'gist' scope: https://github.com/settings/tokens"
    $GistToken = (Read-Host "Paste GIST_TOKEN (press Enter to skip)").Trim()
  }
  if ($GistToken -and $GistToken.Length -lt 20) { Write-Warning "That does not look like a GitHub token; GIST_TOKEN was not saved."; $GistToken = "" }
  if ($GistToken) {
    $add = ""
    if ($envText -notmatch '(?m)^\s*QUICK_TUNNEL\s*=') { $add += "`r`nQUICK_TUNNEL=1" }
    $add += "`r`nGIST_TOKEN=$GistToken"
    if ($GistId -and $envText -notmatch '(?m)^\s*GIST_ID\s*=') { $add += "`r`nGIST_ID=$GistId" }
    Add-Content -Path ".env" -Value $add -Encoding ascii
    Write-Host "GIST_TOKEN saved to .env" -ForegroundColor Green
  }
}
try { New-NetFirewallRule -DisplayName "RemotePCControl Tailscale only" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 -RemoteAddress "100.64.0.0/10" -Profile Any | Out-Null }
catch { Write-Warning "Run elevated PowerShell to add a firewall rule restricted to 100.64.0.0/10. Never expose publicly." }
Write-Host "Setup complete. Run .\scripts\start.ps1"
