"""Live screen streaming (/ws/screen) and mouse/keyboard input (/ws/input).

Protocol (JSON text frames, after the client sends {"token": "..."} first):

  /ws/screen  server -> client: {"type":"ready"}, {"type":"screen","width":W,"height":H,
              "max_width":..,"fps":..,"quality":..}, then binary JPEG frames.
              client -> server (any time while streaming, all fields optional):
      {"type":"config","max_width":1920,"fps":15,"quality":70}
          max_width 0 (native) or 320..3840, fps 1..30, quality 25..90; out-of-range values are
          clamped, unusable ones ignored. Applied live; the server answers with a fresh
          {"type":"screen",...} (carrying the values now in effect) followed by a new frame.
              {"type":"ack"}   send one after each frame you have shown. Once the server has seen an ack it
          keeps at most 2 frames in flight (the newest screen always wins) and lowers JPEG quality when the
          link is slow, so the picture and the pointer never lag behind. Clients that never ack get the
          old fixed-rate stream.
  /ws/input   client -> server:
      {"type":"move",   "nx":0..1, "ny":0..1}                    cursor to a normalized position
      {"type":"rel",    "dx":int, "dy":int}                       move the pointer by pixel deltas from where it is
                                                                  (clamped to the monitor and to +-500 per message)
      {"type":"click",  "button":"left|right|middle", "count":1|2, "nx":.., "ny":..}
      {"type":"down"|"up", "button":"left", "nx":.., "ny":..}    press/release (for drag)
      (click/down/up without nx/ny act at the current pointer position, as the trackpad needs)
      {"type":"scroll", "dx":int, "dy":int}                      wheel steps (dy>0 = up)
      {"type":"key",    "key":"ENTER"}                           single key
      {"type":"hotkey", "keys":["CTRL","C"]}                     key combination
      {"type":"type",   "text":"hello"}                          type text
  Pixel coordinates ("x","y") are still accepted for older clients.

Normalized coordinates make the mapping independent of the (possibly downscaled)
frame the phone is showing, and of Windows display scaling.
"""
import asyncio, collections, contextlib, hmac, io, json, math, platform, zlib
from dataclasses import dataclass
from fastapi import WebSocket, WebSocketDisconnect
from PIL import Image, ImageDraw
from .config import settings
from . import security

MAX_IN_FLIGHT = 2         # frames sent but not yet acknowledged (only once the client sends acks)
ACK_TIMEOUT = 1.0         # no ack for this long: assume the frames were lost and carry on
KEEPALIVE_SECONDS = 3.0   # resend the last frame so idle screens don't hit client read timeouts
MAX_SCROLL = 20
MAX_REL = 500   # max pixels a single "rel" message may move the pointer on each axis
BUTTONS = ("left", "right", "middle")


def enable_dpi_awareness():
    """Make capture pixels and pointer coordinates use the same physical pixel space."""
    if platform.system() != "Windows":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try: ctypes.windll.user32.SetProcessDPIAware()
        except Exception: pass


def primary_monitor() -> dict:
    import mss
    with mss.mss() as sct:
        m = sct.monitors[1]
        return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}


def to_screen_xy(d: dict, mon: dict) -> tuple[int, int] | None:
    """Map a message's position (normalized nx/ny, or legacy pixels x/y) to absolute screen pixels."""
    try:
        if "nx" in d and "ny" in d:
            nx = min(1.0, max(0.0, float(d["nx"]))); ny = min(1.0, max(0.0, float(d["ny"])))
            x = mon["left"] + round(nx * (mon["width"] - 1)); y = mon["top"] + round(ny * (mon["height"] - 1))
        elif "x" in d and "y" in d:
            x = mon["left"] + min(mon["width"] - 1, max(0, int(d["x"]))); y = mon["top"] + min(mon["height"] - 1, max(0, int(d["y"])))
        else:
            return None
    except (TypeError, ValueError):
        return None
    return x, y


def _clamp_int(value, limit: int) -> int:
    """int(value) limited to +-limit; garbage (None, text, NaN, inf) counts as 0."""
    try: v = int(value)
    except (TypeError, ValueError, OverflowError): return 0
    return max(-limit, min(limit, v))


def rel_screen_xy(d: dict, mon: dict, current: tuple) -> tuple[int, int] | None:
    """New absolute pointer position for a "rel" message, or None when there is nothing to move."""
    dx, dy = _clamp_int(d.get("dx", 0), MAX_REL), _clamp_int(d.get("dy", 0), MAX_REL)
    if not dx and not dy: return None
    try: cx, cy = int(current[0]), int(current[1])
    except (TypeError, ValueError, IndexError): return None
    x = min(mon["left"] + mon["width"] - 1, max(mon["left"], cx + dx))
    y = min(mon["top"] + mon["height"] - 1, max(mon["top"], cy + dy))
    return x, y


