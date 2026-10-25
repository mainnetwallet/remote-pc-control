import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app import envfile, panel, pinlock, security


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(pinlock, "STATE_PATH", tmp_path / "lock_state.json")
    monkeypatch.setattr(panel, "env_path", lambda: tmp_path / ".env")
    (tmp_path / ".env").write_text("# my notes\nREMOTE_PC_TOKEN=old\nCUSTOM=keep me\n")
    return tmp_path


def local(**kw):
    return TestClient(app, base_url="http://127.0.0.1:8888", client=("127.0.0.1", 50000), **kw)


def auth(): return {"Authorization": "Bearer " + settings.token}


def test_no_web_page_any_more():
    with local() as c:
        assert c.get("/panel").status_code in (404, 405)   # the control panel is the desktop app, not a website
        assert c.get("/panel/").status_code in (404, 405)


def test_api_opens_on_this_pc_only():
    with TestClient(app, base_url="http://127.0.0.1:8888", client=("100.64.1.2", 5)) as c:   # phone over Tailscale
        assert c.get("/panel/api/state", headers=auth()).status_code == 403


def test_blocked_through_tunnel_and_dns_rebinding():
    with local() as c:
        assert c.get("/panel/api/state", headers={**auth(), "cf-connecting-ip": "1.2.3.4"}).status_code == 403   # cloudflare tunnel
        assert c.get("/panel/api/state", headers={**auth(), "x-forwarded-for": "1.2.3.4"}).status_code == 403
        assert c.get("/panel/api/state", headers={**auth(), "host": "evil.example.com"}).status_code == 403


def test_api_needs_the_token():
    with local() as c:
        assert c.get("/panel/api/state").status_code == 401
        assert c.get("/panel/api/state", headers={"Authorization": "Bearer nope"}).status_code == 401
        r = c.get("/panel/api/state", headers=auth())
        assert r.status_code == 200 and {f["key"] for f in r.json()["fields"]} == {f["key"] for f in envfile.FIELDS}


def test_change_password_is_live_and_saved(isolated):
    old = auth()
    with local() as c:
        assert c.post("/panel/api/token", headers=auth(), json={"token": "has space"}).status_code == 400
        assert c.post("/panel/api/token", headers=auth(), json={"token": "abc"}).status_code == 400
        assert c.post("/panel/api/token", headers=auth(), json={"token": "new-password-123"}).status_code == 200
        assert settings.token == "new-password-123"
        assert c.get("/panel/api/token", headers=old).status_code == 401   # old password no longer works
        assert c.get("/panel/api/token", headers={"Authorization": "Bearer new-password-123"}).json() == {"token": "new-password-123"}
    text = (isolated / ".env").read_text()
    assert "REMOTE_PC_TOKEN=new-password-123" in text and "# my notes" in text and "CUSTOM=keep me" in text


def test_random_password(isolated):
    with local() as c:
        token = c.post("/panel/api/token/random", headers=auth()).json()["token"]
        assert len(token) >= 32 and settings.token == token
        assert f"REMOTE_PC_TOKEN={token}" in (isolated / ".env").read_text()


def test_settings_are_validated_and_saved(isolated):
    with local() as c:
        bad = [{"REMOTE_PC_JPEG_QUALITY": "999"}, {"REMOTE_PC_RTC_ENCODER": "rm -rf"}, {"EVIL": "1"}, {"REMOTE_PC_WEBRTC": "maybe"}]
        for values in bad:
            assert c.post("/panel/api/settings", headers=auth(), json={"values": values}).status_code == 400
        r = c.post("/panel/api/settings", headers=auth(), json={"values": {"REMOTE_PC_JPEG_QUALITY": 70, "REMOTE_PC_WEBRTC": False, "REMOTE_PC_RTC_FPS": "60"}})
        assert r.status_code == 200 and r.json()["restart_needed"]
    saved = envfile.read(isolated / ".env")
    assert saved["REMOTE_PC_JPEG_QUALITY"] == "70" and saved["REMOTE_PC_WEBRTC"] == "0" and saved["REMOTE_PC_RTC_FPS"] == "60"
    assert "EVIL" not in saved


