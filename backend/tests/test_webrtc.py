"""WebRTC transport tests. Capture, input devices and the peer connection are mocked: no real network, no real screen."""
import asyncio, contextlib, json, sys, threading
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import screen, security, webrtc, webrtc_encoder
from app.config import settings
from app.main import app

MON = {"left": 0, "top": 0, "width": 1920, "height": 1080}
GOOD_SDP = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\n"


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    webrtc._sessions.clear(); webrtc_encoder.Limits.reset()
    monkeypatch.setattr(settings, "webrtc", True)
    monkeypatch.setattr(screen, "_on_windows", lambda: True)
    yield
    webrtc._sessions.clear(); webrtc_encoder.Limits.reset()


# ---------------------------------------------------------------- fakes

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


class FakeChannel:
    def __init__(self, label): self.label = label; self.readyState = "open"; self.sent = []; self.handlers = {}; self.closed = False
    def on(self, name, fn=None):
        if fn is None: return lambda f: self.handlers.__setitem__(name, f) or f
        self.handlers[name] = fn
    def send(self, data): self.sent.append(json.loads(data))
    def close(self): self.closed = True; self.readyState = "closed"


def fake_backend():
    mouse, kb = FakeMouse(), FakeKb()
    mod = NS(Button=NS(left="L", right="R", middle="M"))
    return mouse, kb, mod, {"ENTER": "<enter>", "CTRL": "<ctrl>", "C": "c"}


class FakeCapture:
    """capture_factory: a context manager yielding grab(); records the thread it ran on and when it was closed."""
    def __init__(self, size=(64, 48)):
        self.size = size; self.n = 0; self.change = True; self.threads = set(); self.closed_on = None; self.opened = 0
    def __call__(self):
        outer = self
        @contextlib.contextmanager
        def cm():
            outer.opened += 1
            def grab():
                outer.threads.add(threading.get_ident())
                if outer.change: outer.n += 1
                w, h = outer.size
                return bytes([outer.n % 256, 0, 0, 255]) * (w * h), (w, h), None, outer.n
            try: yield grab
            finally: outer.closed_on = threading.get_ident()
        return cm()


def make_session(**kw):
    backend = {}
    def factory():
        backend["b"] = fake_backend(); return backend["b"]
    s = webrtc.RtcSession(input_backend=factory, monitor_factory=lambda: dict(MON), **kw)
    s._backend_box = backend
    return s


async def started(session, label="control", also=("input",)):
    chans = {}
    for name in (label, *also):
        ch = FakeChannel(name); session._on_datachannel(ch); chans[name] = ch
    for _ in range(100):
        if session.sink.mon is not None: break
        await asyncio.sleep(0.01)
    return chans


async def settle(session, ticks=5):
    for _ in range(ticks): await asyncio.sleep(0.01)


def _short_id(v):
    """Test ids stay short: a 64 KB parameter would overflow Windows' 32767-character environment variable limit
    (pytest stores the running test's id in PYTEST_CURRENT_TEST)."""
    if isinstance(v, (str, bytes)): return v if len(v) <= 40 else f"{type(v).__name__}-len{len(v)}"
    return None


# ---------------------------------------------------------------- signaling message validation

def test_parse_offer_ok_and_normalized():
    assert webrtc.parse_signal(json.dumps({"type": "offer", "sdp": GOOD_SDP, "junk": 1})) == {"type": "offer", "sdp": GOOD_SDP}


@pytest.mark.parametrize("text", [
    "not json", "[]", "42", "null", '{"type":"offer"}', '{"type":"offer","sdp":""}', '{"type":"offer","sdp":5}',
    json.dumps({"type": "offer", "sdp": "hello"}),                                  # not an SDP
    json.dumps({"type": "offer", "sdp": "v=0\r\nm=audio 9 RTP/AVP 0\r\n"}),         # no video section
    json.dumps({"type": "offer", "sdp": GOOD_SDP + "a" * webrtc.MAX_SDP_BYTES}),    # too large
    '{"type":"nope"}', "{}", json.dumps({"type": ["offer"]}),
    json.dumps({"type": "candidate", "candidate": "not-a-candidate"}),
    json.dumps({"type": "candidate", "candidate": {"candidate": "candidate:1 1 udp 1 1.2.3.4 5 typ host", "sdpMLineIndex": "0"}}),
    json.dumps({"type": "candidate", "candidate": {"candidate": "candidate:1 1 udp 1 1.2.3.4 5 typ host", "sdpMLineIndex": True}}),
    json.dumps({"type": "candidate", "candidate": {"candidate": "candidate:1 1 udp 1 1.2.3.4 5 typ host", "sdpMLineIndex": 99}}),
    json.dumps({"type": "candidate", "candidate": {"candidate": "candidate:" + "9" * 5000}}),
    json.dumps({"type": "candidate", "candidate": {"candidate": "candidate:1 1 udp 1 1.2.3.4 5 typ host", "sdpMid": 7}}),
], ids=_short_id)
def test_parse_rejects_malformed(text):
    with pytest.raises(webrtc.SignalError): webrtc.parse_signal(text)


