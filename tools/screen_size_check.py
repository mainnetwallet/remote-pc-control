"""Find out why the stream shows the wrong picture size.

Run it ON THE PC you control (Windows), from the repo folder:

    python tools/screen_size_check.py

It prints the real size of the screen (what Windows says the monitor is set to), the size the capture libraries
see (mss and dxcam), the Windows display scaling and the DPI awareness of this process. Send the whole output
back if the numbers do not match: a smaller capture size than the real size means Windows is scaling the
picture for this program (DPI virtualization).
"""
from __future__ import annotations

import platform
import sys


def line(name: str, value) -> None:
    print(f"  {name:<38} {value}")


def real_mode() -> tuple[int, int, int] | None:
    """(width, height, refresh Hz) the primary monitor is really set to, read straight from the display driver."""
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
    if not ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):   # -1 = current settings
        return None
    return int(dm.dmPelsWidth), int(dm.dmPelsHeight), int(dm.dmDisplayFrequency)


def dpi_info() -> None:
    import ctypes
    user32 = ctypes.windll.user32
    try:
        awareness = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
        names = {0: "unaware (Windows scales the picture)", 1: "system aware", 2: "per-monitor aware"}
        line("DPI awareness of this process", names.get(awareness.value, awareness.value))
    except Exception as exc:
        line("DPI awareness of this process", f"unknown ({type(exc).__name__})")
    try:
        dc = user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)   # LOGPIXELSX
        user32.ReleaseDC(0, dc)
        line("Display scaling seen by this process", f"{round(dpi / 96 * 100)} %  ({dpi} dpi)")
    except Exception:
        pass
    line("GetSystemMetrics screen size", f"{user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)}")


def main() -> int:
    print(f"Python {platform.python_version()} on {platform.system()} {platform.release()}")
    if platform.system() != "Windows":
        print("Run this script on the Windows PC you want to control.")
        return 1

    print("\n1. Before the app's own DPI setting (what a plain Python program sees):")
    dpi_info()
    mode = real_mode()
    line("Real monitor setting (driver)", f"{mode[0]}x{mode[1]} @ {mode[2]} Hz" if mode else "unknown")

    print("\n2. After the app's DPI setting (backend/app/screen.py enable_dpi_awareness):")
    try:
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "backend"))
        from app import screen
        screen.enable_dpi_awareness()
    except Exception as exc:
        print(f"  could not import the app ({type(exc).__name__}: {exc}); continuing without it")
    dpi_info()

    print("\n3. What the capture libraries see:")
    mss_size = None
    try:
        import mss
        with mss.mss() as sct:
            for i, m in enumerate(sct.monitors):
                line(f"mss monitors[{i}]" + (" (all screens)" if i == 0 else " (primary)" if i == 1 else ""),
                     f"{m['width']}x{m['height']} at ({m['left']}, {m['top']})")
            m = sct.monitors[1]; mss_size = (m["width"], m["height"])
    except Exception as exc:
        line("mss", f"not usable: {type(exc).__name__}: {exc}")
    dx_size = None
    try:
        import dxcam
        cam = dxcam.create(output_color="BGRA", processor_backend="numpy")
        dx_size = (cam.width, cam.height)
        line("dxcam (DXGI) primary output", f"{cam.width}x{cam.height}")
        try: cam.release()
        except Exception: pass
    except Exception as exc:
        line("dxcam (DXGI)", f"not installed or not usable: {type(exc).__name__}")

    print("\n=== Result ===")
    if not mode or not mss_size:
        print("Could not read both sizes; send this whole output.")
        return 0
    real = (mode[0], mode[1])
    if mss_size == real:
        print(f"OK: the capture size ({mss_size[0]}x{mss_size[1]}) is the real monitor size.")
        if real[0] <= 1920:
            print("The screen itself is Full HD or smaller, so no preset can send more than this. To get a bigger\n"
                  "picture raise the resolution in Windows: Settings > System > Display > Display resolution.")
    else:
        print(f"MISMATCH: the monitor is {real[0]}x{real[1]} but mss captures {mss_size[0]}x{mss_size[1]}.\n"
              "Windows is scaling the picture for this program (DPI virtualization). Send this output back.")
    if dx_size and dx_size != mss_size:
        print(f"Also: dxcam sees {dx_size[0]}x{dx_size[1]} but mss sees {mss_size[0]}x{mss_size[1]}, so the app "
              "silently falls back to the slower standard capture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
