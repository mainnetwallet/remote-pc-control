"""REMOTE_PC_FPS / REMOTE_PC_RTC_FPS: numbers are clamped, "auto" follows the monitor up to FPS_CEILING."""
import pytest

from app import config
from app.config import FPS_CEILING, WS_FPS_CEILING, fps_setting


@pytest.mark.parametrize("raw,expected", [("30", 30), ("60", 60), ("500", FPS_CEILING), ("0", None), ("-5", 1), (" 45 ", 45)])
def test_numbers(raw, expected, monkeypatch):
    monkeypatch.setattr(config, "monitor_hz", lambda: 144)
    assert fps_setting(raw, "20") == (FPS_CEILING if expected is None else expected)


@pytest.mark.parametrize("hz", [144, 75, 60, 30, None])
def test_auto_follows_the_monitor(hz, monkeypatch):
    monkeypatch.setattr(config, "monitor_hz", lambda: hz)
    assert fps_setting("auto", "20") == min(FPS_CEILING, hz or FPS_CEILING)


def test_websocket_ceiling_is_lower_than_webrtc(monkeypatch):
    monkeypatch.setattr(config, "monitor_hz", lambda: 144)
    assert fps_setting("auto", "20", WS_FPS_CEILING) == WS_FPS_CEILING == 60
    assert fps_setting("auto", "20") == FPS_CEILING == 120
    assert fps_setting("500", "20", WS_FPS_CEILING) == 60


def test_empty_and_garbage_use_the_default(monkeypatch):
    monkeypatch.setattr(config, "monitor_hz", lambda: 144)
    assert fps_setting("", "20") == 20
    assert fps_setting("fast", "20") == 20
    assert fps_setting("", "auto") == FPS_CEILING
