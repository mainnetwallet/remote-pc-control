# Cloudflare setup

Two ways to reach your PC through Cloudflare. Neither needs port forwarding or Tailscale, and both give the phone an `https://` link.

| | Quick tunnel | Permanent tunnel |
|---|---|---|
| Link | Random, changes every run | Your own name, for example `https://pc.example.com` |
| Requirements | None (no account) | Free Cloudflare account and a domain added to it |
| Cost | Free | Free tunnel plus a domain (about $10/year) |
| Starts with Windows | No | Yes (Windows service) |

Both require the server to be running: `.\scripts\start.ps1` in its own PowerShell window (see the [README](../README.md)).

## A. Quick tunnel

```powershell
cd $HOME\remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-tunnel.ps1
```

The first run installs `cloudflared`. If prompted, open a new PowerShell window and run the command again. Open the printed `https://....trycloudflare.com` link on the phone. Press `Ctrl+C` to stop. Each run creates a new link.

To publish the link to the Android app automatically, see [Automatic link for the Android app](../README.md#automatic-link-for-the-android-app).

## B. Permanent tunnel

### B1. Add a domain to Cloudflare

You need a domain whose DNS is managed by Cloudflare. A subdomain such as `pc.example.com` will point to your PC.

1. Sign in at [dash.cloudflare.com](https://dash.cloudflare.com).
2. **Existing domain:** choose **Add a domain**, enter it, select the **Free** plan and replace the nameservers at your registrar with the two Cloudflare provides. Wait until the domain shows **Active** (minutes to a few hours).
3. **No domain:** register one through Cloudflare (**Domain Registration**) or any registrar, then follow step 2. Without a domain, use the quick tunnel.

### B2. Create the tunnel (dashboard method)

1. Open **Zero Trust** in the dashboard menu. On first use it asks for a team name and the Free plan.
2. Go to **Networks > Tunnels** (shown as *Connectors* in newer dashboards), choose **Create a tunnel**, type **Cloudflared**, name it (for example `mypc`) and save.
3. Select **Windows**. Cloudflare shows an install command containing a token. In an **administrator PowerShell**, run the command exactly as shown:
   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared.exe service install <TOKEN-FROM-DASHBOARD>
   ```
   If `cloudflared` is not recognized right after installing, open a new administrator PowerShell. Treat the token like a password; do not share it or commit it.
4. When the connector shows **Connected**, click **Next**.
5. Add a **public hostname**:
   - Subdomain: `pc` (or any name); Domain: your domain; Path: empty
   - Service type **HTTP**, URL `localhost:8888`
6. On the phone, open `https://pc.example.com` and enter the access token. The tunnel now starts with Windows; the server (`start.ps1`) must also be running.

WebSockets (live screen and input) work through the tunnel without extra configuration.

### B2 (alternative). Command line

```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create mypc
cloudflared tunnel route dns mypc pc.example.com
```

Create `%USERPROFILE%\.cloudflared\config.yml`:

```yaml
tunnel: mypc
credentials-file: C:\Users\YOU\.cloudflared\<tunnel-id>.json
ingress:
  - hostname: pc.example.com
    service: http://localhost:8888
  - service: http_status:404
```

Test with `cloudflared tunnel run mypc`. To run at startup, use `cloudflared service install`. The Windows service runs as SYSTEM and reads `C:\Windows\System32\config\systemprofile\.cloudflared\`. If it does not start, copy `config.yml` and the credentials `.json` there and update `credentials-file`.

## C. Protect the link with Cloudflare Access

A permanent public hostname is reachable by anyone on the internet; only the token and the lockout protect it. Cloudflare Access adds a login in front. It is recommended for any permanent tunnel.

1. In Zero Trust, go to **Access > Applications**, choose **Add an application** and select **Self-hosted**.
2. Set the application name (for example `PC`) and the **Application domain** to your hostname.
3. Add a policy: action **Allow**, rule **Emails** set to your own address only. **One-time PIN** is enabled by default.
4. Save. The browser now asks for your email and a one-time code before it shows the app's token screen.

**Limitation:** the Android app cannot complete the browser login, so with Access enabled the app is blocked while the browser works. Alternatives: use the browser, use the app over Tailscale or Wi-Fi, or create a *Service Token* policy (**Access > Service credentials**), which requires the app to send `CF-Access-Client-Id` and `CF-Access-Client-Secret` headers. The app does not support this yet.

## Using the link

- **Phone browser:** open `https://pc.example.com`, enter the token and tap **Start screen**.
- **Android app:** set *PC URL* to `https://pc.example.com` and enter the access token from `.env`.

WebRTC video does not pass through a Cloudflare tunnel; the app uses the WebSocket stream unless the phone and PC have a direct path. See [WebRTC mode](../README.md#webrtc-mode).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `502 Bad gateway` | `start.ps1` is not running, or the hostname's service URL is not `http://localhost:8888`. |
| Error 1033 / tunnel not found | The `cloudflared` service is not running. In an administrator PowerShell: `Get-Service cloudflared`, then `Start-Service cloudflared`. |
| Connector shows *Inactive* | The PC is offline or the service stopped. Restart it. |
| Hostname does not resolve | The public hostname must exist in the tunnel and the domain must be **Active**. |
| Access login loops or the app is blocked | See the Access limitation above. |
| Stop access | `Stop-Service cloudflared`, or delete the public hostname or tunnel in the dashboard. |

Dashboard labels change from time to time. Look for **Zero Trust > Networks > Tunnels** and **Access > Applications**.