def test_pin_lock_and_unlock():
    with local() as c:
        assert c.post("/panel/api/lock", headers=auth(), json={"locked": True}).status_code == 400   # no PIN yet
        assert c.post("/panel/api/pin", headers=auth(), json={"pin": "12ab"}).status_code == 400
        assert c.post("/panel/api/pin", headers=auth(), json={"pin": "4821"}).status_code == 200
        assert c.post("/panel/api/lock", headers=auth(), json={"locked": True}).status_code == 200
        assert c.get("/panel/api/state", headers=auth()).json()["lock"] == {"locked": True, "pin_set": True}
        assert c.post("/panel/api/lock", headers=auth(), json={"locked": False}).status_code == 200


def test_logs_only_known_files():
    with local() as c:
        assert c.get("/panel/api/logs/agent", headers=auth()).status_code == 200
        assert c.get("/panel/api/logs/..%2F.env", headers=auth()).status_code in (404, 422)


def test_windows_actions_report_clean_errors_elsewhere(monkeypatch):
    from app import winadmin
    monkeypatch.setattr(winadmin, "IS_WINDOWS", False)   # never touch the real firewall of the machine running the tests
    with local() as c:
        r = c.post("/panel/api/firewall", headers=auth(), json={"rule": "lan", "enabled": True})
        assert r.status_code == 400 and "Windows" in r.json()["detail"]


def test_envfile_keeps_other_lines(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\n# c\nB=2\n")
    envfile.update(p, {"B": "3", "C": "4"})
    assert p.read_text() == "A=1\n# c\nB=3\nC=4\n"
    with pytest.raises(ValueError): envfile.update(p, {"X\nY": "1"})
    for bad in ("a b", "ab", "q\"x", "a$b", "a#b", "back\\slash"):
        with pytest.raises(ValueError): envfile.validate_token(bad)
    assert envfile.validate_token("Good-pass_1.ok!") == "Good-pass_1.ok!"


def test_login_lockout_applies_to_panel():
    with local() as c:
        for _ in range(security.MAX_FAILS): c.get("/panel/api/state", headers={"Authorization": "Bearer bad"})
        assert c.get("/panel/api/state", headers=auth()).status_code == 429


def test_clear_log_empties_the_file_and_keeps_it_appendable(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "data_dir", lambda: tmp_path)
    log = tmp_path / "agent.log"
    writer = open(log, "a", buffering=1, encoding="utf-8")   # the running agent keeps its handle open and appends
    writer.write("old line 1\nold line 2\n")
    with local() as c:
        assert "old line 2" in c.get("/panel/api/logs/agent", headers=auth()).json()["text"]
        assert c.post("/panel/api/logs/agent/clear", headers=auth()).json() == {"ok": True}
        assert c.get("/panel/api/logs/agent", headers=auth()).json()["text"] == ""
        writer.write("new line\n"); writer.close()
        assert c.get("/panel/api/logs/agent", headers=auth()).json()["text"] == "new line\n"   # no gap of zero bytes
        assert c.post("/panel/api/logs/nope/clear", headers=auth()).status_code == 404
        assert c.post("/panel/api/logs/agent/clear", headers={}).status_code in (401, 403)


def test_state_reports_how_long_the_stream_has_run(monkeypatch):
    """The app window's Logs card shows a "Streaming mm:ss" tag from this."""
    from app import screen
    monkeypatch.setattr(screen, "_streams", {})
    with local() as c:
        assert c.get("/panel/api/state", headers=auth()).json()["streaming"] == {"active": False, "count": 0, "seconds": 0}
        clock = [1000.0]
        monkeypatch.setattr(screen.time, "monotonic", lambda: clock[0])
        screen.stream_begin("phone"); clock[0] += 75
        assert c.get("/panel/api/state", headers=auth()).json()["streaming"] == {"active": True, "count": 1, "seconds": 75}
        screen.stream_begin("phone")   # asking again must not restart the clock
        clock[0] += 5; screen.stream_begin("tablet"); clock[0] += 10
        assert c.get("/panel/api/state", headers=auth()).json()["streaming"] == {"active": True, "count": 2, "seconds": 90}   # the oldest stream counts
        screen.stream_end("phone"); screen.stream_end("nobody")   # ending an unknown key is harmless
        assert c.get("/panel/api/state", headers=auth()).json()["streaming"] == {"active": True, "count": 1, "seconds": 10}
        screen.stream_end("tablet")
        assert c.get("/panel/api/state", headers=auth()).json()["streaming"]["active"] is False
