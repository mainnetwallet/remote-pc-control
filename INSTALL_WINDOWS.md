# Windows Installation and Autostart

This guide covers installing the agent, connecting your phone, and optionally starting the agent at Windows sign-in.

## Requirements

- Windows 10/11 x64
- Python 3.11+ (Python 3.12 recommended), Node.js 22 and Git
- Tailscale on the PC and phone for private remote access

## Install and run

Open PowerShell as your normal user in the logged-in desktop session:

```powershell
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
.\scripts\start.ps1
```

Setup installs dependencies, builds the dashboard, and creates `.env` with a random access token. Keep the token private and never commit `.env`. Keep the `start.ps1` window open while you use the agent; press **Ctrl+C** to stop it.

## Connect the phone

Choose one method:

- **Tailscale:** Sign in to the same tailnet on both devices and use `http://<PC-Tailscale-IP>:8888`.
- **Same Wi-Fi:** Use `http://<PC-LAN-IP>:8888` from a trusted local network.
- **Cloudflare:** For access from outside the LAN, follow [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md).

Do not forward port 8888 directly to the internet. Prefer a private network or protect a named Cloudflare hostname with Cloudflare Access.

## Optional: start at sign-in

Run this from the repository folder:

```powershell
.\scripts\install-autostart.ps1
```

This registers a scheduled task that starts the agent hidden when **your user signs in**. It runs in the interactive desktop session because screen capture and input need that session; it does not run before sign-in. The runner waits for network availability and restarts the agent if it exits.

Useful commands:

```powershell
Start-ScheduledTask -TaskName RemotePCControl
Stop-ScheduledTask -TaskName RemotePCControl
.\scripts\install-autostart.ps1 -Remove
```

The log is written to `autostart.log`. To remove the task, use the final command above.

## Build artifacts

- **Android APK:** GitHub Actions → **Android APK**, or see [android/README.md](android/README.md).
- **Windows installer:** Run the **Windows installer** workflow manually or push a version tag such as `v1.0.0`. The workflow packages the agent and builds an Inno Setup installer.

## Security and limitations

- Anyone with the token and network access can control the PC. Keep the token and tunnel URL private.
- The agent controls only the signed-in interactive Windows desktop. It cannot capture/control the Windows sign-in screen, UAC secure desktop, or bypass Windows authentication.
- Setup attempts to add a firewall rule restricted to Tailscale addresses. Verify the rule if setup warns; do not replace it with a public inbound rule.
- Wake-on-LAN is **not configured** in the API. The PC cannot wake itself; mobile-data wake requires a separately authenticated, always-on LAN relay.
- The agent does not need administrator privileges for normal operation. Use Administrator PowerShell only for firewall changes when necessary.
- To control elevated windows (Task Manager, Registry Editor, admin terminals), run the agent as administrator: `.\scripts\install-autostart.ps1 -Admin` from an Administrator PowerShell. Use a strong password, because the agent then has full admin rights.

For the full setup flow and troubleshooting, see [docs/QUICKSTART_WINDOWS.md](docs/QUICKSTART_WINDOWS.md). For the repository structure, endpoints, tests and transports, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
