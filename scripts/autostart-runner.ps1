# Runs at Windows sign-in (hidden, via autostart-hidden.vbs). Waits for the network, then keeps the server running.
#  - Network not ready: retries every 10 s for the first 20 tries, then every 60 s, until it is ready.
#  - "Ready" = internet reachable (TCP 1.1.1.1:443) and, if Tailscale is installed, it has its 100.x address.
#  - If the server stops or crashes it is restarted after 10 s.
# Log: autostart.log in the project folder.
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$log = Join-Path $Root "autostart.log"
if ((Test-Path $log) -and (Get-Item $log).Length -gt 1MB) { Remove-Item $log -Force -ErrorAction SilentlyContinue }
function Log($m) { Add-Content -Path $log -Value ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $m) }

function Test-Online {
  $c = $null
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect("1.1.1.1", 443, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(3000, $false)
    if ($ok) { try { $c.EndConnect($iar) } catch { $ok = $false } }
    return ($ok -and $c.Connected)
  } catch { return $false }
  finally { if ($c) { $c.Close() } }
}

function Test-Tailscale {
  $ts = Get-Command tailscale -ErrorAction SilentlyContinue
  if (-not $ts) {
    $p = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
    if (Test-Path $p) { $ts = $p } else { return $true }   # Tailscale not used on this PC
  }
  try { return [bool]((& $ts ip -4 2>$null) -match '^100\.') } catch { return $false }
}

function Wait-ForNetwork {
  $n = 0
  while ($true) {
    $online = Test-Online
    $tail = Test-Tailscale
    if ($online -and $tail) { if ($n -gt 0) { Log "Network is ready after $n retries" }; return }
    $n++
    $delay = if ($n -le 20) { 10 } else { 60 }
    if ($n -le 3 -or $n % 10 -eq 0) { Log "Network not ready (internet=$online tailscale=$tail), try $n, next try in $delay s" }
    Start-Sleep -Seconds $delay
  }
}

Log "Autostart runner started"
while ($true) {
  if (Get-NetTCPConnection -LocalPort 8888 -State Listen -ErrorAction SilentlyContinue) {
    Log "Port 8888 is already in use (server already running). Runner exits."
    exit 0
  }
  Wait-ForNetwork
  Log "Starting server"
  try { & (Join-Path $PSScriptRoot "start.ps1") *>> $log } catch { Log "Server error: $($_.Exception.Message)" }
  Log "Server stopped. Restarting in 10 s"
  Start-Sleep -Seconds 10
}
