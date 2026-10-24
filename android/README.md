<div align="center">

# Remote PC Control: Android App

Native Kotlin + Jetpack Compose companion app for the Remote PC Control Windows agent.

![android](https://img.shields.io/badge/min%20SDK-26-3DDC84?logo=android&logoColor=white)
![target](https://img.shields.io/badge/target%20SDK-35-3DDC84?logo=android&logoColor=white)
![kotlin](https://img.shields.io/badge/Kotlin-2.1-7F52FF?logo=kotlin&logoColor=white)
![compose](https://img.shields.io/badge/Jetpack%20Compose-Material%203-4285F4?logo=jetpackcompose&logoColor=white)

[← Project README](../README.md) · [Windows quick start](../docs/QUICKSTART_WINDOWS.md) · [WebRTC details](../docs/WEBRTC.md)

</div>

---

## Get the app

**Download a build (easiest).** Open **GitHub → Actions → Android APK**, or the repository **Releases** page, and download the debug APK (artifact `remote-pc-control-android-debug`, or the `RemotePCControl-Android-android-build-<n>.apk` release asset). Allow installation from this source if Android asks.

**Build it yourself.** Open the `android/` directory in Android Studio (JDK 17, Android SDK 35), wait for Gradle sync, then choose **Build → Build APK(s)**. The debug APK is written to `app/build/outputs/apk/debug/app-debug.apk`. From the command line, in this directory:

```bash
gradle assembleDebug
```

This needs Gradle 8.11.1 or newer (CI uses 8.13; the Android Gradle plugin is 8.9.2).

> [!NOTE]
> Builds are signed with the debug keystore stored in the repository (`app/debug.keystore`) so each build installs over the previous one. That is fine for personal use, but anyone can sign an APK with that key, so this is not a Play Store release.

## Connect

1. Install and start the Windows agent using the [Windows quick start](../docs/QUICKSTART_WINDOWS.md).
2. Make the PC reachable from the phone:

   | Method | PC URL |
   |---|---|
   | Tailscale / WireGuard | `http://100.x.x.x:8888` |
   | Same Wi-Fi | `http://<PC-LAN-IP>:8888` |
   | Cloudflare quick tunnel | `https://….trycloudflare.com` |
   | Cloudflare link published to a Gist | `gist:<id>` ([how](../docs/CLOUDFLARE.md#a2--one-command-start-with-an-automatic-link-for-the-android-app)) |

3. Enter the PC base URL and the API token from the PC's `.env`.
4. Tap **Connect**. The Dashboard shows system metrics and the power buttons, and opens a live screen session.

After the first successful login the URL and password are stored encrypted (Android Keystore) so the app signs in by itself at start. Tap **Log out** to forget them.

## Using it

| Screen | What you can do |
|---|---|
| **Dashboard** | CPU, memory and disk gauges, network speed, Sleep / Restart / Shutdown (with confirmation), the PIN lock card (set a PIN, lock, unlock), and the Quality menu |
| **Session** | Live screen with the modes **Click** (tap = click, drag = move the pointer), **Drag** and **Scroll**; Double-click button; **Quality** menu (Low / Medium / High / Native, applied live); quick-key bar; trackpad; Rotate button |

The corner overlay shows the transport, the stream resolution and the frame rate.

> [!WARNING]
> Do not expose port 8888 directly to the public internet. The agent may serve plain HTTP/WebSocket without TLS, so use a trusted private network (Tailscale, home Wi-Fi) or a Cloudflare tunnel.

The app can only control the logged-in interactive Windows desktop. It cannot bypass Windows sign-in, the UAC secure desktop, or other OS security boundaries. Sleep, restart and shutdown require confirmation. With a PIN set, the **Lock** button engages the [PIN lock](../README.md#-pin-lock) screen instead of the Windows lock.

## WebRTC live screen

The live screen first tries WebRTC (low-latency H.264 video over UDP, input over data channels) through the PC's `/ws/rtc` endpoint. If the PC has no WebRTC, the network blocks UDP, or nothing connects within about 20 seconds, the app switches to the WebSocket JPEG stream by itself and shows a short notice. The corner label shows which transport is active (`WebRTC` or `WebSocket`), the frame rate and, for WebRTC, the round-trip time.

| Quality preset | WebRTC bitrate (upper limit) | Width | Max FPS |
|---|---|---|---|
| Low | 1500 kbit/s | 960 px | 20 |
| Medium (default) | 3000 kbit/s | 1280 px | 30 |
| High | 8000 kbit/s | 1920 px | 30 |
| Native | 20000 kbit/s | PC resolution | 30 |

Pick **Native** for the sharpest picture on the same Wi-Fi or Tailscale. The bitrate is a ceiling that the link's own estimate can still lower. Over a Cloudflare quick tunnel only the signaling travels through the tunnel; the video needs a direct path (same Wi-Fi, Tailscale, or a TURN relay configured on the PC with `REMOTE_PC_TURN_URL`). Details: [WebRTC guide](../docs/WEBRTC.md).

Library: `io.getstream:stream-webrtc-android` (package `org.webrtc`).

## Code layout

| File | Role |
|---|---|
| `MainActivity.kt` | Entry point and navigation |
| `RemoteController.kt` | HTTP, WebSocket, session state and quality presets |
| `Rtc.kt` | WebRTC peer, signaling and data channels |
| `SecureStore.kt` | Android Keystore encryption of the saved credentials |
| `ConnectScreen.kt`, `DashboardScreen.kt`, `SessionScreen.kt` | The three main screens |
| `Trackpad.kt` | Trackpad gestures |
| `Keyboard.kt` | Keyboard input |
| `Theme.kt`, `Components.kt` | Material 3 theme and shared UI components |