def test_parse_rejects_non_text():
    with pytest.raises(webrtc.SignalError): webrtc.parse_signal(b"{}")


def test_parse_candidate_forms():
    line = "candidate:1 1 udp 2130706431 192.168.1.5 50000 typ host"
    nested = webrtc.parse_signal(json.dumps({"type": "candidate", "candidate": {"candidate": line, "sdpMid": "0", "sdpMLineIndex": 0}}))
    assert nested == {"type": "candidate", "candidate": line, "sdpMid": "0", "sdpMLineIndex": 0}
    flat = webrtc.parse_signal(json.dumps({"type": "candidate", "candidate": line, "sdpMid": "1", "sdpMLineIndex": 1}))
    assert flat["sdpMid"] == "1" and flat["sdpMLineIndex"] == 1
    assert webrtc.parse_signal(json.dumps({"type": "candidate", "candidate": line}))["sdpMLineIndex"] == 0
    for end in (None, "", {"candidate": ""}):
        assert webrtc.parse_signal(json.dumps({"type": "candidate", "candidate": end})) == {"type": "candidate", "candidate": None}
    assert webrtc.parse_signal('{"type":"bye"}') == {"type": "bye"}


# ---------------------------------------------------------------- ICE servers

def test_ice_servers_default_stun_only(monkeypatch):
    monkeypatch.setattr(settings, "turn_url", "")
    assert webrtc.ice_servers() == [{"urls": ["stun:stun.l.google.com:19302"]}]


def test_ice_servers_with_turn_and_custom_stun(monkeypatch):
    monkeypatch.setattr(settings, "stun_urls", ["stun:a.example:3478", "stun:b.example:3478"])
    monkeypatch.setattr(settings, "turn_url", "turn:turn.example:3478")
    monkeypatch.setattr(settings, "turn_user", "u"); monkeypatch.setattr(settings, "turn_pass", "p")
    assert webrtc.ice_servers() == [{"urls": ["stun:a.example:3478", "stun:b.example:3478"]},
                                    {"urls": "turn:turn.example:3478", "username": "u", "credential": "p"}]
    monkeypatch.setattr(settings, "stun_urls", [])
    monkeypatch.setattr(settings, "turn_user", ""); monkeypatch.setattr(settings, "turn_pass", "")
    assert webrtc.ice_servers() == [{"urls": "turn:turn.example:3478"}]


def test_create_peer_connection_uses_configured_servers(monkeypatch):
    import aiortc
    seen = {}
    class Capture:
        def __init__(self, configuration=None): seen["cfg"] = configuration
    monkeypatch.setattr(aiortc, "RTCPeerConnection", Capture)
    monkeypatch.setattr(settings, "stun_urls", ["stun:a.example:3478"])
    monkeypatch.setattr(settings, "turn_url", "turn:turn.example:3478")
    monkeypatch.setattr(settings, "turn_user", "u"); monkeypatch.setattr(settings, "turn_pass", "p")
    webrtc.create_peer_connection()
    stun, turn = seen["cfg"].iceServers
    assert stun.urls == ["stun:a.example:3478"] and stun.username is None
    assert (turn.urls, turn.username, turn.credential) == ("turn:turn.example:3478", "u", "p")


# ---------------------------------------------------------------- /ws/rtc authentication (same rules as /ws/screen)

def test_rtc_rejects_wrong_token_with_4401():
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        ws.send_text(json.dumps({"token": "wrong"}))
        with pytest.raises(WebSocketDisconnect) as e: ws.receive_text()
        assert e.value.code == 4401


def test_rtc_requires_token_before_anything_else():
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        ws.send_text(json.dumps({"type": "offer", "sdp": GOOD_SDP}))   # no token: must not be answered
        with pytest.raises((WebSocketDisconnect, Exception)):
            msg = ws.receive_text()
            assert json.loads(msg).get("type") != "ready"
            raise WebSocketDisconnect(1000)
    assert not webrtc._sessions


def test_rtc_lockout_applies_and_wrong_tokens_are_counted():
    with TestClient(app) as c:
        for _ in range(security.MAX_FAILS):
            with c.websocket_connect("/ws/rtc") as ws:
                ws.send_text(json.dumps({"token": "bad"}))
                with pytest.raises(WebSocketDisconnect): ws.receive_text()
        with c.websocket_connect("/ws/rtc") as ws:   # right token, but this client is now locked out
            ws.send_text(json.dumps({"token": settings.token}))
            with pytest.raises(WebSocketDisconnect) as e: ws.receive_text()
            assert e.value.code == 4429


def test_rtc_blocked_client_is_closed_before_reading_a_token():
    for _ in range(security.MAX_FAILS): security.record_fail("testclient")
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        with pytest.raises(WebSocketDisconnect) as e: ws.receive_text()
        assert e.value.code == 4429


