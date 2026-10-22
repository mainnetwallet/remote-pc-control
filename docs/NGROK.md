# ngrok setup: a permanent free `https` link

ngrok gives every free account **one static domain** (for example `your-name.ngrok-free.dev`).
The link does not change when you restart the tunnel, so you enter it in the Android app once.
No domain purchase and no port-forwarding are needed.

> Free-plan limits (check the ngrok dashboard for the current numbers): about 1 GB of bandwidth
> per month, 20,000 HTTP requests per month and 3 concurrent endpoints. The live screen sends frames
> continuously, so the bandwidth can run out quickly. At home use the LAN address
> (`http://<PC_IP>:8888`) and keep ngrok for when you are away.
>
> A free HTTP endpoint can show a browser warning page ("Visit Site"). Click through it in a browser.

Compare with the other ways to connect in the main [README](../README.md) and [CLOUDFLARE.md](CLOUDFLARE.md)
(a permanent Cloudflare link needs your own domain).

## 1. Create an ngrok account and get the two values you need

1. Sign up (free): <https://dashboard.ngrok.com/signup>
2. **Authtoken**: <https://dashboard.ngrok.com/get-started/your-authtoken>
3. **Your static domain**: <https://dashboard.ngrok.com/domains> (looks like `something.ngrok-free.dev`).

The authtoken works like a password. Never paste it in a chat, an issue or a commit. If it leaks, press
**Reset** on the authtoken page and run step 3 again with the new value.

## 2. Install ngrok on the PC

```powershell
winget install ngrok.ngrok
```

Close PowerShell and open a new window so the `ngrok` command is found, then check the version:

```powershell
ngrok version
```

Your account needs a recent agent. If you see `ERR_NGROK_121` / "ngrok-agent version ... is too old", update:

```powershell
ngrok update
```

If `ngrok update` does not work, download the current Windows zip from <https://ngrok.com/download>,
extract it, and replace the old `ngrok.exe` (`(Get-Command ngrok).Source` shows where the old one is).

## 3. Save the authtoken (once)

```powershell
ngrok config add-authtoken <YOUR_AUTHTOKEN>
```

Expected: `Authtoken saved to configuration file: ...ngrok.yml`.

## 4. Start the server and the tunnel

Window 1, the Remote PC Control server:

```powershell
cd $HOME\remote-pc-control
.\scripts\start.ps1
```

Window 2, the tunnel (use **your own** domain from step 1):

```powershell
ngrok http --url=https://your-name.ngrok-free.dev 8888
```

Older agents do not know `--url`; use `--domain` instead:

```powershell
ngrok http --domain=your-name.ngrok-free.dev 8888
```

ngrok then shows a status screen. It is output, not something to type:

```
Session Status   online
Forwarding       https://your-name.ngrok-free.dev -> http://localhost:8888
```

Keep both windows open. `Ctrl+C` stops a window.

## 5. Test and connect the phone

1. Open `https://your-name.ngrok-free.dev/api/health` in a browser. `{"ok":true,...}` means the server and the tunnel work.
2. In the Android app set **PC URL** to `https://your-name.ngrok-free.dev` (no port) and the API token from your `.env` (`REMOTE_PC_TOKEN`).

## Troubleshooting

| Problem | Fix |
|---|---|
| `ngrok` is not recognized | ngrok is not installed, or the PowerShell window was opened before installing. Install it and open a new window. |
| `unknown flag: --url` | Old agent. Run `ngrok update`, or use `--domain=` instead of `--url=`. |
| `ERR_NGROK_121` agent too old | Run `ngrok update` (see step 2). |
| `Forwarding : The term 'Forwarding' is not recognized` | You pasted ngrok's output line as a command. Only type the `ngrok http ...` command. |
| `502` / "failed to connect to localhost:8888" | `start.ps1` is not running. Start the server first. |
| `ERR_NGROK_334` (endpoint already online) | The tunnel is already running in another window or on another machine. Stop it first. |
| App cannot connect over ngrok | Check the browser test in step 5 first. Use `https://` and no `:8888` in the app URL. |
| Works at first, then stops | The monthly free bandwidth may be used up (see the dashboard). Use the LAN address meanwhile. |

## Security

- The link is public: anyone who knows it can reach the login screen. Only the API token protects the PC, so keep the
  token long and private and do not share the link.
- Do not commit `.env` or the ngrok config file.
