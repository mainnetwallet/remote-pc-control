"""WebRTC transport for the live screen (/ws/rtc). The WebSocket JPEG stream in screen.py stays as the fallback.

Signaling runs over an authenticated WebSocket, exactly like /ws/screen: the first message must be {"token": "..."}.

  server -> client   {"type":"ready","ice_servers":[{"urls":[..],"username":..,"credential":..}]}
                     {"type":"answer","sdp":"..."}
                     {"type":"candidate","candidate":{"candidate":"candidate:..","sdpMid":"0","sdpMLineIndex":0}}
                     {"type":"state","state":"connected|failed|closed"}
                     {"type":"unavailable","reason":".."}   WebRTC cannot be used (disabled, aiortc missing, not
                                                              Windows, busy): use /ws/screen instead.
                     {"type":"error","message":".."}
  client -> server   {"type":"offer","sdp":"..."}           must contain a video m-line (receive only)
                     {"type":"candidate","candidate":{..}}  trickle ICE; {"type":"candidate","candidate":null} = done
                     {"type":"bye"}

The client creates two data channels in its offer. Everything on them is JSON text in the same format as /ws/input:

  "input"    unordered, maxRetransmits=0: pointer moves ("move", "rel"). The PC also sends {"type":"cursor",..}
             here after {"type":"watch_cursor","on":true}.
  "control"  reliable and ordered: clicks, down/up, scroll, key, hotkey, type, watch_cursor, and
      {"type":"config","max_width":1280,"fps":30,"bitrate":3000,"cursor":true}   (all fields optional, applied
      live; bitrate in kbit/s; "cursor":true = the client draws the pointer itself). The PC answers on the
      same channel with {"type":"screen","width":W,"height":H,"max_width":..,"fps":..,"bitrate":..,"encoder":".."}.
      {"type":"ping","t":..} is answered with {"type":"pong","t":..}.

Any message type is accepted on either channel; clients should send clicks and keys on "control" because "input"
may drop messages.

The video track pulls the newest screen from the same capture code as the WebSocket stream (screen._capture_source),
only when the encoder is ready for the next frame, so old frames are never queued.
"""
import asyncio, collections, contextlib, fractions, json, logging, time
from dataclasses import dataclass
from fastapi import WebSocket, WebSocketDisconnect
from .config import settings
from . import screen

log = logging.getLogger("remote_pc.webrtc")

MAX_SESSIONS = 4              # simultaneous WebRTC sessions
MAX_SDP_BYTES = 64 * 1024
MAX_CANDIDATE_BYTES = 2048
MAX_CHANNEL_MESSAGE = 4096    # bytes of one data channel message
MAX_SIGNAL_ERRORS = 5         # this many invalid signaling messages and the socket is closed
CONNECT_TIMEOUT = 20.0        # seconds after the answer until the peer connection must be up
KEEPALIVE = 0.5               # an unchanged screen is re-sent this often (receivers and PLI recovery need frames)
CLOCK = 90_000                # RTP video clock
BITRATE_MIN_KBPS, BITRATE_MAX_KBPS = 200, 30_000
ALLOWED_CHANNELS = ("input", "control")
_now = time.perf_counter


# ---------------------------------------------------------------- signaling messages

class SignalError(ValueError):
    """A signaling message is malformed. The text is safe to send back to the client."""


