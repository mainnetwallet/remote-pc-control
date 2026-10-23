"""Live stream configuration on /ws/screen: {"type":"config","max_width":..,"fps":..,"quality":..}."""
import asyncio, contextlib, io, os

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app import screen
from app.config import settings
from app.main import app
from app.screen import StreamConfig

W, H = 800, 450
RAW = bytes([20, 40, 60, 0]) * (W * H)   # solid BGRX frame


@pytest.fixture(autouse=True)
def server_defaults(monkeypatch):
    monkeypatch.setattr(settings, "max_width", 1280)
    monkeypatch.setattr(settings, "fps", 10)
    monkeypatch.setattr(settings, "jpeg_quality", 55)


def fake_grab():
    return RAW, (W, H), None, 1       # constant digest: the screen never "changes"


# ---- clamping -------------------------------------------------------------

def test_defaults_come_from_settings():
    assert StreamConfig.from_settings() == StreamConfig(1280, 10, 55)


@pytest.mark.parametrize("msg, expected", [
    ({"max_width": 1920, "fps": 15, "quality": 70}, (1920, 15, 70)),
    ({"max_width": 0}, (0, 10, 55)),                       # 0 = native
    ({"max_width": 1}, (320, 10, 55)),                     # below the minimum -> 320
    ({"max_width": 319}, (320, 10, 55)),
    ({"max_width": 320}, (320, 10, 55)),
    ({"max_width": 3840}, (3840, 10, 55)),
    ({"max_width": 99999}, (3840, 10, 55)),
    ({"max_width": -5}, (0, 10, 55)),                      # negative -> native
    ({"fps": 0}, (1280, 1, 55)),
    ({"fps": -3}, (1280, 1, 55)),
    ({"fps": 31}, (1280, 30, 55)),
    ({"fps": 1000}, (1280, 30, 55)),
    ({"quality": 1}, (1280, 10, 25)),
    ({"quality": 24}, (1280, 10, 25)),
    ({"quality": 91}, (1280, 10, 90)),
    ({"quality": 90}, (1280, 10, 90)),
    ({"fps": 14.6, "quality": "70", "max_width": "1920"}, (1920, 15, 70)),   # floats / numeric strings
])
def test_config_values_are_clamped(msg, expected):
    c = StreamConfig.from_settings().updated({"type": "config", **msg})
    assert (c.max_width, c.fps, c.quality) == expected


@pytest.mark.parametrize("msg", [
    {}, {"fps": "fast"}, {"fps": None}, {"fps": True}, {"quality": float("nan")},
    {"max_width": float("inf")}, {"max_width": [1920]}, {"fps": {"x": 1}}, {"quality": 10 ** 400},
])
def test_garbage_fields_are_ignored(msg):
    assert StreamConfig.from_settings().updated({"type": "config", **msg}) == StreamConfig(1280, 10, 55)


def test_fields_are_independent_and_cumulative():
    c = StreamConfig.from_settings().updated({"fps": 20}).updated({"quality": 80}).updated({"max_width": 0})
    assert c == StreamConfig(0, 20, 80)


# ---- encode_frame ---------------------------------------------------------

def test_encode_frame_uses_explicit_width_and_defaults(monkeypatch):
    assert screen.encode_frame(RAW, (W, H))[1] == (800, 450)                       # settings.max_width 1280 > 800
    assert screen.encode_frame(RAW, (W, H), max_width=400)[1] == (400, 225)
    assert screen.encode_frame(RAW, (W, H), max_width=0)[1] == (800, 450)          # 0 = native, not "use default"
    monkeypatch.setattr(settings, "max_width", 400)
    assert screen.encode_frame(RAW, (W, H))[1] == (400, 225)                       # None -> server setting


def test_encode_frame_quality_changes_jpeg_size():
    noise = os.urandom(4 * 320 * 200)
    small = screen.encode_frame(noise, (320, 200), max_width=0, quality=25)[0]
    large = screen.encode_frame(noise, (320, 200), max_width=0, quality=90)[0]
    assert len(large) > len(small) * 1.5
    assert Image.open(io.BytesIO(large)).size == (320, 200)


# ---- /ws/screen end to end (fake capture, so it runs on any OS) ------------

@pytest.fixture
def stream(monkeypatch):
    monkeypatch.setattr(screen, "_on_windows", lambda: True)
    monkeypatch.setattr(screen, "_capture_source", lambda: contextlib.nullcontext(fake_grab))
    with TestClient(app) as client, client.websocket_connect("/ws/screen") as ws:
        ws.send_json({"token": settings.token})
        assert ws.receive_json() == {"type": "ready"}
        yield ws


def jpeg_size(data: bytes):
    return Image.open(io.BytesIO(data)).size


