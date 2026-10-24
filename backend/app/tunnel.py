"""Optional internet link through a free Cloudflare quick tunnel (the same thing scripts/start-tunnel.ps1 does).
The link changes every time the tunnel starts. Anyone with the link still needs the access token."""
import atexit, os, re, shutil, subprocess, threading
from pathlib import Path
from .winadmin import IS_WINDOWS, _NO_WINDOW

_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_lock = threading.Lock()
_proc = None
_url = None
_error = ""
_installing = False
_install_msg = ""


def find_cloudflared():
    found = shutil.which("cloudflared")
    if found: return found
    for base in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)")):
        p = Path(base or "") / "cloudflared" / "cloudflared.exe"
        if base and p.exists(): return str(p)
    local = os.getenv("LOCALAPPDATA")
    if local:
        p = Path(local) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe"
        if p.exists(): return str(p)
    return None


def _running() -> bool: return _proc is not None and _proc.poll() is None


def status() -> dict:
    with _lock:
        return {"supported": IS_WINDOWS, "installed": bool(find_cloudflared()), "installing": _installing,
                "install_message": _install_msg, "running": _running(), "url": _url if _running() else None, "error": _error}


def _read(proc):
    global _url, _error
    for line in proc.stdout:
        m = _URL.search(line)
        if m:
            with _lock: _url = m.group(0)
    with _lock:
        if _proc is proc and _url is None: _error = "The tunnel stopped before it got a link"


def start(port: int) -> None:
    global _proc, _url, _error
    exe = find_cloudflared()
    if not exe: raise RuntimeError("cloudflared is not installed yet")
    with _lock:
        if _running(): return
        _url, _error = None, ""
        _proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{int(port)}"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                 errors="replace", creationflags=_NO_WINDOW if IS_WINDOWS else 0)
        threading.Thread(target=_read, args=(_proc,), daemon=True).start()


def stop() -> None:
    global _proc, _url
    with _lock:
        p, _proc, _url = _proc, None, None
    if p and p.poll() is None:
        p.terminate()
        try: p.wait(5)
        except subprocess.TimeoutExpired: p.kill()


def install() -> None:
    """Install cloudflared with winget (Windows 10/11)."""
    global _installing, _install_msg
    if not IS_WINDOWS: raise RuntimeError("This works on Windows only")
    with _lock:
        if _installing: return
        _installing, _install_msg = True, "Installing cloudflared..."

    def work():
        global _installing, _install_msg
        try:
            r = subprocess.run(["winget", "install", "--id", "Cloudflare.cloudflared", "-e", "--silent",
                                "--accept-source-agreements", "--accept-package-agreements"],
                               capture_output=True, text=True, timeout=600, creationflags=_NO_WINDOW)
            msg = "Installed" if r.returncode == 0 or find_cloudflared() else (r.stdout or r.stderr or "winget failed").strip()[-300:]
        except (OSError, subprocess.TimeoutExpired) as e:
            msg = f"Could not run winget: {e}"
        with _lock: _installing, _install_msg = False, msg

    threading.Thread(target=work, daemon=True).start()


atexit.register(stop)
