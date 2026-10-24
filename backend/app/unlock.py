"""Secure Windows unlock: device enrollment, biometric challenges and the bridge to the Credential Provider.

Design (see docs/UNLOCK.md):
  * This agent NEVER authenticates anyone itself. Windows does, inside the native Credential Provider
    (CPUS_UNLOCK_WORKSTATION) that listens on a local named pipe. Success is reported only when that
    component returns Windows' own result for the logon attempt.
  * No Windows credential is ever stored. A phone fingerprint is never proof of a Windows logon: the biometric mode
    is an additional device factor (a signature from a hardware-backed, biometric-gated key) that must accompany the
    Windows PIN/password.
"""
from __future__ import annotations

import base64, hashlib, json, os, platform, secrets, threading, time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .config import settings

PIPE_NAME = r"\\.\pipe\RemotePCControlUnlock"
CHALLENGE_TTL = 60.0            # seconds a biometric challenge stays valid
MAX_PENDING_CHALLENGES = 32
UNLOCK_TIMEOUT = 25.0           # seconds to wait for Windows' answer
MAX_CREDENTIAL_CHARS = 128      # Windows passwords/PINs are at most 127
MAX_DEVICES = 8
MAX_FAILS = 5                   # failed Windows attempts per window (all clients together)
FAIL_WINDOW = 600.0
MSG_PREFIX = b"RPC-UNLOCK-V1"

# Result codes (never contain secrets or Windows error text).
SUCCESS = "SUCCESS"
INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
LOCKED_OUT = "ACCOUNT_RESTRICTED"
TIMEOUT = "TIMEOUT"
NOT_CONFIGURED = "NOT_CONFIGURED"
UNSUPPORTED = "UNSUPPORTED"
NOT_LOCKED = "NOT_LOCKED"
BUSY = "BUSY"
RATE_LIMITED = "RATE_LIMITED"
ERROR = "ERROR"
HTTP_FOR = {SUCCESS: 200, INVALID_CREDENTIALS: 400, LOCKED_OUT: 403, TIMEOUT: 504, NOT_CONFIGURED: 503,
            UNSUPPORTED: 501, "DEVICE_NOT_AUTHORIZED": 403, NOT_LOCKED: 409, BUSY: 409, RATE_LIMITED: 429, ERROR: 502}


class UnlockError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code); self.code = code; self.detail = detail or code


# ---------------------------------------------------------------- bridge to the Windows component
class Bridge:
    """Talks to the Credential Provider. Replaced by a fake in tests."""
    def available(self) -> bool: raise NotImplementedError
    def attempt(self, request_id: str, account: str, session_id: int, secret: bytearray, timeout: float) -> str: raise NotImplementedError


class PipeBridge(Bridge):
    def available(self) -> bool:
        if platform.system() != "Windows": return False
        try:
            import ctypes
            return bool(ctypes.windll.kernel32.WaitNamedPipeW(PIPE_NAME, 1)) or ctypes.GetLastError() == 121  # busy still means present
        except Exception:
            return False

    def attempt(self, request_id, account, session_id, secret, timeout):
        if platform.system() != "Windows": return NOT_CONFIGURED
        # Build the message as bytes so the secret never becomes an extra str copy; wiped right after the write.
        head = json.dumps({"v": 1, "id": request_id, "account": account, "session": session_id}).encode()
        msg = bytearray(head[:-1]); msg += b',"pwd":'; msg += json.dumps(secret.decode("utf-8")).encode(); msg += b"}\n"
        try:
            deadline = time.monotonic() + timeout
            with open(PIPE_NAME, "r+b", buffering=0) as pipe:
                pipe.write(msg)
                out = pipe.read(512)
        except FileNotFoundError: return NOT_CONFIGURED
        except OSError: return ERROR
        finally:
            for i in range(len(msg)): msg[i] = 0
        try: reply = json.loads(out.decode()); status = reply.get("status")
        except Exception: return ERROR
        if reply.get("id") != request_id: return ERROR
        return status if status in (SUCCESS, INVALID_CREDENTIALS, LOCKED_OUT, NOT_LOCKED, TIMEOUT) else ERROR


# ---------------------------------------------------------------- helpers
def data_dir() -> Path:
    d = settings.unlock_data_dir or os.path.join(os.environ.get("PROGRAMDATA", os.path.expanduser("~")), "RemotePCControl")
    p = Path(d); p.mkdir(parents=True, exist_ok=True); return p