def test_stream_starts_with_unchanged_defaults(stream):
    msg = stream.receive_json()
    assert msg == {"type": "screen", "width": 800, "height": 450, "max_width": 1280, "fps": 10, "quality": 55}
    assert jpeg_size(stream.receive_bytes()) == (800, 450)


def test_config_is_applied_live_and_answered_with_fresh_screen_message(stream):
    stream.receive_json(); stream.receive_bytes()
    stream.send_json({"type": "config", "max_width": 400, "fps": 5, "quality": 40})
    assert stream.receive_json() == {"type": "screen", "width": 400, "height": 225, "max_width": 400, "fps": 5, "quality": 40}
    assert jpeg_size(stream.receive_bytes()) == (400, 225)
    # same size again still gets an answer (the client asked for it)
    stream.send_json({"type": "config", "quality": 80})
    assert stream.receive_json() == {"type": "screen", "width": 400, "height": 225, "max_width": 400, "fps": 5, "quality": 80}
    assert jpeg_size(stream.receive_bytes()) == (400, 225)
    stream.send_json({"type": "config", "max_width": 0})
    assert stream.receive_json()["width"] == 800
    assert jpeg_size(stream.receive_bytes()) == (800, 450)


def test_out_of_range_config_is_clamped_in_the_reply(stream):
    stream.receive_json(); stream.receive_bytes()
    stream.send_json({"type": "config", "max_width": 10, "fps": 99, "quality": 5})
    assert stream.receive_json() == {"type": "screen", "width": 320, "height": 180, "max_width": 320, "fps": 30, "quality": 25}
    stream.receive_bytes()
    stream.send_json({"type": "config", "max_width": 99999, "fps": 0, "quality": 500})
    reply = stream.receive_json()
    assert (reply["max_width"], reply["fps"], reply["quality"], reply["width"]) == (3840, 1, 90, 800)   # never upscales


def test_junk_messages_do_not_break_the_stream(stream):
    stream.receive_json(); stream.receive_bytes()
    stream.send_text("not json"); stream.send_text("[1,2,3]"); stream.send_json({"type": "nope"}); stream.send_bytes(b"\x00\x01")
    stream.send_json({"type": "config", "fps": "fast"})            # unusable field: ignored, still answered
    assert stream.receive_json() == {"type": "screen", "width": 800, "height": 450, "max_width": 1280, "fps": 10, "quality": 55}
    assert jpeg_size(stream.receive_bytes()) == (800, 450)


def test_stream_ends_when_client_disconnects():
    class FakeWS:
        def __init__(self): self.inbox = asyncio.Queue(); self.sent = []
        async def receive(self): return await self.inbox.get()
        async def send_json(self, d): self.sent.append(d)
        async def send_bytes(self, b): self.sent.append(b)

    async def run():
        ws = FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, fake_grab))
        await asyncio.sleep(0.2)
        ws.inbox.put_nowait({"type": "websocket.receive", "text": '{"type":"config","fps":2}'})
        await asyncio.sleep(0.2)
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)                            # must return, not hang
        return ws.sent
    sent = asyncio.run(run())
    screens = [m for m in sent if isinstance(m, dict)]
    assert [m["fps"] for m in screens] == [10, 2]


# ---- latency: flow control, adaptive quality, input coalescing ---------------

class _FakeWS:
    def __init__(self): self.inbox = asyncio.Queue(); self.sent = []
    async def receive(self): return await self.inbox.get()
    async def send_json(self, d): self.sent.append(d)
    async def send_bytes(self, b): self.sent.append(b)
    def say(self, text): self.inbox.put_nowait({"type": "websocket.receive", "text": text})


def _changing_grab():
    n = [0]
    def grab():
        n[0] += 1
        return RAW, (W, H), None, n[0]     # a new digest every time: the screen always changed
    return grab


def _frames(ws): return [m for m in ws.sent if isinstance(m, bytes)]


def test_without_acks_the_stream_keeps_its_fixed_rate(monkeypatch):
    monkeypatch.setattr(settings, "fps", 30)
    async def run():
        ws = _FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, _changing_grab()))
        await asyncio.sleep(0.5)
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)
        return len(_frames(ws))
    assert asyncio.run(run()) > screen.MAX_IN_FLIGHT + 2      # old clients are not throttled


def test_with_acks_at_most_two_frames_are_in_flight(monkeypatch):
    monkeypatch.setattr(settings, "fps", 30)
    async def run():
        ws = _FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, _changing_grab()))
        ws.say('{"type":"ack"}')                               # the client speaks ack: flow control is on
        await asyncio.sleep(0.5)
        waiting = len(_frames(ws))
        ws.say('{"type":"ack"}'); await asyncio.sleep(0.3)     # one frame shown: exactly one more is sent
        after = len(_frames(ws))
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)
        return waiting, after
    waiting, after = asyncio.run(run())
    assert waiting == screen.MAX_IN_FLIGHT and after == waiting + 1


