import os, sys, traceback


def _report_crash(text):
    """The packaged exe has no console: keep the error in crash.log and show it, so "nothing happens" never again."""
    try:
        d = os.path.join(os.getenv("LOCALAPPDATA") or os.path.dirname(sys.executable), "RemotePCControl")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "crash.log"), "a", encoding="utf-8") as f: f.write(text + "\n")
    except Exception: d = ""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "Remote PC Control could not start.\n\n" + text[-1200:] + "\n\nSaved in: " + os.path.join(d, "crash.log"),
                                         "Remote PC Control", 0x10)
    except Exception: print(text, file=sys.stderr)


def main():
    if "--lock-overlay" in sys.argv:   # packaged exe: the PIN lock screen runs as a second copy of this program
        import lock_overlay
        sys.exit(lock_overlay.main())
    from app import firstrun
    firstrun.prepare()   # packaged exe: create .env on first start; must run before app.config is imported
    import uvicorn
    from app.config import settings
    from app.main import app   # imported (not a string) so PyInstaller bundles the whole app
    background = "--background" in sys.argv   # started by the Windows autostart task: do not open the browser
    if firstrun.already_running(settings.port):
        if not background: firstrun.open_panel(settings.port, settings.token, wait_for_server=False)
        import time; time.sleep(1.5)   # the browser thread is a daemon: give it time to start
        sys.exit(0)
    if firstrun.first_run() or (not background and firstrun.frozen()): firstrun.open_panel(settings.port, settings.token)
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False, ws_per_message_deflate=False)


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except BaseException: _report_crash(traceback.format_exc()); sys.exit(1)
