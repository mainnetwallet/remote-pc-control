"""Packaged-exe start-up helpers: nothing here runs when the agent is started from source.
Imported by run_agent.py BEFORE app.config, because the settings are read from .env at import time."""
import secrets, socket, sys, threading
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


def prepare():
    """Create the data folder and, on the very first start, a .env with a random access token."""
    global _new_token
    if not frozen():
        return
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    _redirect_output(folder)
    env = folder / ".env"
    if not env.exists():
        _new_token = secrets.token_urlsafe(48)
        env.write_text(_ENV.format(token=_new_token), encoding="ascii")


def _open_url(url):
    """This program runs as administrator. A browser started from an elevated program often fails to open (it cannot
    hand the page to the normal browser window), so on Windows the page is opened through explorer.exe, which opens it
    as the signed-in user."""
    import subprocess, webbrowser
    if sys.platform == "win32":
        try:
            subprocess.Popen(["explorer.exe", url], creationflags=0x08000000)
            return
        except OSError as e:
            print("explorer.exe could not open the page:", e)
    try: webbrowser.open(url)
    except Exception as e: print("Could not open the browser:", e)


def wait_for_port(port, seconds=30) -> bool:
    import time
    for _ in range(int(seconds * 2)):
        try: socket.create_connection(("127.0.0.1", int(port)), timeout=1).close(); return True
        except OSError: time.sleep(0.5)
    return False


def open_panel(port, token, wait_for_server=True):
    """Open the control panel in the default browser (the token travels in the #hash: it never reaches the server)."""
    url = f"http://127.0.0.1:{int(port)}/panel#{token}"

    def work():
        import time
        if wait_for_server:
            for _ in range(60):
                try:
                    socket.create_connection(("127.0.0.1", int(port)), timeout=1).close(); break
                except OSError: time.sleep(0.5)
        _open_url(url)

    threading.Thread(target=work, daemon=True).start()


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