def test_rtc_success_clears_failures_for_that_client():
    security.record_fail("testclient")
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        ws.send_text(json.dumps({"token": settings.token}))
        assert json.loads(ws.receive_text())["type"] in ("ready", "unavailable")
    assert len(security._fails.get("testclient", [])) == 0


# ---------------------------------------------------------------- fallback path: WebRTC unavailable

def _auth(ws): ws.send_text(json.dumps({"token": settings.token}))


def test_unavailable_when_disabled_by_env(monkeypatch):
    monkeypatch.setattr(settings, "webrtc", False)
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        _auth(ws)
        m = json.loads(ws.receive_text())
        assert m["type"] == "unavailable" and "REMOTE_PC_WEBRTC" in m["reason"]


def test_unavailable_when_not_windows(monkeypatch):
    monkeypatch.setattr(screen, "_on_windows", lambda: False)
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        _auth(ws)
        assert json.loads(ws.receive_text())["type"] == "unavailable"


def test_unavailable_when_aiortc_missing_and_app_still_works(monkeypatch):
    monkeypatch.setitem(sys.modules, "aiortc", None)   # import aiortc -> ImportError
    assert "aiortc" in webrtc.unavailable_reason()
    with TestClient(app) as c:
        with c.websocket_connect("/ws/rtc") as ws:
            _auth(ws)
            m = json.loads(ws.receive_text())
            assert m["type"] == "unavailable" and "aiortc" in m["reason"]
        assert c.get("/api/health").json()["ok"]   # nothing else broke


def test_unavailable_when_too_many_sessions(monkeypatch):
    monkeypatch.setattr(webrtc, "MAX_SESSIONS", 1)
    class Busy:
        async def close(self): pass
    webrtc._sessions.add(Busy())
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        _auth(ws)
        m = json.loads(ws.receive_text())
        assert m["type"] == "unavailable" and "too many" in m["reason"]


def test_websocket_stream_endpoints_are_still_registered():
    paths = {r.path for r in app.routes}
    assert {"/ws/screen", "/ws/input", "/ws/rtc"} <= paths


# ---------------------------------------------------------------- signaling flow with a fake session

class FakeSession:
    instances = []
    def __init__(self):
        FakeSession.instances.append(self)
        self.dead = asyncio.Event(); self.send_signal = None; self.pc = None
        self.state = "new"; self.closed = False; self.offers = []; self.candidates = []
    @property
    def connected(self): return self.state == "connected"
    async def handle_offer(self, sdp):
        if self.offers: raise webrtc.SignalError("this session already has an offer")
        self.offers.append(sdp); self.pc = object(); return {"type": "answer", "sdp": "ANSWER"}
    async def add_candidate(self, msg): self.candidates.append(msg)
    async def close(self):
        self.closed = True; self.dead.set(); webrtc._sessions.discard(self)


@pytest.fixture
def fake_sessions(monkeypatch):
    FakeSession.instances = []
    monkeypatch.setattr(webrtc, "RtcSession", FakeSession)
    return FakeSession.instances


def test_signaling_offer_candidate_bye(fake_sessions):
    cand = {"candidate": "candidate:1 1 udp 2130706431 192.168.1.5 50000 typ host", "sdpMid": "0", "sdpMLineIndex": 0}
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        _auth(ws)
        ready = json.loads(ws.receive_text())
        assert ready["type"] == "ready" and isinstance(ready["ice_servers"], list)
        ws.send_text(json.dumps({"type": "offer", "sdp": GOOD_SDP}))
        assert json.loads(ws.receive_text()) == {"type": "answer", "sdp": "ANSWER"}
        ws.send_text(json.dumps({"type": "candidate", "candidate": cand}))
        ws.send_text(json.dumps({"type": "offer", "sdp": GOOD_SDP}))   # a second offer is refused, the session lives on
        assert "already has an offer" in json.loads(ws.receive_text())["message"]
        ws.send_text('{"type":"bye"}')
        with pytest.raises(WebSocketDisconnect): ws.receive_text()
    s = fake_sessions[0]
    assert s.offers == [GOOD_SDP] and s.candidates[0]["candidate"] == cand["candidate"] and s.closed


