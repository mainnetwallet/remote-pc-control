<div align="center">

# Windows Installation and Autostart

Install the agent, connect your phone, and optionally start it at Windows sign-in.

[Requirements](#requirements) ·
[Install](#install) ·
[Connect](#connect-the-phone) ·
[Autostart](#start-at-sign-in-optional) ·
[Firewall](#firewall) ·
[Security](#security-and-limitations)

</div>

---

> [!NOTE]
> This file is also copied next to `RemotePCControl.exe` by the Windows installer, so its links point to the GitHub repository instead of relative paths.

## Requirements

| | Needed for |
|---|---|
| Windows 10 or 11, x64 | Both install options |
| Python 3.11+ x64 (3.12 recommended), Node.js 22, Git | Option A (from source) only |
| Tailscale on the PC and phone | Private remote access (recommended) |

## Install

Choose **one** option.

### Option A · From source (recommended: full feature set)

Open PowerShell as your normal user, in the signed-in desktop session you want to control:

```powershell
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
.\scripts\start.ps1
```

`setup.ps1` installs dependencies, builds the dashboard, and creates `.env` with a random access token (printed once, and stored in `.env`). Keep the token private and never commit `.env`. Keep the `start.ps1` window open while you use the agent; press **Ctrl+C** to stop it.

### Option B · Windows installer (packaged `RemotePCControl.exe`)

1. Get `RemotePCControl-Setup.exe`: open **GitHub → Actions → Windows installer**, run the workflow (or push a version tag such as `v1.0.0`), and download the artifact `RemotePCControl-Windows-x64`.
2. Run the setup. It installs per user (no administrator rights) into `%LOCALAPPDATA%\Programs\RemotePCControl`, adds Start Menu and desktop shortcuts, and offers to run `configure-installed.ps1` when it finishes.
3. `configure-installed.ps1` creates `.env` next to the program, with a random token printed in its PowerShell window, **only if `.env` does not exist yet**. Save the token from that window; it stays in `.env`.
4. Start **Remote PC Control** from the shortcut. It runs from its own folder, reads `.env` there, and serves on port 8888. It runs as a console program: close its window to stop it.

What the installer does **not** do or include:

- It does not create a firewall rule; the script only prints a reminder. From an **Administrator PowerShell** create the same Tailscale-only rule that `setup.ps1` would create:

  ```powershell
  New-NetFirewallRule -DisplayName "RemotePCControl Tailscale only" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 -RemoteAddress "100.64.0.0/10" -Profile Any
  ```

- The helper scripts (`set-password.ps1`, `install-autostart.ps1`, tunnel and PIN-lock scripts) and `lock_overlay.py` are not packaged. Change the password by editing `REMOTE_PC_TOKEN` in `.env`, then restart the program. For autostart and the PIN lock use Option A.

## Connect the phone

Choose one method:

| Method | URL | Notes |
|---|---|---|
| **Tailscale** | `http://<PC-Tailscale-IP>:8888` | Same tailnet on both devices. Find the address with `tailscale ip -4` |
| **Same Wi-Fi** | `http://<PC-LAN-IP>:8888` | Trusted local network only. See [Firewall](#firewall) |
| **Cloudflare** | `https://….trycloudflare.com` or your own hostname | [Cloudflare guide](https://github.com/mainnetwallet/remote-pc-control/blob/main/docs/CLOUDFLARE.md) |

Do not forward port 8888 directly to the internet. Prefer a private network, or protect a named Cloudflare hostname with Cloudflare Access.

## Start at sign-in (optional)

Option A only. Run from the repository folder:

```powershell
.\scripts\install-autostart.ps1
```

This registers the scheduled task `RemotePCControl`, which starts the agent **hidden** when **your user signs in** (10 seconds after sign-in). It runs in your interactive desktop session because screen capture and input need that session, so it cannot run before sign-in. The runner waits for the network (internet reachable, and Tailscale up if it is installed), then starts `start.ps1`, and restarts the server 10 seconds after it exits.

| Task | Command |
|---|---|
| Start now (no reboot) | `Start-ScheduledTask -TaskName RemotePCControl` |
| Stop (server and runner) | `Stop-ScheduledTask -TaskName RemotePCControl` |
| Remove the task | `.\scripts\install-autostart.ps1 -Remove` |
| Control elevated windows | From an Administrator PowerShell: `.\scripts\install-autostart.ps1 -Admin` (run once) |

Good to know:

- Logs: `autostart.log` (runner), `server.out.log` and `server.err.log` (server), all in the project folder. At each runner start, a log larger than 1 MB is deleted and started fresh.
- Stopping only the python process makes the runner restart it. Use `Stop-ScheduledTask` to really stop it.
- Running `start.ps1` by hand stops a running `RemotePCControl` task first (otherwise the old server would restart). Resume autostart afterwards with `Start-ScheduledTask -TaskName RemotePCControl` or by signing in again.
- `-Admin` gives the agent full administrator rights, so use a strong password. The UAC secure desktop still cannot be controlled.

## Firewall

| Rule | Created by | Allows | Remove |
|---|---|---|---|
| `RemotePCControl Tailscale only` | `setup.ps1` (needs an Administrator PowerShell, otherwise it warns) | TCP 8888 from `100.64.0.0/10` | `.\scripts\remove-firewall.ps1` (Administrator PowerShell) |
| `RemotePCControl LAN` | You, if you want same-Wi-Fi access | TCP 8888 from the local subnet, private profile | `Remove-NetFirewallRule -DisplayName "RemotePCControl LAN"` |

LAN rule (Administrator PowerShell):

```powershell
New-NetFirewallRule -DisplayName "RemotePCControl LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 -RemoteAddress LocalSubnet -Profile Private
```

Verify the rules if setup warns; never replace them with a public inbound rule.

## Build artifacts

| Artifact | Where | Trigger |
|---|---|---|
| **Android APK** | GitHub Actions → *Android APK*, or the Releases page | Push to `main` touching `android/`, or run manually. See the [Android guide](https://github.com/mainnetwallet/remote-pc-control/blob/main/android/README.md) |
| **Windows installer** | GitHub Actions → *Windows installer* | Run manually, or push a tag matching `v*`. Packages `RemotePCControl.exe` and builds an Inno Setup installer |

## Security and limitations

- Anyone with the token and network access can control the PC. Keep the token and tunnel URL private.
- The agent controls only the signed-in interactive Windows desktop. It cannot capture or control the Windows sign-in screen or the UAC secure desktop, and it does not bypass Windows authentication.
- Setup tries to add a firewall rule restricted to Tailscale addresses. Do not replace it with a public inbound rule.
- Wake-on-LAN is **not configured** in the API. The PC cannot wake itself; waking over mobile data needs a separately authenticated, always-on LAN relay.
- The agent does not need administrator privileges for normal operation. Use an Administrator PowerShell only for firewall changes, or when you deliberately choose `-Admin`.

## Next steps

| Guide | Covers |
|---|---|
| [Windows quick start](https://github.com/mainnetwallet/remote-pc-control/blob/main/docs/QUICKSTART_WINDOWS.md) | Step-by-step first run and troubleshooting |
| [Architecture](https://github.com/mainnetwallet/remote-pc-control/blob/main/docs/ARCHITECTURE.md) | Repository structure, endpoints, tests and transports |
| [Project README](https://github.com/mainnetwallet/remote-pc-control#readme) | Features, configuration and command reference |
