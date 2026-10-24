import base64, logging, time
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from app import unlock
from app.config import settings
from app.main import app

SECRET = "Sup3r-S3cret-PIN-8842"


class FakeBridge(unlock.Bridge):
    def __init__(self, result=unlock.SUCCESS, present=True): self.result, self.present, self.calls = result, present, []
    def available(self): return self.present
    def attempt(self, request_id, account, session_id, secret, timeout):
        self.calls.append((account, session_id, bytes(secret), timeout)); return self.result


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "unlock_enabled", True)
    monkeypatch.setattr(settings, "unlock_account", "alice")
    monkeypatch.setattr(settings, "unlock_require_biometric", False)
    monkeypatch.setattr(settings, "unlock_data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "pc_id", "pc-one")
    monkeypatch.setattr(unlock, "console_session_id", lambda: 1)
    bridge = FakeBridge(); svc = unlock.UnlockService(bridge)
    monkeypatch.setattr(unlock, "service", svc)
    svc.reset()
    with TestClient(app) as c:
        c.headers.update({"Authorization": "Bearer " + settings.token}); c.bridge, c.svc = bridge, svc
        yield c


def phone():
    key = ec.generate_private_key(ec.SECP256R1())
    spki = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    return key, spki


def enroll(c, approve=True):
    key, spki = phone()
    r = c.post("/api/v1/unlock/devices", json={"name": "Pixel", "public_key": spki}); assert r.status_code == 200, r.text
    d = r.json(); assert d["status"] == "PENDING_LOCAL_APPROVAL"
    if approve: assert c.svc.approve(d["device_id"])
    return key, d["device_id"]


def sign(key, ch):
    return base64.b64encode(key.sign(unlock.signed_message(ch), ec.ECDSA(hashes.SHA256()))).decode()


def bio(c, key, did, **over):
    ch = c.post("/api/v1/unlock/challenge", json={"device_id": did}).json()
    body = {"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(key, ch), "credential": SECRET}; body.update(over)
    return ch, c.post("/api/v1/unlock/biometric", json=body)


# ---- authorization -------------------------------------------------------------------------------------
@pytest.mark.parametrize("method,path,body", [("get", "/api/v1/unlock/status", None), ("get", "/api/v1/unlock/devices", None),
    ("post", "/api/v1/unlock/devices", {"name": "x", "public_key": "A" * 100}), ("post", "/api/v1/unlock/challenge", {"device_id": "0" * 16}),
    ("post", "/api/v1/unlock/password", {"credential": SECRET}), ("delete", "/api/v1/unlock/devices/abc", None),
    ("post", "/api/v1/unlock/biometric", {"device_id": "0" * 16, "challenge_id": "0" * 16, "signature": "A" * 20, "credential": SECRET})])
def test_every_unlock_route_requires_token(env, method, path, body):
    with TestClient(app) as anon:
        r = getattr(anon, method)(path, **({"json": body} if body else {})); assert r.status_code == 401
        r = getattr(anon, method)(path, headers={"Authorization": "Bearer wrong"}, **({"json": body} if body else {})); assert r.status_code == 401
    assert env.bridge.calls == []


# ---- not configured / unsupported --------------------------------------------------------------------
def test_disabled_by_default(monkeypatch, env):
    monkeypatch.setattr(settings, "unlock_enabled", False)
    s = env.get("/api/v1/unlock/status").json(); assert s["state"] == "NOT_CONFIGURED" and not s["methods"]["password"]
    r = env.post("/api/v1/unlock/password", json={"credential": SECRET}); assert r.status_code == 503 and r.json()["detail"]["result"] == "NOT_CONFIGURED"
    assert env.bridge.calls == []

def test_component_missing_never_reports_success(env):
    env.bridge.present = False
    r = env.post("/api/v1/unlock/password", json={"credential": SECRET}); assert r.status_code == 503 and r.json()["detail"]["result"] == "NOT_CONFIGURED"
    assert env.get("/api/v1/unlock/status").json()["integration_installed"] is False

def test_missing_account_is_not_configured(monkeypatch, env):
    monkeypatch.setattr(settings, "unlock_account", "")
    assert env.post("/api/v1/unlock/password", json={"credential": SECRET}).status_code == 503

def test_real_pipe_bridge_off_windows_is_unavailable(): assert unlock.PipeBridge().available() is False

def test_password_refused_when_policy_requires_biometric(monkeypatch, env):
    monkeypatch.setattr(settings, "unlock_require_biometric", True)
    r = env.post("/api/v1/unlock/password", json={"credential": SECRET}); assert r.status_code == 501 and env.bridge.calls == []


# ---- password path -------------------------------------------------------------------------------------
def test_password_success_only_when_windows_confirms(env):
    r = env.post("/api/v1/unlock/password", json={"credential": SECRET}); assert r.status_code == 200 and r.json()["result"] == "SUCCESS"
    account, session, sent, timeout = env.bridge.calls[0]; assert (account, session, sent) == ("alice", 1, SECRET.encode()) and timeout == unlock.UNLOCK_TIMEOUT

@pytest.mark.parametrize("result,code", [("INVALID_CREDENTIALS", 400), ("ACCOUNT_RESTRICTED", 403), ("TIMEOUT", 504), ("NOT_LOCKED", 409), ("ERROR", 502)])
def test_failures_are_not_success(env, result, code):
    env.bridge.result = result
    r = env.post("/api/v1/unlock/password", json={"credential": SECRET}); assert r.status_code == code and r.json()["detail"]["result"] == result

def test_failed_attempts_are_rate_limited(env):
    env.bridge.result = "INVALID_CREDENTIALS"
    for _ in range(unlock.MAX_FAILS): assert env.post("/api/v1/unlock/password", json={"credential": "bad"}).status_code == 400
    n = len(env.bridge.calls)
    env.bridge.result = "SUCCESS"
    r = env.post("/api/v1/unlock/password", json={"credential": SECRET}); assert r.status_code == 429 and len(env.bridge.calls) == n   # even the right one is refused

def test_concurrent_attempt_is_refused(env):
    env.svc._busy.acquire()
    assert env.post("/api/v1/unlock/password", json={"credential": SECRET}).status_code == 409

def test_input_validation_and_size(env):
    assert env.post("/api/v1/unlock/password", json={"credential": ""}).status_code == 422
    assert env.post("/api/v1/unlock/password", json={"credential": "x" * 129}).status_code == 422
    assert env.post("/api/v1/unlock/password", content=b"{" + b" " * 5000 + b'"credential":"x"}', headers={"Content-Type": "application/json"}).status_code == 413
    assert env.bridge.calls == []

def test_secret_not_echoed_or_logged(env, caplog):
    caplog.set_level(logging.DEBUG)
    r1 = env.post("/api/v1/unlock/password", json={"credential": SECRET + "x" * 120}); assert SECRET not in r1.text      # 422: too long
    r2 = env.post("/api/v1/unlock/password", json={"credential": SECRET, "extra": 1}); assert SECRET not in r2.text
    env.bridge.result = "INVALID_CREDENTIALS"; r3 = env.post("/api/v1/unlock/password", json={"credential": SECRET}); assert SECRET not in r3.text
    env.bridge.result = "ERROR"; r4 = env.post("/api/v1/unlock/password", json={"credential": SECRET}); assert SECRET not in r4.text
    assert SECRET not in caplog.text
    assert SECRET not in repr(unlock.service) and "pwd" not in (env.svc._path().read_text() if env.svc._path().exists() else "")

def test_secret_buffer_is_wiped(env):
    seen = []
    class Spy(FakeBridge):
        def attempt(self, rid, account, session_id, secret, timeout): seen.append(secret); return unlock.SUCCESS
    env.svc.bridge = Spy(); env.post("/api/v1/unlock/password", json={"credential": SECRET})
    assert bytes(seen[0]) == b"\x00" * len(SECRET)


# ---- enrollment ---------------------------------------------------------------------------------------
def test_enrollment_needs_local_approval(env):
    key, did = enroll(env, approve=False)
    assert env.post("/api/v1/unlock/challenge", json={"device_id": did}).status_code == 403
    assert env.get("/api/v1/unlock/devices").json()["devices"][0]["status"] == "PENDING"
    assert env.get("/api/v1/unlock/status").json()["methods"]["biometric"] is False
    assert not any("spki" in d for d in env.get("/api/v1/unlock/devices").json()["devices"])

def test_enrollment_rejects_bad_keys(env):
    assert env.post("/api/v1/unlock/devices", json={"name": "x", "public_key": "A" * 100}).status_code == 400
    rsa_like = base64.b64encode(ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    assert env.post("/api/v1/unlock/devices", json={"name": "x", "public_key": rsa_like}).status_code == 400

def test_device_limit(env):
    for _ in range(unlock.MAX_DEVICES): enroll(env, approve=False)
    _, spki = phone(); assert env.post("/api/v1/unlock/devices", json={"name": "x", "public_key": spki}).status_code == 400


# ---- biometric chain ---------------------------------------------------------------------------------
def test_biometric_success(env):
    key, did = enroll(env); assert env.get("/api/v1/unlock/status").json()["methods"]["biometric"] is True
    ch, r = bio(env, key, did); assert r.status_code == 200 and env.bridge.calls[0][2] == SECRET.encode()
    assert ch["account"] == "alice" and ch["pc_id"] == "pc-one" and ch["session"] == 1 and ch["op"] == "unlock"

def test_challenge_replay_rejected(env):
    key, did = enroll(env); ch, r = bio(env, key, did); assert r.status_code == 200
    body = {"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(key, ch), "credential": SECRET}
    assert env.post("/api/v1/unlock/biometric", json=body).status_code == 400 and len(env.bridge.calls) == 1

def test_expired_challenge_rejected(env, monkeypatch):
    key, did = enroll(env); ch = env.post("/api/v1/unlock/challenge", json={"device_id": did}).json()
    real = time.time; monkeypatch.setattr(unlock.time, "time", lambda: real() + unlock.CHALLENGE_TTL + 1)
    r = env.post("/api/v1/unlock/biometric", json={"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(key, ch), "credential": SECRET})
    assert r.status_code == 400 and env.bridge.calls == []

def test_invalid_signature_and_wrong_key(env):
    key, did = enroll(env); other, _ = phone()
    ch = env.post("/api/v1/unlock/challenge", json={"device_id": did}).json()
    r = env.post("/api/v1/unlock/biometric", json={"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(other, ch), "credential": SECRET})
    assert r.status_code == 400 and r.json()["detail"]["result"] == "SIGNATURE_INVALID" and env.bridge.calls == []
    r = env.post("/api/v1/unlock/biometric", json={"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(key, ch), "credential": SECRET})
    assert r.status_code == 400   # the failed attempt consumed the challenge

def test_tampered_challenge_fields_fail(env):
    key, did = enroll(env); ch = env.post("/api/v1/unlock/challenge", json={"device_id": did}).json()
    forged = dict(ch, account="bob")
    r = env.post("/api/v1/unlock/biometric", json={"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(key, forged), "credential": SECRET})
    assert r.status_code == 400 and env.bridge.calls == []

def test_revoked_device_rejected(env):
    key, did = enroll(env); ch = env.post("/api/v1/unlock/challenge", json={"device_id": did}).json()
    assert env.delete(f"/api/v1/unlock/devices/{did}").status_code == 200
    r = env.post("/api/v1/unlock/biometric", json={"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(key, ch), "credential": SECRET})
    assert r.status_code == 400 and env.bridge.calls == []
    assert env.post("/api/v1/unlock/challenge", json={"device_id": did}).status_code == 403
    assert env.delete(f"/api/v1/unlock/devices/{did}").status_code == 404

def test_cross_device_challenge_rejected(env):
    k1, d1 = enroll(env); k2, d2 = enroll(env)
    ch = env.post("/api/v1/unlock/challenge", json={"device_id": d1}).json()
    r = env.post("/api/v1/unlock/biometric", json={"device_id": d2, "challenge_id": ch["challenge_id"], "signature": sign(k2, ch), "credential": SECRET})
    assert r.status_code == 400 and env.bridge.calls == []

@pytest.mark.parametrize("field,change", [("pc_id", lambda m: m.setattr(settings, "pc_id", "pc-two")),
    ("account", lambda m: m.setattr(settings, "unlock_account", "bob")), ("session", lambda m: m.setattr(unlock, "console_session_id", lambda: 2))])
def test_cross_pc_account_session_misuse_rejected(env, monkeypatch, field, change):
    key, did = enroll(env); ch = env.post("/api/v1/unlock/challenge", json={"device_id": did}).json()
    change(monkeypatch)
    r = env.post("/api/v1/unlock/biometric", json={"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(key, ch), "credential": SECRET})
    assert r.status_code == 400 and env.bridge.calls == []

def test_biometric_never_unlocks_without_windows_result(env):
    key, did = enroll(env); env.bridge.result = "INVALID_CREDENTIALS"
    ch, r = bio(env, key, did); assert r.status_code == 400 and r.json()["detail"]["result"] == "INVALID_CREDENTIALS"

def test_biometric_without_credential_is_rejected(env):
    key, did = enroll(env); ch = env.post("/api/v1/unlock/challenge", json={"device_id": did}).json()
    r = env.post("/api/v1/unlock/biometric", json={"device_id": did, "challenge_id": ch["challenge_id"], "signature": sign(key, ch)})
    assert r.status_code == 422 and env.bridge.calls == []   # a fingerprint alone is never enough

def test_challenges_are_unique_and_unpredictable(env):
    key, did = enroll(env); a = env.post("/api/v1/unlock/challenge", json={"device_id": did}).json(); b = env.post("/api/v1/unlock/challenge", json={"device_id": did}).json()
    assert a["nonce"] != b["nonce"] and len(a["nonce"]) >= 43

def test_pending_challenge_cap(env):
    key, did = enroll(env)
    for _ in range(unlock.MAX_PENDING_CHALLENGES): assert env.post("/api/v1/unlock/challenge", json={"device_id": did}).status_code == 200
    assert env.post("/api/v1/unlock/challenge", json={"device_id": did}).status_code == 429


# ---- pipe protocol (Windows-only code path is not run here) ----------------------------------------------
def test_pipe_bridge_off_windows_reports_not_configured():
    assert unlock.PipeBridge().attempt("id", "alice", 1, bytearray(b"x"), 1) == "NOT_CONFIGURED"

def test_local_admin_cli(env, monkeypatch, capsys):
    from app import unlock_admin
    monkeypatch.setattr(unlock_admin, "service", env.svc)
    key, did = enroll(env, approve=False)
    assert unlock_admin.main(["approve", did]) == 0 and unlock_admin.main(["revoke", did]) == 0 and unlock_admin.main(["revoke", did]) == 1
    assert unlock_admin.main(["list"]) == 0 and unlock_admin.main([]) == 2


# ---- regression: existing control endpoints --------------------------------------------------------------
def test_existing_control_endpoints_unchanged(env):
    assert env.post("/api/v1/control/shutdown", json={"confirm": False}).status_code == 400
    assert env.post("/api/v1/control/bogus", json={"confirm": True}).status_code == 404
    assert env.post("/api/v1/control/lock").status_code in (200, 501)          # 501 off Windows
    assert env.post("/api/v1/control/sleep").status_code in (200, 501)
    assert env.get("/api/v1/status").status_code == 200 and env.get("/api/health").json()["ok"]
    with TestClient(app) as anon: assert anon.post("/api/v1/control/lock").status_code == 401
    assert env.bridge.calls == []   # lock/power never touch the unlock bridge
