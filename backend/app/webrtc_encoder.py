"""Low-latency H.264 encoder for aiortc.

aiortc's built-in H264Encoder always uses libx264 with the default (slow) preset and clamps the bitrate to
0.5-3 Mbit/s. LowLatencyH264Encoder replaces it:

  * hardware encoders first when available (h264_nvenc, h264_qsv, h264_amf), then libx264 with
    preset ultrafast + tune zerolatency; no B-frames, so a frame leaves as soon as it is encoded;
  * a backend that fails to open or to encode is skipped for the rest of the process (libx264 always works);
  * the bitrate follows the receiver's estimate (REMB) but never exceeds the cap set by the user's config.

It is installed with install(), which swaps the encoder aiortc creates for "video/h264". The whole module imports
aiortc lazily, so the server still starts (and the WebSocket stream still works) when aiortc is not installed.
"""
import contextlib, fractions, logging, threading, time

log = logging.getLogger("remote_pc.webrtc")

MIN_BITRATE = 300_000
INITIAL_BITRATE = 3_000_000    # used until the receiver reports its own estimate
FLOOR_BITRATE = 1_000_000      # the receiver's estimate never lowers the bitrate below this (or below the cap, if that is lower):
                               # on a mostly still screen the estimate sinks, and the next scroll would arrive blocky
FLOOR_SHARE = 6                # ...and never below 1/FLOOR_SHARE of the cap when that is higher, so a High/Native preset
                               # (cap 8-20 Mbit/s) does not sink to the picture of a Low one between two scrolls
REOPEN_RATIO = 0.25            # the encoder is re-opened only when the target moved by more than this fraction...
REOPEN_MIN_SECONDS = 2.0       # ...and not more often than this (re-opening a hardware encoder takes a moment)
GOP_FRAMES = 120               # a key frame at least this often; receivers also ask for one (PLI) after packet loss
ORDER = ("nvenc", "qsv", "amf", "x264")
FFMPEG_NAMES = {"nvenc": "h264_nvenc", "qsv": "h264_qsv", "amf": "h264_amf", "x264": "libx264"}


class Limits:
    """Process-wide limits set from the clients' config messages (the encoder object is created inside aiortc, so
    this is the only way to reach it). With several sessions the highest requested bitrate wins."""
    _lock = threading.Lock()
    _per_owner: dict = {}
    default_bps = 4_000_000

    @classmethod
    def set(cls, owner, bitrate_bps: int | None) -> None:
        with cls._lock:
            if bitrate_bps is None: cls._per_owner.pop(owner, None)
            else: cls._per_owner[owner] = int(bitrate_bps)

    @classmethod
    def cap(cls) -> int:
        with cls._lock:
            return max(cls._per_owner.values(), default=cls.default_bps)

    @classmethod
    def reset(cls) -> None:
        with cls._lock: cls._per_owner.clear()


