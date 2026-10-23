# Remote PC Control — Android app

Native Kotlin + Jetpack Compose companion app for the Remote PC Control Windows agent.

## Build APK
Open the `android/` directory in Android Studio (JDK 17; Android SDK 35), wait for Gradle sync, then select **Build > Build APK(s)**. The debug APK is written to `app/build/outputs/apk/debug/app-debug.apk`.

Or run from this directory: `gradle assembleDebug` with Gradle 8.11.1 or newer installed.

## Connect
1. Install and start the Windows agent using the repository's Windows setup guide.
2. Make the PC reachable from the phone: Tailscale/WireGuard (`http://100.x.x.x:8888`), the same Wi-Fi (`http://<PC-LAN-IP>:8888`) or a Cloudflare tunnel (`https://....trycloudflare.com`, see the main README).
3. Enter the PC base URL and the API token from the PC's `.env`.

4. Tap Connect. The Dashboard shows system metrics and the power buttons, and opens a live screen session.

In the screen session use the toolbar modes Click (tap = click, drag = move the pointer) / Drag / Scroll, the Double-click button, the **Quality** menu (Low / Medium / High / Native, applied live) and the quick-key bar. The corner overlay shows the stream resolution and frames per second.

Do not expose port 8888 directly to the public internet. After the first successful login the password is stored encrypted (Android Keystore) so the app signs in by itself at start; tap Log out to forget it. The app requires a trusted private network because the current agent setup may use HTTP/WebSocket rather than TLS.

The app can only control the logged-in interactive Windows desktop. It cannot bypass Windows sign-in, UAC secure desktop, or other OS security boundaries. Sleep, restart and shutdown require confirmation.

## Code layout
`MainActivity.kt` (entry and navigation), `RemoteController.kt` (HTTP, WebSocket, session state and quality presets), `Rtc.kt` (WebRTC peer/signaling/data channels), `SecureStore.kt` (Android Keystore encryption), `ConnectScreen.kt`, `DashboardScreen.kt`, `SessionScreen.kt`, `Trackpad.kt`, `Theme.kt`, and `Components.kt`. The app uses Jetpack Compose and Material 3.

## WebRTC live screen

The live screen first tries WebRTC (low-latency H.264 video over UDP, input over data channels) through the PC's
`/ws/rtc` endpoint. If the PC has no WebRTC, the network blocks UDP, or nothing connects within about 20 seconds, the
app switches to the old WebSocket JPEG stream by itself and shows a short notice. The corner label of the live
screen shows which transport is active (`WebRTC` or `WebSocket`), the frame rate and, for WebRTC, the round-trip time.

Library: `io.getstream:stream-webrtc-android` (package `org.webrtc`). The Quality presets map to bitrate/size/fps
(Low 1500, Medium 3000, High 6000, Native 10000 kbit/s). Over a Cloudflare quick tunnel only the signaling travels
through the tunnel; the video needs a direct path (same Wi-Fi, Tailscale, or TURN set on the PC with
`REMOTE_PC_TURN_URL`, see the root README).
