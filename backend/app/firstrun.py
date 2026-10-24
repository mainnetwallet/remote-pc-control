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


def _addresses():
    found = set()
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."): found.add(ip)
    except OSError:
        pass
    return sorted(found, key=lambda ip: (not ip.startswith("100."), ip))   # Tailscale (100.x) first


def _message_box(title, text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40 | 0x40000)   # information icon, always on top
    except Exception:
        print(text)


def _notify(title, text, wait=False):
    t = threading.Thread(target=_message_box, args=(title, text), daemon=not wait)
    t.start()
    if wait: t.join()


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


def already_running(port) -> bool:
    """Packaged exe only: True (and a message) when another copy already serves this port."""
    if not frozen():
        return False
    try:
        socket.create_connection(("127.0.0.1", int(port)), timeout=1).close()
    except OSError:
        return False
    _notify("Remote PC Control", "Remote PC Control is already running on this PC.", wait=True)
    return True


def announce(port):
    """First start only: show the access token once, so it can be typed into the phone app."""
    if not _new_token:
        return
    urls = "\n".join(f"http://{ip}:{port}" for ip in _addresses()) or f"http://<this PC's address>:{port}"
    _notify("Remote PC Control is ready",
            f"Enter this in the phone app.\n\nPC address (Tailscale address starts with 100.):\n{urls}\n\n"
            f"Access token:\n{_new_token}\n\nThe token is saved in:\n{data_dir() / '.env'}")
