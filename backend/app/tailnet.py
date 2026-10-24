"""Built-in Tailscale: runs tsbridge.exe (a small Tailscale node shipped with the app) so the PC does not need Tailscale
installed. The phone still needs the Tailscale app, signed in to the same account. Turned on/off from the app window;
the choice is remembered and the bridge starts again with the server."""
import json, re, shutil, socket, subprocess, sys, threading, time
from pathlib import Path
from .paths import data_dir, frozen
from .winadmin import IS_WINDOWS, _NO_WINDOW

_lock = threading.Lock()
_proc = None
_started = 0.0


def base_dir() -> Path: return data_dir() / "tailscale"


def _flag() -> Path: return base_dir() / "enabled"


def _status_file() -> Path: return base_dir() / "status.json"


def find_bridge():
    names = ("tsbridge.exe", "tsbridge") if IS_WINDOWS else ("tsbridge",)
    here = Path(sys.executable).resolve().parent if frozen() else Path(__file__).resolve().parents[2] / "tsbridge"
    for n in names:
        if (here / n).exists(): return str(here / n)
    return shutil.which("tsbridge")


def device_name() -> str:
    n = re.sub(r"[^a-z0-9-]+", "-", socket.gethostname().lower()).strip("-")[:40] or "pc"
    return "remote-" + n


def _running() -> bool: return _proc is not None and _proc.poll() is None


def enabled() -> bool: return _flag().exists()


def _read_status() -> dict:
    try: return json.loads(_status_file().read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}


def status() -> dict:
    with _lock:
        run = _running()
        s = _read_status() if run else {}
        fresh = bool(s) and time.time() - float(s.get("updated") or 0) < 15
        state = (s.get("state") or "Starting") if run else "Off"
        if run and s and not fresh: state = "Starting"
        return {"supported": IS_WINDOWS, "available": bool(find_bridge()), "enabled": enabled(), "running": run, "state": state,
                "auth_url": (s.get("auth_url") or "") if run and fresh else "", "ips": (s.get("ips") or []) if run and fresh else [],
                "name": (s.get("name") or "").rstrip(".") if run and fresh else "",
                "error": (s.get("error") or "") if run and fresh else ""}


def start(port: int) -> None:
    global _proc, _started
    exe = find_bridge()
    if not exe: raise RuntimeError("The built-in Tailscale part (tsbridge.exe) is missing. Install the newest Remote PC Control setup.")
    with _lock:
        if _running(): return
        d = base_dir(); d.mkdir(parents=True, exist_ok=True)
        try: _status_file().unlink()
        except OSError: pass
        log = open(d / "tailscale.log", "ab")
        _proc = subprocess.Popen([exe, "-state", str(d / "state"), "-status", str(_status_file()), "-port", str(int(port)), "-hostname", device_name()],
                                 stdin=subprocess.PIPE, stdout=log, stderr=log, creationflags=_NO_WINDOW if IS_WINDOWS else 0)
        _started = time.time()


def stop() -> None:
    global _proc
    with _lock:
        p, _proc = _proc, None
    if p and p.poll() is None:
        try: p.stdin.close()
        except OSError: pass
        p.terminate()
        try: p.wait(5)
        except subprocess.TimeoutExpired: p.kill()


def set_enabled(on: bool, port: int) -> dict:
    d = base_dir(); d.mkdir(parents=True, exist_ok=True)
    if on:
        start(port)   # fails first when the bridge is missing, so the flag is not left on
        _flag().write_text("1", encoding="ascii")
    else:
        try: _flag().unlink()
        except OSError: pass
        stop()
    return status()


def autostart(port: int) -> None:
    """Called when the server starts: bring the bridge back if the user turned it on before."""
    if enabled() and find_bridge():
        try: start(port)
        except Exception as e: print("Built-in Tailscale could not start:", e)
