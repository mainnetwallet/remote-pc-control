# Remote PC Control

Windows 11 Pro remote monitor/control starter for a PC you own. Use only through a private Tailscale/WireGuard network; never port-forward port 8788.

Features: CPU/RAM/disk/network monitor, token-authenticated API, mobile dashboard, screen/input WebSockets, lock/sleep/restart/shutdown, WOL helper, tests and Windows build workflow.

Important: run the agent in the logged-in interactive desktop session. It does not capture/control Windows secure desktop, UAC prompts or sign-in screen, and does not bypass Windows authentication. Use Windows Remote Desktop or a reviewed remote-access product to log in. Mobile-data WOL requires a separately authenticated always-on LAN relay. JPEG WebSocket streaming is a starter; test performance on your hardware.

Setup: install Python 3.12 x64, Node.js 22 and Tailscale on PC/phone. Run `scripts/setup.ps1`, then `scripts/start.ps1`. Connect phone to the same tailnet and open `http://<PC-Tailscale-IP>:8788`. Keep `.env` secret.