def _draw_cursor(img: Image.Image, x: float, y: float) -> None:
    s = max(10, img.width // 80)
    pts = [(x, y), (x, y + s * 1.6), (x + s * 0.45, y + s * 1.25), (x + s * 0.8, y + s * 1.9), (x + s * 1.1, y + s * 1.75), (x + s * 0.75, y + s * 1.15), (x + s * 1.25, y + s * 1.1)]
    ImageDraw.Draw(img).polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))


WIDTH_MIN, WIDTH_MAX = 320, 3840
FPS_MIN, FPS_MAX = 1, 30
QUALITY_MIN, QUALITY_MAX = 25, 90


def _number(value) -> float | None:
    """float(value) for numbers and numeric strings; None for bool, text, NaN and inf."""
    if isinstance(value, bool): return None
    try: f = float(value)
    except (TypeError, ValueError, OverflowError): return None
    return f if math.isfinite(f) else None


@dataclass
class StreamConfig:
    """Per-connection stream settings. Starts from the server defaults, changed live by "config" messages."""
    max_width: int   # 0 = native resolution
    fps: int
    quality: int     # JPEG quality

    @classmethod
    def from_settings(cls) -> "StreamConfig":
        return cls(settings.max_width, settings.fps, settings.jpeg_quality)

    def updated(self, d: dict) -> "StreamConfig":
        """New config with the fields of a "config" message applied (clamped). Missing or unusable fields keep their value."""
        width, fps, quality = self.max_width, self.fps, self.quality
        if (n := _number(d.get("max_width"))) is not None:
            n = round(n); width = 0 if n <= 0 else min(WIDTH_MAX, max(WIDTH_MIN, n))
        if (n := _number(d.get("fps"))) is not None: fps = min(FPS_MAX, max(FPS_MIN, round(n)))
        if (n := _number(d.get("quality"))) is not None: quality = min(QUALITY_MAX, max(QUALITY_MIN, round(n)))
        return StreamConfig(width, fps, quality)


def encode_frame(raw: bytes, size: tuple[int, int], cursor: tuple[float, float] | None = None,
                 max_width: int | None = None, quality: int | None = None) -> tuple[bytes, tuple[int, int]]:
    """BGRA screen bytes -> (JPEG bytes, (width, height)) with optional downscale and cursor overlay.

    max_width (0 = native) and quality default to the server settings."""
    max_width = settings.max_width if max_width is None else max_width
    quality = settings.jpeg_quality if quality is None else quality
    img = Image.frombytes("RGB", size, raw, "raw", "BGRX")
    scale = 1.0
    if max_width and img.width > max_width:
        scale = max_width / img.width
        img = img.resize((max_width, max(1, round(img.height * scale))), Image.BILINEAR)
    if cursor is not None:
        _draw_cursor(img, cursor[0] * scale, cursor[1] * scale)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue(), img.size


async def _authenticate(ws: WebSocket) -> bool:
    key = security.client_key(ws.headers, ws.client)
    if security.is_blocked(key):
        await ws.close(code=4429, reason="Too many failed attempts"); return False
    auth = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=8))
    if not security.token_ok(str(auth.get("token", ""))):
        security.record_fail(key); await ws.close(code=4401); return False
    security.record_success(key)
    return True


def _on_windows() -> bool:
    return platform.system() == "Windows"


@contextlib.contextmanager
def _capture_source():
    """Yield grab() -> (raw BGRX bytes, (w, h), cursor position or None, change digest) for the primary monitor."""
    import mss
    from pynput import mouse
    enable_dpi_awareness()
    pointer = mouse.Controller()
    with mss.mss() as sct:
        mon = sct.monitors[1]

        def grab():
            shot = sct.grab(mon)
            cur = None
            if settings.show_cursor:
                px, py = pointer.position
                if mon["left"] <= px < mon["left"] + mon["width"] and mon["top"] <= py < mon["top"] + mon["height"]:
                    cur = (px - mon["left"], py - mon["top"])
            return shot.raw, shot.size, cur, zlib.crc32(shot.raw) ^ hash(cur)

        yield grab


class _StreamState:
    def __init__(self):
        self.config = StreamConfig.from_settings()
        self.dirty = False                # a config message arrived: send a fresh screen message + frame
        self.closed = False               # the client went away
        self.wake = asyncio.Event()       # cuts the frame-interval sleep short
        self.acks = False                 # the client sends acks, so flow control and quality adaptation are on
        self.inflight = 0                 # frames sent and not yet acknowledged
        self.sent_at: collections.deque = collections.deque()
        self.rtt = 0.0                    # smoothed seconds between sending a frame and its ack


