Get-NetFirewallRule -DisplayName "RemotePCControl Tailscale only" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