def test_stream_resumes_if_the_client_stops_acking(monkeypatch):
    monkeypatch.setattr(settings, "fps", 30)
    monkeypatch.setattr(screen, "ACK_TIMEOUT", 0.2)
    async def run():
        ws = _FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, _changing_grab()))
        ws.say('{"type":"ack"}')
        await asyncio.sleep(0.8)                               # no more acks: must not stall forever
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)
        return len(_frames(ws))
    assert asyncio.run(run()) > screen.MAX_IN_FLIGHT


@pytest.mark.parametrize("rtt, expected", [(0.0, 65), (0.1, 65), (0.25, 53), (0.5, 40), (2.0, 40)])
def test_quality_drops_when_frames_arrive_slowly(rtt, expected):
    assert screen.adaptive_quality(65, rtt) == expected
    assert screen.adaptive_quality(30, 5.0) == screen.QUALITY_MIN


def test_coalesce_merges_pointer_moves_but_keeps_clicks_in_order():
    msgs = [{"type": "rel", "dx": 3, "dy": 1}, {"type": "rel", "dx": 4, "dy": -2},
            {"type": "click", "button": "left"},
            {"type": "rel", "dx": 1, "dy": 1}, {"type": "move", "nx": 0.1, "ny": 0.1}, {"type": "move", "nx": 0.5, "ny": 0.5},
            {"type": "scroll", "dy": 2}]
    out = screen.coalesce_input(msgs)
    assert out == [{"type": "rel", "dx": 7, "dy": -1}, {"type": "click", "button": "left"},
                   {"type": "rel", "dx": 1, "dy": 1}, {"type": "move", "nx": 0.5, "ny": 0.5}, {"type": "scroll", "dy": 2}]
    assert msgs[0] == {"type": "rel", "dx": 3, "dy": 1}        # input list is left untouched


# ---- smoothness: latency-aware window, fps cap, pipelined capture/encode -----------

@pytest.mark.parametrize("base_rtt, fps, expected", [
    (0.0, 30, 2),      # unknown latency: the old minimum
    (0.02, 30, 2),     # LAN
    (0.15, 15, 4),     # tunnel, moderate rate
    (0.15, 30, 6),     # tunnel, full rate
    (1.5, 30, 6),      # never above MAX_WINDOW
])
def test_flight_window_covers_the_link_round_trip(base_rtt, fps, expected):
    assert screen.flight_window(base_rtt, fps) == expected


def test_steady_high_latency_is_not_mistaken_for_congestion():
    st = screen._StreamState()
    for _ in range(10): st.rtts.append(0.25)
    st.rtt = 0.25
    assert st.base_rtt == 0.25 and st.queue_delay() == 0.0
    assert screen.adaptive_quality(65, st.queue_delay()) == 65       # quality is kept on a slow but steady tunnel
    st.rtt = 0.25 + 0.4                                              # frames now wait in a queue
    assert screen.adaptive_quality(65, st.queue_delay()) == 40


def test_base_latency_needs_a_few_samples():
    st = screen._StreamState()
    st.rtts.append(0.5)
    assert st.base_rtt == 0.0 and st.window(30) == screen.MAX_IN_FLIGHT


async def _run_acking_client(grab, seconds, ack_delay):
    """A client that shows every frame ack_delay seconds after it was sent. Returns how many frames the server sent."""
    ws = _FakeWS()
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(screen.stream_frames(ws, grab))
    seen = 0
    async def client():
        nonlocal seen
        while True:
            while len(_frames(ws)) > seen:
                seen += 1
                loop.call_later(ack_delay, ws.say, '{"type":"ack"}')   # acks overlap, like frames on a real link
            await asyncio.sleep(0.002)
    c = asyncio.create_task(client())
    await asyncio.sleep(seconds)
    c.cancel()
    ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
    await asyncio.wait_for(task, 3)
    return len(_frames(ws))


def test_acks_do_not_push_the_stream_past_the_fps_cap(monkeypatch):
    monkeypatch.setattr(settings, "fps", 10)
    n = asyncio.run(_run_acking_client(_changing_grab(), 1.0, 0.0))
    assert 7 <= n <= 12          # about 10 frames in a second, however fast the client acks


def test_high_latency_link_still_reaches_the_target_fps(monkeypatch):
    monkeypatch.setattr(settings, "fps", 30)
    n = asyncio.run(_run_acking_client(_changing_grab(), 1.5, 0.15))
    # two frames per 150 ms round trip would give ~20 frames in 1.5 s; the wider window must beat that clearly
    assert n > 32


