"""Repeated-failure limiter: the same failing request again and again from one client gets 429 + Retry-After."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import security
from app.config import settings
from app.main import app


def test_same_failing_request_is_rate_limited():
    with TestClient(app) as c:
        for _ in range(security.ROUTE_MAX_FAILS):
            assert c.get("/nope").status_code == 404
        r = c.get("/nope")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
        assert c.get("/api/health").status_code == 200   # other requests of the same client still work


def test_missing_authorization_header_is_limited():
    with TestClient(app) as c:
        for _ in range(security.ROUTE_MAX_FAILS):
            assert c.get("/api/v1/status").status_code == 401
        assert c.get("/api/v1/status").status_code == 429


def test_success_resets_the_route_counter():
    good = {"Authorization": "Bearer " + settings.token}
    with TestClient(app) as c:
        for _ in range(security.ROUTE_MAX_FAILS - 1): c.get("/api/v1/status")
        assert c.get("/api/v1/status", headers=good).status_code == 200
        for _ in range(security.ROUTE_MAX_FAILS - 1): c.get("/api/v1/status")
        assert c.get("/api/v1/status", headers=good).status_code == 200


def test_limit_is_per_client():
    with TestClient(app, client=("127.0.0.1", 50000)) as c:   # the Cloudflare tunnel connects from localhost
        for _ in range(security.ROUTE_MAX_FAILS): c.get("/nope", headers={"CF-Connecting-IP": "1.2.3.4"})
        assert c.get("/nope", headers={"CF-Connecting-IP": "1.2.3.4"}).status_code == 429
        assert c.get("/nope", headers={"CF-Connecting-IP": "5.6.7.8"}).status_code == 404


def test_scanner_trying_many_paths_is_blocked_as_a_client():
    with TestClient(app) as c:
        for i in range(security.CLIENT_MAX_FAILS): assert c.get(f"/probe-{i}").status_code == 404
        assert c.get("/probe-new").status_code == 429
        assert c.get("/api/health").status_code == 429   # the whole client waits, not just one path


def test_limit_expires(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(security.time, "monotonic", lambda: now[0])
    with TestClient(app) as c:
        for _ in range(security.ROUTE_MAX_FAILS): c.get("/nope")
        assert c.get("/nope").status_code == 429
        now[0] += security.ROUTE_WINDOW_SECONDS + 1
        assert c.get("/nope").status_code == 404


def test_server_errors_and_blocked_answers_are_not_counted():
    security.record_request_result("k", "GET", "/x", 500)
    security.record_request_result("k", "GET", "/x", 429)
    assert security.request_blocked("k", "GET", "/x") == 0 and not security._route_fails


def test_tables_stay_bounded(monkeypatch):
    monkeypatch.setattr(security, "MAX_TRACKED", 50)
    for i in range(500): security.record_request_result(f"ip{i}", "GET", f"/p{i}", 404)
    assert len(security._route_fails) <= 100 and len(security._client_fails) <= 100


@pytest.mark.parametrize("first", ["not json", "[]", "123"])
def test_garbled_websocket_login_counts_as_a_failure(first):
    with TestClient(app) as c, c.websocket_connect("/ws/input") as ws:
        ws.send_text(first)
        with pytest.raises(WebSocketDisconnect) as e: ws.receive_text()
        assert e.value.code == 4401
    assert len(security._fails["testclient"]) == 1
