import socket, threading, time
import pytest
from app import gui
from app.gui_text import TEXT


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


@pytest.fixture
def server(monkeypatch, tmp_path):
    """The real agent app on a free local port, so the window's client is tested against the real panel API."""
    import uvicorn
    from app.config import settings
    from app.main import app
    from app import panel
    monkeypatch.setattr(settings, "token", "test-token-" + "x" * 30)
    monkeypatch.setattr(panel, "env_path", lambda: tmp_path / ".env")
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); break
        except OSError: time.sleep(0.1)
    yield port, settings.token
    srv.should_exit = True; th.join(5)


def test_client_talks_to_the_panel_api(server):
    port, token = server
    c = gui.PanelClient(port, token)
    s = c.call("/state")
    assert s["port"] and s["hostname"] and isinstance(s["fields"], list) and "lock" in s
    assert c.call("/logs/agent") == {"text": ""} or "text" in c.call("/logs/agent")
    assert c.call("/token")["token"] == token
    c.call("/settings", "POST", {"values": {"REMOTE_PC_RTC_FPS": "60"}})
    assert next(f for f in c.call("/state")["fields"] if f["key"] == "REMOTE_PC_RTC_FPS")["value"] == "60"


def test_client_errors(server):
    port, token = server
    with pytest.raises(gui.ApiError) as e: gui.PanelClient(port, "wrong-token").call("/state")
    assert e.value.status == 401
    with pytest.raises(gui.ApiError) as e: gui.PanelClient(port, token).call("/settings", "POST", {"values": {"REMOTE_PC_RTC_FPS": "99"}})
    assert "choose one of" in str(e.value)
    with pytest.raises(gui.ApiError) as e: gui.PanelClient(_free_port(), token).call("/state", timeout=2)   # nothing listens
    assert str(e.value) == ""   # the window then shows its own "cannot reach the agent" text


class FakeClient:
    token = "secret-token-123"
    def call(self, path, method="GET", body=None, timeout=60):
        if path == "/state":
            return {"hostname": "MY-PC", "port": 8888, "elevated": True, "installed": True,
                    "addresses": [{"ip": "100.64.0.5", "kind": "tailscale"}, {"ip": "192.168.1.7", "kind": "lan"}],
                    "fields": [{"key": "REMOTE_PC_RTC_FPS", "kind": "choice", "default": "auto", "value": "60", "options": ["auto", "30", "60"]},
                               {"key": "REMOTE_PC_RTC_BITRATE", "kind": "int", "default": "4000", "value": "4000", "min": 300, "max": 30000},
                               {"key": "REMOTE_PC_WEBRTC", "kind": "bool", "default": "1", "value": "1"}],
                    "lock": {"locked": False, "pin_set": True}, "tunnel": {"supported": True, "installed": True, "running": False, "url": None, "error": ""}}
        if path == "/system":
            return {"supported": True, "task_tools": True, "autostart": {"exists": True}, "lock_task": {"exists": False},
                    "fw_tailscale": {"exists": True}, "fw_lan": {"exists": False}}
        if path.startswith("/logs/"): return {"text": "agent started\n"}
        if path == "/token": return {"token": self.token}
        return {"ok": True}


@pytest.fixture
def window():
    tk = pytest.importorskip("tkinter")
    try: root = tk.Tk()
    except tk.TclError: pytest.skip("no display")
    root.withdraw()
    yield root
    root.destroy()


def _settle(root, seconds=1.0):
    end = time.time() + seconds
    while time.time() < end: root.update(); time.sleep(0.02)


