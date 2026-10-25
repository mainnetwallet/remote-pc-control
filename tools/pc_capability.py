"""Check what this PC can really do and recommend FPS settings.

Run it ON THE PC you want to control (not on the phone):

    python tools/pc_capability.py            # measure and print a report
    python tools/pc_capability.py --apply    # also write the recommended values into .env

It measures:
  * monitor refresh rate (Windows)
  * real screen-capture speed (dxcam if installed, otherwise mss)
  * JPEG encode speed at the stream widths (WebSocket mode)
  * which H.264 encoders work (NVENC / QSV / AMF / x264) and how fast each one is (WebRTC mode)

The recommendation is the lowest of those limits, so the stream never asks the PC for more than it can deliver.
"""
from __future__ import annotations

import argparse
import io
import os
import platform
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_FPS_CAP = 120         # FPS_CEILING (WebRTC) in backend/app/config.py
WS_FPS_CAP = 120           # WS_FPS_CEILING (JPEG over WebSocket), same as the WebRTC ceiling
TEST_SECONDS = 2.0
WIDTHS = (960, 1280, 1920, 2560, 3840)


def monitor_refresh_hz() -> int | None:
    """Refresh rate of the primary monitor in Hz (Windows only)."""
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DEVMODE(ctypes.Structure):
            _fields_ = [("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
                        ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
                        ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
                        ("dmPositionX", wintypes.LONG), ("dmPositionY", wintypes.LONG),
                        ("dmDisplayOrientation", wintypes.DWORD), ("dmDisplayFixedOutput", wintypes.DWORD),
                        ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
                        ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
                        ("dmCollate", ctypes.c_short), ("dmFormName", wintypes.WCHAR * 32),
                        ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
                        ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
                        ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
                        ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
                        ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
                        ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
                        ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD)]

        dm = DEVMODE(); dm.dmSize = ctypes.sizeof(DEVMODE)
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):   # -1 = current settings
            return int(dm.dmDisplayFrequency) or None
    except Exception:
        pass
    return None


def cpu_info() -> str:
    try:
        import psutil
        cores = f"{psutil.cpu_count(logical=False)} cores / {psutil.cpu_count()} threads"
    except Exception:
        cores = f"{os.cpu_count()} threads"
    return f"{platform.processor() or platform.machine()} ({cores})"


def measure_capture() -> tuple[str, float | None, tuple[int, int] | None]:
    """(method, frames per second, (w, h)) of the fastest working capture method."""
    results = []
    if platform.system() == "Windows":
        try:
            import dxcam
            # dxcam only returns a frame when the screen CHANGED, so a still desktop measures 0 fps.
            # Keep a small window flashing during the test so the screen is always changing.
            root = canvas = None
            try:
                import tkinter as tk
                root = tk.Tk(); root.title("capture test"); root.geometry("300x200+50+50")
                root.attributes("-topmost", True)
                canvas = tk.Canvas(root, width=300, height=200, highlightthickness=0); canvas.pack()
            except Exception:
                root = None
            cam = dxcam.create(output_color="BGRA", processor_backend="numpy")
            cam.start(target_fps=240)
            n, size, tick, end = 0, None, 0, time.perf_counter() + TEST_SECONDS
            while time.perf_counter() < end:
                if root is not None:
                    tick += 1
                    canvas.configure(bg="#%06x" % ((tick * 0x0F0F0F) & 0xFFFFFF)); root.update()
                f = cam.get_latest_frame()
                if f is not None:
                    n += 1; size = (f.shape[1], f.shape[0])
            cam.stop(); del cam
            if root is not None: root.destroy()
            if n == 0:
                print("  dxcam started but returned no frames (screen looked unchanged or GPU capture is blocked)")
            else:
                results.append(("dxcam (DXGI)", n / TEST_SECONDS, size))
        except Exception as exc:
            print(f"  dxcam not usable: {type(exc).__name__}: {exc}   (fix: pip install dxcam numpy)")
    try:
        import mss
        with (getattr(mss, "MSS", None) or mss.mss)() as sct:
            mon = sct.monitors[1]
            n, end = 0, time.perf_counter() + TEST_SECONDS
            while time.perf_counter() < end:
                sct.grab(mon); n += 1
            results.append(("mss", n / TEST_SECONDS, (mon["width"], mon["height"])))
    except Exception:
        pass
    if not results:
        return "none", None, None
    return max(results, key=lambda r: r[1])


