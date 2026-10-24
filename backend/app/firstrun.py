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


def already_running(port) -> bool:
    """Packaged exe only: True when another copy already serves this port."""
    if not frozen():
        return False
    try:
        socket.create_connection(("127.0.0.1", int(port)), timeout=1).close()
    except OSError:
        return False
    return True


def first_run() -> bool:
    return _new_token is not None
