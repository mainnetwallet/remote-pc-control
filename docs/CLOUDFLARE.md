# Cloudflare Tunnel

Connect to your Windows PC through an HTTPS hostname without router port forwarding.

> Keep `REMOTE_PC_TOKEN` private. A tunnel makes the service reachable from the internet; use Cloudflare Access for a named public hostname where possible.

## Choose a tunnel

| Type | Best for | Requirements |
|---|---|---|
| Quick tunnel | Temporary access and testing | No Cloudflare account; URL changes after restart |
| Named tunnel | Stable hostname | Cloudflare account and a domain managed by Cloudflare |

Start the agent first in a separate PowerShell window:

```powershell
cd $HOME\remote-pc-control
.\scripts\start.ps1
```

## Quick tunnel

Open a second PowerShell window:

```powershell
cd $HOME\remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-tunnel.ps1
```

Open the printed `https://….trycloudflare.com` URL on your phone or enter it as the PC URL in the Android app. The URL changes each time the tunnel starts. Keep both windows open; press **Ctrl+C** in the tunnel window to stop it.

## Named tunnel

1. Add your domain to Cloudflare and wait for its status to become **Active**.
2. In Cloudflare Zero Trust, open **Networks → Tunnels** and create a **Cloudflared** tunnel.
3. Choose **Windows** and run the installation command shown in the dashboard in an Administrator PowerShell window. Treat the tunnel token like a password.
4. Add a public hostname, for example `pc.example.com`, with service type **HTTP** and URL `localhost:8888`.
5. Confirm the connector is **Connected**, then open `https://pc.example.com` on the phone.

The tunnel service starts with Windows, but the Remote PC Control agent must also be running. For a command-line setup, see [Cloudflare's tunnel documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

## Protect the hostname

For a named public hostname, configure **Zero Trust → Access → Applications → Add application → Self-hosted** and allow only your own email address. Test browser access before relying on it.

**Android limitation:** the app cannot complete the Cloudflare Access email/OTP browser flow. Use a browser with Access enabled, or connect the Android app over Tailscale/private Wi-Fi instead. Service-token headers are not built into the app.

## WebRTC and tunnels

Cloudflare Tunnel carries HTTP and WebSocket traffic, including signaling, but not the app's direct UDP WebRTC video. The app will fall back to JPEG over WebSocket when WebRTC cannot connect. For lower-latency video, use the same LAN, Tailscale, or configure a TURN relay on the PC.

## Troubleshooting

| Symptom | Check |
|---|---|
| 502 Bad Gateway | Agent is running and the hostname service points to `http://localhost:8888`. |
| Error 1033 | Check the Cloudflared service status and tunnel connector. |
| Hostname does not resolve | Domain is Active and the public hostname/DNS route exists. |
| Access login loops or Android is blocked | See the Access limitation above. |
