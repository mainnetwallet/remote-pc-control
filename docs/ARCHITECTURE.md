# Repository Architecture Guide

This guide describes the current source tree, runtime paths, APIs, security boundaries, tests and build workflows.

## Project layout

```text
.
├── backend/app/             FastAPI service and Windows desktop control
│   ├── main.py              HTTP routes, WebSocket routes, app lifecycle
│   ├── config.py            Environment configuration and validation
│   ├── security.py          Bearer-token auth and failed-login lockout
│   ├── monitor.py           CPU, memory, disk, network and uptime
│   ├── control.py           Lock, sleep, restart and shutdown
│   ├── pinlock.py           Persistent PIN-lock state (lock_state.json)
│   ├── screen.py            Capture, JPEG stream, pointer and input
│   ├── webrtc.py            WebRTC signaling, video track and data channels
│   └── webrtc_encoder.py    Low-latency H.264 encoder selection
├── backend/tests/           API, screen, input, streaming and WebRTC tests
├── frontend/                React + TypeScript + Vite web dashboard
├── android/                 Kotlin + Jetpack Compose Android client
├── lock_overlay.py          Full-screen PIN lock (single instance, own log, focus + hook handling)
├── scripts/                 Windows setup, startup, tunnel and autostart
├── installer/               Inno Setup installer definition
├── tools/wol_sender.py      Standalone Wake-on-LAN magic-packet utility
├── tests/                   Wake-on-LAN packet tests
├── docs/                    Setup and connection guides
├── .github/workflows/       CI, Android APK and Windows installer workflows
├── .env.example              Supported configuration settings
└── pyproject.toml            Python dependencies and pytest configuration
```

## Runtime flow

1. `scripts/setup.ps1` creates `.venv`, installs the Python package, builds the frontend, copies the dashboard into `backend/app/static/`, and creates `.env` with a random token.
2. `scripts/start.ps1` launches Uvicorn on port **8888**. If `QUICK_TUNNEL=1`, it can launch a Cloudflare quick tunnel and optionally publish its URL to a secret GitHub Gist.
3. The web dashboard or Android app authenticates against the FastAPI service.
4. The Android app starts JPEG/WebSocket streaming immediately while attempting WebRTC. When WebRTC video is decoded, it switches to WebRTC and closes the JPEG stream.
5. Mouse and keyboard events travel through the input WebSocket or WebRTC data channels.

Run the agent as the Windows user signed in to the desktop you want to control. It cannot control the secure sign-in desktop or UAC prompts.

## HTTP API

All endpoints except the health check require a bearer token.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Public liveness check |
| GET | `/api/v1/status` | System status and usage metrics |
| GET | `/api/v1/metrics` | System metrics snapshot |
| POST | `/api/v1/control/lock` | Lock the workstation |
| POST | `/api/v1/control/sleep` | Request sleep |
| POST | `/api/v1/control/restart` | Restart; requires `{"confirm":true}` |
| POST | `/api/v1/control/shutdown` | Shutdown; requires `{"confirm":true}` |
| GET | `/api/v1/wol/status` | Reports Wake-on-LAN as unconfigured |
| POST | `/api/v1/wol/wake` | Returns HTTP 501 until an authenticated LAN relay is configured |
| GET | `/api/v1/lock/status` | `{"locked": bool, "pin_set": bool}` |
| POST | `/api/v1/lock/pin` | Set/change the PC-side unlock PIN; body `{"pin":"1234"}` |
| POST | `/api/v1/lock/lock` | Engage the persistent PIN lock (requires a PIN already set) |
| POST | `/api/v1/lock/unlock` | Release the PIN lock (token already authenticates the app) |

The dashboard is served from `backend/app/static/` after the frontend is built.

## Live screen and input transports

| Endpoint | Transport | Role |
|---|---|---|
| `/ws/rtc` | WebSocket signaling | Exchanges WebRTC offers/answers, ICE candidates and connection state |
| WebRTC media | H.264 over UDP when a direct route is available | Low-latency video; old frames can be dropped instead of queued |
| WebRTC data channels | `input` and `control` | Pointer events, clicks, keyboard, text, cursor updates and live configuration |
| `/ws/screen` | JPEG frames over WebSocket | Fallback with acknowledgements, flow control, adaptive quality and resolution |
| `/ws/input` | JSON over WebSocket | Mouse, trackpad, keyboard, text input and cursor updates |

WebRTC can use NVIDIA NVENC, Intel QSV or AMD AMF hardware encoding; otherwise it falls back to libx264. The WebSocket stream remains available when WebRTC is disabled or cannot deliver video. A Cloudflare quick tunnel carries HTTP/WebSocket signaling but not direct UDP media; use LAN/Tailscale or configure TURN when needed.

## Authentication and security

