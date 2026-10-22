"""Live screen streaming (/ws/screen) and mouse/keyboard input (/ws/input).

Protocol (JSON text frames, after the client sends {"token": "..."} first):

  /ws/screen  server -> client: {"type":"ready"}, {"type":"screen","width":W,"height":H},
              then binary JPEG frames.
  /ws/input   client -> server:
      {"type":"move",   "nx":0..1, "ny":0..1}                    cursor to a normalized position
      {"type":"click",  "button":"left|right|middle", "count":1|2, "nx":.., "ny":..}
      {"type":"down"|"up", "button":"left", "nx":.., "ny":..}    press/release (for drag)
      {"type":"scroll", "dx":int, "dy":int}                      wheel steps (dy>0 = up)
      {"type":"key",    "key":"ENTER"}                           single key
      {"type":"hotkey", "keys":["CTRL","C"]}                     key combination
      {"type":"type",   "text":"hello"}                          type text
  Pixel coordinates ("x","y") are still accepted for older clients.

Normalized coordinates make the mapping independent of the (possibly downscaled)
frame the phone is showing, and of Windows display scaling.
"""
import asyncio, hmac, io, json, platform, zlib
from fastapi import WebSocket, WebSocketDisconnect
from PIL import Image, ImageDraw
from .config import settings
from . import security

KEEPALIVE_SECONDS = 3.0   # resend the last frame so idle screens don't hit client read timeouts
MAX_SCROLL = 20
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


def _draw_cursor(img: Image.Image, x: float, y: float) -> None:
    s = max(10, img.width // 80)
    pts = [(x, y), (x, y + s * 1.6), (x + s * 0.45, y + s * 1.25), (x + s * 0.8, y + s * 1.9), (x + s * 1.1, y + s * 1.75), (x + s * 0.75, y + s * 1.15), (x + s * 1.25, y + s * 1.1)]
    ImageDraw.Draw(img).polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))


def encode_frame(raw: bytes, size: tuple[int, int], cursor: tuple[float, float] | None = None) -> tuple[bytes, tuple[int, int]]:
    """BGRA screen bytes -> (JPEG bytes, (width, height)) with optional downscale and cursor overlay."""
    img = Image.frombytes("RGB", size, raw, "raw", "BGRX")
    scale = 1.0
    if settings.max_width and img.width > settings.max_width:
        scale = settings.max_width / img.width
        img = img.resize((settings.max_width, max(1, round(img.height * scale))), Image.BILINEAR)
    if cursor is not None:
        _draw_cursor(img, cursor[0] * scale, cursor[1] * scale)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=settings.jpeg_quality)
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


async def screen_socket(ws: WebSocket):
    await ws.accept()
    try:
        if not await _authenticate(ws): return
        await ws.send_json({"type": "ready"})
        if platform.system() != "Windows":
            await ws.send_json({"type": "error", "message": "Windows required"}); return
        import mss
        from pynput import mouse
        enable_dpi_awareness()
        pointer = mouse.Controller()
        loop = asyncio.get_running_loop()
        with mss.mss() as sct:
            mon = sct.monitors[1]

            def grab():
                shot = sct.grab(mon)
                cur = None
                if settings.show_cursor:
                    px, py = pointer.position
                    if mon["left"] <= px < mon["left"] + mon["width"] and mon["top"] <= py < mon["top"] + mon["height"]:
                        cur = (px - mon["left"], py - mon["top"])
                digest = zlib.crc32(shot.raw) ^ hash(cur)
                return shot, cur, digest

            last_digest, last_jpeg, last_sent, size_sent = None, None, 0.0, None
            while True:
                started = loop.time()
                shot, cur, digest = await asyncio.to_thread(grab)
                if digest != last_digest:
                    last_jpeg, size = await asyncio.to_thread(encode_frame, shot.raw, shot.size, cur)
                    last_digest = digest
                    if size != size_sent:
                        await ws.send_json({"type": "screen", "width": size[0], "height": size[1]}); size_sent = size
                    await ws.send_bytes(last_jpeg); last_sent = loop.time()
                elif last_jpeg is not None and loop.time() - last_sent >= KEEPALIVE_SECONDS:
                    await ws.send_bytes(last_jpeg); last_sent = loop.time()
                await asyncio.sleep(max(0.0, 1 / settings.fps - (loop.time() - started)))
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
    if kind == "click":
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


async def input_socket(ws: WebSocket):
    await ws.accept()
    held = False
    try:
        if not await _authenticate(ws): return
        enable_dpi_awareness()
        from pynput import keyboard, mouse
        m, k = mouse.Controller(), keyboard.Controller()
        keys = key_map(keyboard)
        mon = await asyncio.to_thread(primary_monitor)
        await ws.send_json({"type": "ready"})
        while True:
            try: d = json.loads(await ws.receive_text())
            except json.JSONDecodeError: continue
            if not isinstance(d, dict): continue
            if d.get("type") == "down": held = True
            elif d.get("type") == "up": held = False
            try: handle_input(d, mon, m, k, mouse, keys)
            except Exception: pass   # a bad message must not kill the whole session
    except WebSocketDisconnect: return
    except asyncio.TimeoutError: await ws.close(code=4401, reason="Authentication timeout")
    except Exception:
        try: await ws.close(code=1008, reason="Invalid input")
        except Exception: pass
    finally:
        if held:  # never leave a mouse button stuck down if the phone disconnects mid-drag
            try:
                from pynput import mouse as _mouse
                _mouse.Controller().release(_mouse.Button.left)
            except Exception: pass
