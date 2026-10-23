# Windows installation

Two ways to install. Both run the agent in your signed-in desktop session.

## Option A: Installer

1. Download `RemotePCControl-Setup.exe` from the **Windows installer** workflow artifacts (GitHub **Actions** tab).
2. Run it. It installs per user, without administrator rights, and creates Start menu and desktop shortcuts.
3. Let the final step run `configure-installed.ps1`. It creates `.env` in the install folder and prints your access token once. Save it privately.
4. Start **Remote PC Control** from the shortcut.
5. Allow TCP port 8888 only from Tailscale (`100.64.0.0/10`) or your local network.

## Option B: From source

1. Install Python 3.11 or newer (x64), Node.js 22 and Git.
2. Clone the repository and open PowerShell in its folder.
3. Run:
   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\setup.ps1
   .\scripts\start.ps1
   ```
4. Save the generated token privately. Never commit `.env`.

See the [README](README.md#quick-start) for details and [docs/QUICKSTART_WINDOWS.md](docs/QUICKSTART_WINDOWS.md) for a step-by-step guide.

## Connect from the phone

Choose one:

- **Tailscale:** sign in to the same account on both devices and open `http://<PC-Tailscale-IP>:8888`.
- **Cloudflare tunnel:** see [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md) for the quick tunnel and for a permanent link on your own domain.

Do not port-forward TCP 8888. Test screen and input on the local network first.

## Limitations

- The agent cannot capture or control the Windows secure desktop, UAC prompts or the sign-in screen. Use Windows Remote Desktop or a reviewed remote-access client to sign in; this project does not bypass authentication.
- Wake-on-LAN requires firmware and NIC support. Waking over mobile data needs an authenticated, always-on LAN relay; the API currently reports Wake-on-LAN as not configured.
