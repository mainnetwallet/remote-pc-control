<div align="center">

# Windows Quick Start

Install the Windows agent and connect the Android app in about ten minutes.

[← Project README](../README.md) · [Install and autostart](../INSTALL_WINDOWS.md) · [Architecture](ARCHITECTURE.md)

</div>

---

## Requirements

| | |
|---|---|
| **PC** | Windows 10/11, signed in to the desktop session you want to control |
| **Software** | Python 3.11+ x64 (3.12 recommended), Node.js 22, Git |
| **Phone** | Android phone; Tailscale on both devices for private remote access |

## 1 · Clone and install

Open PowerShell as your normal Windows user:

```powershell
cd $HOME
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

Setup creates `.venv`, installs dependencies, builds the web dashboard, and creates `.env` with a random `REMOTE_PC_TOKEN`. It ends with `Setup complete. Run .\scripts\start.ps1`. Re-running setup is safe and fast: it only reinstalls what changed. Use `.\scripts\setup.ps1 -Force` to reinstall dependencies and rebuild everything.

> [!TIP]
> Already cloned? Review local changes, then run `git pull origin main` before setup.

## 2 · Find your access token

Setup prints the generated token once. Save it securely. To view it later:

```powershell
Get-Content .env | Select-String '^REMOTE_PC_TOKEN='
```

Use the full value after `REMOTE_PC_TOKEN=`.

To choose your own password instead, run `.\scripts\set-password.ps1` and follow the prompt (minimum 4 characters, no spaces; 12+ recommended), then restart the agent.

> [!WARNING]
> Anyone with the token and network access can control your PC. Never commit or share `.env`.

## 3 · Start the agent

```powershell
.\scripts\start.ps1
```

Keep this window open. The agent listens on port **8888**. Check it on the PC at `http://localhost:8888/api/health`; a healthy response contains `"ok":true`. Stop the agent with **Ctrl+C**.

## 4 · Connect the phone

Choose one connection method.

<details open>
<summary><b>A · Tailscale</b> (recommended for remote access)</summary>

1. Install Tailscale on the PC and phone and sign in to the same tailnet.
2. On the PC run `tailscale ip -4`.
3. In the app enter `http://<PC-Tailscale-IP>:8888`.

`setup.ps1` tries to create a firewall rule restricted to the Tailscale range `100.64.0.0/10`. If it warns, run setup again from an Administrator PowerShell and verify the rule before connecting.

</details>

<details>
<summary><b>B · Same Wi-Fi</b></summary>

1. Run `ipconfig` and find the PC's IPv4 address.
2. Connect the phone to the same trusted Wi-Fi.
3. In the app enter `http://<PC-LAN-IP>:8888`.

If needed, add a firewall rule limited to the private profile and the local subnet (Administrator PowerShell):

```powershell
New-NetFirewallRule -DisplayName "RemotePCControl LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 -RemoteAddress LocalSubnet -Profile Private
```

If Windows marks your Wi-Fi as *Public*, switch the network to *Private* in Windows settings instead of widening the rule.

</details>

<details>
<summary><b>C · From outside the home network</b></summary>

Follow the [Cloudflare Tunnel guide](CLOUDFLARE.md). Never port-forward port 8888 directly to the internet.

</details>

## 5 · Install and use Android

1. Open the repository's **Actions → Android APK** workflow, or **Releases**.
2. Download the `remote-pc-control-android-debug` artifact or the latest APK release.
3. Install the APK (allow installation from this source if Android asks).
4. Enter the PC URL and token, tap **Connect**, then start a screen session.

Choose **Click** (tap = click, drag = move the pointer), **Drag**, or **Scroll** mode. The toolbar also offers double-click, fullscreen, quick keys, text entry and quality presets.

## 6 · Run the tests (optional)

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
```

The CI workflow also builds the React dashboard.

## Optional next steps

| I want to… | Go to |
|---|---|
| Start the agent automatically at sign-in | [Install and autostart](../INSTALL_WINDOWS.md#start-at-sign-in-optional) |
| Lock the PC with a PIN from my phone | [PIN lock](../README.md#-pin-lock) |
| Get a stable `https://` link | [Cloudflare guide](CLOUDFLARE.md) |
| Reduce lag or fix "WebSocket" mode | [WebRTC details](WEBRTC.md) |

## Troubleshooting

| Problem | Fix |
|---|---|
| Python or npm not found | Install Python 3.11+ and Node.js, then open a new PowerShell window |
| Token rejected | Copy the full `REMOTE_PC_TOKEN` from `.env` and check it is not the placeholder `replace-with-your-password` |
| Phone cannot connect | Check the agent is running, the URL, port 8888, the network route and Windows Firewall |
| `502 Bad Gateway` | Start the agent first; confirm the tunnel forwards to `http://localhost:8888` |
| Black screen or missing input | Unlock Windows and close any UAC prompt; the secure sign-in desktop is not controllable |
| Too many failed attempts | Wait for the lockout to expire (5 minutes per client, 10 minutes for the global guard) and use the correct token |
| WebRTC does not connect | Try the same Wi-Fi or Tailscale; a TURN relay may be needed on restrictive mobile networks |

More fixes (elevated windows, autostart, lock screen): [full troubleshooting table](../README.md#-troubleshooting).