def parse_signal(text) -> dict:
    """Validate one signaling message and return it normalized. Raises SignalError."""
    if not isinstance(text, str): raise SignalError("text messages only")
    if len(text) > MAX_SDP_BYTES + 4096: raise SignalError("message too large")
    try: d = json.loads(text)
    except (ValueError, RecursionError): raise SignalError("not valid JSON")
    if not isinstance(d, dict): raise SignalError("expected a JSON object")
    kind = d.get("type")
    if kind == "offer":
        sdp = d.get("sdp")
        if not isinstance(sdp, str) or not sdp.strip(): raise SignalError("offer needs an sdp string")
        if len(sdp) > MAX_SDP_BYTES: raise SignalError("sdp too large")
        if not sdp.lstrip().startswith("v=0"): raise SignalError("sdp is not a session description")
        if "m=video" not in sdp: raise SignalError("offer must contain a video section")
        return {"type": "offer", "sdp": sdp}
    if kind == "candidate":
        cand = d.get("candidate")
        if cand is None or cand == "": return {"type": "candidate", "candidate": None}   # end of candidates
        mid, idx = None, None
        if isinstance(cand, dict):
            mid, idx, cand = cand.get("sdpMid"), cand.get("sdpMLineIndex"), cand.get("candidate")
            if cand is None or cand == "": return {"type": "candidate", "candidate": None}
        else:
            mid, idx = d.get("sdpMid"), d.get("sdpMLineIndex")
        if not isinstance(cand, str) or not cand.startswith("candidate:"): raise SignalError("bad candidate")
        if len(cand) > MAX_CANDIDATE_BYTES: raise SignalError("candidate too large")
        if mid is not None and (not isinstance(mid, str) or len(mid) > 64): raise SignalError("bad sdpMid")
        if idx is not None and (isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < 16): raise SignalError("bad sdpMLineIndex")
        if mid is None and idx is None: idx = 0
        return {"type": "candidate", "candidate": cand, "sdpMid": mid, "sdpMLineIndex": idx}
    if kind == "bye": return {"type": "bye"}
    raise SignalError("unknown message type")


def ice_servers() -> list[dict]:
    """ICE servers as JSON for clients (and, in the same shape, for the PC's own peer connection)."""
    out = []
    if settings.stun_urls: out.append({"urls": list(settings.stun_urls)})
    if settings.turn_url:
        entry = {"urls": settings.turn_url}
        if settings.turn_user: entry["username"] = settings.turn_user
        if settings.turn_pass: entry["credential"] = settings.turn_pass
        out.append(entry)
    return out


def unavailable_reason() -> str | None:
    """Why WebRTC cannot be offered right now, or None."""
    if not settings.webrtc: return "disabled (REMOTE_PC_WEBRTC=0)"
    if not screen._on_windows(): return "Windows required"
    try: import aiortc  # noqa: F401
    except Exception: return "aiortc is not installed (pip install -e . on the PC)"
    return None


def create_peer_connection():
    """The PC's RTCPeerConnection, configured with the ICE servers from the settings."""
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection
    servers = [RTCIceServer(urls=s["urls"], username=s.get("username"), credential=s.get("credential")) for s in ice_servers()]
    return RTCPeerConnection(RTCConfiguration(iceServers=servers))


# ---------------------------------------------------------------- live stream settings

@dataclass
class RtcConfig:
    """Per-session video settings, changed live by "config" messages."""
    max_width: int      # 0 = native
    fps: int
    bitrate: int        # kbit/s, upper limit
    overlay: bool = False   # the client draws the pointer itself (frames carry none)

    @classmethod
    def from_settings(cls) -> "RtcConfig":
        return cls(settings.max_width, settings.rtc_fps, settings.rtc_bitrate)

    def updated(self, d: dict) -> "RtcConfig":
        width, fps, bitrate, overlay = self.max_width, self.fps, self.bitrate, self.overlay
        if (n := screen._number(d.get("max_width"))) is not None:
            n = round(n); width = 0 if n <= 0 else min(screen.WIDTH_MAX, max(screen.WIDTH_MIN, n))
        if (n := screen._number(d.get("fps"))) is not None: fps = min(settings.rtc_fps, max(screen.FPS_MIN, round(n)))
        if (n := screen._number(d.get("bitrate"))) is not None: bitrate = min(BITRATE_MAX_KBPS, max(BITRATE_MIN_KBPS, round(n)))
        if "cursor" in d: overlay = d["cursor"] is True
        return RtcConfig(width, fps, bitrate, overlay)


def output_size(size: tuple[int, int], max_width: int) -> tuple[int, int]:
    """Frame size to encode: scaled down to max_width (0 = native), both sides even as H.264 needs."""
    w, h = size
    if max_width and w > max_width: w, h = max_width, max(2, round(h * max_width / w))
    return max(2, w - w % 2), max(2, h - h % 2)


