# Android App

Native Kotlin + Jetpack Compose client for Remote PC Control.

## Install and connect

1. Download the Android APK from GitHub Actions or the repository's Releases.
2. Install it on your phone.
3. Start the Windows agent using the [Windows quick start](../docs/QUICKSTART_WINDOWS.md).
4. Enter the PC URL and the `REMOTE_PC_TOKEN` from the PC's `.env`.
5. Tap **Connect**, then start a screen session.

Use Tailscale or the same trusted Wi-Fi for private access. A Cloudflare URL is supported for signaling and the WebSocket stream; the quick tunnel alone cannot carry WebRTC video. Do not expose port 8888 directly to the internet.

## Build the APK

Open the `android/` folder in Android Studio with JDK 17 and Android SDK 35, sync Gradle, then choose **Build > Build APK(s)**.

Or run from this directory with Gradle 8.11.1 or newer:

```powershell
gradle assembleDebug
```

The debug APK is written to `app/build/outputs/apk/debug/app-debug.apk`.

## Screen controls

- **Click / Move / Drag / Scroll:** choose how touch gestures control the PC.
- **Trackpad:** move the pointer, click, drag, and scroll.
- **Keys:** send common keys or enter text.
- **Quality:** change stream quality while the session is active.
- **Stop:** end the screen session.

The screen overlay shows the active transport, resolution, and frame rate. WebRTC may also show round-trip time. If WebRTC cannot connect, the app falls back to JPEG over WebSocket.

## Transport notes

WebRTC sends H.264 video over UDP and input over data channels. A direct route usually works best over the same Wi-Fi or Tailscale. Mobile carrier NAT or strict firewalls may require a TURN relay configured on the PC with `REMOTE_PC_TURN_URL`, `REMOTE_PC_TURN_USER`, and `REMOTE_PC_TURN_PASS`.

A Cloudflare quick tunnel carries HTTP/WebSocket traffic but not WebRTC media. Cloudflare Access browser login is not supported by the Android app.

## Security

The app stores the access token encrypted with the Android Keystore after login. Use **Log out** to clear saved credentials. Anyone with the token and network access can control the PC, so keep it private.

The app controls only the logged-in interactive desktop. It cannot bypass Windows sign-in, UAC secure desktop, or other operating-system security boundaries. Power actions require confirmation.

## Code map

- `MainActivity.kt` — app entry and navigation
- `RemoteController.kt` — connection, state, and quality presets
- `ConnectScreen.kt`, `DashboardScreen.kt`, `SessionScreen.kt` — app screens
- `Trackpad.kt` — touchpad controls
- `Theme.kt`, `Components.kt` — theme and shared UI
