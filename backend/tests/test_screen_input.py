from types import SimpleNamespace as NS
from PIL import Image
import io
from app import screen
from app.config import settings

MON = {"left": 0, "top": 0, "width": 1920, "height": 1080}
MON2 = {"left": -1920, "top": 0, "width": 1920, "height": 1080}   # monitor placed left of origin
BTN = NS(left="L", right="R", middle="M")
MOUSE_MOD = NS(Button=BTN)
KEYS = {"CTRL": "<ctrl>", "C": "c-key", "ENTER": "<enter>", "ALT": "<alt>"}


class FakeMouse:
    def __init__(self): self.position = (0, 0); self.calls = []
    def click(self, b, n=1): self.calls.append(("click", b, n))
    def press(self, b): self.calls.append(("press", b))
    def release(self, b): self.calls.append(("release", b))
    def scroll(self, dx, dy): self.calls.append(("scroll", dx, dy))


class FakeKb:
    def __init__(self): self.calls = []
    def press(self, k): self.calls.append(("press", k))
    def release(self, k): self.calls.append(("release", k))
    def type(self, t): self.calls.append(("type", t))


def run(msg, mon=MON):
    m, k = FakeMouse(), FakeKb()
    screen.handle_input(msg, mon, m, k, MOUSE_MOD, KEYS)
    return m, k


def test_normalized_coords_map_to_screen_corners():
    assert screen.to_screen_xy({"nx": 0, "ny": 0}, MON) == (0, 0)
    assert screen.to_screen_xy({"nx": 1, "ny": 1}, MON) == (1919, 1079)
    assert screen.to_screen_xy({"nx": .5, "ny": .5}, MON) == (960, 540)


def test_coords_are_clamped_and_garbage_rejected():
    assert screen.to_screen_xy({"nx": 9, "ny": -3}, MON) == (1919, 0)
    assert screen.to_screen_xy({"nx": "abc", "ny": 0}, MON) is None
    assert screen.to_screen_xy({}, MON) is None


def test_monitor_offset_is_applied():
    assert screen.to_screen_xy({"nx": 0, "ny": 0}, MON2) == (-1920, 0)


def test_legacy_pixel_coords_still_work():
    assert screen.to_screen_xy({"x": 100, "y": 50}, MON) == (100, 50)
    assert screen.to_screen_xy({"x": 99999, "y": 99999}, MON) == (1919, 1079)


def test_tap_moves_then_left_clicks():
    m, _ = run({"type": "click", "nx": .5, "ny": .5})
    assert m.position == (960, 540) and m.calls == [("click", "L", 1)]


def test_right_and_double_click():
    assert run({"type": "click", "button": "right", "nx": 0, "ny": 0})[0].calls == [("click", "R", 1)]
    assert run({"type": "click", "count": 2, "nx": 0, "ny": 0})[0].calls == [("click", "L", 2)]


def test_drag_is_down_move_up():
    m, _ = run({"type": "down", "nx": .1, "ny": .1}); assert m.calls == [("press", "L")]
    m, _ = run({"type": "up", "nx": .9, "ny": .9}); assert m.calls == [("release", "L")] and m.position == (1727, 971)


def test_move_does_not_click():
    m, _ = run({"type": "move", "nx": .25, "ny": .25}); assert m.calls == [] and m.position == (480, 270)


def test_scroll_is_clamped_and_zero_ignored():
    assert run({"type": "scroll", "dy": 500})[0].calls == [("scroll", 0, 20)]
    assert run({"type": "scroll", "dy": -500, "dx": 3})[0].calls == [("scroll", 3, -20)]
    assert run({"type": "scroll", "dy": 0})[0].calls == []


def test_hotkey_presses_in_order_releases_reversed():
    _, k = run({"type": "hotkey", "keys": ["CTRL", "c"]})
    assert k.calls == [("press", "<ctrl>"), ("press", "c-key"), ("release", "c-key"), ("release", "<ctrl>")]


def test_hotkey_with_unknown_key_does_nothing():
    assert run({"type": "hotkey", "keys": ["CTRL", "NOPE"]})[1].calls == []


def test_key_and_type():
    assert run({"type": "key", "key": "ENTER"})[1].calls == [("press", "<enter>"), ("release", "<enter>")]
    assert run({"type": "type", "text": "x" * 900})[1].calls == [("type", "x" * 500)]


def test_unknown_message_ignored():
    m, k = run({"type": "format-c-drive"}); assert not m.calls and not k.calls


def test_encode_frame_downscales_and_overlays_cursor(monkeypatch):
    monkeypatch.setattr(settings, "max_width", 960)
    raw = bytes([20, 40, 60, 0]) * (1920 * 1080)          # BGRX solid colour
    jpeg, size = screen.encode_frame(raw, (1920, 1080), cursor=(100, 100))
    assert size == (960, 540)
    img = Image.open(io.BytesIO(jpeg)); assert img.size == (960, 540)
    assert img.getpixel((50 + 3, 50 + 6))[0] > 150        # white cursor pixel drawn near (50,50) after scaling
    assert img.getpixel((800, 400))[2] < 40               # background stays the original dark colour (blue channel 20)


def test_encode_frame_native_when_unlimited(monkeypatch):
    monkeypatch.setattr(settings, "max_width", 0)
    raw = bytes([0, 0, 0, 0]) * (320 * 200)
    assert screen.encode_frame(raw, (320, 200))[1] == (320, 200)