def make_video_frame(raw, size: tuple[int, int], out: tuple[int, int], cursor=None):
    """BGRX screen bytes -> yuv420p av.VideoFrame of size `out` (scaled by swscale; the pointer is drawn only when `cursor` is given)."""
    import av
    w, h = size
    if cursor is not None:
        from PIL import Image
        img = Image.frombytes("RGB", size, bytes(raw), "raw", "BGRX")
        screen._draw_cursor(img, cursor[0], cursor[1])
        return av.VideoFrame.from_image(img).reformat(width=out[0], height=out[1], format="yuv420p")
    src = av.VideoFrame(w, h, "bgra")
    plane = src.planes[0]
    row, stride = w * 4, plane.line_size
    if stride == row: plane.update(raw)
    else:   # the frame buffer's rows are padded: copy row by row
        buf = bytearray(stride * h); mv = memoryview(raw)
        for y in range(h): buf[y * stride:y * stride + row] = mv[y * row:(y + 1) * row]
        plane.update(bytes(buf))
    return src.reformat(width=out[0], height=out[1], format="yuv420p")


def _screen_track_class():
    from aiortc import VideoStreamTrack
    from aiortc.mediastreams import MediaStreamError

    class ScreenTrack(VideoStreamTrack):
        """Video track of the PC screen. recv() is called by aiortc only when its encoder wants the next frame, and
        then captures the newest screen right away, so a slow encoder or link drops frames instead of queueing them."""

        def __init__(self, capture_factory, config: RtcConfig):
            super().__init__()
            self.config = config
            self.size: tuple[int, int] | None = None   # size of the frames being produced
            self.native: tuple[int, int] | None = None  # size of the PC screen
            self._open = capture_factory
            self._cm = None; self._grab = None
            self._pool = None
            self._frame = None; self._key = None
            self._t0 = None; self._next = None; self._last_emit = 0.0
            self.frames = 0

        def _start_capture(self):   # runs on the capture thread: mss keeps GDI handles per thread
            self._cm = self._open(); self._grab = self._cm.__enter__()

        def _stop_capture(self):    # same thread
            cm, self._cm, self._grab = self._cm, None, None
            if cm is not None:
                with contextlib.suppress(BaseException): cm.__exit__(None, None, None)

        def _capture(self, cfg: RtcConfig, force: bool):
            """Capture + convert on the capture thread. Returns (frame or None if the screen did not change)."""
            if self._grab is None: self._start_capture()
            raw, size, cur, digest = self._grab()
            if cfg.overlay: cur = None
            self.native = size
            out = output_size(size, cfg.max_width)
            key = (digest, cur, out)
            if not force and key == self._key and self._frame is not None: return None
            self._key = key; self.size = out
            self._frame = make_video_frame(raw, size, out, cur)
            return self._frame

        async def recv(self):
            if self.readyState != "live": raise MediaStreamError
            from concurrent.futures import ThreadPoolExecutor
            loop = asyncio.get_running_loop()
            if self._pool is None: self._pool = ThreadPoolExecutor(1, thread_name_prefix="rpc-rtc-capture")
            pool = self._pool
            while True:
                cfg = self.config
                interval = 1.0 / max(1, cfg.fps)
                now = _now()
                if self._next is None or now - self._next > interval: self._next = now   # late: no catch-up burst
                wait = self._next - now
                if wait > 0: await asyncio.sleep(wait)
                self._next += interval
                if self.readyState != "live": raise MediaStreamError
                keepalive = _now() - self._last_emit >= KEEPALIVE
                try: frame = await loop.run_in_executor(pool, self._capture, cfg, keepalive)
                except RuntimeError:   # the pool was shut down by stop()
                    raise MediaStreamError
                if frame is None: continue   # unchanged screen: poll again next slot
                break
            if self._t0 is None: self._t0 = _now()
            frame.pts = int((_now() - self._t0) * CLOCK); frame.time_base = fractions.Fraction(1, CLOCK)
            self._last_emit = _now(); self.frames += 1
            return frame

        def stop(self):
            """Mark the track ended (call on the event loop thread) and release the capture handles on the capture
            thread that created them. Idempotent. await released() to wait for the handles to be gone."""
            super().stop()
            pool, self._pool = self._pool, None
            if pool is not None:
                self._release = pool.submit(self._stop_capture)
                pool.shutdown(wait=False)   # the thread exits once the release job has run

        async def released(self, timeout: float = 5.0) -> None:
            fut = getattr(self, "_release", None)
            if fut is not None:
                with contextlib.suppress(BaseException): await asyncio.wait_for(asyncio.wrap_future(fut), timeout)

    return ScreenTrack


# ---------------------------------------------------------------- input from the data channels

