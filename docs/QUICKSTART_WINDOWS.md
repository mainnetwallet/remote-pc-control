# Windows Quick Start

Install the Windows agent and connect the Android app.

## Requirements

- Windows 10/11, in the desktop session you want to control
- Python 3.11+ x64 (Python 3.12 recommended)
- Node.js 22 and Git
- Android phone; Tailscale on both devices for private remote access

## 1. Clone and install

Open PowerShell as your normal Windows user:

```powershell
cd $HOME
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

Setup creates `.venv`, installs dependencies, builds the web dashboard, and creates `.env` with a random `REMOTE_PC_TOKEN`. Re-running setup is safe; use `.\scripts\setup.ps1 -Force` to reinstall dependencies and rebuild.

Already cloned? Review local changes, then run `git pull origin main` before setup.

## 2. Find your access token

The setup script prints the generated token. Save it securely. To view it later:

```powershell
Get-Content .env | Select-String '^REMOTE_PC_TOKEN='
```

Use the full value after `REMOTE_PC_TOKEN=`. Anyone with the token and network access can control your PC. Never commit or share `.env`.

To set a new password, run `.\scripts\set-password.ps1` and follow the prompt. Use a long, unique password (12+ characters recommended); restart the agent afterwards.

## 3. Start the agent

```powershell
.\scripts\start.ps1
```

Keep this window open. The agent listens on port **8888**. Check it on the PC at `http://localhost:8888/api/health`; a healthy response contains `"ok":true`.

Stop the agent with **Ctrl+C**.

## 4. Connect the phone

Choose one connection method:

**A. Tailscale (recommended for remote access)**

1. Install Tailscale on the PC and phone and sign in to the same tailnet.
2. On the PC run `tailscale ip -4`.
3. In the app enter `http://<PC-Tailscale-IP>:8888`.

The setup script attempts to create a firewall rule restricted to the Tailscale address range `100.64.0.0/10`. If that fails, run setup from an Administrator PowerShell and verify the rule before connecting.

**B. Same Wi-Fi**

1. Run `ipconfig` and find the PC's IPv4 address.
2. Connect the phone to the same trusted Wi-Fi.
3. In the app enter `http://<PC-LAN-IP>:8888`.

If needed, add a firewall rule limited to the private profile and local subnet (Administrator PowerShell):

```powershell
New-NetFirewallRule -DisplayName "RemotePCControl LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 -RemoteAddress LocalSubnet -Profile Private
```

**C. From outside the home network**

Follow the [Cloudflare Tunnel guide](CLOUDFLARE.md). Never port-forward port 8888 directly to the internet.

## 5. Install and use Android

1. Open the repository's **Actions → Android APK** workflow or **Releases**.
2. Download the `remote-pc-control-android-debug` artifact or latest APK release.
3. Install the APK (allow installation from this source if Android asks).
4. Enter the PC URL and token, tap **Connect**, then start a screen session.

Choose **Click** (tap = click, drag = move the pointer), **Drag**, or **Scroll** mode. The toolbar also provides double-click, fullscreen, quick keys, text entry and quality presets.

## 6. Tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
```

The CI workflow also builds the React dashboard.

## Troubleshooting

| Problem | Fix |
|---|---|
| Python or npm not found | Install Python 3.11+ and Node.js, then open a new PowerShell window. |
| Token rejected | Copy the full `REMOTE_PC_TOKEN` from `.env`; check that it is not the placeholder. |
| Phone cannot connect | Check the agent, URL, port 8888, network route and Windows Firewall. |
| `502 Bad Gateway` | Start the agent first; confirm the tunnel forwards to `http://localhost:8888`. |
| Black screen or missing input | Unlock Windows and close any UAC prompt. The secure sign-in desktop is not controllable. |
| Too many failed attempts | Wait for the temporary lockout to expire and use the correct token. |
| WebRTC does not connect | Try the same Wi-Fi or Tailscale; a TURN relay may be needed on restrictive mobile networks. |

For architecture, endpoints and component details, see [ARCHITECTURE.md](ARCHITECTURE.md).
