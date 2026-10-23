# Remote PC Control: Android app

Native Kotlin and Jetpack Compose client for the Remote PC Control Windows agent.

| | |
|---|---|
| Package | `com.mainnetwallet.remotepccontrol` |
| Min / target SDK | 26 / 35 |
| UI | Jetpack Compose, Material 3 (dark) |
| WebRTC | `io.getstream:stream-webrtc-android` (package `org.webrtc`) |

## Build

Prebuilt debug APKs are published on the repository's **Releases** page by the *Android APK* workflow.

To build locally, open `android/` in Android Studio (JDK 17, Android SDK 35), wait for Gradle sync and select **Build > Build APK(s)**. The output is `app/build/outputs/apk/debug/app-debug.apk`.

From the command line, with Gradle 8.11.1 or newer:

```
cd android
gradle assembleDebug
```

## Connect

1. Install and start the Windows agent ([Windows quick start](../docs/QUICKSTART_WINDOWS.md)).
2. Make the PC reachable from the phone:
   - Tailscale: `http://100.x.x.x:8888`
   - Same Wi-Fi: `http://<PC-LAN-IP>:8888`
   - Cloudflare tunnel: `https://....trycloudflare.com`, or `gist:<id>` for the [automatic link](../README.md#automatic-link-for-the-android-app)
3. Enter the PC URL and the access token from the PC's `.env`, then tap **Connect**.

The Dashboard shows system metrics and power buttons (Sleep, Restart and Shutdown ask for confirmation) and opens the live screen session.

In the session, use the Click / Move / Drag / Scroll modes, the Double-click button, the trackpad, the quick-key bar and the **Quality** menu (Low, Medium, High, Native; applied live). The corner overlay shows the transport, resolution and frame rate.

After the first successful login the password is stored encrypted with the Android Keystore, and the app signs in automatically at start. **Log out** forgets it.

## Security notes

- Do not expose port 8888 directly to the internet. Use Tailscale, the same network, or a Cloudflare tunnel.
- The agent may serve plain HTTP and WebSocket without TLS, so use the app only on a trusted private network or through an `https://` tunnel.
- The app controls only the signed-in interactive desktop. It cannot bypass Windows sign-in or the UAC secure desktop.

## WebRTC live screen

The live screen first tries WebRTC (H.264 video over UDP, input over data channels) through the PC's `/ws/rtc` endpoint. If the PC has no WebRTC, UDP is blocked, or no video arrives within about 20 seconds, the app switches to the WebSocket JPEG stream and shows a notice. The overlay shows the active transport, the frame rate and, for WebRTC, the round-trip time.

Quality presets map to these WebRTC bitrates: Low 1500, Medium 3000, High 6000 and Native 10000 kbit/s. Over a Cloudflare quick tunnel only signaling passes through the tunnel; the video needs a direct path (same Wi-Fi, Tailscale) or a TURN relay configured on the PC. See [WebRTC mode](../README.md#webrtc-mode).

## Code layout

| File | Role |
|---|---|
| `MainActivity.kt` | Edge-to-edge setup and navigation |
| `RemoteController.kt` | State, HTTP and WebSocket clients, quality presets, transport fallback |
| `Rtc.kt` | WebRTC client |
| `ConnectScreen.kt`, `DashboardScreen.kt`, `SessionScreen.kt` | Screens |
| `Trackpad.kt` | Trackpad gestures |
| `SecureStore.kt` | Encrypted credential storage |
| `Theme.kt`, `Components.kt` | Material 3 theme and shared widgets |

Only stable Compose and Material 3 APIs are used (no `@OptIn(Experimental...)`), because the APK is built by GitHub Actions.
