# Windows 11 Pro setup

1. Install Python 3.12 x64, Node.js 22 and Tailscale on PC and Android.
2. Sign in to the same tailnet on both devices.
3. Clone this repository and open PowerShell in its folder.
4. Run `Set-ExecutionPolicy -Scope Process Bypass`, then `scripts/setup.ps1`.
5. Store the generated token privately; never commit `.env`.
6. Run `scripts/start.ps1` in the logged-in desktop session.
7. On the phone, connect to Tailscale and open `http://<PC-Tailscale-IP>:8788`.
8. Do not port-forward TCP 8788. Test screen and input locally first.

The agent cannot capture/control Windows secure desktop, UAC prompts or the sign-in screen. Use Windows Remote Desktop or a reviewed remote-access client to log in; this project does not bypass authentication.

Wake-on-LAN requires firmware/NIC support. Mobile-data wake needs an authenticated always-on LAN relay; the API currently reports WOL as unconfigured.

## Cloudflare tunnel (no Tailscale)
Quick link (changes every run): run `scripts/start.ps1` in one PowerShell window and `scripts/start-tunnel.ps1` in a second one, then open the printed `https://...trycloudflare.com` link on the phone (browser, or paste it as the PC URL in the Android app).

Permanent link (needs a domain added to your Cloudflare account):
```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create mypc
cloudflared tunnel route dns mypc pc.YOUR-DOMAIN.com
```
Create `%USERPROFILE%\.cloudflared\config.yml`:
```yaml
tunnel: mypc
credentials-file: C:\Users\YOU\.cloudflared\<tunnel-id>.json
ingress:
  - hostname: pc.YOUR-DOMAIN.com
    service: http://localhost:8788
  - service: http_status:404
```
Run with `cloudflared tunnel run mypc` (or `cloudflared service install` to start with Windows).

**Security:** a public link means only the token protects mouse/keyboard/shutdown. Put the hostname behind Cloudflare Access (Zero Trust, free) and never share the link. The agent locks a client out for 5 minutes after 8 wrong tokens.
