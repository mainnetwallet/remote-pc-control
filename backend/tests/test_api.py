from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

def test_health_public():
    with TestClient(app) as c:
        r=c.get("/api/health"); assert r.status_code==200 and r.json()["ok"]

def test_status_requires_token():
    with TestClient(app) as c: assert c.get("/api/v1/status").status_code==401

def test_status_rejects_wrong_token():
    with TestClient(app) as c: assert c.get("/api/v1/status",headers={"Authorization":"Bearer bad"}).status_code==401

def test_power_requires_confirmation(monkeypatch):
    monkeypatch.setattr(settings,"token","z"*40)
    with TestClient(app) as c:
        r=c.post("/api/v1/control/shutdown",headers={"Authorization":"Bearer "+"z"*40},json={"confirm":False}); assert r.status_code==400


def test_lockout_after_repeated_wrong_tokens():
    from app import security
    good = "Bearer " + settings.token
    with TestClient(app) as c:
        for _ in range(security.MAX_FAILS):
            assert c.get("/api/v1/status", headers={"Authorization": "Bearer bad"}).status_code == 401
        assert c.get("/api/v1/status", headers={"Authorization": "Bearer bad"}).status_code == 429
        assert c.get("/api/v1/status", headers={"Authorization": good}).status_code == 429   # locked out even with right token


def test_lockout_is_per_client_ip_and_success_resets():
    from app import security
    good = "Bearer " + settings.token
    with TestClient(app, client=("127.0.0.1", 50000)) as c:   # the Cloudflare tunnel connects from localhost
        for _ in range(security.MAX_FAILS):
            c.get("/api/v1/status", headers={"Authorization": "Bearer bad", "CF-Connecting-IP": "1.2.3.4"})
        assert c.get("/api/v1/status", headers={"Authorization": good, "CF-Connecting-IP": "1.2.3.4"}).status_code == 429
        assert c.get("/api/v1/status", headers={"Authorization": good, "CF-Connecting-IP": "5.6.7.8"}).status_code == 200
        c.get("/api/v1/status", headers={"Authorization": "Bearer bad", "CF-Connecting-IP": "9.9.9.9"})
        assert c.get("/api/v1/status", headers={"Authorization": good, "CF-Connecting-IP": "9.9.9.9"}).status_code == 200
        assert len(security._fails.get("9.9.9.9", [])) == 0


def test_direct_client_cannot_dodge_lockout_with_a_fake_header():
    from app import security
    good = "Bearer " + settings.token
    with TestClient(app, client=("192.168.1.50", 50000)) as c:   # not the tunnel: the header must be ignored
        for i in range(security.MAX_FAILS):
            c.get("/api/v1/status", headers={"Authorization": "Bearer bad", "CF-Connecting-IP": f"10.0.0.{i}"})
        assert c.get("/api/v1/status", headers={"Authorization": good, "CF-Connecting-IP": "10.9.9.9"}).status_code == 429


def test_websocket_lockout():
    import pytest
    from starlette.websockets import WebSocketDisconnect
    from app import security
    for _ in range(security.MAX_FAILS): security.record_fail("testclient")
    with TestClient(app) as c, c.websocket_connect("/ws/input") as ws:
        with pytest.raises(WebSocketDisconnect) as e: ws.receive_text()
        assert e.value.code == 4429


def test_short_password_allowed_but_not_shorter(monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "token", "ab12"); config.validate_settings()
    monkeypatch.setattr(config.settings, "token", "abc")
    import pytest
    with pytest.raises(RuntimeError): config.validate_settings()


def test_global_lockout_across_different_ips():
    from app import security
    good = "Bearer " + settings.token
    with TestClient(app) as c:
        for i in range(security.GLOBAL_MAX_FAILS):
            c.get("/api/v1/status", headers={"Authorization": "Bearer bad", "CF-Connecting-IP": f"10.0.{i // 200}.{i % 200}"})
        assert c.get("/api/v1/status", headers={"Authorization": good, "CF-Connecting-IP": "77.7.7.7"}).status_code == 429
