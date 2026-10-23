# Remote PC Control

Control your own Windows desktop from an Android phone or browser. The agent provides live screen streaming, mouse and keyboard input, system metrics, and power controls.

> **Security:** Keep your access token private. Never forward port **8888** directly to the internet. Use Tailscale for private access or Cloudflare Tunnel with additional access protection.

## Documentation

- [Windows quick start](docs/QUICKSTART_WINDOWS.md) — install, configure, connect, and test.
- [Cloudflare Tunnel](docs/CLOUDFLARE.md) — temporary and named HTTPS links.
- [Windows setup notes](INSTALL_WINDOWS.md) — prerequisites and security limitations.
- [Android app and build](android/README.md) — install, use, and build the APK.

## Features

- **Live screen:** WebRTC H.264 over UDP when a direct route is available; JPEG over WebSocket as fallback.
- **Remote input:** Click, move, drag, scroll, keyboard shortcuts, and text entry.
- **Android trackpad:** Laptop-style pointer control.
- **System controls:** CPU, memory, disk, network, lock, sleep, restart, and shutdown.
- **Live quality settings:** Adjust resolution, frame rate, and image quality.
- **Authentication:** Token-protected API and WebSocket connections with temporary lockout after repeated failed attempts.

## Quick setup

Requirements: Windows, Python 3.11+ (Python 3.12 recommended), Node.js/npm, and Git. Install Tailscale on both devices if using a private tailnet.

```powershell
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
.\scripts\start.ps1
```

Setup creates a virtual environment, builds the web dashboard, and generates a private `.env` with a random `REMOTE_PC_TOKEN`. Save the token securely; never commit `.env`.

Check the agent on the PC at `http://localhost:8888/api/health`. Connect the phone using one of these methods:

| Connection | PC URL | Notes |
|---|---|---|
| Tailscale | `http://<PC-Tailscale-IP>:8888` | Recommended for private remote access. |
| Same Wi-Fi | `http://<PC-LAN-IP>:8888` | Keep both devices on the same trusted network. |
| Cloudflare Tunnel | `https://<tunnel-hostname>` | See the [Cloudflare guide](docs/CLOUDFLARE.md). |

Enter the URL and token in the Android app, tap **Connect**, then start a screen session. Do not expose port 8888 directly.

## Android APK

Download the latest APK from the repository's GitHub Actions artifact or Releases. For local builds, see [android/README.md](android/README.md). The debug APK is for personal use, not a Play Store release.

## Streaming

WebRTC offers lower latency when the phone and PC can establish a direct UDP connection. Tailscale or the same LAN usually works best. A Cloudflare quick tunnel carries signaling but not WebRTC video; the app falls back to JPEG/WebSocket. A TURN relay may be needed behind strict firewalls or mobile carrier NAT.

The WebSocket stream's starting values come from `.env`; clients can change these per connection:

```json
{"type":"config","max_width":1920,"fps":15,"quality":70}
```

- `max_width`: `0` for native resolution, otherwise 320–3840.
- `fps`: 1–30.
- `quality`: JPEG quality 25–90.

### Main settings

| Variable | Default | Purpose |
|---|---:|---|
| `REMOTE_PC_TOKEN` | generated | Required access token. Use a long, unique value. |
| `REMOTE_PC_HOST` | `0.0.0.0` in setup | Server listen address. |
| `REMOTE_PC_PORT` | `8888` | Server port. |
| `REMOTE_PC_MAX_WIDTH` | `1280` | Initial stream width; `0` means native. |
| `REMOTE_PC_FPS` | `20` | Initial JPEG stream frame rate. |
| `REMOTE_PC_JPEG_QUALITY` | `55` | Initial JPEG quality. |
| `REMOTE_PC_WEBRTC` | `1` | Enable WebRTC with WebSocket fallback. |
| `REMOTE_PC_RTC_FPS` | `30` | WebRTC frame-rate limit. |
| `REMOTE_PC_RTC_BITRATE` | `4000` | WebRTC bitrate limit in kbit/s. |
| `REMOTE_PC_RTC_ENCODER` | `auto` | H.264 encoder selection. |
| `REMOTE_PC_STUN_URL` | Google STUN | STUN server list. |
| `REMOTE_PC_TURN_URL` / `_USER` / `_PASS` | empty | Optional TURN relay credentials. |

Restart `scripts/start.ps1` after changing `.env`. See `.env.example` for all supported settings.

## Troubleshooting

| Issue | Check |
|---|---|
| Cannot connect | Confirm the agent is running, URL/token are correct, and firewall rules allow the chosen private network. |
| Tunnel returns 502 | Start the agent with `scripts/start.ps1`; verify the tunnel forwards to `http://localhost:8888`. |
| Black screen | Unlock the Windows desktop and close any UAC prompt. |
| WebRTC falls back | Try the same Wi-Fi or Tailscale; configure TURN if direct UDP is blocked. |
| Too many failed attempts | Wait for the temporary lockout to expire, then use the correct token. |

## Security and limitations

- Anyone with the token and network access can control the desktop. Protect the token and tunnel URL.
- Run the agent as the signed-in desktop user; screen capture and input do not work on the secure sign-in desktop or UAC prompts.
- The agent does not bypass Windows authentication.
- The Android app may use HTTP/WebSocket on private networks. Prefer a trusted private network; use appropriate access protection for public hostnames.
- Wake-on-LAN is not configured by default and mobile-data wake requires a separately authenticated LAN relay.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
cd frontend
npm install
npm run build
```

Backend code is in `backend/app/`, the web dashboard in `frontend/`, and the Android app in `android/`.
