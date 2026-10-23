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

In the screen session use the toolbar modes Click / Move / Drag / Scroll, the Double-click button, the **Quality** menu (Low / Medium / High / Native, applied live) and the quick-key bar. The corner overlay shows the stream resolution and frames per second.

Do not expose port 8888 directly to the public internet. After the first successful login the password is stored encrypted (Android Keystore) so the app signs in by itself at start; tap Log out to forget it. The app requires a trusted private network because the current agent setup may use HTTP/WebSocket rather than TLS.

The app can only control the logged-in interactive Windows desktop. It cannot bypass Windows sign-in, UAC secure desktop, or other OS security boundaries. Sleep, restart and shutdown require confirmation.

## Code layout
`MainActivity.kt` (edge-to-edge setup, navigation), `RemoteController.kt` (state, HTTP/WebSocket, Quality presets), `ConnectScreen.kt`, `DashboardScreen.kt`, `SessionScreen.kt`, `Trackpad.kt`, `Theme.kt` (Material 3 dark theme), `Components.kt` (shared widgets, window-insets helper). Only stable Compose / Material 3 APIs are used (no `@OptIn(Experimental...)`), because the APK is built by GitHub Actions.
