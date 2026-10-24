"""
Persistent PIN lock.

One JSON file (lock_state.json, in the project root) is the single source of truth for
whether the PC is "locked". It is read and written by two independent things:

  1. This FastAPI backend (lock/unlock/set-pin over the authenticated app API).
  2. scripts/lock_overlay.py, a separate always-running process that shows a full-screen
     PIN screen whenever the file says locked=True -- including right after Windows boots,
     before this server has even started.

Because the state lives in a file instead of memory, it survives a restart of the PC and a
restart of this server. Nothing in this module ever locks or unlocks on its own: the state
only changes when lock(), unlock(), or a correct PIN is given to unlock_with_pin().
"""
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path

STATE_PATH = Path(os.getenv("REMOTE_PC_LOCK_STATE", str(Path(__file__).resolve().parents[2] / "lock_state.json")))

MIN_PIN_LEN = 4
MAX_PIN_LEN = 12
MAX_PIN_FAILS = 5          # wrong PINs allowed at the physical PC before a cooldown
PIN_LOCKOUT_SECONDS = 60

_lock = threading.Lock()

_DEFAULT_STATE = {
    "locked": False,
    "pin_hash": "",
    "pin_salt": "",
    "fail_count": 0,
    "lockout_until": 0.0,   # time.time() value; 0 = not locked out
}


def _load() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = dict(_DEFAULT_STATE)
        state.update({k: data[k] for k in _DEFAULT_STATE if k in data})
        return state
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(_DEFAULT_STATE)


def _save(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)   # atomic on both Windows and POSIX


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()


def status() -> dict:
    with _lock:
        s = _load()
        return {"locked": s["locked"], "pin_set": bool(s["pin_hash"])}


def set_pin(pin: str) -> None:
    pin = pin.strip()
    if not pin.isdigit():
        raise ValueError("PIN must contain digits only")
    if not (MIN_PIN_LEN <= len(pin) <= MAX_PIN_LEN):
        raise ValueError(f"PIN must be {MIN_PIN_LEN}-{MAX_PIN_LEN} digits")
    with _lock:
        s = _load()
        salt = secrets.token_hex(16)
        s["pin_salt"] = salt
        s["pin_hash"] = _hash_pin(pin, salt)
        s["fail_count"] = 0
        s["lockout_until"] = 0.0
        _save(s)


def lock() -> None:
    with _lock:
        s = _load()
        if not s["pin_hash"]:
            raise ValueError("Set a PIN before locking")
        s["locked"] = True
        _save(s)


def unlock() -> None:
    """Unlock from the app (already authenticated with the access token) -- no PIN needed."""
    with _lock:
        s = _load()
        s["locked"] = False
        s["fail_count"] = 0
        s["lockout_until"] = 0.0
        _save(s)


def pin_lockout_remaining() -> float:
    with _lock:
        s = _load()
        remaining = s["lockout_until"] - time.time()
        return max(0.0, remaining)


def unlock_with_pin(pin: str) -> tuple[bool, str]:
    """
    Used by the local overlay running on the PC itself. Returns (ok, message).
    Independent, file-based fail counter -- so lockouts survive the overlay process restarting.
    """
    with _lock:
        s = _load()
        now = time.time()
        if s["lockout_until"] > now:
            return False, f"Too many attempts. Try again in {int(s['lockout_until'] - now)}s"
        if not s["pin_hash"]:
            return False, "No PIN set"
        ok = secrets.compare_digest(_hash_pin(pin.strip(), s["pin_salt"]), s["pin_hash"])
        if ok:
            s["locked"] = False
            s["fail_count"] = 0
            s["lockout_until"] = 0.0
            _save(s)
            return True, "Unlocked"
        s["fail_count"] += 1
        if s["fail_count"] >= MAX_PIN_FAILS:
            s["lockout_until"] = now + PIN_LOCKOUT_SECONDS
            s["fail_count"] = 0
            _save(s)
            return False, f"Too many attempts. Try again in {PIN_LOCKOUT_SECONDS}s"
        _save(s)
        left = MAX_PIN_FAILS - s["fail_count"]
        return False, f"Wrong PIN ({left} attempt{'s' if left != 1 else ''} left)"