def adaptive_quality(quality: int, rtt: float) -> int:
    """Lower the JPEG quality when frames take long to arrive, so the stream catches up instead of lagging."""
    if rtt > 0.35: return max(QUALITY_MIN, quality - 25)
    if rtt > 0.20: return max(QUALITY_MIN, quality - 12)
    return quality


async def _read_client(ws: WebSocket, state: _StreamState) -> None:
    """Read client messages while frames are being streamed; only "config" is understood."""
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect": break
            text = msg.get("text")
            if text is None: continue
            try: d = json.loads(text)
            except (ValueError, RecursionError): continue
            if isinstance(d, dict) and d.get("type") == "ack":
                state.acks = True
                state.inflight = max(0, state.inflight - 1)
                if state.sent_at:
                    rtt = asyncio.get_running_loop().time() - state.sent_at.popleft()
                    state.rtt = rtt if state.rtt == 0.0 else state.rtt * 0.7 + rtt * 0.3
                state.wake.set()
            elif isinstance(d, dict) and d.get("type") == "config":
                state.config = state.config.updated(d)
                state.dirty = True; state.wake.set()
    except Exception:
        pass
    finally:
        state.closed = True; state.wake.set()


async def stream_frames(ws: WebSocket, grab) -> None:
    """Send screen frames until the client disconnects, applying "config" messages live."""
    state = _StreamState()
    loop = asyncio.get_running_loop()
    reader = asyncio.create_task(_read_client(ws, state))
    try:
        last_digest, last_jpeg, last_sent, size_sent = None, None, 0.0, None
        while not state.closed:
            started = loop.time()
            if state.dirty:   # config changed: re-encode even an unchanged screen and re-announce the size
                state.dirty = False; last_digest = None; size_sent = None
            cfg = state.config
            if state.acks and state.inflight >= MAX_IN_FLIGHT:
                # The client has not shown the previous frames yet: wait instead of queueing more (newest screen wins).
                state.wake.clear()
                try: await asyncio.wait_for(state.wake.wait(), ACK_TIMEOUT)
                except asyncio.TimeoutError: state.inflight = 0; state.sent_at.clear()
                continue
            raw, size, cur, digest = await asyncio.to_thread(grab)
            if digest != last_digest:
                quality = adaptive_quality(cfg.quality, state.rtt) if state.acks else cfg.quality
                last_jpeg, out = await asyncio.to_thread(encode_frame, raw, size, cur, cfg.max_width, quality)
                last_digest = digest
                if out != size_sent:
                    await ws.send_json({"type": "screen", "width": out[0], "height": out[1],
                                        "max_width": cfg.max_width, "fps": cfg.fps, "quality": cfg.quality})
                    size_sent = out
                await ws.send_bytes(last_jpeg); last_sent = loop.time()
                state.inflight += 1; state.sent_at.append(last_sent)
            elif last_jpeg is not None and loop.time() - last_sent >= KEEPALIVE_SECONDS:
                await ws.send_bytes(last_jpeg); last_sent = loop.time()
                state.inflight += 1; state.sent_at.append(last_sent)
            if state.dirty or state.closed: continue
            state.wake.clear()
            try: await asyncio.wait_for(state.wake.wait(), max(0.0, 1 / cfg.fps - (loop.time() - started)))
            except asyncio.TimeoutError: pass
    finally:
        reader.cancel()


async def screen_socket(ws: WebSocket):
    await ws.accept()
    try:
        if not await _authenticate(ws): return
        await ws.send_json({"type": "ready"})
        if not _on_windows():
            await ws.send_json({"type": "error", "message": "Windows required"}); return
        with _capture_source() as grab:
            await stream_frames(ws, grab)
    except WebSocketDisconnect: return
    except asyncio.TimeoutError: await ws.close(code=4401, reason="Authentication timeout")
    except Exception as exc:
        try: await ws.send_json({"type": "error", "message": type(exc).__name__}); await ws.close(code=1011)
        except Exception: pass


def key_map(keyboard) -> dict:
    k = keyboard.Key
    m = {"ENTER": k.enter, "TAB": k.tab, "BACKSPACE": k.backspace, "ESC": k.esc, "SPACE": k.space,
         "UP": k.up, "DOWN": k.down, "LEFT": k.left, "RIGHT": k.right, "CTRL": k.ctrl, "ALT": k.alt,
         "SHIFT": k.shift, "DELETE": k.delete, "HOME": k.home, "END": k.end, "PAGEUP": k.page_up,
         "PAGEDOWN": k.page_down, "WIN": k.cmd}
    for i in range(1, 13): m[f"F{i}"] = getattr(k, f"f{i}")
    return m