def test_input_socket_rejects_bad_token():
    import pytest
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from app.main import app
    with TestClient(app) as c, c.websocket_connect("/ws/input") as ws:
        ws.send_text('{"token":"wrong"}')
        with pytest.raises(WebSocketDisconnect) as e: ws.receive_text()
        assert e.value.code == 4401


def test_screen_socket_rejects_bad_token():
    import pytest
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from app.main import app
    with TestClient(app) as c, c.websocket_connect("/ws/screen") as ws:
        ws.send_text('{"token":"wrong"}')
        with pytest.raises(WebSocketDisconnect) as e: ws.receive_text()
        assert e.value.code == 4401


# ---- relative pointer movement ("rel", used by the Android trackpad) ----

def run_from(start, msg, mon=MON):
    m, k = FakeMouse(), FakeKb(); m.position = start
    screen.handle_input(msg, mon, m, k, MOUSE_MOD, KEYS)
    return m, k


def test_rel_moves_by_deltas_from_current_position():
    m, k = run_from((100, 200), {"type": "rel", "dx": 15, "dy": -30})
    assert m.position == (115, 170) and m.calls == [] and k.calls == []


def test_rel_is_clamped_to_monitor_edges():
    assert run_from((10, 10), {"type": "rel", "dx": -50, "dy": -50})[0].position == (0, 0)
    assert run_from((1900, 1070), {"type": "rel", "dx": 400, "dy": 400})[0].position == (1919, 1079)


def test_rel_is_clamped_per_message_to_500():
    assert run_from((100, 100), {"type": "rel", "dx": 9999, "dy": -9999})[0].position == (600, 0)
    assert run_from((1000, 600), {"type": "rel", "dx": 9999, "dy": 9999})[0].position == (1500, 1079)
    assert run_from((1000, 600), {"type": "rel", "dx": -9999, "dy": -9999})[0].position == (500, 100)


def test_rel_respects_monitor_offset():
    assert run_from((-1900, 5), {"type": "rel", "dx": -100, "dy": -100}, MON2)[0].position == (-1920, 0)
    assert run_from((-5, 5), {"type": "rel", "dx": 100, "dy": 0}, MON2)[0].position == (-1, 5)
    # pointer currently on another monitor is pulled back onto this one
    assert run_from((50, 50), {"type": "rel", "dx": 1, "dy": 1}, MON2)[0].position == (-1, 51)


def test_rel_zero_missing_and_garbage_do_nothing():
    for msg in ({"type": "rel"}, {"type": "rel", "dx": 0, "dy": 0},
                {"type": "rel", "dx": "abc", "dy": None}, {"type": "rel", "dx": float("nan"), "dy": float("inf")}):
        m, k = run_from((300, 300), msg)
        assert m.position == (300, 300) and not m.calls and not k.calls


def test_rel_one_axis_only_and_numeric_strings():
    assert run_from((10, 10), {"type": "rel", "dx": 7})[0].position == (17, 10)
    assert run_from((10, 10), {"type": "rel", "dx": "5", "dy": 2.9})[0].position == (15, 12)


def test_click_down_up_without_coords_act_at_current_position():
    m, _ = run_from((321, 123), {"type": "click", "button": "right"})
    assert m.position == (321, 123) and m.calls == [("click", "R", 1)]
    m, _ = run_from((321, 123), {"type": "down"}); assert m.position == (321, 123) and m.calls == [("press", "L")]
    m, _ = run_from((321, 123), {"type": "up"}); assert m.position == (321, 123) and m.calls == [("release", "L")]


def test_old_messages_unchanged_after_rel_added():
    assert run({"type": "move", "nx": .5, "ny": .5})[0].position == (960, 540)
    assert run({"type": "click", "count": 2, "nx": 0, "ny": 0})[0].calls == [("click", "L", 2)]
    assert run({"type": "scroll", "dy": 3})[0].calls == [("scroll", 0, 3)]


def test_moves_while_button_held_use_real_input_events(monkeypatch):
    moves = []
    monkeypatch.setattr(screen, "native_move", lambda x, y, mon: moves.append((x, y)) or True)
    m, k = FakeMouse(), FakeKb()
    screen.handle_input({"type": "down", "nx": .1, "ny": .1}, MON, m, k, MOUSE_MOD, KEYS)
    assert moves == [] and m.position == (192, 108)            # nothing held yet: plain move, then press
    screen.handle_input({"type": "move", "nx": .5, "ny": .5}, MON, m, k, MOUSE_MOD, KEYS)
    screen.handle_input({"type": "rel", "dx": 10, "dy": 0}, MON, m, k, MOUSE_MOD, KEYS)
    assert moves == [(960, 540), (202, 108)] and m.position == (192, 108)   # held: real input events, SetCursorPos untouched
    screen.handle_input({"type": "up", "nx": .9, "ny": .9}, MON, m, k, MOUSE_MOD, KEYS)
    assert moves[-1] == (1727, 971) and m.calls == [("press", "L"), ("release", "L")]
    screen.handle_input({"type": "move", "nx": 0, "ny": 0}, MON, m, k, MOUSE_MOD, KEYS)
    assert m.position == (0, 0)                                 # released: back to the plain move


def test_release_held_lets_go_of_a_stuck_button():
    m, k = FakeMouse(), FakeKb()
    screen.handle_input({"type": "down", "nx": 0, "ny": 0}, MON, m, k, MOUSE_MOD, KEYS)
    screen.release_held(m)
    assert m.calls == [("press", "L"), ("release", "L")]
    screen.release_held(m); assert len(m.calls) == 2
