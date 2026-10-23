# Remote PC Control

See and control your own Windows PC from your phone: live screen, touch-as-mouse, keyboard, system monitor and power controls. Works from anywhere through a private Tailscale network **or** a Cloudflare tunnel, from a phone browser or the Android app.

> Use it only on a PC you own. Never port-forward port 8888 to the internet.

New here? Follow the step-by-step **[Windows quick start](docs/QUICKSTART_WINDOWS.md)**.

## Features
- **Live screen, low latency**: WebRTC (H.264 video over UDP, input over data channels) first, with the original JPEG-over-WebSocket stream as automatic fallback. See *WebRTC mode*.
- **Live screen (fallback)** streamed to the phone (JPEG over WebSocket, downscaled, idle-frame skipping, on-screen pointer). Resolution, frame rate and JPEG quality can be changed live from the client (see *Stream quality*).
- **Touch control**: tap = click, long-press = right click, drag, scroll, double-click, fullscreen/landscape.
- **Trackpad (Android app)**: laptop-style pad under the screen. One finger = move, tap = click, double-tap = double click, two-finger tap = right click, two-finger slide = scroll, tap-then-slide = drag. Portrait: screen on top, pad below. Landscape: full-window screen with a hideable pad.
- **Keyboard**: text box plus quick keys (Esc, Tab, arrows, Win, Alt+Tab, Ctrl+C/V/A/Z).
- **Monitor and power**: CPU/RAM/disk/network, lock, sleep, restart, shutdown (with confirmation).
- **Security**: token-protected API and WebSockets, lockout after 8 wrong tokens (5 minutes).
- **Clients**: mobile web dashboard and a native Android app (`android/`): Material 3 dark UI with a Connect screen, a Dashboard (CPU/RAM/disk gauges, network, lock/sleep/restart/shutdown) and the screen session.

## Quick start (Windows PC + phone)

### 1. Prerequisites on the PC
Install **Python 3.12 (x64)**, **Node.js 22** and **Git**. (Tailscale only if you choose that connection method.)

### 2. Get the code and set it up
Open PowerShell (normal user, in your logged-in desktop session):
```powershell
cd $HOME
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```
`setup.ps1` creates a virtual environment, installs dependencies, builds the web dashboard and generates a private `.env` containing your **access token**. A new `.env` is a copy of the full `.env.example` with a fresh password; on later runs `setup.ps1` appends any setting that `.env.example` gained (never changing your existing values or password). It also asks for an optional `GIST_TOKEN` (press Enter to skip; or pass `-GistToken ghp_...` and `-GistId <id>`), which turns on the automatic tunnel link for the Android app (see A2 below). Save the token somewhere safe; never commit `.env`. To show it again later:
```powershell
Get-Content .env | Select-String REMOTE_PC_TOKEN
```
(Copy only the text after `REMOTE_PC_TOKEN=`.)

### 3. Start the server
```powershell
.\scripts\start.ps1
```
Leave this window open. The server listens on port 8888.

### 4. Connect the phone (pick one method)

**A. Cloudflare quick tunnel (works anywhere, no account needed)**

In a **second** PowerShell window:
```powershell
cd $HOME\remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-tunnel.ps1
```
The first run installs `cloudflared`; if it asks, close the window, open a new one and run the same command again. It prints a link like `https://xxxx-xxxx.trycloudflare.com`. Open it on the phone (browser, or use it as the *PC URL* in the Android app) and enter the token.
- Test first: `https://<your-link>/api/health` should show `{"ok":true,...}`.
- The link **changes every time** the tunnel restarts. Keep both windows open; press `Ctrl+C` in the tunnel window when done. Do not share the link.
- For a **permanent link** that never changes (and starts with Windows) use a named tunnel: step-by-step in **[docs/CLOUDFLARE.md](docs/CLOUDFLARE.md)**. It needs a domain on your Cloudflare account; the guide also covers Cloudflare Access login protection.

**A2. One command: quick tunnel + automatic link for the Android app**

