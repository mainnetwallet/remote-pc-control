# Remote PC Control

Windows 11 Pro remote monitor/control starter for a PC you own. Use only through a private Tailscale/WireGuard network; never port-forward port 8788.

## Features
- CPU/RAM/disk/network monitor and token-authenticated API.
- Native Android companion app in `android/` with status, lock/sleep/restart/shutdown controls, screen streaming, touch-to-click, and text input.
- Mobile web dashboard, screen/input WebSockets, Wake-on-LAN relay integration point, tests, Windows installer workflow, and Android APK workflow.

## Android app
Open the `android/` folder in Android Studio (JDK 17, Android SDK 35) and build **app > Build > Build APK(s)**. Or trigger **Actions > Android APK > Run workflow** on GitHub. A successful workflow publishes `remote-pc-control-android-debug` as an artifact. This is a debug APK for testing, not a Play Store release.

Connect the phone and PC to the same private Tailscale/WireGuard network. In the app, enter the PC URL such as `http://100.64.0.10:8788` and the API token from the PC's `.env`.

## Windows setup
Install Python 3.12 x64, Node.js 22 and Tailscale on the PC and phone. Run `scripts/setup.ps1`, then `scripts/start.ps1`. Keep `.env` secret.

## Security and limitations
Run the agent in the logged-in interactive desktop session. It does not capture/control Windows secure desktop, UAC prompts or sign-in screen, and does not bypass Windows authentication. Use Windows Remote Desktop or a reviewed remote-access product to log in. Mobile-data Wake-on-LAN requires a separately authenticated always-on LAN relay. JPEG WebSocket streaming is a starter; test performance on your hardware. Never expose port 8788 directly to the public internet.