class InputSink:
    """Applies input messages like /ws/input does: they are batched and pointer moves merged (screen.coalesce_input), so
    a slow moment never turns into a delayed, rubber-band pointer. Everything else keeps its order."""

    def __init__(self, backend_factory, monitor_factory):
        self._backend_factory, self._monitor_factory = backend_factory, monitor_factory
        self.inbox: collections.deque = collections.deque()
        self.wake = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.mon = None
        self.backend = None   # (mouse controller, keyboard controller, mouse module, key map) once started

    def start(self):
        if self.task is None: self.task = asyncio.create_task(self._run())

    def push(self, d: dict) -> None:
        self.inbox.append(d); self.wake.set()

    async def _run(self):
        try:
            mouse_ctl, kb_ctl, mouse_mod, keys = self.backend = self._backend_factory()
            self.mon = await asyncio.to_thread(self._monitor_factory)
            while True:
                await self.wake.wait(); self.wake.clear()
                batch = []
                while self.inbox: batch.append(self.inbox.popleft())
                for d in screen.coalesce_input(batch):
                    with contextlib.suppress(Exception): screen.handle_input(d, self.mon, mouse_ctl, kb_ctl, mouse_mod, keys)
        except asyncio.CancelledError: raise
        except Exception: log.exception("input handling stopped")

    def stop(self):
        if self.task is not None: self.task.cancel(); self.task = None


def default_input_backend():
    screen.enable_dpi_awareness()
    from pynput import keyboard, mouse
    return mouse.Controller(), keyboard.Controller(), mouse, screen.key_map(keyboard)


class _ChannelJson:
    """Gives a data channel the send_json() that screen._push_cursor expects from a WebSocket."""
    def __init__(self, channel): self.channel = channel

    async def send_json(self, obj) -> None:
        if getattr(self.channel, "readyState", "open") != "open": raise ConnectionError("channel closed")
        self.channel.send(json.dumps(obj, separators=(",", ":")))


# ---------------------------------------------------------------- one WebRTC session

_sessions: set["RtcSession"] = set()


