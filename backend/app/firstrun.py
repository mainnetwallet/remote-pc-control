"""Packaged-exe start-up helpers: nothing here runs when the agent is started from source.
Imported by run_agent.py BEFORE app.config, because the settings are read from .env at import time."""
import secrets, socket, sys
from .paths import data_dir, frozen

_new_token = None

_ENV = """REMOTE_PC_TOKEN={token}
REMOTE_PC_HOST=0.0.0.0
REMOTE_PC_PORT=8888
REMOTE_PC_FPS=auto
REMOTE_PC_JPEG_QUALITY=55
"""


def _redirect_output(folder):
    # The exe has no console window, so stdout/stderr do not exist; uvicorn needs them. Write them to agent.log.
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_file = folder / "agent.log"
    try:
        if log_file.exists() and log_file.stat().st_size > 1_000_000:
            log_file.unlink()
    except OSError:
        pass
    log = open(log_file, "a", buffering=1, encoding="utf-8")
    if sys.stdout is None: sys.stdout = log
    if sys.stderr is None: sys.stderr = log


def ensure_uac_configured():
    """Ensure UAC does not switch to Secure Desktop and auto-elevates for admins,
    so remote screens and mouse inputs are never blocked."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "PromptOnSecureDesktop", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "ConsentPromptBehaviorAdmin", 0, winreg.REG_DWORD, 0)
    except Exception:
        pass


def prepare():
    """Create the data folder and, on the very first start, a .env with a random access token."""
    global _new_token
    ensure_uac_configured()
    if not frozen():
        return
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    _redirect_output(folder)
    env = folder / ".env"
    if not env.exists():
        _new_token = secrets.token_urlsafe(48)
        env.write_text(_ENV.format(token=_new_token), encoding="ascii")


def wait_for_port(port, seconds=30) -> bool:
    import time
    for _ in range(int(seconds * 2)):
        try: socket.create_connection(("127.0.0.1", int(port)), timeout=1).close(); return True
        except OSError: time.sleep(0.5)
    return False


def _listener(port):
    """The process that listens on this port (psutil), or None."""
    try:
        import psutil
        for c in psutil.net_connections(kind="tcp"):
            if c.status == "LISTEN" and c.laddr and c.laddr.port == int(port) and c.pid:
                return psutil.Process(c.pid)
    except Exception:
        pass
    return None


def _health(port):
    import json, urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/api/health", timeout=2) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def classify(listening, health):
    """none = port free, current = this version already runs, old = an older Remote PC Control (no control panel),
    other = some other program."""
    if not listening: return "none"
    if isinstance(health, dict) and health.get("service") == "remote-pc-control":
        return "current" if health.get("panel") else "old"
    return "other"


def server_state(port) -> str:
    """Packaged exe only (source runs always report "none")."""
    if not frozen(): return "none"
    try: socket.create_connection(("127.0.0.1", int(port)), timeout=1).close()
    except OSError: return "none"
    return classify(True, _health(port))


def stop_old_server(port) -> bool:
    """End an older Remote PC Control that still holds the port (for example the PowerShell/source version), so this
    version can start. Only used when /api/health proved that it is a Remote PC Control."""
    import time
    proc = _listener(port)
    try:
        if proc is not None:
            for child in proc.children(recursive=True): child.kill()
            proc.kill()
    except Exception as e:
        print("Could not stop the old server:", e)
    for _ in range(40):
        try: socket.create_connection(("127.0.0.1", int(port)), timeout=0.5).close()
        except OSError: return True
        time.sleep(0.5)
    return False


def message(text, title="Remote PC Control"):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40 | 0x40000)
    except Exception:
        print(text)


def first_run() -> bool:
    return _new_token is not None
