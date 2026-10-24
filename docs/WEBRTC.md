<div align="center">

# WebRTC and Stream Details

Reference for the live-screen transports: the WebSocket JPEG stream (fallback), WebRTC (low latency), quality settings, TURN setup and the signaling protocol.

[← Project README](../README.md) · [Architecture](ARCHITECTURE.md) · [Cloudflare guide](CLOUDFLARE.md)

</div>

---

**On this page:** [Stream quality](#stream-quality-protocol) · [WebRTC mode](#webrtc-mode-low-latency) · [Which network](#which-networks-give-low-latency) · [Settings](#settings) · [TURN](#turn-setup) · [Check transport](#check-which-transport-is-active) · [Protocol](#protocol-for-other-clients) · [Related settings](#related-env-settings)

## Stream quality (protocol)

The server's `.env` values below are only the *starting* values of every `/ws/screen` connection. A client can change them at any time while streaming:

```json
{"type":"config","max_width":1920,"fps":15,"quality":70}
```

All fields are optional. `max_width` is `0` (native) or 320-3840, `fps` is 1-30, `quality` is JPEG 25-90; out-of-range numbers are clamped and unusable values are ignored. Settings are per connection. The server answers with a fresh `{"type":"screen","width":W,"height":H,"max_width":..,"fps":..,"quality":..}` (the values now in effect) followed by a new frame. Frames are never upscaled, so a `max_width` above the PC's resolution just sends native size. Clients that never send `config` get exactly the `.env` behaviour.

### Motion quality (less lag)

While the picture keeps changing (scrolling, window animations, dragging) the server sends frames at `REMOTE_PC_MOTION_QUALITY` percent of the JPEG quality (40-100, default `100` = off), so they are smaller and reach the phone sooner. As soon as the picture rests for about 0.2 s it sends one full-quality frame, so text is sharp again. Frames are also scaled to `REMOTE_PC_MOTION_WIDTH` percent of their width (50-100, default `100` = off) while the picture moves. Set both to `100` in `.env` to turn this off. No client change is needed.

### Fast capture

`setup.ps1` also tries to install the optional `dxcam` package, which captures the screen through DXGI several times faster than the default `mss`. If it is missing or does not work on your PC (remote desktop session, other monitor layout, no frames) the server prints one line and keeps using `mss` by itself. `REMOTE_PC_CAPTURE=mss` in `.env` forces the old capture.

## WebRTC mode (low latency)

The default JPEG stream sends one picture per frame over a TCP WebSocket. One slow packet delays everything behind it, and a Cloudflare tunnel adds a relay hop on top. WebRTC sends H.264 video over UDP (old frames are dropped instead of queued) and carries mouse and keyboard input on data channels.

**How it works.** When you tap *Start screen*, the Android app first opens `/ws/rtc` on the same PC address with the same password. That socket is only used to exchange the connection offer (signaling). The video and the input then travel directly between phone and PC.

- The WebSocket JPEG stream starts at the same moment, so there is a picture from the first second while WebRTC negotiates. As soon as WebRTC video is really being decoded the app switches to it and closes the JPEG stream.
- If WebRTC has not delivered video within about 20 seconds, or the PC says WebRTC is unavailable, the app keeps the WebSocket stream and shows a small notice. A short network drop (under 5 seconds) does not end a working WebRTC session.
- The PC encodes with the GPU when it can (NVIDIA `nvenc`, Intel `qsv`, AMD `amf`) and otherwise with libx264 (`ultrafast`, `zerolatency`, no B-frames). A hardware encoder that does not work is skipped automatically.
- Input uses two data channels with the same JSON messages as `/ws/input`: `input` (unordered, no retransmits) for pointer moves, and `control` (reliable) for clicks, keys, scroll, hotkeys and typed text.

### Which networks give low latency

| Network | Result |
|---|---|
| Same Wi-Fi / LAN | Direct UDP, lowest latency (about 50 ms or less is realistic) |
| Tailscale (phone and PC both on it) | Direct UDP through the Tailscale addresses |
| Internet, both sides reachable with STUN | Direct UDP after NAT punch-through |
| Mobile data behind CGNAT / strict firewall | Needs a **TURN** relay, otherwise the app falls back to the WebSocket stream |

> [!NOTE]
> A free **Cloudflare quick tunnel only carries TCP/HTTP**. It can carry the signaling, but it cannot carry the WebRTC video. Over a quick tunnel alone WebRTC usually will not connect and the app falls back to the WebSocket stream. For the best result use Tailscale or the same LAN.

### Settings

Set in `.env`; restart `start.ps1` after changing.

| Variable | Default | Meaning |
|---|---|---|
| `REMOTE_PC_WEBRTC` | `1` | `0` turns WebRTC off; clients then always use the WebSocket stream |
| `REMOTE_PC_RTC_FPS` | `30` | Maximum video frames per second (1-30) |
| `REMOTE_PC_RTC_BITRATE` | `4000` | Upper video bitrate limit in kbit/s (300-30000). The app's quality preset can lower it for its session. The receiver's own bandwidth estimate can lower the live bitrate, but not below 1 Mbit/s (or this limit if it is lower) |
| `REMOTE_PC_RTC_ENCODER` | `auto` | `auto`, or force `nvenc`, `qsv`, `amf` or `x264`. libx264 is always the last resort |
| `REMOTE_PC_STUN_URL` | `stun:stun.l.google.com:19302` | STUN server(s), comma separated |
| `REMOTE_PC_TURN_URL` / `_USER` / `_PASS` | empty | Optional TURN relay, see below |

### TURN setup

Only needed if the direct connection fails. TURN relays the video through a server you control, which adds a little delay but works behind CGNAT. You need a small server with a public IP and open UDP port 3478 (and the relay port range). With [coturn](https://github.com/coturn/coturn) a minimal `turnserver.conf` is:

```text
listening-port=3478
realm=remote-pc
lt-cred-mech
user=pcuser:use-a-long-random-password
fingerprint
no-cli
```

Then put this in the PC's `.env` and restart:

```text
REMOTE_PC_TURN_URL=turn:YOUR.SERVER.IP:3478
REMOTE_PC_TURN_USER=pcuser
REMOTE_PC_TURN_PASS=use-a-long-random-password
```

The PC sends the TURN details only to clients that signed in with the token, and uses them for itself. They are never printed to the log. Use a dedicated TURN user, not a password you use elsewhere.

### Check which transport is active

| Where | What to look for |
|---|---|
| **Android** | The small label in the corner of the picture starts with the transport, e.g. `WebRTC · 1280×720 · 30 fps · 38 ms` or `WebSocket · 1280×720 · 20/30 fps`. After a fallback a notice says why |
| **PC** | `start.ps1`'s window logs `WebRTC connection connected` (and `WebRTC encoder: h264_nvenc ...` or `libx264`) for every WebRTC session. If the app fell back, there is a `/ws/screen` connection instead and no such lines |
| **Web dashboard** | The corner label says `WebRTC` or `WebSocket`; `chrome://webrtc-internals` shows details |

### Protocol (for other clients)

`/ws/rtc` uses the same first message as the other sockets, `{"token":"..."}`, then JSON:

1. The PC sends `{"type":"ready","ice_servers":[...]}`.
2. The client sends `{"type":"offer","sdp":"..."}` (receive-only video plus data channels `input` and `control`) and gets `{"type":"answer","sdp":"..."}`.
3. Trickle candidates go both ways as `{"type":"candidate","candidate":{"candidate":"...","sdpMid":"0","sdpMLineIndex":0}}`.
4. `{"type":"unavailable","reason":"..."}` means: use `/ws/screen`.
5. Over the `control` channel `{"type":"config","max_width":1280,"fps":30,"bitrate":3000,"cursor":true}` changes the video live (bitrate in kbit/s).

Details are in the header of `backend/app/webrtc.py`.

## Related `.env` settings

| Variable | Default | Meaning |
|---|---|---|
| `REMOTE_PC_LATENCY_FIRST` | `1` | `1`: on a slow link the picture is made smaller at once (and grows back slowly, in steps of 10 quality / 80 px) so the delay stays low. `0`: always exactly the quality and width chosen in the app |
| `REMOTE_PC_FPS` | `20` | Starting frames per second (1-30); clients can change it live |
| `REMOTE_PC_JPEG_QUALITY` | `55` | Starting JPEG quality (25-85); clients can raise it to 90 live |
| `REMOTE_PC_MAX_WIDTH` | `1280` | Starting width limit; wider frames are downscaled (`0` = native) |
| `REMOTE_PC_MOTION_QUALITY` / `_WIDTH` | `100` / `100` | Motion-frame reduction, see [Motion quality](#motion-quality-less-lag) |
| `REMOTE_PC_SHOW_CURSOR` | `1` | Draw a pointer on the stream |
| `REMOTE_PC_CAPTURE` | `auto` | `mss` forces the classic capture instead of `dxcam` |
