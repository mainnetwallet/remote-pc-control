"""
Persistent PIN lock.

One JSON file (lock_state.json) is the single source of truth for whether the PC is
"locked". It is read and written by two independent processes:

  1. This FastAPI backend (lock/unlock/set-pin over the authenticated app API).
  2. lock_overlay.py, a separate always-running process that shows a full-screen PIN
     screen whenever the file says locked=True -- including right after Windows boots,
     before this server has even started.

Because the state lives in a file instead of memory, it survives a restart of the PC and a
restart of this server. Nothing in this module ever locks or unlocks on its own: the state
only changes when lock(), unlock(), or a correct PIN is given to unlock_with_pin().

Canonical location: every process resolves the same absolute path, regardless of its working
directory (see resolve_state_path). Cross-process safety: all reads and writes take an OS-level
file lock, and writes are atomic (temp file + os.replace), so the API and the overlay can never
see a half-written file or overwrite each other's update.

Failure policy: an unreadable/corrupt state file raises StateFileError instead of silently
reading as "unlocked" -- the file is never treated as a reason to unlock.
No PIN, PIN hash or salt is ever logged.
"""
import contextlib
import hashlib
import json
import logging
import os
import secrets
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("remote_pc_control.pinlock")


class StateFileError(RuntimeError):
    """The lock state file exists but cannot be read or written."""


def _project_root() -> Path:
    if getattr(sys, "frozen", False):                      # PyInstaller build: use the exe's folder,
        return Path(sys.executable).resolve().parent       # not the throw-away _MEIPASS temp dir
    return Path(__file__).resolve().parents[2]


