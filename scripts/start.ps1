$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Run .\scripts\setup.ps1 first." }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Optional settings in .env:
#   QUICK_TUNNEL=1       start a free Cloudflare quick tunnel together with the server
#   GIST_TOKEN=...       GitHub token (scope: gist only). The new tunnel link is written to a secret Gist
#   GIST_ID=...          created automatically on first run; the Android app reads the link from it ("gist:<id>")
$envVars = @{}
if (Test-Path ".env") {
  foreach ($line in Get-Content ".env") {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and -not $line.TrimStart().StartsWith("#")) {
      $envVars[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
  }
}

function Read-SharedText($path) {
  try {
    # .NET resolves relative paths against the process folder, not PowerShell's current folder, so use a full path
    $full = [System.IO.Path]::GetFullPath((Join-Path $Root $path))
    $fs = [System.IO.File]::Open($full, 'Open', 'Read', 'ReadWrite')
    try { return (New-Object System.IO.StreamReader($fs)).ReadToEnd() } finally { $fs.Dispose() }
  } catch { return "" }
}

function Publish-Gist($url, $token, $gistId) {
  $headers = @{ Authorization = "Bearer $token"; "User-Agent" = "remote-pc-control"; Accept = "application/vnd.github+json" }
  $files = @{ "pc-url.txt" = @{ content = $url } }
  if ($gistId) {
    $body = @{ files = $files } | ConvertTo-Json -Depth 5
    Invoke-RestMethod -Method Patch -Uri "https://api.github.com/gists/$gistId" -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8" | Out-Null
    return $gistId
  }
  $body = @{ description = "remote-pc-control link"; public = $false; files = $files } | ConvertTo-Json -Depth 5
  $r = Invoke-RestMethod -Method Post -Uri "https://api.github.com/gists" -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8"
  Add-Content -Path ".env" -Value "GIST_ID=$($r.id)" -Encoding ascii
  return $r.id
}

$tunnel = $null
if ($envVars["QUICK_TUNNEL"] -eq "1") {
  if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "Installing cloudflared..." -ForegroundColor Yellow
    winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
  }
  if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Warning "cloudflared is not available yet. Close PowerShell, open a new one and run start.ps1 again. Starting without the tunnel."
  } else {
    Remove-Item "cloudflared.log" -ErrorAction SilentlyContinue
    $tunnel = Start-Process cloudflared -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://localhost:8888") -WindowStyle Hidden -PassThru `
      -RedirectStandardError "cloudflared.log" -RedirectStandardOutput "cloudflared.out.log"
    $url = $null
    for ($i = 0; $i -lt 40 -and -not $url; $i++) {
      Start-Sleep -Seconds 1
      if ($tunnel.HasExited) { break }
      if ((Read-SharedText "cloudflared.log") -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $url = $Matches[0] }
    }
    if (-not $url) {
      Write-Warning "Could not get a tunnel link. See cloudflared.log. Starting the server without it."
    } else {
      Write-Host "Tunnel link: $url" -ForegroundColor Green
      if ($envVars["GIST_TOKEN"]) {
        try {
          $id = Publish-Gist $url $envVars["GIST_TOKEN"] $envVars["GIST_ID"]
          Write-Host "Saved to your secret Gist. In the Android app enter as PC URL:  gist:$id" -ForegroundColor Green
        } catch { Write-Warning "Could not update the Gist: $($_.Exception.Message)" }
      } else {
        Write-Host "(Set GIST_TOKEN in .env to publish this link automatically for the Android app.)" -ForegroundColor Yellow
      }
      Write-Host "The tunnel link needs a few seconds before it works on the phone." -ForegroundColor Cyan
    }
  }
}

try {
  & ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8888 --ws-per-message-deflate false
} finally {
  if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
}
