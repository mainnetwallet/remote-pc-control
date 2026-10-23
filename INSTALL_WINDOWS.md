# Windows Installation

Install and run Remote PC Control on your own Windows desktop.

## Requirements

- Windows 10/11
- Python 3.11+ (Python 3.12 recommended)
- Node.js/npm and Git
- Tailscale on the PC and phone for private remote access

## Setup

```powershell
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
.\scripts\start.ps1
```

The setup script creates a virtual environment, builds the dashboard, and generates `.env` with a random `REMOTE_PC_TOKEN`. Store the token securely and never commit `.env`.

## Connect

- **Tailscale:** Sign in on both devices and use `http://<PC-Tailscale-IP>:8888`.
- **Same Wi-Fi:** Use `http://<PC-LAN-IP>:8888`.
- **Remote access without Tailscale:** Follow [Cloudflare Tunnel setup](docs/CLOUDFLARE.md).

Keep the server running in the signed-in desktop session. Never port-forward port 8888 directly to the internet.

## Important limitations

The agent cannot capture or control the Windows sign-in screen, UAC secure desktop, or other protected desktop sessions. It does not bypass Windows authentication. Wake-on-LAN is not configured by default; mobile-data wake requires a separately authenticated always-on LAN relay.

For detailed steps and troubleshooting, see the [Windows quick start](docs/QUICKSTART_WINDOWS.md).