def pc_id() -> str:
    if settings.pc_id: return settings.pc_id
    guid = ""
    try:
        if platform.system() == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k: guid = winreg.QueryValueEx(k, "MachineGuid")[0]
    except Exception: pass
    return hashlib.sha256(f"{guid}|{platform.node()}".encode()).hexdigest()[:32]


def console_session_id() -> int:
    """The Windows session this agent runs in = the session that gets unlocked. 0 off Windows."""
    try:
        import ctypes
        sid = ctypes.c_ulong()
        if ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid)): return int(sid.value)
    except Exception: pass
    return 0


def fingerprint(spki_der: bytes) -> str:
    h = hashlib.sha256(spki_der).hexdigest().upper()
    return "-".join(h[i:i + 4] for i in range(0, 20, 4))


def signed_message(challenge: dict) -> bytes:
    """Exact bytes the phone signs. Fields are fixed-order and newline separated (none can contain a newline)."""
    parts = [MSG_PREFIX, challenge["op"], challenge["pc_id"], challenge["account"], str(challenge["session"]), challenge["device_id"], challenge["challenge_id"], challenge["nonce"], str(int(challenge["expires_at"]))]
    return b"\n".join(p if isinstance(p, bytes) else p.encode() for p in parts)


# ---------------------------------------------------------------- the service
@dataclass
class Device:
    device_id: str; name: str; spki_b64: str; status: str; created: float; fp: str