Add to `.env`:
```
QUICK_TUNNEL=1
GIST_TOKEN=your-gist-token
```
`GIST_TOKEN` is a GitHub *classic* token with **only the `gist` scope** (<https://github.com/settings/tokens>); do not reuse a repo token. Then just run `.\scripts\start.ps1`. It installs `cloudflared` if needed, starts the tunnel with the server, and writes the new `https://....trycloudflare.com` link to a **secret Gist**. The first run creates the Gist and prints `gist:<id>`.

In the Android app enter `gist:<id>` as *PC URL* once. Every time you tap Connect, the app reads the PC's current link from the Gist, so you never type a link again. (Browser: open the link printed by `start.ps1`.) The tunnel link itself still changes on every run; only the Gist id is fixed. Anyone who knows the Gist id can read the link, but still needs the API token.

**B. Tailscale (private VPN, stable IP)**

Install Tailscale on the PC and phone and sign in to the **same account** on both, with the VPN switched on on the phone. Get the PC's address with `tailscale ip -4`, then open `http://<that-ip>:8888`. The firewall rule created by `setup.ps1` only accepts connections from Tailscale addresses (`100.64.0.0/10`). Run `setup.ps1` from an administrator PowerShell if the rule could not be created.

**C. Same Wi-Fi only**

From an administrator PowerShell:
```powershell
New-NetFirewallRule -DisplayName "RemotePCControl LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 -RemoteAddress LocalSubnet -Profile Any
ipconfig
```
Open `http://<PC-IPv4-address>:8888` on a phone on the same Wi-Fi. Give the PC a fixed address (DHCP reservation in your router) so the URL does not change.

### 5. Use it
Enter the token, tap **Connect**, then **Start screen**. Pick a mode on the toolbar:

| Mode | What your finger does |
|---|---|
| Click | tap = left click, long-press = right click (web: two fingers = scroll) |
| Move | drag moves the pointer without clicking |
| Drag | drag holds the left button (select text, move windows) |
| Scroll | drag up/down scrolls the page |

Also: **Double-click** button, **Fullscreen**, **Keys** (quick keys) and a text box.

## Android app
Open **GitHub > Actions > Android APK** (it runs on every push to `main`, or use *Run workflow*) and download the APK from the run's artifact or from **Releases**. Install it (allow "install unknown apps" if asked). In the app enter the *PC URL* (`https://...trycloudflare.com`, `http://100.x.x.x:8888` or your LAN address) and the token. This is a debug build for personal use, not a Play Store release. Build instructions: [android/README.md](android/README.md).

The app has three screens:
- **Connect**: PC URL and token. The URL and the password (encrypted with the Android Keystore) are remembered after the first login, so the login screen only appears once; Log out forgets them.
- **Dashboard**: CPU, memory and disk gauges, network speed (refreshed every 5 s), and power buttons. Sleep, Restart and Shutdown ask for confirmation; Lock does not. It also holds the **Quality** setting and the *Start screen session* button.
- **Session**: live screen, touch modes, trackpad, keys. A small overlay in the corner of the picture shows the received resolution and the measured/maximum frames per second (for example `1280×720 · 27/30 fps`). **Quality** in the toolbar changes the stream while it is running, and the choice is remembered.

| Quality | Width | Max FPS | WebRTC bitrate | JPEG quality (fallback) |
|---|---|---|---|---|
| Low | 960 px | 20 | 1.5 Mbit/s | 45 |
| Medium (default) | 1280 px | 30 | 3 Mbit/s | 65 |
| High | 1920 px | 30 | 6 Mbit/s | 78 |
| Native | PC resolution | 20 | 10 Mbit/s | 85 |

Frames are drawn with high-quality (bicubic) filtering so text stays sharp when the picture is scaled to the phone screen. Native on a 4K PC needs a fast connection and decodes large images; use High if it stutters.

## Stream quality (protocol)
The server's `.env` values below are only the *starting* values of every `/ws/screen` connection. A client can change them at any time while streaming:
```json
{"type":"config","max_width":1920,"fps":15,"quality":70}
```
All fields are optional. `max_width` is `0` (native) or 320-3840, `fps` is 1-30, `quality` is JPEG 25-90; out-of-range numbers are clamped and unusable values are ignored. Settings are per connection. The server answers with a fresh `{"type":"screen","width":W,"height":H,"max_width":..,"fps":..,"quality":..}` (the values now in effect) followed by a new frame. Frames are never upscaled, so `max_width` above the PC's resolution just sends native size. Clients that never send `config` get exactly the `.env` behaviour.

**Motion quality (less lag).** While the picture keeps changing (scrolling, window animations, dragging) the server sends frames at `REMOTE_PC_MOTION_QUALITY` percent (default 100 = off) of the JPEG quality, so they are smaller and reach the phone sooner. As soon as the picture rests for about 0.2 s it sends one full-quality frame, so text is sharp again. Frames are also scaled to `REMOTE_PC_MOTION_WIDTH` percent (default 100 = off) of their width while the picture moves. Set `REMOTE_PC_MOTION_QUALITY=100` and `REMOTE_PC_MOTION_WIDTH=100` in `.env` to turn this off. No client change is needed.

**Fast capture.** `setup.ps1` also tries to install the optional `dxcam` package, which captures the screen through DXGI several times faster than the default `mss`. If it is missing or does not work on your PC (remote desktop session, other monitor layout, no frames) the server prints one line and keeps using `mss` by itself. `REMOTE_PC_CAPTURE=mss` in `.env` forces the old capture.

## WebRTC mode (low latency)
The default JPEG stream sends one picture per frame over a TCP WebSocket. One slow packet delays everything behind it, and a Cloudflare tunnel adds a relay hop on top. WebRTC sends H.264 video over UDP (old frames are dropped instead of queued) and carries mouse/keyboard input on data channels.

**How it works.** When you tap *Start screen*, the Android app first opens `/ws/rtc` on the same PC address and with the same password. That socket is only used to exchange the connection offer (signaling). The video and the input then travel directly between phone and PC.
- If the connection is not up within about 5 seconds, or the PC says WebRTC is unavailable, the app switches to the WebSocket JPEG stream by itself and shows a small notice. Nothing else changes.
- The PC encodes with the GPU when it can (NVIDIA `nvenc`, Intel `qsv`, AMD `amf`) and otherwise with libx264 (`ultrafast`, `zerolatency`, no B-frames). A hardware encoder that does not work is skipped automatically.
- Input uses two data channels with the same JSON messages as `/ws/input`: `input` (unordered, no retransmits) for pointer moves, and `control` (reliable) for clicks, keys, scroll, hotkeys and typed text.

**Which networks give low latency.**
| Network | Result |
|---|---|
| Same Wi-Fi / LAN | direct UDP, lowest latency (about 50 ms or less is realistic) |
| Tailscale (phone and PC both on it) | direct UDP through the Tailscale addresses |
| Internet, both sides can reach each other with STUN | direct UDP after NAT punch-through |
| Mobile data behind CGNAT / strict firewall | needs a **TURN** relay, otherwise the app falls back to the WebSocket stream |

A free **Cloudflare quick tunnel only carries TCP/HTTP**. It can carry the signaling, but it cannot carry the WebRTC video. Over a quick tunnel alone WebRTC usually will not connect and the app falls back to the WebSocket stream, exactly as before. For the best result use Tailscale or the same LAN.

**Settings (`.env`, restart `start.ps1` after changing).**
| Variable | Default | Meaning |
|---|---|---|
| `REMOTE_PC_WEBRTC` | `1` | `0` turns WebRTC off; clients then always use the WebSocket stream. |
| `REMOTE_PC_RTC_FPS` | `30` | Maximum video frames per second (1-30). |
| `REMOTE_PC_RTC_BITRATE` | `4000` | Upper video bitrate limit in kbit/s (300-30000). The app's quality preset can lower it for its session. The receiver's own bandwidth estimate can lower the live bitrate, but not below 1 Mbit/s (or this limit if it is lower). |
| `REMOTE_PC_RTC_ENCODER` | `auto` | `auto`, or force `nvenc`, `qsv`, `amf` or `x264`. libx264 is always the last resort. |
| `REMOTE_PC_STUN_URL` | `stun:stun.l.google.com:19302` | STUN server(s), comma separated. |
| `REMOTE_PC_TURN_URL` / `_USER` / `_PASS` | empty | Optional TURN relay, see below. |

**TURN setup (only if the direct connection fails).** TURN relays the video through a server you control, which adds a little delay but works behind CGNAT. You need a small server with a public IP and open UDP port 3478 (and the relay port range). With [coturn](https://github.com/coturn/coturn) a minimal `turnserver.conf` is:
```
listening-port=3478
realm=remote-pc
lt-cred-mech
user=pcuser:use-a-long-random-password
fingerprint
no-cli
```
Then put this in the PC's `.env` and restart:
```
REMOTE_PC_TURN_URL=turn:YOUR.SERVER.IP:3478
REMOTE_PC_TURN_USER=pcuser
REMOTE_PC_TURN_PASS=use-a-long-random-password
```
The PC sends the TURN details only to clients that signed in with the token, and uses them for itself. They are never printed to the log. Use a dedicated TURN user, not a password you use elsewhere.

**Check which transport is active.**
- Android: the small label in the corner of the picture starts with the transport, for example `WebRTC · 1280×720 · 30 fps · 38 ms`, or `WebSocket · 1280×720 · 20/30 fps`. After a fallback a notice says why.
- PC: `start.ps1`'s window logs `WebRTC connection connected` (and `WebRTC encoder: h264_nvenc ...` or `libx264`) for every WebRTC session. If the app fell back, there is a `/ws/screen` connection instead and no such lines.
- Web dashboard: the corner label says `WebRTC` or `WebSocket`; `chrome://webrtc-internals` shows details.

**Protocol (for other clients).** `/ws/rtc` uses the same first message as the other sockets, `{"token":"..."}`, then JSON: the PC sends `{"type":"ready","ice_servers":[...]}`; the client sends `{"type":"offer","sdp":"..."}` (receive-only video plus data channels `input` and `control`) and gets `{"type":"answer","sdp":"..."}`; trickle candidates go both ways as `{"type":"candidate","candidate":{"candidate":"...","sdpMid":"0","sdpMLineIndex":0}}`. `{"type":"unavailable","reason":"..."}` means: use `/ws/screen`. Over the `control` channel `{"type":"config","max_width":1280,"fps":30,"bitrate":3000,"cursor":true}` changes the video live (bitrate in kbit/s). Details are in the header of `backend/app/webrtc.py`.

## Updating
```powershell
cd $HOME\remote-pc-control
git checkout main
git pull
.\scripts\setup.ps1     # rebuilds the dashboard / installs new dependencies (WebRTC needs aiortc and av; setup installs them)
.\scripts\start.ps1
```

## Configuration (`.env`)
| Variable | Default | Meaning |
|---|---|---|
| `REMOTE_PC_TOKEN` | generated | Access password (4+ characters, 12+ recommended; setup generates a long random one). Required. |
| `REMOTE_PC_LATENCY_FIRST` | `1` | `1`: on a slow link the picture is made smaller at once (and grows back slowly, in steps of 10 quality / 80 px) so the delay stays low. `0`: always exactly the quality and width chosen in the app. |
| `REMOTE_PC_HOST` / `REMOTE_PC_PORT` | `0.0.0.0` / `8888` | Listen address. |
| `REMOTE_PC_FPS` | `20` | Starting frames per second (1-30); clients can change it live. If you set it in an existing `.env`, change it there too: the file wins over the default. |
| `REMOTE_PC_JPEG_QUALITY` | `55` | Starting JPEG quality (25-85); clients can raise it to 90 live. |
| `REMOTE_PC_MAX_WIDTH` | `1280` | Starting width limit; wider frames are downscaled (`0` = native). Clients can change it live. |
| `REMOTE_PC_SHOW_CURSOR` | `1` | Draw a pointer on the stream. |
| `REMOTE_PC_WEBRTC` | `1` | WebRTC live screen on/off (WebSocket stream is the fallback). See *WebRTC mode*. |
| `REMOTE_PC_RTC_FPS` / `REMOTE_PC_RTC_BITRATE` | `30` / `4000` | WebRTC maximum frames per second and bitrate limit (kbit/s). |
| `REMOTE_PC_RTC_ENCODER` | `auto` | `auto`, `nvenc`, `qsv`, `amf` or `x264`. |
| `REMOTE_PC_STUN_URL` | Google STUN | STUN server(s), comma separated. |
| `REMOTE_PC_TURN_URL` / `_USER` / `_PASS` | empty | Optional TURN relay for networks without a direct path. |

Restart `start.ps1` after editing `.env`.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Phone page does not open (Tailscale) | Phone's Tailscale must be on and on the same account. An error mentioning your `192.168.x.x` address means the phone is not using Tailscale. |
| Tunnel link shows 502 / bad gateway | `start.ps1` is not running. Start it in its own window. |
| New tunnel link not reachable yet | Wait 1-2 minutes and retry. |
| Black screen / stream error | The PC is locked or a UAC prompt is open. Unlock the desktop. |
| `python` or `npm` not found | Install Python 3.12 and Node.js 22, then open a new PowerShell. |
| Locked out ("Too many failed attempts") | Wait 5 minutes and use the correct token. |
| App always says "WebSocket" and never "WebRTC" | The phone and PC have no direct UDP path (Cloudflare quick tunnel only, mobile CGNAT). Use Tailscale or the same Wi-Fi, or set up TURN. Also check `.env` has `REMOTE_PC_WEBRTC=1` and that `setup.ps1` printed no warning about `aiortc`. |
| WebRTC works on Wi-Fi but not over mobile data | Add a TURN relay (see *WebRTC mode*). |
| Windows asks to allow python.exe through the firewall | Allow it on the private network only if you use WebRTC on your LAN; Tailscale does not need it. |
| `aiortc is not installed` in the app notice | Run `.\scripts\setup.ps1 -Force`, then restart `start.ps1`. The WebSocket stream keeps working meanwhile. |
| `git clone` says folder exists | Use the existing folder: `cd $HOME\remote-pc-control`, then `git pull`. |

## Security and limitations
- Anyone with the token (and a reachable URL) can control the PC. Keep the token and tunnel link private; revoke any credential you have pasted into chats or tickets.
- Prefer Tailscale or Cloudflare Access (see [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md)) over a bare public link. Never expose port 8888 directly.
- The agent runs in the logged-in desktop session. It cannot capture or control the Windows sign-in screen or UAC prompts and does not bypass Windows authentication. Use Windows Remote Desktop or a reviewed remote-access product to sign in.
- Wake-on-LAN over mobile data needs a separately authenticated always-on LAN relay (API reports it as not configured).
- JPEG streaming is simple and bandwidth-hungry; tune FPS, quality and width for your connection. WebRTC needs a direct UDP path or a TURN relay (see *WebRTC mode*); a free Cloudflare quick tunnel cannot carry its video.

## Development
```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q   # backend tests
cd frontend; npm install; npm run build                        # web dashboard
```
Protocol and input handling live in `backend/app/screen.py`; the WebRTC transport is `backend/app/webrtc.py` (signaling, session, video track, data channels) and `backend/app/webrtc_encoder.py` (H.264 encoder selection); the touch UI is `frontend/src/RemoteScreen.tsx` (web). The Android app lives in `android/app/src/main/java/com/mainnetwallet/remotepccontrol/` (`MainActivity.kt` entry and navigation, `RemoteController.kt` networking/state, `ConnectScreen.kt`, `DashboardScreen.kt`, `SessionScreen.kt`, `Trackpad.kt`, `Theme.kt`, `Components.kt`).

---

## বাংলা সারসংক্ষেপ
1. PC-তে Python 3.12, Node.js 22, Git ইনস্টল করুন।
2. PowerShell-এ: `git clone https://github.com/mainnetwallet/remote-pc-control.git`, তারপর `cd remote-pc-control`, `Set-ExecutionPolicy -Scope Process Bypass`, `.\scripts\setup.ps1`। শেষে যে token দেখাবে সেটা সেভ করুন।
3. `.\scripts\start.ps1` চালান (window খোলা রাখুন)।
4. নতুন PowerShell window-তে `.\scripts\start-tunnel.ps1` চালান। যে `https://...trycloudflare.com` লিংক আসবে সেটা ফোনে খুলুন (লিংক প্রতিবার বদলায়)।
5. Token দিয়ে Connect করে Start screen চাপুন। Click/Move/Drag/Scroll mode দিয়ে আঙুলে mouse চালান।
6. কাজ শেষে tunnel window-তে `Ctrl+C` চাপুন। লিংক ও token কাউকে দেবেন না।

## বাংলা: WebRTC (কম delay)
- নতুন WebRTC মোডে ভিডিও UDP-তে সরাসরি ফোন ↔ PC যায় (H.264), তাই delay অনেক কম। Mouse/keyboard-এর input-ও একই সংযোগের data channel দিয়ে যায়।
- অ্যাপে *Start screen* চাপলে আগে WebRTC চেষ্টা হয়। প্রায় ৫ সেকেন্ডে না লাগলে অ্যাপ নিজে থেকেই পুরোনো WebSocket (JPEG) স্ট্রিমে চলে যায় এবং ছোট একটা নোটিশ দেখায়।
- সবচেয়ে ভালো ফল: একই Wi-Fi বা Tailscale। Cloudflare quick tunnel শুধু TCP বহন করে, তাই শুধু tunnel দিয়ে WebRTC সাধারণত লাগে না। মোবাইল ডেটায় না লাগলে TURN সার্ভার দিন (`.env`-এ `REMOTE_PC_TURN_URL`, `REMOTE_PC_TURN_USER`, `REMOTE_PC_TURN_PASS`)।
- বন্ধ করতে `.env`-এ `REMOTE_PC_WEBRTC=0`। কোন মোড চলছে বোঝার উপায়: ছবির কোণার লেখা `WebRTC · …` বা `WebSocket · …`।
- আপডেট: `git pull`, তারপর `.\scripts\setup.ps1`, তারপর `.\scripts\start.ps1`; নতুন APK ইনস্টল করুন।