def test_invalid_messages_get_an_error_and_too_many_close_the_socket(fake_sessions):
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        _auth(ws); ws.receive_text()
        for _ in range(webrtc.MAX_SIGNAL_ERRORS):
            ws.send_text("garbage")
            assert json.loads(ws.receive_text())["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as e: ws.receive_text()
        assert e.value.code == 1008
    assert fake_sessions[0].closed and not fake_sessions[0].offers


def test_unconnected_session_is_closed_when_the_socket_drops(fake_sessions):
    with TestClient(app) as c:
        with c.websocket_connect("/ws/rtc") as ws:
            _auth(ws); ws.receive_text()
    assert fake_sessions[0].closed and not webrtc._sessions


def test_offer_failure_reports_error_and_cleans_up(monkeypatch, fake_sessions):
    async def boom(self, sdp): raise RuntimeError("secret internals")
    monkeypatch.setattr(FakeSession, "handle_offer", boom)
    with TestClient(app) as c, c.websocket_connect("/ws/rtc") as ws:
        _auth(ws); ws.receive_text()
        ws.send_text(json.dumps({"type": "offer", "sdp": GOOD_SDP}))
        m = json.loads(ws.receive_text())
        assert m["type"] == "error" and "secret" not in m["message"]   # no internals leak to the client
    assert fake_sessions[0].closed


def test_connected_session_survives_signaling_loss_until_it_dies():
    async def go():
        s = FakeSession(); s.state = "connected"; s.pc = object()
        ws = NS()
        async def accept(): pass
        sent = []
        async def send_text(t): sent.append(t)
        async def close(code=1000, reason=None): pass
        # drive rtc_socket with a scripted websocket: auth, then a disconnect
        script = iter([json.dumps({"token": settings.token})])
        async def receive_text():
            try: return next(script)
            except StopIteration: raise WebSocketDisconnect(1001)
        ws.accept, ws.send_text, ws.close, ws.receive_text = accept, send_text, close, receive_text
        ws.headers = {}; ws.client = NS(host="9.9.9.9")
        webrtc._sessions.add(s)
        await webrtc.rtc_socket(ws, session_factory=lambda: s)
        assert not s.closed                       # media may still be flowing: not torn down
        s.dead.set(); await asyncio.sleep(0.05)   # the peer connection / control channel died
        assert s.closed
    asyncio.run(go())


# ---------------------------------------------------------------- live config

def test_rtc_config_clamps_and_ignores_garbage(monkeypatch):
    monkeypatch.setattr(settings, "rtc_fps", 60)
    base = webrtc.RtcConfig(1280, 30, 4000)
    c = base.updated({"max_width": 99999, "fps": 500, "bitrate": 10**9, "cursor": True})
    assert (c.max_width, c.fps, c.bitrate, c.overlay) == (screen.WIDTH_MAX, 60, webrtc.BITRATE_MAX_KBPS, True)
    c = base.updated({"max_width": 0, "fps": 0, "bitrate": 1})
    assert (c.max_width, c.fps, c.bitrate) == (0, 1, webrtc.BITRATE_MIN_KBPS)
    c = base.updated({"max_width": 100})
    assert c.max_width == screen.WIDTH_MIN
    for junk in ("x", None, True, float("nan"), [1]):
        assert base.updated({"max_width": junk, "fps": junk, "bitrate": junk}) == base
    monkeypatch.setattr(settings, "rtc_fps", 15)
    assert base.updated({"fps": 30}).fps == 15   # REMOTE_PC_RTC_FPS is the ceiling


def test_output_size_is_even_and_scaled():
    assert webrtc.output_size((1920, 1080), 1280) == (1280, 720)
    assert webrtc.output_size((1920, 1080), 0) == (1920, 1080)
    assert webrtc.output_size((1366, 768), 0) == (1366, 768)
    w, h = webrtc.output_size((1921, 1081), 0); assert w % 2 == 0 and h % 2 == 0
    assert webrtc.output_size((800, 600), 1280) == (800, 600)   # never scaled up


# ---------------------------------------------------------------- data channels: input, control, config, cursor

def test_input_and_control_messages_reach_handle_input_identically():
    async def go():
        s = make_session(); ch = await started(s)
        s.on_channel_message(ch["control"], json.dumps({"type": "click", "button": "right", "nx": 0.5, "ny": 0.5}))
        s.on_channel_message(ch["control"], json.dumps({"type": "key", "key": "ENTER"}))
        s.on_channel_message(ch["control"], json.dumps({"type": "hotkey", "keys": ["CTRL", "C"]}))
        s.on_channel_message(ch["control"], json.dumps({"type": "type", "text": "hi"}))
        s.on_channel_message(ch["control"], json.dumps({"type": "scroll", "dy": 3}))
        s.on_channel_message(ch["input"], json.dumps({"type": "move", "nx": 1, "ny": 1}))
        await settle(s)
        mouse, kb, _, _ = s._backend_box["b"]
        assert ("click", "R", 1) in mouse.calls and ("scroll", 0, 3) in mouse.calls
        assert mouse.position == (1919, 1079)
        assert kb.calls[:2] == [("press", "<enter>"), ("release", "<enter>")]
        assert ("type", "hi") in kb.calls and ("press", "<ctrl>") in kb.calls
        await s.close()
    asyncio.run(go())


def test_pointer_moves_are_coalesced_but_clicks_keep_order():
    async def go():
        s = make_session(); ch = await started(s)
        mouse_ref = []
        for i in range(50): s.on_channel_message(ch["input"], json.dumps({"type": "rel", "dx": 2, "dy": 1}))
        s.on_channel_message(ch["control"], json.dumps({"type": "click", "button": "left"}))
        await settle(s)
        mouse = s._backend_box["b"][0]
        assert mouse.position == (100, 50) and mouse.calls == [("click", "L", 1)]
        await s.close()
    asyncio.run(go())


@pytest.mark.parametrize("payload", [
    "not json", "[]", "5", "null", json.dumps({"type": "click", "button": "left", "count": "x"}),
    json.dumps({"type": "hotkey", "keys": ["NOPE_KEY"]}), json.dumps({"type": "scroll", "dy": "abc"}),
    json.dumps({"type": "who-knows"}), b"binary", "x" * (webrtc.MAX_CHANNEL_MESSAGE + 1), 12345,
], ids=_short_id)
def test_malformed_channel_messages_are_dropped_and_the_session_survives(payload):
    async def go():
        s = make_session(); ch = await started(s)
        s.on_channel_message(ch["control"], payload)
        s.on_channel_message(ch["control"], json.dumps({"type": "key", "key": "ENTER"}))   # still works afterwards
        await settle(s)
        assert ("press", "<enter>") in s._backend_box["b"][1].calls
        assert not s.closed
        await s.close()
    asyncio.run(go())


def test_unknown_channel_labels_are_closed_and_ignored():
    async def go():
        s = make_session(); stray = FakeChannel("evil"); s._on_datachannel(stray)
        assert stray.closed and "evil" not in s.channels and s.sink.task is None
    asyncio.run(go())


def test_config_message_applies_live_and_answers_on_the_same_channel():
    async def go():
        s = make_session(); ch = await started(s)
        async def released(): pass
        s.track = NS(config=None, size=None, native=(1920, 1080), stop=lambda: None, released=released)
        s.on_channel_message(ch["control"], json.dumps({"type": "config", "max_width": 960, "fps": 20, "bitrate": 2000, "cursor": True}))
        assert s.config == webrtc.RtcConfig(960, 20, 2000, True) and s.track.config is s.config
        reply = ch["control"].sent[-1]
        assert reply == {"type": "screen", "width": 960, "height": 540, "max_width": 960, "fps": 20, "bitrate": 2000, "transport": "webrtc"}
        assert webrtc_encoder.Limits.cap() == 2_000_000
        s.on_channel_message(ch["control"], json.dumps({"type": "config", "bitrate": 8000}))
        assert webrtc_encoder.Limits.cap() == 8_000_000 and s.config.max_width == 960   # fields you leave out keep their value
        await s.close()
        assert webrtc_encoder.Limits.cap() == webrtc_encoder.Limits.default_bps          # released with the session
    asyncio.run(go())


def test_ping_is_answered_with_pong():
    async def go():
        s = make_session(); ch = await started(s)
        s.on_channel_message(ch["control"], json.dumps({"type": "ping", "t": 12345}))
        assert ch["control"].sent == [{"type": "pong", "t": 12345}]
        await s.close()
    asyncio.run(go())


def test_cursor_is_streamed_on_the_input_channel_and_stops_on_request(monkeypatch):
    monkeypatch.setattr(screen, "CURSOR_INTERVAL", 0.005)
    async def go():
        s = make_session(); ch = await started(s)
        s.on_channel_message(ch["control"], json.dumps({"type": "watch_cursor", "on": True}))
        s._backend_box["b"][0].position = (960, 540)
        await asyncio.sleep(0.15)
        cursors = [m for m in ch["input"].sent if m["type"] == "cursor"]
        assert cursors and cursors[-1]["w"] == 1920 and cursors[-1]["h"] == 1080
        assert any(abs(m["nx"] - 0.5) < 0.01 for m in cursors)
        assert not [m for m in ch["control"].sent if m["type"] == "cursor"]
        s.on_channel_message(ch["control"], json.dumps({"type": "watch_cursor", "on": False}))
        await asyncio.sleep(0.02); n = len(ch["input"].sent); await asyncio.sleep(0.1)
        assert len(ch["input"].sent) == n
        await s.close()
    asyncio.run(go())


def test_cursor_loop_ends_by_itself_when_the_channel_closes(monkeypatch):
    monkeypatch.setattr(screen, "CURSOR_INTERVAL", 0.005)
    async def go():
        s = make_session(); ch = await started(s)
        s.on_channel_message(ch["control"], json.dumps({"type": "watch_cursor"}))
        await asyncio.sleep(0.05)
        ch["input"].readyState = "closed"
        s._backend_box["b"][0].position = (5, 5)   # a pointer move makes the loop try to send, and notice
        await asyncio.sleep(0.1)
        assert s.cursor_task.done()
        await s.close()
    asyncio.run(go())


# ---------------------------------------------------------------- the video track

def run_track(cap, cfg, body):
    async def go():
        track = webrtc._screen_track_class()(cap, cfg)
        try: return await body(track)
        finally:
            track.stop(); await track.released()
    return asyncio.run(go())


def test_track_delivers_newest_frames_with_increasing_timestamps():
    cap = FakeCapture((64, 48))
    async def body(t):
        frames = [await t.recv() for _ in range(4)]
        return frames
    frames = run_track(cap, webrtc.RtcConfig(0, 30, 2000), body)
    assert [f.pts for f in frames] == sorted({f.pts for f in frames}) and frames[0].width == 64 and frames[0].height == 48
    assert frames[0].format.name == "yuv420p"
    assert cap.n >= 4   # every frame came from a fresh capture, nothing was queued


def test_track_does_not_resend_a_still_screen_until_keepalive(monkeypatch):
    monkeypatch.setattr(webrtc, "KEEPALIVE", 0.3)
    cap = FakeCapture((64, 48))
    async def body(t):
        await t.recv(); cap.change = False
        loop = asyncio.get_running_loop(); t0 = loop.time()
        await t.recv()
        return loop.time() - t0
    waited = run_track(cap, webrtc.RtcConfig(0, 30, 2000), body)
    assert 0.25 <= waited < 1.0   # held back until the keepalive, not re-sent at 30 fps


def test_track_scales_to_max_width_and_follows_live_config():
    cap = FakeCapture((640, 360))
    async def body(t):
        a = await t.recv()
        t.config = webrtc.RtcConfig(320, 30, 2000)
        b = await t.recv(); c = await t.recv()
        return a, b, c
    a, b, c = run_track(cap, webrtc.RtcConfig(0, 30, 2000), body)
    assert (a.width, a.height) == (640, 360) and (c.width, c.height) == (320, 180)


def test_track_stop_releases_capture_on_the_capture_thread_and_ends_the_thread():
    cap = FakeCapture()
    before = {t.name for t in threading.enumerate()}
    async def go():
        t = webrtc._screen_track_class()(cap, webrtc.RtcConfig(0, 30, 2000))
        await t.recv(); t.stop(); await t.released()
        with pytest.raises(Exception): await t.recv()   # an ended track raises MediaStreamError
        return t
    asyncio.run(go())
    assert cap.opened == 1 and cap.closed_on in cap.threads and cap.closed_on != threading.get_ident()
    import time
    for _ in range(50):
        if not [t for t in threading.enumerate() if t.name.startswith("rpc-rtc-capture")]: break
        time.sleep(0.02)
    assert not [t for t in threading.enumerate() if t.name.startswith("rpc-rtc-capture")]


def test_make_video_frame_handles_padded_rows_and_cursor_overlay():
    raw = bytes([10, 20, 30, 255]) * (100 * 50)
    f = webrtc.make_video_frame(raw, (100, 50), (100, 50))
    assert (f.width, f.height, f.format.name) == (100, 50, "yuv420p")
    g = webrtc.make_video_frame(raw, (100, 50), (50, 24), cursor=(10, 10))
    assert (g.width, g.height) == (50, 24)


# ---------------------------------------------------------------- the offer/answer path with a fake peer connection

class FakePC:
    def __init__(self):
        self.log = []; self.handlers = {}; self.connectionState = "new"; self.added = []
        self.localDescription = NS(sdp="LOCAL-ANSWER"); self.transceiver = NS(kind="video", prefs=None)
        self.transceiver.setCodecPreferences = lambda c: setattr(self.transceiver, "prefs", c)
    def on(self, name, fn=None):
        if fn is None: return lambda f: self.handlers.__setitem__(name, f) or f
        self.handlers[name] = fn
    def addTrack(self, track): self.log.append("addTrack"); self.added.append(track)
    def getTransceivers(self): return [self.transceiver]
    async def setRemoteDescription(self, d): self.log.append("setRemote")
    async def createAnswer(self): self.log.append("createAnswer"); return "ANSWER-OBJ"
    async def setLocalDescription(self, d): self.log.append("setLocal")
    async def addIceCandidate(self, c): self.log.append(("cand", c.sdpMid, c.sdpMLineIndex, c.ip))
    async def close(self): self.log.append("close")


def test_offer_adds_track_and_h264_preferences_before_the_remote_description():
    async def go():
        pc = FakePC(); cap = FakeCapture()
        s = make_session(pc_factory=lambda: pc, capture_factory=cap)
        answer = await s.handle_offer(GOOD_SDP)
        assert answer == {"type": "answer", "sdp": "LOCAL-ANSWER"}
        assert pc.log[:2] == ["addTrack", "setRemote"]   # aiortc fixes the answer's codec order in setRemoteDescription
        assert pc.transceiver.prefs and pc.transceiver.prefs[0].mimeType.lower() == "video/h264"
        assert pc.added[0] is s.track
        await s.close(); assert "close" in pc.log
    asyncio.run(go())


def test_candidates_before_the_offer_are_held_and_applied_after_it():
    async def go():
        pc = FakePC(); s = make_session(pc_factory=lambda: pc)
        line = "candidate:1 1 udp 2130706431 192.168.1.5 50000 typ host"
        await s.add_candidate({"type": "candidate", "candidate": line, "sdpMid": "0", "sdpMLineIndex": 0})
        await s.handle_offer(GOOD_SDP)
        await s.add_candidate({"type": "candidate", "candidate": None})              # end-of-candidates: ignored
        await s.add_candidate({"type": "candidate", "candidate": "candidate:garbage", "sdpMid": "0", "sdpMLineIndex": 0})  # unusable: ignored
        assert ("cand", "0", 0, "192.168.1.5") in pc.log and not s.closed
        with pytest.raises(webrtc.SignalError): await s.handle_offer(GOOD_SDP)
        await s.close()
    asyncio.run(go())


def test_connection_state_updates_signal_and_failure_ends_the_session():
    async def go():
        pc = FakePC(); s = make_session(pc_factory=lambda: pc); sent = []
        async def send(m): sent.append(m)
        s.send_signal = send
        await s.handle_offer(GOOD_SDP)
        pc.connectionState = "connected"; pc.handlers["connectionstatechange"](); await asyncio.sleep(0.01)
        assert s.connected and {"type": "state", "state": "connected"} in sent and not s.dead.is_set()
        pc.connectionState = "failed"; pc.handlers["connectionstatechange"]()
        assert s.dead.is_set()
        await s.close()
    asyncio.run(go())


def test_control_channel_close_ends_the_session():
    async def go():
        s = make_session(); ch = await started(s)
        ch["control"].handlers["close"]()
        assert s.dead.is_set()
        await s.close()
    asyncio.run(go())


def test_connect_timeout_marks_the_session_dead(monkeypatch):
    monkeypatch.setattr(webrtc, "CONNECT_TIMEOUT", 0.05)
    async def go():
        s = make_session(pc_factory=FakePC); await s.handle_offer(GOOD_SDP)
        await asyncio.wait_for(s.dead.wait(), 2)
        await s.close()
    asyncio.run(go())


def test_close_is_idempotent_and_releases_everything(monkeypatch):
    released = []
    monkeypatch.setattr(screen._Dx, "reset", classmethod(lambda cls: released.append(1)))
    async def go():
        cap = FakeCapture(); pc = FakePC()
        s = make_session(pc_factory=lambda: pc, capture_factory=cap)
        webrtc._sessions.add(s)
        await s.handle_offer(GOOD_SDP); await started(s)
        await s.track.recv()                      # capture is open on its thread
        s.on_channel_message(s.channels["control"], json.dumps({"type": "watch_cursor"}))
        await s.close(); await s.close()          # twice: harmless
        assert s.closed and not webrtc._sessions and released == [1]
        assert cap.closed_on is not None and s.sink.task is None and s.cursor_task is None
        assert webrtc_encoder.Limits.cap() == webrtc_encoder.Limits.default_bps
    asyncio.run(go())


def test_two_sessions_are_independent_and_shutdown_closes_both():
    async def go():
        a = make_session(pc_factory=FakePC, capture_factory=FakeCapture())
        b = make_session(pc_factory=FakePC, capture_factory=FakeCapture())
        for s in (a, b): webrtc._sessions.add(s); await s.handle_offer(GOOD_SDP)
        ca, cb = await started(a), await started(b)
        a.on_channel_message(ca["control"], json.dumps({"type": "key", "key": "ENTER"}))
        await settle(a)
        assert a._backend_box["b"][1].calls and not b._backend_box["b"][1].calls   # input goes only to its own session
        a.on_channel_message(ca["control"], json.dumps({"type": "config", "bitrate": 1000}))
        b.on_channel_message(cb["control"], json.dumps({"type": "config", "bitrate": 5000}))
        assert webrtc_encoder.Limits.cap() == 5_000_000
        await a.close(); assert webrtc_encoder.Limits.cap() == 5_000_000 and not b.closed
        await webrtc.shutdown_all()
        assert b.closed and not webrtc._sessions
    asyncio.run(go())


# ---------------------------------------------------------------- the encoder

def test_backend_order():
    assert webrtc_encoder.backend_order("auto", set()) == ["nvenc", "qsv", "amf", "x264"]
    assert webrtc_encoder.backend_order("auto", {"nvenc"}) == ["qsv", "amf", "x264"]
    assert webrtc_encoder.backend_order("qsv", set()) == ["qsv", "x264"]
    assert webrtc_encoder.backend_order("x264", set()) == ["x264"]
    assert webrtc_encoder.backend_order("nonsense", set()) == ["nvenc", "qsv", "amf", "x264"]
    assert webrtc_encoder.backend_order("auto", {"nvenc", "qsv", "amf"}) == ["x264"]
    assert webrtc_encoder.backend_order("auto", set(), available={"libx264", "h264_amf"}) == ["amf", "x264"]
    assert webrtc_encoder.backend_order("nvenc", {"nvenc"}) == ["x264"]   # forced but known broken: libx264


def test_x264_options_are_low_latency():
    o = webrtc_encoder.codec_options("x264")
    assert o["preset"] == "ultrafast" and o["tune"] == "zerolatency"
    assert webrtc_encoder.codec_options("nvenc")["bf"] == "0"


def test_encoder_install_patches_aiortc_and_encodes_h264(monkeypatch):
    import av, fractions, aiortc.codecs
    monkeypatch.setattr(settings, "rtc_encoder", "x264")
    cls = webrtc_encoder.install()
    assert aiortc.codecs.H264Encoder is cls and webrtc_encoder.install() is cls
    enc = cls()
    f = av.VideoFrame(320, 240, "yuv420p"); f.pts = 0; f.time_base = fractions.Fraction(1, 90000)
    packets, ts = enc.encode(f, True)
    assert packets and enc.backend == "x264"
    nal_types = {p[0] & 0x1F for p in packets}
    assert nal_types & {5, 7, 8, 24, 28}   # IDR / SPS / PPS / STAP-A / FU-A: a decodable key frame went out
    assert enc.codec.max_b_frames == 0


def test_encoder_skips_backends_known_to_be_broken(monkeypatch):
    import av, fractions
    monkeypatch.setattr(settings, "rtc_encoder", "nvenc")
    cls = webrtc_encoder.install()
    monkeypatch.setattr(cls, "failed", {"nvenc", "qsv", "amf"})
    enc = cls()
    f = av.VideoFrame(320, 240, "yuv420p"); f.pts = 0; f.time_base = fractions.Fraction(1, 90000)
    assert enc.encode(f, True)[0] and enc.backend == "x264"


def test_encoder_falls_back_when_a_hardware_encoder_cannot_open(monkeypatch):
    """On a machine without that GPU the open fails; on one with it the hardware encoder is used. Either way video flows."""
    import av, fractions
    monkeypatch.setattr(settings, "rtc_encoder", "auto")
    cls = webrtc_encoder.install()
    monkeypatch.setattr(cls, "failed", set())
    enc = cls()
    f = av.VideoFrame(320, 240, "yuv420p"); f.pts = 0; f.time_base = fractions.Fraction(1, 90000)
    packets, _ = enc.encode(f, True)
    assert packets and enc.backend in webrtc_encoder.ORDER
    assert enc.backend == "x264" or enc.backend not in cls.failed


def test_encoder_bitrate_follows_the_receiver_within_floor_and_cap():
    cls = webrtc_encoder.install()
    enc = cls()
    webrtc_encoder.Limits.set("t", 4_000_000)
    assert enc.target_bitrate == webrtc_encoder.INITIAL_BITRATE           # no estimate yet
    enc.target_bitrate = 2_000_000; assert enc.target_bitrate == 2_000_000
    enc.target_bitrate = 50_000;    assert enc.target_bitrate == webrtc_encoder.FLOOR_BITRATE   # a quiet screen must not starve the next scroll
    enc.target_bitrate = 50_000_000; assert enc.target_bitrate == 4_000_000                      # never above the user's cap
    webrtc_encoder.Limits.set("t", 600_000)
    assert enc.target_bitrate == 600_000                                  # a low cap lowers the floor too
    webrtc_encoder.Limits.set("t", None)


def test_encoder_floor_rises_with_a_high_cap_but_never_exceeds_it():
    assert webrtc_encoder.floor_for(4_000_000) == webrtc_encoder.FLOOR_BITRATE        # unchanged for the default cap
    assert webrtc_encoder.floor_for(600_000) == 600_000                               # never above the cap
    assert webrtc_encoder.floor_for(20_000_000) == 20_000_000 // webrtc_encoder.FLOOR_SHARE
    cls = webrtc_encoder.install()
    enc = cls()
    webrtc_encoder.Limits.set("t", 20_000_000)
    enc.target_bitrate = 50_000                                           # a quiet screen on the Native preset...
    assert enc.target_bitrate == webrtc_encoder.floor_for(20_000_000) > webrtc_encoder.FLOOR_BITRATE   # ...keeps a sharp floor
    enc.target_bitrate = 50_000_000; assert enc.target_bitrate == 20_000_000
    webrtc_encoder.Limits.set("t", None)


# ---------------------------------------------------------------- start-up warm-up

def test_warm_up_does_nothing_when_webrtc_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "webrtc", False)
    called = []
    monkeypatch.setattr(webrtc_encoder, "probe_backends", lambda *a, **k: called.append(1))
    webrtc.warm_up()
    assert called == []


def test_warm_up_never_raises(monkeypatch):
    monkeypatch.setattr(webrtc, "unavailable_reason", lambda: None)
    def boom(*a, **k): raise RuntimeError("driver exploded")
    monkeypatch.setattr(webrtc_encoder, "install", boom)
    webrtc.warm_up()   # must only log


def test_probe_marks_a_broken_hardware_encoder_as_failed(monkeypatch):
    av = pytest.importorskip("av")
    class Cls: failed = set()
    monkeypatch.setattr(av, "codecs_available", {"h264_nvenc", "libx264"}, raising=False)
    real_create = av.CodecContext.create
    def create(name, mode):
        if name == "h264_nvenc": raise PermissionError("Operation not permitted")
        return real_create(name, mode)
    monkeypatch.setattr(av.CodecContext, "create", staticmethod(create), raising=False)
    assert webrtc_encoder.probe_backends(Cls) == "x264"
    assert Cls.failed == {"nvenc"}
