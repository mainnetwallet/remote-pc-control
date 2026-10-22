# Remote PC Control — Android app

Native Kotlin + Jetpack Compose companion app for the Remote PC Control Windows agent.

## Build APK
Open the `android/` directory in Android Studio (JDK 17; Android SDK 35), wait for Gradle sync, then select **Build > Build APK(s)**. The debug APK is written to `app/build/outputs/apk/debug/app-debug.apk`.

Or run from this directory: `gradle assembleDebug` with Gradle 8.11.1 or newer installed.

## Connect
1. Install and start the Windows agent using the repository's Windows setup guide.
2. Make the PC reachable from the phone: Tailscale/WireGuard (`http://100.x.x.x:8788`), the same Wi-Fi (`http://<PC-LAN-IP>:8788`) or a Cloudflare tunnel (`https://....trycloudflare.com`, see the main README).
3. Enter the PC base URL and the API token from the PC's `.env`.

In the screen session use the toolbar modes Click / Move / Drag / Scroll, the Double-click button, Fullscreen and the quick-key bar.
4. Tap Connect. The app loads system metrics and can open a live screen session.

Do not expose port 8788 directly to the public internet. The API token is stored only in app memory and is not persisted by this starter app. The app requires a trusted private network because the current agent setup may use HTTP/WebSocket rather than TLS.

The app can only control the logged-in interactive Windows desktop. It cannot bypass Windows sign-in, UAC secure desktop, or other OS security boundaries. Restart/shutdown require confirmation.
