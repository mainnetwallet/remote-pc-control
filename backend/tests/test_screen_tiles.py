"""Changed-region updates ("tiles" mode) on /ws/screen: only what changed after a click is encoded and sent."""
import asyncio, io

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

from app import screen
from app.config import settings

W, H = 800, 450
H_LEN = screen.TILE_HEADER.size


@pytest.fixture(autouse=True)
def server_defaults(monkeypatch):
    monkeypatch.setattr(settings, "max_width", 1280)
    monkeypatch.setattr(settings, "fps", 30)
    monkeypatch.setattr(settings, "jpeg_quality", 70)


def scene(extra=None, size=(W, H)):
    """A busy desktop-like picture (lines and blocks), optionally with one more rectangle drawn on it."""
    img = Image.new("RGB", size, (30, 60, 90))
    d = ImageDraw.Draw(img)
    for i in range(0, size[0], 16): d.line([(i, 0), (size[0] - i, size[1])], fill=(200, 200, 40), width=1)
    for i in range(0, size[1], 24): d.rectangle([20, i, 200, i + 10], fill=(240, 240, 240))
    if extra: d.rectangle(extra, fill=(220, 30, 30))
    return img


def bgrx(img):
    return img.tobytes("raw", "BGRX")


def parse(msg):
    kind, x, y, w, h = screen.TILE_HEADER.unpack(msg[:H_LEN])
    return kind, (x, y, w, h), Image.open(io.BytesIO(msg[H_LEN:])).convert("RGB")


def mean_diff(a, b):
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


# ---- changed_region -----------------------------------------------------------

def test_region_gets_padding_and_stays_inside_the_screen():
    assert screen.changed_region((100, 100, 120, 110), (W, H), (W, H)) == (96, 96, 124, 114)
    assert screen.changed_region((0, 0, 5, 5), (W, H), (W, H)) == (0, 0, 9, 9)
    assert screen.changed_region((795, 445, 800, 450), (W, H), (W, H)) == (791, 441, 800, 450)


def test_region_is_mapped_into_the_downscaled_picture():
    assert screen.changed_region((960, 540, 980, 550), (1920, 1080), (1280, 720)) == (637, 357, 656, 370)


def test_large_changes_are_not_regions():
    assert screen.changed_region((0, 0, W, H), (W, H), (W, H)) is None
    assert screen.changed_region((0, 0, 600, 450), (W, H), (W, H)) is None      # 75 % of the screen


# ---- encode_update ------------------------------------------------------------

def test_first_update_is_a_full_frame():
    msg, out, img, kind = screen.encode_update(bgrx(scene()), (W, H), None, None, 0, 70)
    k, (x, y, w, h), pic = parse(msg)
    assert (kind, k, x, y, w, h, out) == (screen.KIND_FULL, screen.KIND_FULL, 0, 0, W, H, (W, H))
    assert pic.size == (W, H) and img.size == (W, H)


def test_unchanged_screen_sends_nothing():
    raw = bgrx(scene())
    _, out, img, _ = screen.encode_update(raw, (W, H), None, None, 0, 70)
    msg, _, _, _ = screen.encode_update(raw, (W, H), img, out, 0, 70)
    assert msg is None


@pytest.mark.parametrize("max_width", [0, 400, 500])   # native, exact half, a scale that does not divide evenly
def test_region_applied_over_the_old_picture_equals_the_new_full_frame(max_width):
    old, new = scene(), scene(extra=(300, 200, 360, 230))
    m1, out, img, _ = screen.encode_update(bgrx(old), (W, H), None, None, max_width, 80)
    m2, out2, _, kind = screen.encode_update(bgrx(new), (W, H), img, out, max_width, 80)
    assert kind == screen.KIND_REGION and out2 == out
    _, (x, y, w, h), piece = parse(m2)
    assert 0 <= x and 0 <= y and x + w <= out[0] and y + h <= out[1]
    assert w * h < 0.1 * out[0] * out[1]                      # a small rectangle, not the screen
    assert len(m2) < len(m1) / 4                              # and far fewer bytes than a full frame
    canvas = parse(m1)[2]
    canvas.paste(piece, (x, y))
    reference = parse(screen.encode_update(bgrx(new), (W, H), None, None, max_width, 80)[0])[2]
    assert canvas.size == reference.size
    assert mean_diff(canvas, reference) < 1.5                 # same picture; only JPEG noise may differ


def test_a_big_change_falls_back_to_a_full_frame():
    _, out, img, _ = screen.encode_update(bgrx(scene()), (W, H), None, None, 0, 70)
    msg, _, _, kind = screen.encode_update(bgrx(scene(extra=(0, 0, 700, 400))), (W, H), img, out, 0, 70)
    assert kind == screen.KIND_FULL and parse(msg)[0] == screen.KIND_FULL


