# Quick start: run the agent on Windows and connect the Android app

## 1. Get the code

```powershell
cd $HOME
git clone https://github.com/mainnetwallet/remote-pc-control.git
cd remote-pc-control
```

Already cloned? Update it instead:

```powershell
cd $HOME\remote-pc-control
git pull origin main
```

If `git pull` stops because of local changes or a stash conflict, check `git status`.
Files with `<<<<<<<` markers must be restored before the agent can start:

```powershell
git restore --staged --worktree --source=HEAD -- <conflicted file>
```

## 2. Set up

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

This creates `.venv`, installs the Python packages and builds the dashboard.

Re-running it is safe and fast: packages are only reinstalled when `pyproject.toml` changes, and the dashboard is only rebuilt when its sources change. Use `.\scripts\setup.ps1 -Force` to redo everything.

## 3. Create the API token

The agent refuses to start unless `.env` contains a unique `REMOTE_PC_TOKEN` of at least 32 bytes.

```powershell
cp .env.example .env

$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
(Get-Content .env) -replace '^REMOTE_PC_TOKEN=.*', "REMOTE_PC_TOKEN=$token" | Set-Content .env

$token.Length   # must print 64
$token          # enter this in the phone app
```

Keep the token private: anyone who has it can control your PC. `.env` is git-ignored; never commit it.

## 4. Start the agent

```powershell
.\scripts\start.ps1
```

You should see:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8788
```

Stop it with `Ctrl+C`.

## 5. Connect the Android app

1. Install the latest APK from the repository's **Releases** page
   (`RemotePCControl-Android-android-build-<N>.apk`). Allow "Install unknown apps" if asked.
2. Find the PC's IP address:
   ```powershell
   ipconfig
   ```
   Use the **IPv4 Address**, for example `192.168.x.x`.
3. In the app enter `http://<PC_IP>:8788` and the token from step 3.
4. The phone and the PC must be on the same Wi-Fi network. For access from outside, see
   [CLOUDFLARE.md](CLOUDFLARE.md) or use Tailscale.
5. If the app cannot connect, allow the port in Windows Firewall (Administrator PowerShell):
   ```powershell
   New-NetFirewallRule -DisplayName "RemotePCControl" -Direction Inbound -Protocol TCP -LocalPort 8788 -Action Allow -Profile Private
   ```

## 6. Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Set a unique REMOTE_PC_TOKEN (32+ bytes) in .env` | The token is missing, still the placeholder, or shorter than 32 bytes. Redo step 3 and check `$token.Length` prints 64. |
| `SyntaxError ... <<<<<<<` in a `.py` file | A merge or stash conflict left markers in the file. Restore it with `git restore` as shown in step 1. |
| App cannot reach the PC | Same Wi-Fi? Correct IP and port 8788? Firewall rule added? Agent still running? |
