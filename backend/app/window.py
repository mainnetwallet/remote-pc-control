"""Native app window for the control panel (packaged exe on Windows).

Instead of opening the panel in the browser, the program shows its own window (Edge WebView2 through pywebview), so
Remote PC Control looks and behaves like a normal desktop app. If the window cannot be created (WebView2 missing,
pywebview not installed, ...) the caller falls back to the browser."""
import sys
from .paths import data_dir

TITLE = "Remote PC Control"


def available() -> bool:
    if sys.platform != "win32": return False
    try:
        import webview  # noqa: F401
        return True
    except Exception:
        return False


def open_window(url: str, title: str = TITLE) -> bool:
    """Show the panel in an app window and BLOCK until the window is closed (must run on the main thread).
    Returns False when no native window could be shown, so the caller can open the browser instead."""
    if not available(): return False
    try:
        import webview
        storage = data_dir() / "webview"
        storage.mkdir(parents=True, exist_ok=True)
        webview.create_window(title, url, width=1280, height=820, min_size=(900, 600))
        # gui="edgechromium": never fall back to the old Internet Explorer engine, the panel would not render there.
        webview.start(gui="edgechromium", storage_path=str(storage), private_mode=False)
        return True
    except Exception as e:
        print("Could not open the app window:", e)
        return False
