# Quick Cloudflare tunnel: gives your phone an https link that works from anywhere (no Tailscale, no port-forwarding).
# The link changes every time this runs. For a permanent link see docs/CLOUDFLARE.md (section B).
$ErrorActionPreference = "Stop"
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
  Write-Host "cloudflared installed. Close this PowerShell, open a new one and run .\scripts\start-tunnel.ps1 again." -ForegroundColor Yellow
  exit
}
Write-Host "Make sure .\scripts\start.ps1 is running in another window." -ForegroundColor Cyan
Write-Host "Open the https://....trycloudflare.com link printed below on your phone. Do not share it." -ForegroundColor Yellow
cloudflared tunnel --url http://localhost:8888