class UnlockService:
    def __init__(self, bridge: Bridge | None = None):
        self.bridge = bridge or PipeBridge()
        self._lock = threading.Lock()
        self._challenges: dict[str, dict] = {}
        self._fails: deque = deque()
        self._busy = threading.Lock()

    # ----- configuration / status
    def config_state(self) -> tuple[str, str]:
        if not settings.unlock_enabled: return NOT_CONFIGURED, "Unlock is disabled (set REMOTE_PC_UNLOCK=1 after installing the Windows component)."
        if not settings.unlock_account: return NOT_CONFIGURED, "REMOTE_PC_UNLOCK_ACCOUNT is not set."
        if not self.bridge.available(): return NOT_CONFIGURED, "The Windows unlock component is not installed or not running."
        return "READY", ""

    def status(self) -> dict:
        state, reason = self.config_state()
        ready = state == "READY"
        approved = [d for d in self._load().values() if d["status"] == "APPROVED"]
        return {"state": state, "reason": reason, "integration_installed": ready, "pc_id": pc_id(),
                "methods": {"password": ready and not settings.unlock_require_biometric,
                            "biometric": ready and bool(approved)},
                "biometric_requires_credential": True,
                "approved_devices": len(approved)}

    # ----- device registry (public keys only)
    def _path(self) -> Path: return data_dir() / "unlock_devices.json"

    def _load(self) -> dict:
        try: return json.loads(self._path().read_text("utf-8"))
        except (FileNotFoundError, ValueError): return {}

    def _save(self, devices: dict) -> None:
        tmp = self._path().with_suffix(".tmp"); tmp.write_text(json.dumps(devices), "utf-8"); os.replace(tmp, self._path())

    def enroll(self, name: str, spki_b64: str) -> dict:
        try:
            der = base64.b64decode(spki_b64, validate=True)
            key = serialization.load_der_public_key(der)
            if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1): raise ValueError
        except Exception:
            raise UnlockError("INVALID_KEY", "Public key must be a P-256 SubjectPublicKeyInfo (base64 DER).")
        with self._lock:
            devices = self._load()
            if len([d for d in devices.values() if d["status"] != "REVOKED"]) >= MAX_DEVICES: raise UnlockError("TOO_MANY_DEVICES", "Device limit reached; revoke one first.")
            did = secrets.token_hex(8)
            devices[did] = {"name": name.strip()[:40] or "Android device", "spki": spki_b64, "status": "PENDING", "created": time.time(), "fp": fingerprint(der)}
            self._save(devices)
        return {"device_id": did, "fingerprint": devices[did]["fp"], "status": "PENDING_LOCAL_APPROVAL"}

    def list_devices(self) -> list[dict]:
        return [{"device_id": k, "name": v["name"], "status": v["status"], "fingerprint": v["fp"]} for k, v in self._load().items()]

    def approve(self, device_id_or_fp: str) -> bool:
        """Local-admin only (python -m app.unlock_admin approve ...); deliberately not exposed over HTTP."""
        with self._lock:
            devices = self._load()
            for k, v in devices.items():
                if (k == device_id_or_fp or v["fp"] == device_id_or_fp) and v["status"] == "PENDING":
                    v["status"] = "APPROVED"; self._save(devices); return True
        return False

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            devices = self._load()
            if device_id not in devices or devices[device_id]["status"] == "REVOKED": return False
            devices[device_id]["status"] = "REVOKED"; self._save(devices)
            for cid in [c for c, v in self._challenges.items() if v["device_id"] == device_id]: self._challenges.pop(cid, None)
        return True

    # ----- biometric challenge
    def new_challenge(self, device_id: str) -> dict:
        state, reason = self.config_state()
        if state != "READY": raise UnlockError(state, reason)
        dev = self._load().get(device_id)
        if not dev or dev["status"] != "APPROVED": raise UnlockError("DEVICE_NOT_AUTHORIZED", "Device is not enrolled and approved.")
        now = time.time()
        with self._lock:
            for cid in [c for c, v in self._challenges.items() if v["expires_at"] <= now]: self._challenges.pop(cid, None)
            if len(self._challenges) >= MAX_PENDING_CHALLENGES: raise UnlockError(RATE_LIMITED, "Too many pending challenges.")
            ch = {"op": "unlock", "pc_id": pc_id(), "account": settings.unlock_account, "session": console_session_id(),
                  "device_id": device_id, "challenge_id": secrets.token_hex(8), "nonce": secrets.token_urlsafe(32), "expires_at": now + CHALLENGE_TTL}
            self._challenges[ch["challenge_id"]] = ch
        return {**ch, "expires_in": int(CHALLENGE_TTL), "message_prefix": MSG_PREFIX.decode()}

    def _verify_challenge(self, device_id: str, challenge_id: str, signature_b64: str) -> None:
        with self._lock:
            ch = self._challenges.pop(challenge_id, None)       # single use: popped even if verification then fails
        if ch is None or ch["device_id"] != device_id: raise UnlockError("CHALLENGE_INVALID", "Challenge unknown, used or expired.")
        if ch["expires_at"] <= time.time(): raise UnlockError("CHALLENGE_INVALID", "Challenge unknown, used or expired.")
        if ch["pc_id"] != pc_id() or ch["account"] != settings.unlock_account or ch["session"] != console_session_id():
            raise UnlockError("CHALLENGE_INVALID", "Challenge does not match this PC, account or session.")
        dev = self._load().get(device_id)
        if not dev or dev["status"] != "APPROVED": raise UnlockError("DEVICE_NOT_AUTHORIZED", "Device is not enrolled and approved.")
        try:
            key = serialization.load_der_public_key(base64.b64decode(dev["spki"]))
            key.verify(base64.b64decode(signature_b64, validate=True), signed_message(ch), ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, ValueError, TypeError):
            raise UnlockError("SIGNATURE_INVALID", "Signature verification failed.")

    # ----- the unlock attempt
    def _rate_limited(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._fails and now - self._fails[0] > FAIL_WINDOW: self._fails.popleft()
            return len(self._fails) >= MAX_FAILS

    def unlock(self, secret: str, *, device_id: str | None = None, challenge_id: str | None = None, signature: str | None = None) -> str:
        state, reason = self.config_state()
        if state != "READY": raise UnlockError(state, reason)
        if device_id is None and settings.unlock_require_biometric: raise UnlockError(UNSUPPORTED, "Policy requires biometric device approval.")
        if self._rate_limited(): raise UnlockError(RATE_LIMITED, "Too many failed unlock attempts; try again later.")
        if device_id is not None: self._verify_challenge(device_id, challenge_id or "", signature or "")
        if not self._busy.acquire(blocking=False): raise UnlockError(BUSY, "Another unlock attempt is in progress.")
        buf = bytearray(secret.encode("utf-8"))
        try:
            result = self.bridge.attempt(secrets.token_hex(8), settings.unlock_account, console_session_id(), buf, UNLOCK_TIMEOUT)
        finally:
            for i in range(len(buf)): buf[i] = 0
            self._busy.release()
        if result == INVALID_CREDENTIALS:
            with self._lock: self._fails.append(time.monotonic())
        if result != SUCCESS: raise UnlockError(result, result)
        return SUCCESS

    def reset(self) -> None:
        with self._lock: self._challenges.clear(); self._fails.clear()


service = UnlockService()