class RtcSession:
    """One phone/browser: a peer connection, the screen track, the input sink and the cursor pusher."""

    def __init__(self, *, pc_factory=None, capture_factory=None, input_backend=None, monitor_factory=None):
        self.pc_factory = pc_factory or create_peer_connection
        self.capture_factory = capture_factory or screen._capture_source
        self.sink = InputSink(input_backend or default_input_backend, monitor_factory or screen.primary_monitor)
        self.pc = None
        self.track = None
        self.config = RtcConfig.from_settings()
        self.channels: dict[str, object] = {}
        self.cursor_task: asyncio.Task | None = None
        self.state = "new"
        self.closed = False
        self.dead = asyncio.Event()   # set when the peer connection failed or closed
        self._watchdog: asyncio.Task | None = None
        self.send_signal = None       # coroutine function(dict), set while the signaling socket is open
        self._pending_candidates: list[dict] = []
        self._remote_set = False

    @property
    def connected(self) -> bool: return self.state == "connected"

    # ---- offer / answer
    async def handle_offer(self, sdp: str) -> dict:
        from aiortc import RTCRtpSender, RTCSessionDescription
        from . import webrtc_encoder
        if self.pc is not None: raise SignalError("this session already has an offer")
        webrtc_encoder.install()
        self.pc = pc = self.pc_factory()
        self.track = _screen_track_class()(self.capture_factory, self.config)
        webrtc_encoder.Limits.set(self, self.config.bitrate * 1000)
        pc.on("datachannel", self._on_datachannel)
        pc.on("connectionstatechange", lambda: self._on_state(pc.connectionState))
        # The track and the codec preferences must be in place BEFORE the offer is applied: aiortc fixes the answer's
        # codec order in setRemoteDescription. H.264 first (hardware encoders); VP8 stays as a software fallback.
        pc.addTrack(self.track)
        caps = RTCRtpSender.getCapabilities("video").codecs
        h264 = [c for c in caps if c.mimeType.lower() == "video/h264"]
        vp8 = [c for c in caps if c.mimeType.lower() == "video/vp8"]
        for t in pc.getTransceivers():
            if t.kind == "video" and h264: t.setCodecPreferences(h264 + vp8)
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        self._remote_set = True
        await pc.setLocalDescription(await pc.createAnswer())
        for c in self._pending_candidates: await self._add_candidate(c)
        self._pending_candidates.clear()
        screen.enable_high_res_timer()
        self._watchdog = asyncio.create_task(self._connect_watchdog())
        return {"type": "answer", "sdp": pc.localDescription.sdp}

    async def _connect_watchdog(self) -> None:
        await asyncio.sleep(CONNECT_TIMEOUT)
        if not self.connected and not self.closed:
            log.info("WebRTC connection not established within %.0f s", CONNECT_TIMEOUT)
            self.dead.set()

    async def add_candidate(self, msg: dict) -> None:
        if not self._remote_set: self._pending_candidates.append(msg); return
        await self._add_candidate(msg)

    async def _add_candidate(self, msg: dict) -> None:
        if msg["candidate"] is None: return
        from aiortc.sdp import candidate_from_sdp
        try:
            cand = candidate_from_sdp(msg["candidate"].split(":", 1)[1])
            cand.sdpMid, cand.sdpMLineIndex = msg.get("sdpMid"), msg.get("sdpMLineIndex")
            await self.pc.addIceCandidate(cand)
        except Exception as exc:   # one unusable candidate (e.g. an mDNS name) must not end the session
            log.debug("ignored ICE candidate: %s", type(exc).__name__)

    # ---- connection state
    def _on_state(self, state: str) -> None:
        self.state = state
        log.info("WebRTC connection %s", state)
        if self.send_signal is not None and not self.closed:
            asyncio.ensure_future(self._signal({"type": "state", "state": state}))
        if state in ("failed", "closed"): self.dead.set()

    async def _signal(self, msg: dict) -> None:
        send = self.send_signal
        if send is not None:
            with contextlib.suppress(Exception): await send(msg)

    # ---- data channels
    def _on_datachannel(self, channel) -> None:
        label = channel.label
        if label not in ALLOWED_CHANNELS:
            with contextlib.suppress(Exception): channel.close()
            return
        self.channels[label] = channel
        self.sink.start()
        channel.on("message", lambda m, ch=channel: self.on_channel_message(ch, m))
        channel.on("close", lambda l=label: self._channel_closed(l))

    def _channel_closed(self, label: str) -> None:
        self.channels.pop(label, None)
        if label == "control" and not self.closed: self.dead.set()   # the phone closed the session

    def on_channel_message(self, channel, message) -> None:
        """One data channel message. Malformed input is dropped silently, like on /ws/input."""
        if not isinstance(message, str) or len(message) > MAX_CHANNEL_MESSAGE: return
        try: d = json.loads(message)
        except (ValueError, RecursionError): return
        if not isinstance(d, dict): return
        kind = d.get("type")
        if kind == "config": self.apply_config(d, channel)
        elif kind == "ping":
            self._send(channel, {"type": "pong", "t": d.get("t")})
        elif kind == "watch_cursor": self._watch_cursor(d.get("on") is not False)
        else: self.sink.push(d)

    def _send(self, channel, obj: dict) -> None:
        try:
            if getattr(channel, "readyState", "open") == "open": channel.send(json.dumps(obj, separators=(",", ":")))
        except Exception: pass

    def apply_config(self, d: dict, channel=None) -> None:
        from . import webrtc_encoder
        self.config = self.config.updated(d)
        if self.track is not None: self.track.config = self.config
        webrtc_encoder.Limits.set(self, self.config.bitrate * 1000)
        reply = self.screen_info()
        target = channel or self.channels.get("control")
        if target is not None: self._send(target, reply)

    def screen_info(self) -> dict:
        native = self.track.native if self.track is not None else None
        w, h = output_size(native, self.config.max_width) if native else (0, 0)   # what the next frame will measure
        return {"type": "screen", "width": w, "height": h, "max_width": self.config.max_width, "fps": self.config.fps,
                "bitrate": self.config.bitrate, "transport": "webrtc"}

    def _watch_cursor(self, on: bool) -> None:
        if not on:
            if self.cursor_task is not None: self.cursor_task.cancel(); self.cursor_task = None
            return
        if self.cursor_task is not None: return
        channel = self.channels.get("input") or self.channels.get("control")
        if channel is None: return
        self.cursor_task = asyncio.create_task(self._cursor_loop(channel))

    async def _cursor_loop(self, channel) -> None:
        try:
            while self.sink.mon is None: await asyncio.sleep(0.02)   # the input sink is still starting
            await screen._push_cursor(_ChannelJson(channel), self.sink.backend[0], self.sink.mon)
        except asyncio.CancelledError: raise
        except Exception: pass

    # ---- shutdown
    async def close(self) -> None:
        """Idempotent: stops every task, the peer connection and the capture (no threads or handles are left behind)."""
        if self.closed: return
        self.closed = True
        from . import webrtc_encoder
        webrtc_encoder.Limits.set(self, None)
        self.send_signal = None
        self.sink.stop()
        if self._watchdog is not None and self._watchdog is not asyncio.current_task(): self._watchdog.cancel()
        if self.cursor_task is not None: self.cursor_task.cancel(); self.cursor_task = None
        if self.pc is not None:
            with contextlib.suppress(BaseException): await asyncio.wait_for(self.pc.close(), 5)
        if self.track is not None:
            self.track.stop()
            await self.track.released()
        self.channels.clear()
        self.dead.set()
        _sessions.discard(self)
        if not _sessions:   # last session gone: release the shared DXGI capture too (it is re-created on demand)
            with contextlib.suppress(BaseException): screen._Dx.reset()