def test_a_new_picture_size_forces_a_full_frame():
    _, _, img, _ = screen.encode_update(bgrx(scene()), (W, H), None, None, 0, 70)
    msg, out, _, kind = screen.encode_update(bgrx(scene(extra=(300, 200, 330, 220))), (W, H), img, (400, 225), 0, 70)
    assert kind == screen.KIND_FULL and out == (W, H)          # the client still holds a 400 px picture


def test_screen_resolution_change_forces_a_full_frame():
    _, out, img, _ = screen.encode_update(bgrx(scene()), (W, H), None, None, 0, 70)
    small = (640, 360)
    msg, out2, _, kind = screen.encode_update(bgrx(scene(size=small)), small, img, out, 0, 70)
    assert kind == screen.KIND_FULL and out2 == small


# ---- /ws/screen end to end ----------------------------------------------------

class FakeWS:
    def __init__(self): self.inbox = asyncio.Queue(); self.sent = []
    async def receive(self): return await self.inbox.get()
    async def send_json(self, d): self.sent.append(d)
    async def send_bytes(self, b): self.sent.append(b)
    def say(self, text): self.inbox.put_nowait({"type": "websocket.receive", "text": text})


async def run_session(config_json, scenes, pause=0.25):
    """Stream while the screen shows each scene in turn; returns everything the server sent."""
    holder = {"raw": bgrx(scenes[0]), "n": 1}
    def grab(): return holder["raw"], (W, H), None, holder["n"]
    ws = FakeWS()
    task = asyncio.create_task(screen.stream_frames(ws, grab))
    await asyncio.sleep(pause)
    ws.say(config_json)
    await asyncio.sleep(pause)
    for s in scenes[1:]:
        holder["raw"] = bgrx(s); holder["n"] += 1
        await asyncio.sleep(pause)
    ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
    await asyncio.wait_for(task, 3)
    return ws.sent


def test_tiles_client_gets_announcement_full_frame_then_regions():
    sent = asyncio.run(run_session('{"type":"config","max_width":0,"fps":30,"quality":70,"cursor":true,"tiles":true}',
                                   [scene(), scene(extra=(300, 200, 360, 230)), scene(extra=(500, 100, 560, 130))]))
    first_tiles = next(i for i, m in enumerate(sent) if isinstance(m, dict) and m.get("tiles"))
    assert sent[first_tiles]["width"] == W and sent[first_tiles]["height"] == H
    kinds = [parse(m)[0] for m in sent[first_tiles + 1:] if isinstance(m, bytes)]
    assert kinds[0] == screen.KIND_FULL
    assert kinds.count(screen.KIND_REGION) >= 2 and screen.KIND_FULL not in kinds[1:]
    assert sum(isinstance(m, dict) and m.get("tiles") is True for m in sent) == 1   # announced once, not per frame


def test_before_the_config_arrives_and_without_tiles_frames_are_plain_jpeg():
    sent = asyncio.run(run_session('{"type":"config","max_width":0,"fps":30,"quality":70,"cursor":true}',
                                   [scene(), scene(extra=(300, 200, 360, 230))]))
    frames = [m for m in sent if isinstance(m, bytes)]
    assert frames and all(f[:2] == b"\xff\xd8" for f in frames)       # no header: old clients are unaffected
    assert not any(isinstance(m, dict) and "tiles" in m for m in sent)


def test_tiles_need_the_client_to_draw_the_pointer():
    sent = asyncio.run(run_session('{"type":"config","max_width":0,"fps":30,"quality":70,"tiles":true}',
                                   [scene(), scene(extra=(300, 200, 360, 230))]))
    frames = [m for m in sent if isinstance(m, bytes)]
    assert frames and all(f[:2] == b"\xff\xd8" for f in frames)
    assert not any(isinstance(m, dict) and "tiles" in m for m in sent)


def test_a_config_message_refreshes_the_whole_picture():
    async def run():
        holder = {"raw": bgrx(scene()), "n": 1}
        def grab(): return holder["raw"], (W, H), None, holder["n"]
        ws = FakeWS()
        task = asyncio.create_task(screen.stream_frames(ws, grab))
        ws.say('{"type":"config","max_width":0,"fps":30,"cursor":true,"tiles":true}')
        await asyncio.sleep(0.3)
        n_before = len(ws.sent)
        ws.say('{"type":"config","quality":50}')                      # e.g. the user picked another quality
        await asyncio.sleep(0.3)
        ws.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 3)
        return ws.sent[n_before:]
    after = asyncio.run(run())
    screens = [m for m in after if isinstance(m, dict)]
    frames = [parse(m)[0] for m in after if isinstance(m, bytes)]
    assert screens and screens[0].get("tiles") is True and frames[0] == screen.KIND_FULL
