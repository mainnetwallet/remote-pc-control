import json, time
import pytest
from fastapi.testclient import TestClient
from app import panel, tailnet
from app.config import settings
from app.main import app


class FakeProc:
    def __init__(self): self.stdin = type("S", (), {"close": lambda self: None})(); self.dead = False
    def poll(self): return 1 if self.dead else None
    def terminate(self): self.dead = True
    def wait(self, t=None): return 0
    def kill(self): self.dead = True


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(tailnet, "base_dir", lambda: tmp_path / "tailscale")
    monkeypatch.setattr(tailnet, "_proc", None)
    monkeypatch.setattr(tailnet, "find_bridge", lambda: "tsbridge.exe")
    monkeypatch.setattr(tailnet.subprocess, "Popen", lambda cmd, **kw: FakeProc())
    monkeypatch.setattr(tailnet, "open", lambda *a, **k: open(tmp_path / "log", "ab"), raising=False)
    yield
    tailnet.stop()


def test_off_by_default():
    s = tailnet.status()
    assert s["running"] is False and s["state"] == "Off" and s["enabled"] is False and s["available"] is True


def test_enable_runs_bridge_and_remembers_the_choice(tmp_path):
    s = tailnet.set_enabled(True, 8888)
    assert s["running"] and s["enabled"] and (tmp_path / "tailscale" / "enabled").exists()
    s = tailnet.set_enabled(False, 8888)
    assert not s["running"] and not s["enabled"]


def test_status_comes_from_the_bridge_file(tmp_path):
    tailnet.set_enabled(True, 8888)
    f = tmp_path / "tailscale" / "status.json"
    f.write_text(json.dumps({"state": "NeedsLogin", "auth_url": "https://login.tailscale.com/a/x", "ips": [], "updated": time.time()}))
    s = tailnet.status()
    assert s["state"] == "NeedsLogin" and s["auth_url"].startswith("https://login.tailscale.com/")
    f.write_text(json.dumps({"state": "Running", "ips": ["100.101.102.103", "fd7a::1"], "name": "remote-pc.tail1234.ts.net.", "updated": time.time()}))
    s = tailnet.status()
    assert s["state"] == "Running" and s["ips"][0] == "100.101.102.103" and s["name"] == "remote-pc.tail1234.ts.net" and s["auth_url"] == ""
    f.write_text(json.dumps({"state": "Running", "ips": ["100.1.1.1"], "updated": time.time() - 60}))
    assert tailnet.status()["state"] == "Starting" and tailnet.status()["ips"] == []   # a stale file is not believed


def test_missing_bridge_is_a_clear_error_and_leaves_the_switch_off(monkeypatch, tmp_path):
    monkeypatch.setattr(tailnet, "find_bridge", lambda: None)
    with pytest.raises(RuntimeError, match="tsbridge.exe"): tailnet.set_enabled(True, 8888)
    assert not (tmp_path / "tailscale" / "enabled").exists()


def test_autostart_only_when_turned_on():
    tailnet.autostart(8888); assert not tailnet.status()["running"]
    tailnet.set_enabled(True, 8888); tailnet.stop()
    tailnet.autostart(8888); assert tailnet.status()["running"]


def test_panel_api_is_local_only_and_forwarded_requests_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "env_path", lambda: tmp_path / ".env")
    h = {"Authorization": "Bearer " + settings.token}
    local = TestClient(app, base_url="http://127.0.0.1:8888", client=("127.0.0.1", 50000))
    assert local.get("/panel/api/tailscale", headers=h).json()["state"] == "Off"
    assert local.post("/panel/api/tailscale/enable", headers=h).json()["running"] is True
    assert local.post("/panel/api/tailscale/disable", headers=h).json()["running"] is False
    # what tsbridge adds to everything it forwards from the tailnet
    for extra in ({"X-Forwarded-For": "100.100.1.2"}, {"Cf-Connecting-Ip": "100.100.1.2"}):
        r = local.get("/panel/api/tailscale", headers={**h, **extra})
        assert r.status_code == 403