def test_window_builds_and_shows_state(window, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = gui.App(window, FakeClient())
    _settle(window)
    assert len(app.nb.tabs()) == 6
    assert app.host_pill.cget("text") == "MY-PC" and "yes" in app.admin_pill.cget("text").lower()
    assert len(app.addr_box.winfo_children()) == 2
    assert app.v_auto.get() is True and app.v_fwlan.get() is False
    assert set(app.field_vars) == {"REMOTE_PC_RTC_FPS", "REMOTE_PC_RTC_BITRATE", "REMOTE_PC_WEBRTC"}
    assert "agent started" in app.log_text.get("1.0", "end")
    assert len(app.field_vars) == 3


def test_window_toggle_failure_reverts_switch(window, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class Failing(FakeClient):
        def call(self, path, method="GET", body=None, timeout=60):
            if path == "/firewall": raise gui.ApiError("Access denied")
            return super().call(path, method, body, timeout)
    app = gui.App(window, Failing())
    _settle(window, 0.6)
    app.v_fwlan.set(True); app.toggle(app.v_fwlan, app.c_fwlan, lambda on: app.client.call("/firewall", "POST", {"rule": "lan", "enabled": on}))
    _settle(window, 0.8)
    assert app.v_fwlan.get() is False and "Access denied" in app.status.cget("text")


def test_server_bar_on_off_and_on_again(window, tmp_path, monkeypatch):
    """Turn the server off from the window (it stays open), then turn it on again."""
    import tkinter.messagebox as mb
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mb, "askokcancel", lambda *a, **k: True)
    started = []
    monkeypatch.setattr(gui, "start_server", lambda: started.append(1))
    calls = []
    class Switchable(FakeClient):
        up = True
        def call(self, path, method="GET", body=None, timeout=60):
            if not self.up: raise gui.ApiError("")
            if path == "/quit": calls.append(path); self.up = False; return {"ok": True}
            return super().call(path, method, body, timeout)
    client = Switchable()
    app = gui.App(window, client)
    _settle(window, 0.8)
    assert "ON" in app.srv_pill.cget("text") and "Turn off" in app.srv_btn.cget("text")
    app.toggle_server(); _settle(window, 0.4)
    assert calls == ["/quit"] and "stopping" in app.srv_pill.cget("text")   # a late answer from the dying server is ignored
    app.stop_until = 0; app.poll(); _settle(window, 0.6)
    assert app.online is False and "OFF" in app.srv_pill.cget("text") and "Turn on" in app.srv_btn.cget("text")
    assert app.srv_note.cget("text")   # tells that the phone cannot connect now
    client.up = True
    app.toggle_server(); _settle(window, 0.4)
    assert started == [1] and "starting" in app.srv_pill.cget("text")
    app.poll(); _settle(window, 0.8)   # the server answers again: the window loads everything again
    assert app.online is True and "ON" in app.srv_pill.cget("text") and app.host_pill.cget("text") == "MY-PC"


def test_window_opens_while_server_is_still_starting(window, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class Down(FakeClient):
        def call(self, *a, **k): raise gui.ApiError("")
    app = gui.App(window, Down(), starting=True)
    _settle(window, 0.8)
    assert "starting" in app.srv_pill.cget("text") and app.status.cget("text") == ""   # no error pop-up while it starts


def test_start_server_launches_a_background_copy(monkeypatch):
    import subprocess, sys
    seen = {}
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: seen.update(cmd=cmd, **kw))
    gui.start_server()
    assert seen["cmd"][0] == sys.executable and seen["cmd"][-1] == "--background"
    assert seen["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_packaged_window_selftest_flag(window, tmp_path):
    """run_agent.py --gui-selftest is what the Windows build runs on the finished exe."""
    import subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "result.txt"
    r = subprocess.run([sys.executable, str(root / "run_agent.py"), "--gui-selftest", str(out)], cwd=tmp_path, timeout=60,
                       env={**__import__("os").environ, "PYTHONPATH": str(root / "backend")})
    assert r.returncode == 0 and out.read_text().startswith("ok tk=")


def test_clear_logs_button_calls_the_api_and_reloads(window, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    class Logs(FakeClient):
        def call(self, path, method="GET", body=None, timeout=60):
            if path.endswith("/clear"): calls.append((method, path)); return {"ok": True}
            return super().call(path, method, body, timeout)
    app = gui.App(window, Logs())
    _settle(window, 0.6)
    app.log_sel.set("lock"); app.clear_log(); _settle(window, 0.6)
    assert calls == [("POST", "/logs/lock/clear")]
    assert "cleared" in app.status.cget("text").lower()