async def shutdown_all() -> None:
    """Close every session (server shutdown)."""
    for s in list(_sessions): await s.close()


# ---------------------------------------------------------------- the /ws/rtc endpoint

async def _send_json(ws: WebSocket, obj: dict) -> None:
    await ws.send_text(json.dumps(obj, separators=(",", ":")))


async def rtc_socket(ws: WebSocket, session_factory=None):
    await ws.accept()
    session: RtcSession | None = None
    try:
        if not await screen._authenticate(ws): return   # same token check, lockout and brute-force accounting as /ws/screen
        reason = unavailable_reason()
        if reason is None and len(_sessions) >= MAX_SESSIONS: reason = "too many sessions"
        if reason is not None:
            await _send_json(ws, {"type": "unavailable", "reason": reason}); await ws.close(code=1000); return
        session = (session_factory or RtcSession)()
        _sessions.add(session)
        session.send_signal = lambda m: _send_json(ws, m)
        await _send_json(ws, {"type": "ready", "ice_servers": ice_servers()})
        errors = 0
        while True:
            receive = asyncio.ensure_future(ws.receive_text())
            dead = asyncio.ensure_future(session.dead.wait())
            done, _ = await asyncio.wait({receive, dead}, return_when=asyncio.FIRST_COMPLETED)
            if receive not in done:   # the connection failed or the phone hung up
                receive.cancel(); break
            dead.cancel()
            try: msg = parse_signal(receive.result())
            except SignalError as exc:
                errors += 1
                await _send_json(ws, {"type": "error", "message": str(exc)})
                if errors >= MAX_SIGNAL_ERRORS: await ws.close(code=1008, reason="Too many invalid messages"); break
                continue
            kind = msg["type"]
            if kind == "offer":
                try: await _send_json(ws, await session.handle_offer(msg["sdp"]))
                except SignalError as exc: await _send_json(ws, {"type": "error", "message": str(exc)})
                except Exception as exc:
                    log.warning("WebRTC offer failed: %s", type(exc).__name__)
                    await _send_json(ws, {"type": "error", "message": "could not set up the connection"})
                    await session.close(); break
            elif kind == "candidate": await session.add_candidate(msg)
            elif kind == "bye": await session.close(); break
    except WebSocketDisconnect: pass
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception): await ws.close(code=4401, reason="Authentication timeout")
    except Exception as exc:
        log.warning("WebRTC signaling error: %s", type(exc).__name__)
        with contextlib.suppress(Exception): await _send_json(ws, {"type": "error", "message": type(exc).__name__}); await ws.close(code=1011)
    finally:
        if session is not None:
            session.send_signal = None
            if session.connected and not session.closed:
                # Media keeps flowing without the signaling socket (a tunnel hiccup must not end the stream); the
                # session ends when the peer connection or the control channel closes.
                asyncio.ensure_future(_close_when_dead(session))
            else:
                await session.close()
        with contextlib.suppress(Exception): await ws.close(code=1000)   # the signaling socket is done in every case


async def _close_when_dead(session: RtcSession) -> None:
    try: await session.dead.wait()
    finally: await session.close()