def floor_for(cap: int) -> int:
    """Lowest bitrate the receiver's estimate may push the encoder to: 1 Mbit/s, or 1/FLOOR_SHARE of the cap when that is
    higher; never above the cap itself."""
    return min(cap, max(FLOOR_BITRATE, cap // FLOOR_SHARE))


def backend_order(preference: str, failed: set[str], available=None) -> list[str]:
    """Encoders to try, best first. A forced backend goes first and libx264 is always the last resort."""
    pref = (preference or "auto").strip().lower()
    order = list(ORDER) if pref not in ORDER else ([pref] + [b for b in ORDER if b != pref and b == "x264"])
    out = []
    for name in order:
        if name != "x264" and (name in failed or (available is not None and FFMPEG_NAMES[name] not in available)): continue
        out.append(name)
    return out or ["x264"]


def codec_options(backend: str) -> dict:
    """ffmpeg private options for each backend: lowest latency, constant-ish bitrate, no look-ahead, no B-frames."""
    if backend == "nvenc":
        return {"preset": "p1", "tune": "ull", "rc": "cbr", "zerolatency": "1", "delay": "0", "bf": "0", "forced-idr": "1"}
    if backend == "qsv":
        return {"preset": "veryfast", "look_ahead": "0", "async_depth": "1", "forced_idr": "1"}
    if backend == "amf":
        return {"usage": "ultralowlatency", "quality": "speed", "rc": "cbr"}
    return {"preset": "ultrafast", "tune": "zerolatency", "forced-idr": "1"}


def make_encoder_class():
    """Build LowLatencyH264Encoder (needs aiortc, so it is created on demand)."""
    import av
    from aiortc.codecs.h264 import H264Encoder
    from aiortc.mediastreams import VIDEO_TIME_BASE, convert_timebase  # noqa: F401  (kept for parity with the base class)
    from .config import settings

    class LowLatencyH264Encoder(H264Encoder):
        failed: set[str] = set()   # backends that did not work in this process

        def __init__(self):
            super().__init__()
            self._requested: int | None = None   # the receiver's bitrate estimate (REMB) in bit/s
            self._backend: str | None = None
            self._opened_at = 0.0

        @property
        def target_bitrate(self) -> int:
            cap = max(MIN_BITRATE, Limits.cap())
            asked = self._requested if self._requested is not None else INITIAL_BITRATE
            return max(floor_for(cap), min(cap, asked))

        @target_bitrate.setter
        def target_bitrate(self, bitrate: int) -> None:
            self._requested = int(bitrate)

        @property
        def backend(self) -> str | None:
            return self._backend

        def _open(self, frame, bitrate: int) -> None:
            last_error = None
            for name in backend_order(settings.rtc_encoder, self.failed, av.codecs_available):
                try:
                    ctx = av.CodecContext.create(FFMPEG_NAMES[name], "w")
                    ctx.width, ctx.height = frame.width, frame.height
                    ctx.bit_rate = bitrate
                    ctx.pix_fmt = "nv12" if name == "qsv" else "yuv420p"
                    ctx.framerate = fractions.Fraction(30, 1)
                    ctx.time_base = fractions.Fraction(1, 30)
                    ctx.gop_size = GOP_FRAMES
                    ctx.max_b_frames = 0
                    opts = codec_options(name)
                    if name == "x264": opts["level"] = "42" if frame.width * frame.height > 1280 * 720 else "31"
                    ctx.options = opts
                    with contextlib.suppress(Exception): ctx.profile = "Baseline"
                    ctx.open()
                    self.codec, self._backend, self._opened_at = ctx, name, time.monotonic()
                    log.info("WebRTC encoder: %s %dx%d %d kbit/s", FFMPEG_NAMES[name], frame.width, frame.height, bitrate // 1000)
                    return
                except Exception as exc:
                    last_error = exc
                    if name != "x264":
                        self.failed.add(name)
                        log.info("WebRTC encoder %s unavailable (%s: %s); trying the next one", FFMPEG_NAMES[name], type(exc).__name__, exc)
            raise RuntimeError(f"no H.264 encoder could be opened: {last_error}")

        def _needs_reopen(self, frame, bitrate: int) -> bool:
            if self.codec is None: return True
            if frame.width != self.codec.width or frame.height != self.codec.height: return True
            cur = max(1, self.codec.bit_rate)
            return abs(bitrate - cur) / cur > REOPEN_RATIO and time.monotonic() - self._opened_at >= REOPEN_MIN_SECONDS

        def _encode_frame(self, frame, force_keyframe: bool):
            bitrate = self.target_bitrate
            if self._needs_reopen(frame, bitrate):
                self.buffer_data = b""; self.buffer_pts = None
                self.codec = None
                self._open(frame, bitrate)
            frame.pict_type = av.video.frame.PictureType.I if force_keyframe else av.video.frame.PictureType.NONE
            try:
                data = b"".join(bytes(p) for p in self.codec.encode(frame))
            except Exception as exc:
                if self._backend in (None, "x264"): raise
                # A hardware encoder that opened but cannot encode (no GPU, driver problem): give it up for good.
                self.failed.add(self._backend)
                log.info("WebRTC encoder %s failed while encoding (%s); switching", FFMPEG_NAMES[self._backend], type(exc).__name__)
                self.codec = None
                self._open(frame, bitrate)
                frame.pict_type = av.video.frame.PictureType.I
                data = b"".join(bytes(p) for p in self.codec.encode(frame))
            if data: yield from self._split_bitstream(data)

    return LowLatencyH264Encoder


_installed = None


def install():
    """Make aiortc use LowLatencyH264Encoder for H.264. Safe to call repeatedly. Returns the encoder class."""
    global _installed
    if _installed is None:
        import aiortc.codecs
        cls = make_encoder_class()
        aiortc.codecs.H264Encoder = cls   # get_encoder() looks the class up in this module's namespace
        _installed = cls
        Limits.default_bps = _default_cap()
    return _installed


def _default_cap() -> int:
    from .config import settings
    return int(settings.rtc_bitrate) * 1000


def probe_backends(encoder_cls=None, width: int = 1280, height: int = 720) -> str | None:
    """Open (and test-encode one frame with) each encoder in turn, best first, and remember the ones that do not work in
    encoder_cls.failed. Returns the backend that will be used, or None when probing was not possible.

    Done once at server start: otherwise the FIRST WebRTC connection after a PC restart pays for the failing hardware
    encoder attempts (a driver that is still waking up can take seconds) and the phone gives up waiting for video."""
    import av
    from .config import settings
    cls = encoder_cls or install()
    for name in backend_order(settings.rtc_encoder, cls.failed, av.codecs_available):
        if name == "x264": return name   # always available: nothing to learn
        try:
            ctx = av.CodecContext.create(FFMPEG_NAMES[name], "w")
            ctx.width, ctx.height, ctx.bit_rate = width, height, INITIAL_BITRATE
            ctx.pix_fmt = "nv12" if name == "qsv" else "yuv420p"
            ctx.framerate = fractions.Fraction(30, 1); ctx.time_base = fractions.Fraction(1, 30)
            ctx.gop_size = GOP_FRAMES; ctx.max_b_frames = 0
            ctx.options = codec_options(name)
            ctx.open()
            frame = av.VideoFrame(width, height, "yuv420p")
            for plane in frame.planes: plane.update(bytes(plane.buffer_size))
            frame.pts = 0
            list(ctx.encode(frame)); list(ctx.encode(None))
            return name
        except Exception as exc:
            cls.failed.add(name)
            log.info("WebRTC encoder %s unavailable at start-up (%s: %s)", FFMPEG_NAMES[name], type(exc).__name__, exc)
    return "x264"

