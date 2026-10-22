# Remote PC Control

See and control your own Windows PC from your phone: live screen, touch-as-mouse, keyboard, system monitor and power controls. Works from anywhere through a private Tailscale network **or** a Cloudflare tunnel, from a phone browser or the Android app.

> Use it only on a PC you own. Never port-forward port 8788 to the internet.

## Features
- **Live screen** streamed to the phone (JPEG over WebSocket, downscaled, idle-frame skipping, on-screen pointer). Resolution, frame rate and JPEG quality can be changed live from the client (see *Stream quality*).
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
`setup.ps1` creates a virtual environment, installs dependencies, builds the web dashboard and generates a private `.env` containing your **access token**. Save the token somewhere safe; never commit `.env`. To show it again later:
```powershell
Get-Content .env | Select-String REMOTE_PC_TOKEN
```
(Copy only the text after `REMOTE_PC_TOKEN=`.)

### 3. Start the server
```powershell
.\scripts\start.ps1
```
Leave this window open. The server listens on port 8788.

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

**B. Tailscale (private VPN, stable IP)**

Install Tailscale on the PC and phone and sign in to the **same account** on both, with the VPN switched on on the phone. Get the PC's address with `tailscale ip -4`, then open `http://<that-ip>:8788`. The firewall rule created by `setup.ps1` only accepts connections from Tailscale addresses (`100.64.0.0/10`). Run `setup.ps1` from an administrator PowerShell if the rule could not be created.

**C. Same Wi-Fi only**

From an administrator PowerShell:
```powershell
New-NetFirewallRule -DisplayName "RemotePCControl LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8788 -RemoteAddress LocalSubnet -Profile Any
ipconfig
```
Open `http://<PC-IPv4-address>:8788` on a phone on the same Wi-Fi. Give the PC a fixed address (DHCP reservation in your router) so the URL does not change.

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
Open **GitHub > Actions > Android APK** (it runs on every push to `main`, or use *Run workflow*) and download the APK from the run's artifact or from **Releases**. Install it (allow "install unknown apps" if asked). In the app enter the *PC URL* (`https://...trycloudflare.com`, `http://100.x.x.x:8788` or your LAN address) and the token. This is a debug build for personal use, not a Play Store release. Build instructions: [android/README.md](android/README.md).

The app has three screens:
- **Connect**: PC URL and token. Only the URL is remembered; the token stays in memory.
- **Dashboard**: CPU, memory and disk gauges, network speed (refreshed every 5 s), and power buttons. Sleep, Restart and Shutdown ask for confirmation; Lock does not. It also holds the **Quality** setting and the *Start screen session* button.
- **Session**: live screen, touch modes, trackpad, keys. A small overlay in the corner of the picture shows the received resolution and the measured/maximum frames per second (for example `1280×720 · 14/15 fps`). **Quality** in the toolbar changes the stream while it is running, and the choice is remembered.

| Quality | Width | Max FPS | JPEG quality |
|---|---|---|---|
| Low | 960 px | 10 | 45 |
| Medium (default) | 1280 px | 15 | 65 |
| High | 1920 px | 20 | 78 |
| Native | PC resolution | 15 | 85 |

Frames are drawn with high-quality (bicubic) filtering so text stays sharp when the picture is scaled to the phone screen. Native on a 4K PC needs a fast connection and decodes large images; use High if it stutters.

## Stream quality (protocol)
The server's `.env` values below are only the *starting* values of every `/ws/screen` connection. A client can change them at any time while streaming:
```json
{"type":"config","max_width":1920,"fps":15,"quality":70}
```
All fields are optional. `max_width` is `0` (native) or 320-3840, `fps` is 1-30, `quality` is JPEG 25-90; out-of-range numbers are clamped and unusable values are ignored. Settings are per connection. The server answers with a fresh `{"type":"screen","width":W,"height":H,"max_width":..,"fps":..,"quality":..}` (the values now in effect) followed by a new frame. Frames are never upscaled, so `max_width` above the PC's resolution just sends native size. Clients that never send `config` get exactly the `.env` behaviour.

## Updating
```powershell
cd $HOME\remote-pc-control
git checkout main
git pull
.\scripts\setup.ps1     # rebuilds the dashboard / installs new dependencies
.\scripts\start.ps1
```

## Configuration (`.env`)
| Variable | Default | Meaning |
|---|---|---|
| `REMOTE_PC_TOKEN` | generated | Access secret (32+ chars). Required. |
| `REMOTE_PC_HOST` / `REMOTE_PC_PORT` | `0.0.0.0` / `8788` | Listen address. |
| `REMOTE_PC_FPS` | `10` | Starting frames per second (1-30); clients can change it live. |
| `REMOTE_PC_JPEG_QUALITY` | `55` | Starting JPEG quality (25-85); clients can raise it to 90 live. |
| `REMOTE_PC_MAX_WIDTH` | `1280` | Starting width limit; wider frames are downscaled (`0` = native). Clients can change it live. |
| `REMOTE_PC_SHOW_CURSOR` | `1` | Draw a pointer on the stream. |

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
| `git clone` says folder exists | Use the existing folder: `cd $HOME\remote-pc-control`, then `git pull`. |

## Security and limitations
- Anyone with the token (and a reachable URL) can control the PC. Keep the token and tunnel link private; revoke any credential you have pasted into chats or tickets.
- Prefer Tailscale or Cloudflare Access (see [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md)) over a bare public link. Never expose port 8788 directly.
- The agent runs in the logged-in desktop session. It cannot capture or control the Windows sign-in screen or UAC prompts and does not bypass Windows authentication. Use Windows Remote Desktop or a reviewed remote-access product to sign in.
- Wake-on-LAN over mobile data needs a separately authenticated always-on LAN relay (API reports it as not configured).
- JPEG streaming is simple and bandwidth-hungry; tune FPS, quality and width for your connection.

## Development
```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q   # backend tests
cd frontend; npm install; npm run build                        # web dashboard
```
Protocol and input handling live in `backend/app/screen.py`; the touch UI is `frontend/src/RemoteScreen.tsx` (web). The Android app lives in `android/app/src/main/java/com/mainnetwallet/remotepccontrol/` (`MainActivity.kt` entry and navigation, `RemoteController.kt` networking/state, `ConnectScreen.kt`, `DashboardScreen.kt`, `SessionScreen.kt`, `Trackpad.kt`, `Theme.kt`, `Components.kt`).

---

## বাংলা সারসংক্ষেপ
1. PC-তে Python 3.12, Node.js 22, Git ইনস্টল করুন।
2. PowerShell-এ: `git clone https://github.com/mainnetwallet/remote-pc-control.git`, তারপর `cd remote-pc-control`, `Set-ExecutionPolicy -Scope Process Bypass`, `.\scripts\setup.ps1`। শেষে যে token দেখাবে সেটা সেভ করুন।
3. `.\scripts\start.ps1` চালান (window খোলা রাখুন)।
4. নতুন PowerShell window-তে `.\scripts\start-tunnel.ps1` চালান। যে `https://...trycloudflare.com` লিংক আসবে সেটা ফোনে খুলুন (লিংক প্রতিবার বদলায়)।
5. Token দিয়ে Connect করে Start screen চাপুন। Click/Move/Drag/Scroll mode দিয়ে আঙুলে mouse চালান।
6. কাজ শেষে tunnel window-তে `Ctrl+C` চাপুন। লিংক ও token কাউকে দেবেন না।
