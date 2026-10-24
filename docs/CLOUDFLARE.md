<div align="center">

# Cloudflare Setup Guide

Reach your PC from anywhere with an `https://` link: no port-forwarding, no Tailscale.

[← Project README](../README.md) · [Quick start](QUICKSTART_WINDOWS.md) · [WebRTC details](WEBRTC.md)

</div>

---

**On this page:** [Compare](#choose-a-tunnel) · [A · Quick tunnel](#a--quick-tunnel-no-account) · [B · Permanent tunnel](#b--permanent-tunnel-same-link-forever) · [C · Cloudflare Access](#c--protect-the-public-link-with-cloudflare-access) · [Using the link](#using-the-link) · [Troubleshooting](#troubleshooting) · [বাংলা সারসংক্ষেপ](#বাংলা-সারসংক্ষেপ-স্থায়ী-লিংক)

## Choose a tunnel

| | Quick tunnel | Permanent tunnel |
|---|---|---|
| **Link** | Random, **changes every run** | Your own name, e.g. `https://pc.example.com`, **never changes** |
| **Needs** | Nothing (no account) | Free Cloudflare account **and a domain** added to it |
| **Cost** | Free | Free tunnel plus a domain (about $10/year; some domains cost less) |
| **Starts with Windows** | No | Yes (runs as a Windows service) |

> [!IMPORTANT]
> Both need the server running first: `.\scripts\start.ps1` in its own PowerShell window (see the [README](../README.md)).

---

## A · Quick tunnel (no account)

```powershell
cd $HOME\remote-pc-control
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-tunnel.ps1
```

The first run installs `cloudflared` with `winget`; if it asks, close PowerShell, open a new one and run it again. Open the printed `https://….trycloudflare.com` link on the phone. Press `Ctrl+C` to stop. A new link is created each time. Do not share the link.

Test it first: `https://<your-link>/api/health` should return `{"ok":true,...}`.

### A2 · One-command start with an automatic link for the Android app

Instead of running the tunnel in a second window, let `start.ps1` start it and publish the current link to a **secret GitHub Gist** that the Android app reads.

1. Create a GitHub **classic** token with **only the `gist` scope** at <https://github.com/settings/tokens>. Never reuse a repository token.
2. Add to `.env` (running `.\scripts\setup.ps1` also offers to save `GIST_TOKEN` for you):

   ```text
   QUICK_TUNNEL=1
   GIST_TOKEN=your-gist-token
   ```

3. Run `.\scripts\start.ps1`. It installs `cloudflared` if needed, starts the tunnel, prints the link, and writes it to the Gist. On the first run it creates the Gist and appends `GIST_ID=<id>` to `.env`.
4. In the Android app enter `gist:<id>` once as the *PC URL*. The app then always finds the current link.

If the tunnel link cannot be read within about 40 seconds, `start.ps1` warns, points to `cloudflared.log`, and starts the server without the tunnel.

---

## B · Permanent tunnel (same link forever)

### B1 · Get a domain on Cloudflare

You need a domain whose DNS is managed by Cloudflare (a subdomain such as `pc.example.com` will point to your PC).

1. Create or sign in to a Cloudflare account at <https://dash.cloudflare.com>.
2. **Already have a domain?** Dashboard → **Add a domain** (or *Onboard a domain*) → enter it → choose the **Free** plan → at your registrar replace the nameservers with the two Cloudflare gives you. Wait until the domain shows **Active** (minutes to a few hours).
3. **No domain?** Buy one from Cloudflare (dashboard → **Domain Registration** → *Register Domains*, sold at cost) or from any registrar, then do step 2. Without a domain a permanent link is not possible; use the quick tunnel.

### B2 · Create the tunnel (easiest: dashboard method, no config files)

1. Dashboard left menu → **Zero Trust** (the first time it asks for a team name and the Free plan; it may ask for a payment method, but the free plan is not charged).
2. **Networks → Tunnels** (called *Connectors* in newer dashboards) → **Create a tunnel** → type **Cloudflared** → name it e.g. `mypc` → Save.
3. Choose **Windows**. Cloudflare shows an install command containing a long token. Open **PowerShell as Administrator** and run exactly the command shown, which looks like:

   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared.exe service install <LONG-TOKEN-FROM-DASHBOARD>
   ```

   If `cloudflared` is not recognised right after installing, open a new Administrator PowerShell. Treat the token like a password: do not paste it in chats or commit it.
4. Back in the dashboard the connector should show **Connected**. Click **Next**.
5. **Add a public hostname:**
   - Subdomain: `pc` (or any name), Domain: pick your domain, Path: leave empty
   - Service **Type: HTTP**, **URL: `localhost:8888`**
   - Save.
6. On the phone open `https://pc.example.com` (your hostname), enter the app token and connect. The tunnel now starts automatically with Windows; the server (`start.ps1`) must also be running.

WebSockets (live screen and input) work through the tunnel by default; nothing extra to enable.

<details>
<summary><b>B2 alternative · command-line method</b></summary>

```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel login                         # opens a browser; pick your domain
cloudflared tunnel create mypc                   # prints a <tunnel-id> and a credentials .json path
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

Test with `cloudflared tunnel run mypc`. To run at startup: `cloudflared service install`. The Windows service runs as SYSTEM and looks in `C:\Windows\System32\config\systemprofile\.cloudflared\`; if it does not start, copy `config.yml` and the `.json` there and update `credentials-file` to that path. (The dashboard method above avoids this.)

</details>

---

## C · Protect the public link with Cloudflare Access

A permanent public hostname is reachable by anyone on the internet; only the token and the lockout stand in the way. **Access** adds a login in front. Recommended for B.

1. Zero Trust → **Access → Applications** → **Add an application** → **Self-hosted**.
2. Application name `PC`, **Application domain** = your hostname (`pc.example.com`).
3. Add a policy: Action **Allow**, rule **Emails** = your own email address (add nothing else). Login method **One-time PIN** is enabled by default.
4. Save. Opening the link in a browser now asks for your email, then a code Cloudflare emails you, and only then shows the app's token screen.

> [!WARNING]
> **Limitation:** the Android app cannot complete that browser login, so with Access enabled the Android app is blocked (the browser works). Options: use the browser with Access; or use the Android app over Tailscale or Wi-Fi instead; or create a *Service Token* policy (Access → Service credentials), which needs the app to send `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers (not built into the app yet).

---

## Using the link

- **Phone browser:** open `https://pc.example.com`, enter the token, **Start screen**.
- **Android app:** *PC URL* = `https://pc.example.com`, API token = the `.env` token.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `502 Bad gateway` | `start.ps1` is not running, or the hostname's service URL is not `http://localhost:8888` |
| Error 1033 / tunnel not found | The `cloudflared` service is not running: in an Administrator PowerShell run `Get-Service cloudflared` / `Start-Service cloudflared` |
| Connector shows *Inactive* | The PC is offline or the service stopped; restart it |
| Hostname does not resolve | DNS record missing; the public hostname must exist in the dashboard and the domain must be **Active** |
| Access login loops / app blocked | See the Access limitation above |
| Want to stop access | Stop the service (`Stop-Service cloudflared`) or delete the public hostname/tunnel in the dashboard |

Dashboard menu names change from time to time; if a label differs, look for *Zero Trust → Networks → Tunnels* and *Access → Applications*.

---

## বাংলা সারসংক্ষেপ (স্থায়ী লিংক)

1. Cloudflare-এ আপনার domain যোগ করুন, status **Active** হওয়া পর্যন্ত অপেক্ষা করুন (domain না থাকলে স্থায়ী লিংক হবে না)।
2. Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared > নাম `mypc` > Windows বেছে নিন।
3. Dashboard যে `cloudflared.exe service install <token>` command দেখায়, **Administrator PowerShell**-এ সেটা চালান।
4. Public hostname যোগ করুন: subdomain `pc`, domain আপনারটা, Type **HTTP**, URL **`localhost:8888`**।
5. ফোনে `https://pc.আপনার-domain` খুলুন, token দিন। এই লিংক আর বদলাবে না, PC চালু হলেই tunnel আপনা-আপনি চালু হবে (শুধু `start.ps1` চালু রাখতে হবে)।
6. নিরাপত্তার জন্য Access > Applications থেকে শুধু আপনার email-কে অনুমতি দিন। (Access চালু থাকলে Android app ব্লক হবে, শুধু browser চলবে।)
