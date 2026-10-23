# Windows quick start

Run the agent on Windows and connect the Android app.

## 1. Get the code

```powershell
cd $HOME
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
```

If the folder already exists, update it instead:

```powershell
cd $HOME\remote-pc-control
git pull origin main
```

If `git pull` stops because of local changes or a stash conflict, run `git status`. Files containing `<<<<<<<` markers must be restored before the agent can start:

```powershell
git restore --staged --worktree --source=HEAD -- <conflicted file>
```

## 2. Set up

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

This creates `.venv`, installs the Python packages, builds the dashboard and creates `.env` with a generated access token. The token is printed once; save it.

Re-running the script is safe: packages are reinstalled only when `pyproject.toml` changes, and the dashboard is rebuilt only when its sources change. Use `-Force` to redo everything.

## 3. Check or change the access token

The agent refuses to start unless `.env` contains `REMOTE_PC_TOKEN` with at least 4 characters. A longer token is safer; the generated one has 64 characters.

```powershell
Get-Content .env | Select-String REMOTE_PC_TOKEN    # show the current token
.\scripts\set-password.ps1                           # choose your own (4+ characters, no spaces)
```

Anyone who has the token can control your PC. `.env` is git-ignored; never commit it.

## 4. Start the agent

```powershell
.\scripts\start.ps1
```

Expected output:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8888
```

Stop it with `Ctrl+C`. To start it automatically at sign-in, see [Start with Windows](../README.md#start-with-windows).

## 5. Connect the Android app

1. Install the latest APK from the repository's **Releases** page (`RemotePCControl-Android-android-build-<N>.apk`). Allow *Install unknown apps* if asked.
2. Find the PC's IPv4 address with `ipconfig`, for example `192.168.x.x`.
3. In the app, enter `http://<PC_IP>:8888` and the token.
4. The phone and PC must be on the same Wi-Fi network. For access from outside, use Tailscale or see [CLOUDFLARE.md](CLOUDFLARE.md).
5. If the app cannot connect, allow the port in Windows Firewall (administrator PowerShell):
   ```powershell
   New-NetFirewallRule -DisplayName "RemotePCControl" -Direction Inbound -Protocol TCP -LocalPort 8888 -Action Allow -Profile Private
   ```

## 6. Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Set REMOTE_PC_TOKEN in .env` | The token is missing, still the `replace-...` placeholder, or shorter than 4 characters. Run `.\scripts\set-password.ps1`. |
| `SyntaxError ... <<<<<<<` in a `.py` file | A merge or stash conflict left markers in the file. Restore it with `git restore` as shown in step 1. |
| App cannot reach the PC | Check that both devices are on the same Wi-Fi, the IP and port 8888 are correct, the firewall rule exists and the agent is running. |
