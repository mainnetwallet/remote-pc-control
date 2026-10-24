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
| Nothing else for the **Setup installer** (Option B): Python, Node.js and the repository are not needed; everything is inside `RemotePCControl.exe` | Option B |
| Python 3.11+ x64 (3.12 recommended), Node.js 22, Git | Option A (from source) only |
| Tailscale on the phone, and either Tailscale on the PC **or** the built-in Tailscale of the app (Option B: app window → Internet tab → Turn on) | Private remote access (recommended) |

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

### Option B · Windows installer (packaged `RemotePCControl.exe`), no terminal needed

1. Get `RemotePCControl-Setup.exe`: it is built automatically on every push to `main` and published on the **Releases** page (one release per build, `build-<commit>`; it always holds both `RemotePCControl-Setup.exe` and `RemotePCControl-Android.apk`). You can also run **GitHub → Actions → Windows installer** by hand, or push a tag such as `v1.0.0`.
2. Run the setup and accept the Windows (UAC) prompt. The installer does everything itself:
   - installs into `Program Files\RemotePCControl` and adds Start Menu and desktop shortcuts
   - registers the scheduled task `RemotePCControl` that starts the agent at sign-in with **administrator rights** (no prompt), so mouse and keyboard also work in Task Manager, Registry Editor and admin terminals
   - adds the firewall rule `RemotePCControl Tailscale only` (TCP 8888 from `100.64.0.0/10`)
   - starts the agent right away
3. On the first start the **Remote PC Control app window** opens (a normal desktop window, English / বাংলা button at the top). It shows the **PC address and the access token** for the phone app. Open it again any time with the **Remote PC Control** shortcut. The bar at the top has a **Turn off server / Turn on server** button: use it to stop or start the server (the phone cannot connect while it is off) without closing the window. Closing the window leaves the server as it is. From the panel you can, without any terminal:
   - change the password, or make a random one
   - turn **Start with Windows (as administrator)** on or off
   - add or remove the Tailscale and same-Wi-Fi firewall rules
   - set a PIN, lock and unlock, and keep the PIN lock screen running at sign-in
   - start a Cloudflare internet link (installs `cloudflared` for you)
   - change screen and speed settings, read the logs, restart or stop the agent
4. The panel opens **only on the PC itself** (never from the phone, Tailscale, Wi-Fi or a tunnel) and also asks for the password. Files: `%LOCALAPPDATA%\RemotePCControl\.env` (settings) and `agent.log`. The installer's autostart and firewall step writes its result to `%ProgramData%\RemotePCControl\setup.log` (look there if the Startup tab shows autostart or the firewall as off). Uninstalling removes the tasks and the firewall rule.

Because the agent runs as administrator, use a strong token.

### Built-in Tailscale (Option B, no Tailscale install on the PC)

The installer includes `tsbridge.exe`, a small Tailscale node. In the app window open **Internet → Built-in Tailscale → Turn on**, then open the sign-in link once and log in with the same Tailscale account as the phone. The phone then connects to `http://<address shown in the app>:8888`. It needs no driver, no administrator step and no firewall rule. The choice is remembered and it starts with the server.

Limits: screen video uses the WebSocket (JPEG) mode, because the faster WebRTC video cannot pass through the built-in node; and the phone still needs the Tailscale app.

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
| **Windows installer** | Releases page (`build-<commit>`, file `RemotePCControl-Setup.exe`), or GitHub Actions → *Windows installer* | Every push to `main` (docs-only changes excluded), a tag matching `v*`, or run manually. Packages `RemotePCControl.exe` (runs as administrator) and builds the Inno Setup installer |

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
