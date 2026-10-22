$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path ".env")) {
  $bytes = New-Object byte[] 48
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($bytes); $rng.Dispose()
  $token = [Convert]::ToBase64String($bytes).Replace("+","-").Replace("/","_").TrimEnd("=")
  @"
REMOTE_PC_TOKEN=$token
REMOTE_PC_HOST=0.0.0.0
REMOTE_PC_PORT=8888
REMOTE_PC_FPS=5
REMOTE_PC_JPEG_QUALITY=55
"@ | Set-Content -Encoding ascii ".env"
  Write-Host "Save this access token securely: $token" -ForegroundColor Yellow
}
Write-Host "Firewall should allow TCP 8888 only from Tailscale range 100.64.0.0/10. Never expose publicly."