def measure_jpeg(size: tuple[int, int], width: int, quality: int = 65) -> float | None:
    """How many frames per second can be resized + JPEG-encoded at this width."""
    try:
        import numpy as np
        from PIL import Image
        w, h = size
        img = Image.fromarray((np.random.rand(h // 4, w // 4, 3) * 255).astype("uint8")).resize((w, h))
        tw = min(width, w) if width else w
        th = round(h * tw / w)
        n, end = 0, time.perf_counter() + TEST_SECONDS
        while time.perf_counter() < end:
            buf = io.BytesIO()
            img.resize((tw, th), Image.BILINEAR).save(buf, "JPEG", quality=quality)
            n += 1
        return n / TEST_SECONDS
    except Exception:
        return None


def measure_h264(size: tuple[int, int]) -> dict[str, float | None]:
    """{backend: encode fps or None when it does not work on this PC}."""
    out: dict[str, float | None] = {}
    try:
        import av
        import fractions
    except Exception:
        return out
    names = {"nvenc": "h264_nvenc", "qsv": "h264_qsv", "amf": "h264_amf", "x264": "libx264"}
    w, h = (size[0] // 2) * 2, (size[1] // 2) * 2
    for key, codec in names.items():
        try:
            if codec not in av.codecs_available:
                out[key] = None; continue
            ctx = av.CodecContext.create(codec, "w")
            ctx.width, ctx.height, ctx.bit_rate = w, h, 4_000_000
            ctx.pix_fmt = "nv12" if key == "qsv" else "yuv420p"
            ctx.framerate = fractions.Fraction(60, 1); ctx.time_base = fractions.Fraction(1, 60)
            ctx.gop_size = 60; ctx.max_b_frames = 0
            ctx.options = {"preset": "ultrafast", "tune": "zerolatency"} if key == "x264" else {}
            ctx.open()
            import numpy as np
            rng = np.random.default_rng(1)
            noise = rng.integers(0, 256, (h * 3 // 2, w), dtype=np.uint8)   # busy picture, not an empty one
            frames = [av.VideoFrame.from_ndarray(np.roll(noise, i * 16, axis=1), format="yuv420p") for i in range(4)]
            n, end = 0, time.perf_counter() + TEST_SECONDS
            while time.perf_counter() < end:
                frame = frames[n % 4]; frame.pts = n
                list(ctx.encode(frame)); n += 1
            out[key] = n / TEST_SECONDS
        except Exception:
            out[key] = None
    return out


def clamp(v: float, cap: int = CODE_FPS_CAP) -> int:
    return max(1, min(cap, int(v)))


def set_env(path: Path, values: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for k, v in values.items():
        if re.search(rf"^{k}=.*$", text, re.M):
            text = re.sub(rf"^{k}=.*$", f"{k}={v}", text, flags=re.M)
        else:
            text += ("" if text.endswith("\n") or not text else "\n") + f"{k}={v}\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the recommended values into .env")
    args = ap.parse_args()

    print(f"PC       : {platform.system()} {platform.release()}, {cpu_info()}")
    hz = monitor_refresh_hz()
    print(f"Monitor  : {hz} Hz" if hz else "Monitor  : refresh rate unknown (not Windows?)")

    print("\nTesting screen capture ...")
    method, cap_fps, size = measure_capture()
    if cap_fps is None or size is None:
        print("  Capture does not work here. Run this script on the Windows PC you control, with a screen attached.")
        return 1
    print(f"  {method}: {cap_fps:.0f} fps at {size[0]}x{size[1]}")

    print("\nTesting JPEG speed (WebSocket mode) ...")
    jpeg = {}
    for w in WIDTHS:
        jpeg[w] = measure_jpeg(size, w)
        print(f"  width {w}: " + (f"{jpeg[w]:.0f} fps" if jpeg[w] else "n/a"))

    print("\nTesting H.264 encoders (WebRTC mode) ...")
    h264 = measure_h264(size)
    for name, fps in h264.items():
        print(f"  {name:6}: " + (f"{fps:.0f} fps" if fps else "not available"))
    working = {k: v for k, v in h264.items() if v}
    # Hardware encoders keep the CPU free for games/apps, so prefer one whenever it is fast enough (>= 45 fps).
    hw = [k for k in ("nvenc", "qsv", "amf") if working.get(k, 0) >= 45]
    best = hw[0] if hw else (max(working, key=working.get) if working else None)

    # Recommendations: the slowest stage decides, and keep ~20% headroom so the PC is not at 100%.
    limits_ws = [cap_fps] + [v for k, v in jpeg.items() if k == 1280 and v]
    limits_rtc = [cap_fps] + ([working[best]] if best else [])
    if hz: limits_ws.append(hz); limits_rtc.append(hz)
    rec_ws = clamp(min(limits_ws) * 0.8, WS_FPS_CAP)
    rec_rtc = clamp(min(limits_rtc) * 0.8)

    print("\n=== Recommendation ===")
    print(f"REMOTE_PC_FPS={rec_ws}          (WebSocket JPEG mode, 1280 wide, max 120)")
    print(f"REMOTE_PC_RTC_FPS={rec_rtc}      (WebRTC mode)")
    if best: print(f"REMOTE_PC_RTC_ENCODER={best}   (hardware encoder preferred; 'auto' picks the same)")
    if min(limits_rtc) * 0.8 > CODE_FPS_CAP:
        print(f"\nYour PC can do more than {CODE_FPS_CAP} fps. The app itself is capped at {CODE_FPS_CAP} "
              "(FPS_MAX in screen.py); the cap can be raised in code if you want 60.")

    if args.apply:
        env = ROOT / ".env"
        set_env(env, {"REMOTE_PC_FPS": str(rec_ws), "REMOTE_PC_RTC_FPS": str(rec_rtc)})
        print(f"\nWritten to {env}. Restart the server to use it.")
    else:
        print("\nRun again with --apply to save these values into .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
