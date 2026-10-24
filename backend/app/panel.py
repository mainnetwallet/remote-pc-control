"""Control panel API: what the desktop app window uses to do everything the PowerShell scripts do (there is no web page).
Safety: it only answers requests that come from this PC itself (never from the phone, Tailscale, LAN or a Cloudflare
tunnel), and every API call also needs the access token."""
import os, re, secrets, socket
from collections import deque
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from . import envfile, monitor, pinlock, tailnet, tunnel, winadmin
from .config import settings
from .paths import data_dir, frozen
from .security import LOOPBACK, require_auth

PROXY_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-forwarded-host", "forwarded", "x-real-ip")
_HOST = re.compile(r"^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", re.I)
LOG_FILES = {"agent": "agent.log", "lock": "lock_overlay.log"}


async def local_only(request: Request):
    peer = request.client.host if request.client else ""
    if peer not in LOOPBACK or not _HOST.match(request.headers.get("host", "")) or any(h in request.headers for h in PROXY_HEADERS):
        raise HTTPException(403, "The control panel works on the PC itself only: use the Remote PC Control app on this PC")


router = APIRouter()
api = APIRouter(prefix="/panel/api", dependencies=[Depends(local_only), Depends(require_auth)])


def env_path() -> Path: return data_dir() / ".env"


def addresses():
    found = set()
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith(("127.", "169.254.")): found.add(ip)
    except OSError: pass
    try: found.update(ip for ip in tailnet.status()["ips"] if "." in ip)   # address of the built-in Tailscale
    except Exception: pass
    return [{"ip": ip, "kind": "tailscale" if ip.startswith("100.") else "lan"} for ip in sorted(found, key=lambda i: (not i.startswith("100."), i))]


def read_tail(name: str, lines: int = 200) -> str:
    if name not in LOG_FILES: raise HTTPException(404, "Unknown log")
    base = data_dir() if name == "agent" else Path(os.getenv("LOCALAPPDATA") or data_dir()) / "RemotePCControl"
    try:
        with open(base / LOG_FILES[name], encoding="utf-8", errors="replace") as fh: return "".join(deque(fh, maxlen=lines))
    except OSError: return ""


def fail(e: Exception): raise HTTPException(400, str(e))


@api.get("/state")
def state():
    saved = envfile.read(env_path())
    fields = [{**f, "value": saved.get(f["key"], f["default"])} for f in envfile.FIELDS]
    try: lock = pinlock.status()
    except Exception as e: lock = {"error": str(e)}
    return {"hostname": socket.gethostname(), "port": settings.port, "elevated": monitor.is_elevated(), "installed": frozen(),
            "addresses": addresses(), "tailnet": tailnet.status(), "fields": fields, "lock": lock, "tunnel": tunnel.status(), "env_file": str(env_path())}


@api.get("/system")
def system():
    try: return winadmin.system_status()
    except winadmin.AdminError as e: fail(e)


@api.get("/token")
def get_token(): return {"token": settings.token}


class TokenBody(BaseModel): token: str
class SettingsBody(BaseModel): values: dict[str, str | int | bool]
class EnabledBody(BaseModel): enabled: bool
class FirewallBody(BaseModel): rule: str; enabled: bool
class PinBody(BaseModel): pin: str
class LockBody(BaseModel): locked: bool


@api.post("/token")
def set_token(body: TokenBody):
    try: token = envfile.validate_token(body.token)
    except ValueError as e: fail(e)
    envfile.update(env_path(), {"REMOTE_PC_TOKEN": token})
    settings.token = token   # live: the phone must use the new password from now on
    return {"ok": True}


@api.post("/token/random")
def random_token():
    token = secrets.token_urlsafe(32)
    envfile.update(env_path(), {"REMOTE_PC_TOKEN": token})
    settings.token = token
    return {"ok": True, "token": token}


@api.post("/settings")
def save_settings(body: SettingsBody):
    try: clean = {k: envfile.validate_setting(k, v) for k, v in body.values.items()}
    except ValueError as e: fail(e)
    envfile.update(env_path(), clean)
    return {"ok": True, "restart_needed": True}


def _admin(fn, *args):
    try: fn(*args)
    except winadmin.AdminError as e: fail(e)
    return {"ok": True}


@api.post("/autostart")
def autostart(body: EnabledBody): return _admin(winadmin.set_autostart, body.enabled)
@api.post("/lock-task")
def lock_task(body: EnabledBody): return _admin(winadmin.set_lock_task, body.enabled)
@api.post("/firewall")
def firewall(body: FirewallBody): return _admin(winadmin.set_firewall, body.rule, body.enabled)


@api.post("/pin")
def set_pin(body: PinBody):
    try: pinlock.set_pin(body.pin)
    except ValueError as e: fail(e)
    return {"ok": True}


@api.post("/lock")
def lock(body: LockBody):
    try: pinlock.lock() if body.locked else pinlock.unlock()
    except ValueError as e: fail(e)
    return {"ok": True}


@api.get("/tailscale")
def tailscale_status(): return tailnet.status()


@api.post("/tailscale/{action}")
def tailscale_action(action: str):
    if action not in ("enable", "disable"): raise HTTPException(404, "Unknown action")
    try: return tailnet.set_enabled(action == "enable", settings.port)
    except RuntimeError as e: fail(e)


@api.get("/tunnel")
def tunnel_status(): return tunnel.status()


@api.post("/tunnel/{action}")
def tunnel_action(action: str):
    try:
        if action == "install": tunnel.install()
        elif action == "start": tunnel.start(settings.port)
        elif action == "stop": tunnel.stop()
        else: raise HTTPException(404, "Unknown action")
    except RuntimeError as e: fail(e)
    return tunnel.status()


@api.get("/logs/{name}")
def logs(name: str): return {"text": read_tail(name)}


@api.post("/restart")
def restart():
    tunnel.stop()
    return _admin(winadmin.restart_agent)


@api.post("/quit")
def quit_agent():
    tunnel.stop(); winadmin.quit_agent(); return {"ok": True}


router.include_router(api)
