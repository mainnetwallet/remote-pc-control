"""Windows management for the control panel: autostart task, firewall rules, restart. Needs the agent to run as
Administrator (the installed exe does). Everything runs through PowerShell with fixed scripts; the only values put
into a script are paths, which are quoted."""
import json, os, platform, subprocess, sys, threading
from pathlib import Path
from .paths import frozen

TASK = "RemotePCControl"
LOCK_TASK = "RemotePCControlLock"
FW_TAILSCALE = "RemotePCControl Tailscale only"
FW_LAN = "RemotePCControl LAN"
IS_WINDOWS = platform.system() == "Windows"
RESTART_WITH_WINDOW = False   # set by run_agent when this copy was opened by the user (it shows the app window)
_NO_WINDOW = 0x08000000


class AdminError(RuntimeError): pass


def q(value) -> str:
    """PowerShell single-quoted string."""
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(script: str, timeout: int = 60) -> str:
    if not IS_WINDOWS: raise AdminError("This works on Windows only")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                           capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired: raise AdminError("Windows did not answer in time") from None
    except OSError as e: raise AdminError(f"Could not run PowerShell: {e}") from None
    if r.returncode != 0: raise AdminError((r.stderr or r.stdout or "PowerShell failed").strip()[:400])
    return r.stdout.strip()


def exe_path() -> Path: return Path(sys.executable).resolve()


def install_dir() -> Path: return exe_path().parent


def register_script() -> Path: return install_dir() / "register-installed-task.ps1"


_STATUS_PS = f"""
$ErrorActionPreference = 'SilentlyContinue'
function T($n) {{ $t = Get-ScheduledTask -TaskName $n; if ($t) {{ @{{exists=$true; state=[string]$t.State; admin=([string]$t.Principal.RunLevel -eq 'Highest')}} }} else {{ @{{exists=$false}} }} }}
function F($n) {{ @{{exists=[bool](Get-NetFirewallRule -DisplayName $n)}} }}
@{{autostart=(T {q(TASK)}); lock_task=(T {q(LOCK_TASK)}); fw_tailscale=(F {q(FW_TAILSCALE)}); fw_lan=(F {q(FW_LAN)})}} | ConvertTo-Json -Compress -Depth 4
"""


def system_status() -> dict:
    if not IS_WINDOWS: return {"supported": False}
    out = json.loads(run_ps(_STATUS_PS) or "{}")
    out["supported"] = True
    out["task_tools"] = frozen() and register_script().exists()
    return out


def _task(kind: str, enabled: bool) -> None:
    if not (frozen() and register_script().exists()):
        raise AdminError("Only available in the installed Remote PC Control (use the scripts when running from source)")
    args = f"-File {q(register_script())} -Kind {kind} -Exe {q(exe_path())} -NoFirewall -NoStart"
    if not enabled: args += " -Remove"
    run_ps(f"& {q('powershell.exe')} -NoProfile -ExecutionPolicy Bypass {args}; if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}")


def set_autostart(enabled: bool) -> None: _task("agent", enabled)


def set_lock_task(enabled: bool) -> None:
    _task("lock", enabled)
    if enabled: run_ps(f"Start-ScheduledTask -TaskName {q(LOCK_TASK)}")
    else: run_ps(f"Stop-ScheduledTask -TaskName {q(LOCK_TASK)} -ErrorAction SilentlyContinue")


def set_firewall(rule: str, enabled: bool) -> None:
    if rule == "tailscale": name, extra = FW_TAILSCALE, '-RemoteAddress "100.64.0.0/10" -Profile Any'
    elif rule == "lan": name, extra = FW_LAN, "-RemoteAddress LocalSubnet -Profile Private"
    else: raise AdminError("Unknown firewall rule")
    if enabled:
        run_ps(f"if (-not (Get-NetFirewallRule -DisplayName {q(name)} -ErrorAction SilentlyContinue)) "
               f"{{ New-NetFirewallRule -DisplayName {q(name)} -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8888 {extra} | Out-Null }}")
    else:
        run_ps(f"Remove-NetFirewallRule -DisplayName {q(name)} -ErrorAction SilentlyContinue")


def _exit_soon(code: int = 0) -> None:
    threading.Timer(0.7, lambda: os._exit(code)).start()


def quit_agent() -> None: _exit_soon()


def restart_agent() -> None:
    """Start a new copy a few seconds after this one has ended (so the port is free), then end this one."""
    if not (IS_WINDOWS and frozen()): raise AdminError("Restart is available in the installed program only")
    exe = str(exe_path())
    flag = "" if RESTART_WITH_WINDOW else " --background"   # opened by the user: the new copy shows the window again
    subprocess.Popen(["cmd.exe", "/c", f'timeout /t 4 /nobreak >nul & start "" "{exe}"{flag}'],
                     creationflags=_NO_WINDOW | 0x00000008, close_fds=True)   # DETACHED_PROCESS
    _exit_soon()
