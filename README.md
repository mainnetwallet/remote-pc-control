# Remote PC Control

[![CI](https://github.com/mainnetwallet/remote-pc-control/actions/workflows/ci.yml/badge.svg)](https://github.com/mainnetwallet/remote-pc-control/actions/workflows/ci.yml)

View and control your own Windows PC from a phone: live screen, touch-as-mouse, keyboard, system monitor and power controls. It works from anywhere over Tailscale or a Cloudflare tunnel, from a mobile browser or the native Android app.

> **Use it only on a PC you own.** Never port-forward port 8888 to the internet.

[বাংলা নির্দেশিকা](docs/README.bn.md)

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Connect the phone](#connect-the-phone)
- [Using the remote screen](#using-the-remote-screen)
- [Android app](#android-app)
- [Start with Windows](#start-with-windows)
- [WebRTC mode](#webrtc-mode)
- [Stream quality](#stream-quality)
- [Configuration](#configuration)
- [API](#api)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)
- [Security and limitations](#security-and-limitations)
- [Development](#development)

## Features

- **Low-latency live screen.** WebRTC (H.264 over UDP, input over data channels) with automatic fallback to a JPEG-over-WebSocket stream.
- **Touch control.** Tap to click, long-press to right-click, drag, scroll, double-click, fullscreen and landscape.
- **Trackpad (Android).** Laptop-style pad: one finger moves, tap clicks, double-tap double-clicks, two-finger tap right-clicks, two-finger slide scrolls, tap-then-slide drags.
- **Keyboard.** Text input and quick keys (Esc, Tab, arrows, Win, Alt+Tab, Ctrl+C/V/A/Z).
- **Monitor and power.** CPU, memory, disk and network metrics; lock, sleep, restart and shutdown with confirmation.
- **Brute-force protection.** Token-protected API and WebSockets with per-client and global lockouts.
- **Two clients.** A mobile web dashboard and a native Android app (Material 3, Kotlin and Jetpack Compose).

## Requirements

- Windows 10 or 11, signed in to a desktop session
- Python 3.11 or newer (3.12 recommended), x64
- Node.js 22
- Git
- Tailscale, only if you connect over Tailscale

## Quick start

Open PowerShell as a normal user in your signed-in desktop session.

```powershell
cd $HOME
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

`setup.ps1` creates a virtual environment, installs dependencies, builds the web dashboard and creates a private `.env` with a generated access token. Save the token somewhere safe and never commit `.env`.

- On later runs, `setup.ps1` appends settings that were added to `.env.example` and never changes existing values.
- It also offers an optional `GIST_TOKEN` (press Enter to skip) for the [automatic tunnel link](#automatic-link-for-the-android-app).
- To show the token again: `Get-Content .env | Select-String REMOTE_PC_TOKEN`
- To choose your own password (minimum 4 characters, 12 or more recommended): `.\scripts\set-password.ps1`

Start the server and leave the window open. It listens on port 8888.

```powershell
.\scripts\start.ps1
```

Then [connect the phone](#connect-the-phone). A longer walkthrough is in the [Windows quick start](docs/QUICKSTART_WINDOWS.md).

## Connect the phone

Choose one method.

### Cloudflare quick tunnel

Works from anywhere without an account. In a second PowerShell window:

```powershell
cd $HOME\remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-tunnel.ps1
```

The first run installs `cloudflared`. If prompted, open a new PowerShell window and run the command again. The script prints a link such as `https://xxxx-xxxx.trycloudflare.com`; open it on the phone, or enter it as the *PC URL* in the Android app, then enter the token.

- Verify with `https://<your-link>/api/health`, which returns `{"ok":true,...}`.
- The link changes every time the tunnel restarts. Do not share it.
- For a permanent link on your own domain, see [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md).

#### Automatic link for the Android app

Add to `.env`:

```
QUICK_TUNNEL=1
GIST_TOKEN=your-gist-token
```

`GIST_TOKEN` must be a GitHub classic token with **only the `gist` scope** ([create one](https://github.com/settings/tokens)). Do not reuse a repository token.

`start.ps1` then starts the tunnel together with the server and writes the current link to a secret Gist. The first run creates the Gist and prints `gist:<id>`. Enter `gist:<id>` once as the *PC URL* in the Android app; every Connect reads the current link from the Gist. Anyone who knows the Gist id can read the link but still needs the access token.

### Tailscale

Install Tailscale on the PC and the phone, sign in to the same account on both and turn the VPN on. Find the PC address with `tailscale ip -4` and open `http://<that-ip>:8888`.

The firewall rule created by `setup.ps1` accepts connections only from Tailscale addresses (`100.64.0.0/10`). If the rule could not be created, run `setup.ps1` from an administrator PowerShell.

### Same Wi-Fi

From an administrator PowerShell:

```powershell
New-NetFirewallRule -DisplayName "RemotePCControl LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 -RemoteAddress LocalSubnet -Profile Any
ipconfig
```

Open `http://<PC-IPv4-address>:8888` on a phone on the same network. Reserve a fixed address for the PC in your router so the URL stays stable.

## Using the remote screen

Enter the token, tap **Connect**, then **Start screen**. Choose a mode on the toolbar:

| Mode | Behavior |
|---|---|
| Click | Tap is a left click, long-press is a right click. In the web client, two fingers scroll. |
| Move | Drag moves the pointer without clicking. |
| Drag | Drag holds the left button (select text, move windows). |
| Scroll | Drag up or down scrolls. |

The toolbar also provides **Double-click**, **Fullscreen**, **Keys** (quick keys) and a text box.

## Android app

Download the APK from **Releases**, or from the artifact of the latest **Actions > Android APK** run. The workflow runs on every push to `main` that changes `android/`, and can be started manually. Allow *Install unknown apps* if Android asks. This is a debug build for personal use, not a Play Store release. Build instructions: [android/README.md](android/README.md).

In the app, enter the *PC URL* (`https://....trycloudflare.com`, `gist:<id>`, `http://100.x.x.x:8888` or a LAN address) and the token.

| Screen | Purpose |
|---|---|
| Connect | PC URL and token. Both are remembered after the first login (the token is encrypted with the Android Keystore). Log out forgets them. |
| Dashboard | CPU, memory and disk gauges, network speed (refreshed every 5 s), Lock, Sleep, Restart and Shutdown (all except Lock ask for confirmation), the **Quality** setting and *Start screen session*. |
| Session | Live screen, touch modes, trackpad and keys. An overlay shows the transport, resolution and frame rate, for example `WebRTC · 1280×720 · 30 fps · 38 ms`. **Rotate** switches between portrait and landscape even when auto-rotate is off. |

Quality can be changed while streaming and is remembered:

| Quality | Width | Max FPS | WebRTC bitrate | JPEG quality (fallback) |
|---|---|---|---|---|
| Low | 960 px | 20 | 1.5 Mbit/s | 45 |
| Medium (default) | 1280 px | 30 | 3 Mbit/s | 65 |
| High | 1920 px | 30 | 6 Mbit/s | 78 |
| Native | PC resolution | 20 | 10 Mbit/s | 85 |

Native on a 4K PC needs a fast connection; use High if the stream stutters.

## Start with Windows

Run the server automatically, hidden, when you sign in:

```powershell
.\scripts\install-autostart.ps1            # create or update the startup task
.\scripts\install-autostart.ps1 -Remove    # remove it
```

The task runs as your user (screen capture needs the desktop session), so it starts at sign-in rather than at boot. No administrator rights are needed. The runner waits for the network, restarts the server if it stops and logs to `autostart.log`.

```powershell
Start-ScheduledTask -TaskName RemotePCControl
Stop-ScheduledTask  -TaskName RemotePCControl
```

## WebRTC mode

The JPEG stream sends one picture per frame over a TCP WebSocket, so a single slow packet delays everything behind it. WebRTC sends H.264 video over UDP, drops stale frames instead of queueing them, and carries input on data channels.

### How it works

1. When you tap *Start screen*, the app opens `/ws/rtc` with the same password. This socket only exchanges the connection offer (signaling); video and input then travel directly between phone and PC.
2. The WebSocket JPEG stream starts at the same time, so a picture appears immediately. Once WebRTC video is decoded, the app switches to it and closes the JPEG stream.
3. If WebRTC delivers no video within about 20 seconds, or the PC reports it as unavailable, the app keeps the WebSocket stream and shows a notice. A network drop shorter than 5 seconds does not end a working WebRTC session.
4. The PC encodes on the GPU when possible (NVIDIA `nvenc`, Intel `qsv`, AMD `amf`) and falls back to libx264 (`ultrafast`, `zerolatency`, no B-frames). An encoder that fails is skipped automatically.
5. Input uses two data channels with the same JSON messages as `/ws/input`: `input` (unordered, no retransmits) for pointer moves and `control` (reliable) for clicks, keys, scroll, hotkeys and text.

### Which networks work

| Network | Result |
|---|---|
| Same Wi-Fi or LAN | Direct UDP, lowest latency (about 50 ms or less) |
| Tailscale on phone and PC | Direct UDP over Tailscale addresses |
| Internet, reachable through STUN | Direct UDP after NAT traversal |
| Mobile data behind CGNAT or a strict firewall | Requires a TURN relay, otherwise the app falls back to WebSocket |

A free Cloudflare quick tunnel carries only TCP/HTTP. It can carry signaling but not WebRTC video, so over a quick tunnel alone the app uses the WebSocket stream. For the best result use Tailscale or the same LAN.

### TURN relay

Use TURN only if a direct connection fails. It needs a server with a public IP and open UDP port 3478 plus the relay port range. A minimal [coturn](https://github.com/coturn/coturn) `turnserver.conf`:

```
listening-port=3478
realm=remote-pc
lt-cred-mech
user=pcuser:use-a-long-random-password
fingerprint
no-cli
```

Then set in the PC's `.env` and restart:

```
REMOTE_PC_TURN_URL=turn:YOUR.SERVER.IP:3478
REMOTE_PC_TURN_USER=pcuser
REMOTE_PC_TURN_PASS=use-a-long-random-password
```

TURN credentials are sent only to clients that authenticated with the token and are never logged. Use a dedicated TURN user.

### Checking the active transport

- **Android:** the overlay label starts with `WebRTC` or `WebSocket`. After a fallback, a notice gives the reason.
- **PC:** the `start.ps1` window logs `WebRTC connection connected` and `WebRTC encoder: ...` for each WebRTC session. If the app fell back, only a `/ws/screen` connection appears.
- **Web dashboard:** the corner label shows the transport; `chrome://webrtc-internals` shows details.

### Signaling protocol

`/ws/rtc` uses the same first message as the other sockets, `{"token":"..."}`, followed by JSON:

| Direction | Message |
|---|---|
| PC to client | `{"type":"ready","ice_servers":[...]}` |
| Client to PC | `{"type":"offer","sdp":"..."}` (receive-only video plus data channels `input` and `control`) |
| PC to client | `{"type":"answer","sdp":"..."}` |
| Both | `{"type":"candidate","candidate":{"candidate":"...","sdpMid":"0","sdpMLineIndex":0}}` |
| PC to client | `{"type":"unavailable","reason":"..."}`: use `/ws/screen` instead |

On the `control` channel, `{"type":"config","max_width":1280,"fps":30,"bitrate":3000,"cursor":true}` changes the video live (bitrate in kbit/s). The full message reference is in the header of [`backend/app/webrtc.py`](backend/app/webrtc.py).

## Stream quality

The `.env` values are only the starting values of each `/ws/screen` connection. A client can change them at any time:

```json
{"type":"config","max_width":1920,"fps":15,"quality":70}
```

All fields are optional. `max_width` is `0` (native) or 320-3840, `fps` is 1-30 and `quality` is JPEG 25-90. Out-of-range numbers are clamped and unusable values are ignored. Settings apply per connection. The server answers with the values now in effect, `{"type":"screen","width":W,"height":H,"max_width":..,"fps":..,"quality":..}`, followed by a new frame. Frames are never upscaled.

**Motion quality.** While the picture keeps changing, the server sends frames at `REMOTE_PC_MOTION_QUALITY` percent of the JPEG quality and `REMOTE_PC_MOTION_WIDTH` percent of the width, so they arrive sooner. After the picture rests for about 0.2 s, one full-quality frame follows. Both default to 100 (off).

**Fast capture.** `setup.ps1` tries to install the optional `dxcam` package, which captures through DXGI several times faster than `mss`. If it is missing or does not work (remote desktop session, unusual monitor layout), the server logs one line and keeps using `mss`. Set `REMOTE_PC_CAPTURE=mss` to force `mss`.

## Configuration

Settings live in `.env`. Restart `start.ps1` after editing.

| Variable | Default | Description |
|---|---|---|
| `REMOTE_PC_TOKEN` | generated | Access password, 4 or more characters (12+ recommended). Required. |
| `REMOTE_PC_HOST` | `0.0.0.0` | Listen address (the code default without `.env` is `127.0.0.1`). |
| `REMOTE_PC_PORT` | `8888` | Listen port. |
| `REMOTE_PC_WEBRTC` | `1` | Enable WebRTC. `0` makes clients use the WebSocket stream. |
| `REMOTE_PC_RTC_FPS` | `30` | Maximum WebRTC frame rate (1-30). |
| `REMOTE_PC_RTC_BITRATE` | `4000` | Upper WebRTC bitrate limit in kbit/s (300-30000). The app's quality preset can lower it per session; bandwidth estimation can lower it further, but not below 1 Mbit/s (or this limit if lower). |
| `REMOTE_PC_RTC_ENCODER` | `auto` | `auto`, `nvenc`, `qsv`, `amf` or `x264`. libx264 is always the last resort. |
| `REMOTE_PC_STUN_URL` | Google STUN | STUN server(s), comma separated. |
| `REMOTE_PC_TURN_URL`, `_USER`, `_PASS` | empty | Optional TURN relay. |
| `REMOTE_PC_FPS` | `20` | Starting WebSocket frame rate (1-30). |
| `REMOTE_PC_JPEG_QUALITY` | `55` | Starting JPEG quality (25-85). Clients can raise it to 90. |
| `REMOTE_PC_MAX_WIDTH` | `1280` | Starting width limit; `0` is native. |
| `REMOTE_PC_LATENCY_FIRST` | `1` | On a slow link, shrink the picture at once and grow it back in steps (10 quality, 80 px) to keep delay low. `0` always uses the configured quality and width. |
| `REMOTE_PC_MOTION_QUALITY` | `100` | Percent of JPEG quality used while the picture moves (40-100; 100 is off). |
| `REMOTE_PC_MOTION_WIDTH` | `100` | Percent of width used while the picture moves (50-100; 100 is off). |
| `REMOTE_PC_CAPTURE` | `auto` | `auto` uses `dxcam` when available, `mss` forces the standard capture. |
| `REMOTE_PC_SHOW_CURSOR` | `1` | Draw a pointer on the stream. |
| `QUICK_TUNNEL` | unset | `1` starts a Cloudflare quick tunnel together with the server. |
| `GIST_TOKEN`, `GIST_ID` | unset | Publish the tunnel link to a secret Gist (see [above](#automatic-link-for-the-android-app)). `GIST_ID` is written automatically. |

## API

All `/api/v1` endpoints require `Authorization: Bearer <token>`. WebSockets expect `{"token":"..."}` as the first message.

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health check, no authentication. |
| `GET /api/v1/status`, `GET /api/v1/metrics` | CPU, memory, disk and network snapshot. |
| `POST /api/v1/control/lock` | Lock the workstation. |
| `POST /api/v1/control/sleep` | Put the PC to sleep. |
| `POST /api/v1/control/restart`, `.../shutdown` | Body `{"confirm":true}` required; executes after 5 seconds. |
| `GET /api/v1/wol/status`, `POST /api/v1/wol/wake` | Wake-on-LAN placeholders; report that no relay is configured. |
| `WS /ws/screen` | JPEG screen stream. |
| `WS /ws/rtc` | WebRTC signaling. |
| `WS /ws/input` | Mouse and keyboard input. |

## Updating

```powershell
cd $HOME\remote-pc-control
git pull
.\scripts\setup.ps1
.\scripts\start.ps1
```

`setup.ps1` installs new dependencies and rebuilds the dashboard only when needed. `start.ps1` stops an older server (and its leftover tunnel) that still holds port 8888.

If the server runs as the `RemotePCControl` scheduled task, restart it after pulling:

```powershell
git pull
Get-Process python | Stop-Process -Force    # stops every Python process on this PC
Start-ScheduledTask -TaskName RemotePCControl
```

### Reset `.env` to the latest template

`setup.ps1` only adds new settings. To start from a clean `.env.example`, back up first, because this overwrites your password, Gist and TURN values:

```powershell
Copy-Item .env .env.backup
Copy-Item .env.example .env -Force
.\scripts\set-password.ps1 YourNewPassword
```

Restore the values you still need from `.env.backup`, restart `start.ps1`, then delete the backup because it contains secrets: `Remove-Item .env.backup`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Page does not open over Tailscale | Tailscale must be on, on the same account, on the phone. An error mentioning a `192.168.x.x` address means the phone is not using Tailscale. |
| Tunnel link shows 502 / bad gateway | `start.ps1` is not running. Start it in its own window. |
| New tunnel link not reachable yet | Wait 1-2 minutes and retry. |
| Black screen or stream error | The PC is locked or a UAC prompt is open. Unlock the desktop. |
| `python` or `npm` not found | Install Python and Node.js, then open a new PowerShell window. |
| "Too many failed attempts" | Wait 5 minutes and use the correct token. |
| Always `WebSocket`, never `WebRTC` | No direct UDP path (quick tunnel only, or mobile CGNAT). Use Tailscale or the same Wi-Fi, or set up TURN. Also check `REMOTE_PC_WEBRTC=1` and that `setup.ps1` printed no `aiortc` warning. |
| WebRTC works on Wi-Fi but not on mobile data | Add a TURN relay. |
| `aiortc is not installed` | Run `.\scripts\setup.ps1 -Force`, then restart `start.ps1`. The WebSocket stream keeps working meanwhile. |
| Windows asks to allow `python.exe` through the firewall | Allow it on private networks only if you use WebRTC on your LAN. Tailscale does not need it. |
| `git clone` says the folder exists | Run `cd $HOME\remote-pc-control` and `git pull`. |

## Security and limitations

- Anyone with the token and a reachable URL can control the PC. Keep the token and tunnel link private, and revoke any credential that was exposed.
- Prefer Tailscale or Cloudflare Access ([docs/CLOUDFLARE.md](docs/CLOUDFLARE.md)) over a bare public link. Never expose port 8888 directly.
- Failed logins are rate limited: 8 failures per client within 5 minutes lock that client out, and 40 failures from all clients within 10 minutes pause every login.
- The agent runs in the signed-in desktop session. It cannot capture or control the Windows sign-in screen or UAC prompts and does not bypass Windows authentication. Use Windows Remote Desktop or a reviewed remote-access product to sign in.
- Wake-on-LAN over mobile data needs a separately authenticated, always-on LAN relay; the API reports it as not configured. `tools/wol_sender.py` sends a magic packet from a device on the target LAN.
- WebRTC needs a direct UDP path or a TURN relay; a free Cloudflare quick tunnel cannot carry its video.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q    # backend tests
cd frontend; npm install; npm run build                         # web dashboard
```

| Path | Contents |
|---|---|
| `backend/app/main.py` | FastAPI application and routes |
| `backend/app/screen.py` | Screen capture, JPEG stream and input handling |
| `backend/app/webrtc.py`, `webrtc_encoder.py` | WebRTC signaling, session, video track and H.264 encoder selection |
| `backend/app/security.py`, `config.py` | Token authentication, lockouts and settings |
| `frontend/` | Web dashboard (React, Vite); touch UI in `src/RemoteScreen.tsx` |
| `android/` | Android app; see [android/README.md](android/README.md) |
| `scripts/` | Windows setup, start, tunnel, autostart and password scripts |
| `installer/` | Inno Setup script for the Windows installer |
| `.github/workflows/` | CI, Android APK and Windows installer builds |

Release artifacts: pushes to `main` that touch `android/` publish a debug APK as a GitHub Release (`android-build-<N>`); the Windows installer workflow runs on `v*` tags or manually and builds `RemotePCControl-Setup.exe`. See [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md).