- HTTP requests use `Authorization: Bearer <REMOTE_PC_TOKEN>`; WebSocket clients send the token before using the socket.
- `backend/app/security.py` compares tokens in constant time.
- A client is locked out after 8 failed attempts in 5 minutes. A global guard also blocks authentication after 40 failed attempts in 10 minutes, even if requests rotate client IPs.
- Setup generates a long random token. The application accepts a minimum of 4 characters for compatibility, but a unique token of at least 12 characters is strongly recommended.
- `.env` is ignored by Git. Never commit it or share the token/tunnel URL.
- Never port-forward TCP 8888 directly to the public internet. Prefer Tailscale/private Wi-Fi or Cloudflare Access for a named hostname.
- Android encrypts the saved token using an Android Keystore key. **Log out** clears the saved token.

## Configuration

The full settings list is in `.env.example`.

| Group | Variables | Purpose |
|---|---|---|
| Server | `REMOTE_PC_TOKEN`, `REMOTE_PC_HOST`, `REMOTE_PC_PORT` | Authentication and listen settings |
| JPEG/WebSocket stream | `REMOTE_PC_FPS`, `REMOTE_PC_JPEG_QUALITY`, `REMOTE_PC_MAX_WIDTH` | Initial frame rate, JPEG quality and width |
| Adaptive streaming | `REMOTE_PC_LATENCY_FIRST`, `REMOTE_PC_MOTION_QUALITY`, `REMOTE_PC_MOTION_WIDTH` | Reduce queued data and motion-frame size on slow links |
| Capture | `REMOTE_PC_CAPTURE`, `REMOTE_PC_SHOW_CURSOR` | DXGI/mss capture selection and pointer overlay |
| WebRTC | `REMOTE_PC_WEBRTC`, `REMOTE_PC_RTC_FPS`, `REMOTE_PC_RTC_BITRATE`, `REMOTE_PC_RTC_ENCODER` | Video enablement, limits and encoder |
| NAT traversal | `REMOTE_PC_STUN_URL`, `REMOTE_PC_TURN_URL`, `REMOTE_PC_TURN_USER`, `REMOTE_PC_TURN_PASS` | ICE/STUN/TURN connectivity |

Restart `scripts/start.ps1` after changing `.env`. Stream quality can also be adjusted by the client while connected.

## Windows scripts

| File | Purpose |
|---|---|
| `scripts/setup.ps1` | Install dependencies, build dashboard, create/update `.env`, attempt the Tailscale-only firewall rule |
| `scripts/start.ps1` | Start Uvicorn; optionally start a quick tunnel and publish its link to a Gist |
| `scripts/start-tunnel.ps1` | Run a temporary Cloudflare quick tunnel |
| `scripts/set-password.ps1` | Change `REMOTE_PC_TOKEN` in `.env` |
| `scripts/install-autostart.ps1` | Install/remove the hidden scheduled task for user sign-in |
| `scripts/autostart-hidden.vbs`, `scripts/autostart-runner.ps1` | Launch the runner hidden and wait/retry for network |
| `scripts/configure-installed.ps1` | Create initial settings for the packaged executable |
| `scripts/remove-firewall.ps1` | Remove the setup-created Tailscale firewall rule |

## Frontend and Android client

- **Web:** `frontend/src/App.tsx` provides login, status/metrics, power controls and WebSocket setup. `RemoteScreen.tsx` implements touch gestures, keyboard shortcuts and screen interaction. `style.css` contains the responsive dark dashboard.
- **Android:** `MainActivity.kt` handles navigation; `ConnectScreen.kt`, `DashboardScreen.kt`, and `SessionScreen.kt` are the main screens. `RemoteController.kt` manages API/session state. `Rtc.kt` implements WebRTC; `SecureStore.kt` encrypts credentials; `Trackpad.kt` handles trackpad gestures.
- Android settings: min SDK 26, target/compile SDK 35, JDK 17, Kotlin and Jetpack Compose. CI produces a debug APK for personal use, not a Play Store release.

## Tests and CI

Run tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
```

Build the web dashboard:

```powershell
cd frontend
npm install
npm run build
```

Tests cover authentication and lockout, API behavior, screen configuration and frame flow control, pointer/keyboard input, WebRTC signaling, ICE configuration, data channels, video tracks, and encoder fallback.

| Workflow | Trigger / output |
|---|---|
| `.github/workflows/ci.yml` | Runs Python tests and builds the frontend on push, pull request or manual dispatch |
| `.github/workflows/android-build.yml` | Builds a debug APK for Android-related pushes/PRs or manual runs; uploads an artifact and publishes a release outside pull requests |
| `.github/workflows/windows-build.yml` | Manual run or `v*` tag; packages the Windows executable and Inno Setup installer |

## Known limitations

- Wake-on-LAN API support is unconfigured. `tools/wol_sender.py` can send a magic packet from a device already on the target LAN, but the PC agent cannot wake itself. Mobile-data wake needs a separately authenticated, always-on LAN relay.
- The agent cannot control Windows sign-in, UAC secure desktop or other protected sessions.
- Cloudflare Access email/OTP login works in a browser; the Android app cannot complete that browser flow.
- WebRTC requires a direct UDP path or TURN. A quick tunnel alone falls back to WebSocket/JPEG.
- The CI Android APK is a debug build intended for personal use.