def _env_override(root: Path) -> str:
    """REMOTE_PC_LOCK_STATE from the environment, or from the project's .env (the overlay
    does not load .env on its own, so without this the two processes could disagree)."""
    val = os.getenv("REMOTE_PC_LOCK_STATE", "").strip()
    if val:
        return val
    try:
        for line in (root / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("REMOTE_PC_LOCK_STATE="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def resolve_state_path() -> Path:
    root = _project_root()
    override = _env_override(root)
    p = Path(override).expanduser() if override else root / "lock_state.json"
    if not p.is_absolute():
        p = root / p        # relative overrides are relative to the project, never to the cwd
    return p.resolve()


STATE_PATH = resolve_state_path()

MIN_PIN_LEN = 4
MAX_PIN_LEN = 12
MAX_PIN_FAILS = 5          # wrong PINs allowed at the physical PC before a cooldown
PIN_LOCKOUT_SECONDS = 60

_lock = threading.RLock()

_DEFAULT_STATE = {
    "locked": False,
    "pin_hash": "",
    "pin_salt": "",
    "fail_count": 0,
    "lockout_until": 0.0,   # time.time() value; 0 = not locked out
}


# ---- cross-process file lock ---------------------------------------------------------------
@contextlib.contextmanager
def _state_guard(timeout: float = 5.0):
    """Thread lock + OS file lock (msvcrt on Windows, fcntl elsewhere) on <state>.lock."""
    with _lock:
        lock_path = STATE_PATH.with_name(STATE_PATH.name + ".lock")
        try:
            fh = open(lock_path, "a+b")
        except OSError as e:
            raise StateFileError(f"cannot open lock file {lock_path}: {e}") from e
        try:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        fh.seek(0)
                        if fh.read(1) == b"":
                            fh.write(b"0"); fh.flush()
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise StateFileError("timed out waiting for the lock-state file lock")
                    time.sleep(0.02)
            try:
                yield
            finally:
                try:
                    if os.name == "nt":
                        import msvcrt
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            fh.close()


def _load() -> dict:
    """Read the state. Missing file = fresh defaults (never configured). Unreadable or corrupt
    file = StateFileError (never silently 'unlocked')."""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return dict(_DEFAULT_STATE)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log.error("lock state file %s is corrupt: %s", STATE_PATH, type(e).__name__)
        raise StateFileError(f"lock state file is corrupt: {STATE_PATH}") from e
    except OSError as e:
        log.error("cannot read lock state file %s: %s", STATE_PATH, e)
        raise StateFileError(f"cannot read lock state file: {e}") from e
    if not isinstance(data, dict):
        raise StateFileError(f"lock state file has unexpected content: {STATE_PATH}")
    state = dict(_DEFAULT_STATE)
    state.update({k: data[k] for k in _DEFAULT_STATE if k in data})
    return state


def _save(state: dict) -> None:
    tmp = STATE_PATH.with_name(STATE_PATH.name + f".{os.getpid()}.tmp")
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(10):      # Windows: os.replace fails while a reader has the file open
            try:
                os.replace(tmp, STATE_PATH)   # atomic on both Windows and POSIX
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.03)
    except OSError as e:
        log.error("cannot write lock state file %s: %s", STATE_PATH, e)
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise StateFileError(f"cannot write lock state file: {e}") from e


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()


def status() -> dict:
    with _state_guard():
        s = _load()
        return {"locked": bool(s["locked"]), "pin_set": bool(s["pin_hash"])}


def set_pin(pin: str) -> None:
    pin = pin.strip()
    if not (pin.isascii() and pin.isdigit()):
        raise ValueError("PIN must contain digits only")
    if not (MIN_PIN_LEN <= len(pin) <= MAX_PIN_LEN):
        raise ValueError(f"PIN must be {MIN_PIN_LEN}-{MAX_PIN_LEN} digits")
    with _state_guard():
        s = _load()
        salt = secrets.token_hex(16)
        s["pin_salt"] = salt
        s["pin_hash"] = _hash_pin(pin, salt)
        s["fail_count"] = 0
        s["lockout_until"] = 0.0
        _save(s)
    log.info("PIN changed")


def lock() -> None:
    with _state_guard():
        s = _load()
        if not s["pin_hash"]:
            raise ValueError("Set a PIN before locking")
        s["locked"] = True
        _save(s)
    log.info("state -> locked")


def unlock() -> None:
    """Unlock from the app (already authenticated with the access token) -- no PIN needed."""
    with _state_guard():
        s = _load()
        s["locked"] = False
        s["fail_count"] = 0
        s["lockout_until"] = 0.0
        _save(s)
    log.info("state -> unlocked (app)")


def pin_lockout_remaining() -> float:
    with _state_guard():
        s = _load()
        return max(0.0, s["lockout_until"] - time.time())


def unlock_with_pin(pin: str) -> tuple[bool, str]:
    """
    Used by the local overlay running on the PC itself. Returns (ok, message).
    Independent, file-based fail counter -- so lockouts survive the overlay process restarting.
    A state-file problem is reported as a failure; it never unlocks.
    """
    try:
        with _state_guard():
            s = _load()
            now = time.time()
            if s["lockout_until"] > now:
                return False, f"Too many attempts. Try again in {int(s['lockout_until'] - now) + 1}s"
            if not s["pin_hash"]:
                return False, "No PIN set"
            ok = secrets.compare_digest(_hash_pin(pin.strip(), s["pin_salt"]), s["pin_hash"])
            if ok:
                s["locked"] = False
                s["fail_count"] = 0
                s["lockout_until"] = 0.0
                _save(s)
                log.info("state -> unlocked (PIN entered at the PC)")
                return True, "Unlocked"
            s["fail_count"] += 1
            if s["fail_count"] >= MAX_PIN_FAILS:
                s["lockout_until"] = now + PIN_LOCKOUT_SECONDS
                s["fail_count"] = 0
                _save(s)
                log.warning("PIN rejected; attempt limit reached, cooling down %ss", PIN_LOCKOUT_SECONDS)
                return False, f"Too many attempts. Try again in {PIN_LOCKOUT_SECONDS}s"
            _save(s)
            left = MAX_PIN_FAILS - s["fail_count"]
            log.warning("PIN rejected (%d attempt(s) left before cooldown)", left)
            return False, f"Wrong PIN ({left} attempt{'s' if left != 1 else ''} left)"
    except StateFileError as e:
        log.error("PIN check failed: %s", e)
        return False, "Lock state file problem - see lock_overlay.log. Use the phone app to unlock."