def handle_input(d: dict, mon: dict, mouse_ctl, kb_ctl, mouse_mod, keys: dict) -> None:
    """Apply one input message. Raises nothing for malformed input; unknown messages are ignored."""
    kind = d.get("type")
    button = {"left": mouse_mod.Button.left, "right": mouse_mod.Button.right, "middle": mouse_mod.Button.middle}.get(d.get("button", "left"), mouse_mod.Button.left)
    pos = to_screen_xy(d, mon)
    if kind in ("move", "click", "down", "up") and pos is not None:
        mouse_ctl.position = pos
    if kind == "rel":
        target = rel_screen_xy(d, mon, mouse_ctl.position)
        if target is not None: mouse_ctl.position = target
    elif kind == "click":
        mouse_ctl.click(button, 2 if int(d.get("count", 1)) == 2 else 1)
    elif kind == "down": mouse_ctl.press(button)
    elif kind == "up": mouse_ctl.release(button)
    elif kind == "scroll":
        clamp = lambda v: max(-MAX_SCROLL, min(MAX_SCROLL, int(v)))
        dx, dy = clamp(d.get("dx", 0)), clamp(d.get("dy", 0))
        if dx or dy: mouse_ctl.scroll(dx, dy)
    elif kind == "key":
        key = str(d.get("key", ""))
        if len(key) == 1 and key.isprintable(): kb_ctl.press(key); kb_ctl.release(key)
        elif key.upper() in keys: kb_ctl.press(keys[key.upper()]); kb_ctl.release(keys[key.upper()])
    elif kind == "hotkey":
        seq = []
        for name in list(d.get("keys", []))[:4]:
            name = str(name)
            if name.upper() in keys: seq.append(keys[name.upper()])
            elif len(name) == 1 and name.isprintable(): seq.append(name.lower())
            else: return
        for key in seq: kb_ctl.press(key)
        for key in reversed(seq): kb_ctl.release(key)
    elif kind == "type": kb_ctl.type(str(d.get("text", ""))[:500])


def coalesce_input(messages: list[dict]) -> list[dict]:
    """Merge a backlog of pointer moves so a slow moment never turns into a delayed, rubber-band pointer.

    Consecutive "rel" messages are summed; consecutive absolute "move" messages keep only the last one.
    Everything else (clicks, keys, scroll...) keeps its order and is never dropped."""
    out: list[dict] = []
    for d in messages:
        kind = d.get("type")
        if out and kind == "rel" and out[-1].get("type") == "rel":
            prev = out[-1]
            prev["dx"] = (_number(prev.get("dx")) or 0) + (_number(d.get("dx")) or 0)
            prev["dy"] = (_number(prev.get("dy")) or 0) + (_number(d.get("dy")) or 0)
        elif out and kind == "move" and out[-1].get("type") == "move":
            out[-1] = d
        else:
            out.append(dict(d) if kind == "rel" else d)
    return out


async def input_socket(ws: WebSocket):
    await ws.accept()
    pump_task = None
    try:
        if not await _authenticate(ws): return
        enable_dpi_awareness()
        from pynput import keyboard, mouse
        m, k = mouse.Controller(), keyboard.Controller()
        keys = key_map(keyboard)
        mon = await asyncio.to_thread(primary_monitor)
        await ws.send_json({"type": "ready"})

        # A separate reader keeps receiving while input is applied, so messages are batched (and pointer moves merged)
        # instead of piling up in a queue when the PC or the link is briefly slow.
        inbox: collections.deque = collections.deque()
        wake = asyncio.Event()
        gone: list[BaseException] = []

        async def pump():
            try:
                while True:
                    inbox.append(await ws.receive_text()); wake.set()
            except Exception as exc:
                gone.append(exc)
            finally:
                wake.set()

        pump_task = asyncio.create_task(pump())
        while True:
            await wake.wait(); wake.clear()
            batch = []
            while inbox:
                try: d = json.loads(inbox.popleft())
                except (json.JSONDecodeError, RecursionError): continue
                if isinstance(d, dict): batch.append(d)
            for d in coalesce_input(batch):
                try: handle_input(d, mon, m, k, mouse, keys)
                except Exception: pass   # a bad message must not kill the whole session
            if gone and not inbox: raise gone[0]
    except WebSocketDisconnect: return
    except asyncio.TimeoutError: await ws.close(code=4401, reason="Authentication timeout")
    except Exception:
        try: await ws.close(code=1008, reason="Invalid input")
        except Exception: pass
    finally:
        if pump_task: pump_task.cancel()