def test_capture_and_encode_overlap_when_the_pc_is_the_bottleneck(monkeypatch):
    monkeypatch.setattr(settings, "fps", 30)
    real_encode = screen.encode_frame
    def slow_grab_factory():
        n = [0]
        def grab():
            import time; time.sleep(0.04); n[0] += 1
            return RAW, (W, H), None, n[0]
        return grab
    def slow_encode(*a, **k):
        import time; time.sleep(0.04); return real_encode(*a, **k)
    monkeypatch.setattr(screen, "encode_frame", slow_encode)
    async def run():
        ws = _FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, slow_grab_factory()))
        await asyncio.sleep(1.5)
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)
        return len(_frames(ws))
    n = asyncio.run(run())
    assert n > 1.5 / 0.08 * 1.3     # clearly faster than one 80 ms capture+encode after the other (~18 frames)


def test_capture_is_released_on_the_capture_thread():
    import threading
    seen = {}
    def grab():
        seen["grab"] = threading.get_ident(); return RAW, (W, H), None, 1
    def close(): seen["close"] = threading.get_ident()
    grab.close = close
    async def run():
        ws = _FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, grab))
        await asyncio.sleep(0.2)
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)
    asyncio.run(run())
    assert seen["grab"] == seen["close"] != threading.get_ident()


# ---- pointer: separate cursor stream, frames without the pointer for clients that draw it -----

def test_cursor_message_is_normalized_and_clamped():
    mon = {"left": 0, "top": 0, "width": 1920, "height": 1080}
    assert screen.cursor_message((0, 0), mon) == {"type": "cursor", "nx": 0.0, "ny": 0.0, "w": 1920, "h": 1080}
    assert screen.cursor_message((1919, 1079), mon)["nx"] == 1.0
    assert screen.cursor_message((960, 540), mon)["nx"] == round(960 / 1919, 4)
    assert screen.cursor_message((-50, 99999), mon)["nx"] == 0.0 and screen.cursor_message((-50, 99999), mon)["ny"] == 1.0
    off = {"left": -1920, "top": 0, "width": 1920, "height": 1080}
    assert screen.cursor_message((-1920, 0), off)["nx"] == 0.0


def test_cursor_is_pushed_on_change_and_as_heartbeat(monkeypatch):
    monkeypatch.setattr(screen, "CURSOR_HEARTBEAT", 0.15)
    class Mouse: position = (10, 20)
    mon = {"left": 0, "top": 0, "width": 101, "height": 201}
    async def run():
        ws = _FakeWS(); m = Mouse()
        task = asyncio.create_task(screen._push_cursor(ws, m, mon))
        await asyncio.sleep(0.1)
        first = len(ws.sent)
        m.position = (50, 100); await asyncio.sleep(0.1)
        moved = ws.sent[first:]
        await asyncio.sleep(0.4)                                  # idle: only heartbeats
        idle = len(ws.sent) - first - len(moved)
        task.cancel()
        return first, moved, idle
    first, moved, idle = asyncio.run(run())
    assert first == 1                                             # initial position, then nothing while unchanged
    assert moved and moved[0]["nx"] == 0.5 and moved[0]["ny"] == 0.5
    assert 1 <= idle <= 4                                         # a few heartbeats, not 60/s


def _cursor_grab():
    """Same pixels every time, the pointer moves: what dragging a finger on the trackpad looks like."""
    n = [0]
    def grab():
        n[0] += 1
        return RAW, (W, H), (n[0] % 50, 5), 7
    return grab


def _decode_top_left(jpeg):
    return Image.open(io.BytesIO(jpeg)).convert("RGB").getpixel((1, 1))


def test_pointer_only_changes_still_stream_frames_for_old_clients(monkeypatch):
    monkeypatch.setattr(settings, "fps", 30)
    async def run():
        ws = _FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, _cursor_grab()))
        await asyncio.sleep(0.4)
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)
        return len(_frames(ws))
    assert asyncio.run(run()) > 3


def test_overlay_clients_get_no_frames_for_pointer_only_changes_and_no_baked_pointer(monkeypatch):
    monkeypatch.setattr(settings, "fps", 30)
    async def run():
        ws = _FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, _cursor_grab()))
        ws.say('{"type":"config","cursor":true}')
        await asyncio.sleep(0.5)
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)
        return _frames(ws)
    frames = asyncio.run(run())
    assert 1 <= len(frames) <= 3                      # the config answer, not one frame per pointer move
    pix = Image.open(io.BytesIO(frames[-1])).convert("RGB")
    assert len({pix.getpixel((x, 5)) for x in range(0, 40)}) == 1   # no white arrow drawn into the picture
