import sys
from app import window


def test_window_not_available_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert window.available() is False
    assert window.open_window("http://127.0.0.1:8888/panel#x") is False   # caller then falls back to the browser


def test_window_falls_back_when_webview_fails(monkeypatch, tmp_path):
    import types
    fake = types.ModuleType("webview")
    def boom(*a, **k): raise RuntimeError("WebView2 missing")
    fake.create_window = boom
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.chdir(tmp_path)
    assert window.open_window("http://127.0.0.1:8888/panel#x") is False


def test_window_opens_edge_chromium_with_persistent_storage(monkeypatch, tmp_path):
    import types
    calls = {}
    fake = types.ModuleType("webview")
    fake.create_window = lambda title, url, **k: calls.update(url=url, title=title)
    fake.start = lambda **k: calls.update(start=k)
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.chdir(tmp_path)
    assert window.open_window("http://127.0.0.1:8888/panel#tok") is True
    assert calls["url"].endswith("/panel#tok") and calls["start"]["gui"] == "edgechromium" and calls["start"]["private_mode"] is False
