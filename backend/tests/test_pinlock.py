import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app import pinlock


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(pinlock, "STATE_PATH", tmp_path / "lock_state.json")
    yield


def _auth():
    return {"Authorization": "Bearer " + settings.token}


def test_status_defaults_unlocked_no_pin():
    s = pinlock.status()
    assert s == {"locked": False, "pin_set": False}


def test_cannot_lock_without_pin():
    with pytest.raises(ValueError):
        pinlock.lock()


def test_set_pin_rejects_bad_values():
    for bad in ("", "abc", "12", "1" * 13, "12 34"):
        with pytest.raises(ValueError):
            pinlock.set_pin(bad)


def test_lock_unlock_roundtrip_persists():
    pinlock.set_pin("4321")
    pinlock.lock()
    assert pinlock.status()["locked"] is True
    pinlock.unlock()
    assert pinlock.status()["locked"] is False


def test_unlock_with_pin_correct_and_wrong():
    pinlock.set_pin("1111")
    pinlock.lock()
    ok, _ = pinlock.unlock_with_pin("0000")
    assert ok is False and pinlock.status()["locked"] is True
    ok, _ = pinlock.unlock_with_pin("1111")
    assert ok is True and pinlock.status()["locked"] is False


def test_pin_lockout_after_repeated_fails():
    pinlock.set_pin("9999")
    pinlock.lock()
    for _ in range(pinlock.MAX_PIN_FAILS):
        pinlock.unlock_with_pin("0000")
    ok, msg = pinlock.unlock_with_pin("9999")   # correct PIN, but now rate-limited
    assert ok is False and "attempt" in msg.lower()
    assert pinlock.pin_lockout_remaining() > 0


def test_state_survives_reload_from_disk():
    pinlock.set_pin("2468")
    pinlock.lock()
    reloaded = pinlock._load()
    assert reloaded["locked"] is True and reloaded["pin_hash"]


def test_api_requires_auth():
    with TestClient(app) as c:
        assert c.get("/api/v1/lock/status").status_code == 401
        assert c.post("/api/v1/lock/lock").status_code == 401
        assert c.post("/api/v1/lock/unlock").status_code == 401
        assert c.post("/api/v1/lock/pin", json={"pin": "1234"}).status_code == 401


def test_api_set_pin_lock_unlock_flow():
    with TestClient(app) as c:
        r = c.post("/api/v1/lock/pin", json={"pin": "5678"}, headers=_auth())
        assert r.status_code == 200
        r = c.post("/api/v1/lock/lock", headers=_auth())
        assert r.status_code == 200 and r.json()["locked"] is True
        assert c.get("/api/v1/lock/status", headers=_auth()).json() == {"locked": True, "pin_set": True}
        r = c.post("/api/v1/lock/unlock", headers=_auth())
        assert r.status_code == 200 and r.json()["locked"] is False


def test_api_lock_without_pin_rejected():
    with TestClient(app) as c:
        r = c.post("/api/v1/lock/lock", headers=_auth())
        assert r.status_code == 400


def test_api_rejects_bad_pin():
    with TestClient(app) as c:
        r = c.post("/api/v1/lock/pin", json={"pin": "abcd"}, headers=_auth())
        assert r.status_code == 400
