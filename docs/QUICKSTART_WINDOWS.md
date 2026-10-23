# Windows Quick Start

Set up the Windows agent and connect your phone.

## Requirements

- Windows 10/11 desktop session
- Python 3.11+ (Python 3.12 recommended)
- Node.js and npm
- Git
- Android phone; install Tailscale on both devices for private remote access

## 1. Install

Open PowerShell in your user account:

```powershell
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

Setup creates `.venv`, installs Python dependencies, builds the dashboard, and creates `.env` with a random access token. Keep that token private; do not commit `.env`.

If the repository is already cloned, update it with `git pull origin main`. Review or save local changes first.

## 2. Start the agent

```powershell
.\scripts\start.ps1
```

Keep this PowerShell window open. The server listens on port **8888**. Verify locally at `http://localhost:8888/api/health`.

Stop the agent with **Ctrl+C**.

## 3. Connect your phone

Choose one connection method:

- **Tailscale:** Sign in to the same tailnet on both devices. Run `tailscale ip -4` on the PC and use `http://<PC-Tailscale-IP>:8888`.
- **Same Wi-Fi:** Use the PC's LAN IPv4 address from `ipconfig`, for example `http://192.168.1.20:8888`.
- **Outside your network:** Follow the [Cloudflare Tunnel guide](CLOUDFLARE.md).

Install the Android APK from GitHub Actions or Releases. In the app, enter the PC URL and the `REMOTE_PC_TOKEN` value from `.env`, then tap **Connect** and start a screen session.

If a firewall rule is needed, restrict it to your trusted network. Do not expose port 8888 to the public internet.

## 4. Troubleshooting

| Issue | Solution |
|---|---|
| Setup says Python/npm is missing | Install Python and Node.js, then open a new PowerShell window. |
| Token is rejected | Check `.env` for a non-placeholder `REMOTE_PC_TOKEN`; use the complete value. |
| Phone cannot connect | Confirm both devices can reach each other, the URL and port are correct, and the agent is running. |
| Black screen or missing input | Unlock the desktop; UAC prompts and the Windows sign-in screen are not controllable. |
| Tunnel returns 502 | Start the agent before starting the tunnel. |

## 5. Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
```

For Android build instructions, see [android/README.md](../android/README.md).
