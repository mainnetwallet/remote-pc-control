import os, socket, sys, traceback


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
    state = firstrun.server_state(settings.port)
    if state == "old":   # an older version (e.g. the PowerShell/source one) still holds the port: replace it
        if not firstrun.stop_old_server(settings.port):
            firstrun.message(f"An older Remote PC Control still uses port {settings.port} and could not be stopped.\nRestart the PC, then open Remote PC Control again.")
            sys.exit(1)
        state = "none"
    if state == "other":
        firstrun.message(f"Port {settings.port} is used by another program, so Remote PC Control cannot start.\nClose that program (or restart the PC) and open Remote PC Control again.")
        sys.exit(1)
    if state == "current":   # the server already runs (autostart): just show the app window, then leave the server alone
        if not background: show_panel(settings.port, settings.token)
        sys.exit(0)
    if background or not (firstrun.first_run() or firstrun.frozen()):
        uvicorn.run(app, host=settings.host, port=settings.port, reload=False, ws_per_message_deflate=False)
        return
    # Opened by the user (Start menu / desktop icon): run the server in a thread and show the app window on the main
    # thread. Closing the window leaves the server running in the background, like the autostart one.
    import threading, time
    server = threading.Thread(target=uvicorn.run, args=(app,), daemon=False, name="server",
                              kwargs=dict(host=settings.host, port=settings.port, reload=False, ws_per_message_deflate=False))
    server.start()
    for _ in range(120):   # wait (up to 60 s) until the server answers
        if not server.is_alive(): break
        try: socket.create_connection(("127.0.0.1", int(settings.port)), timeout=1).close(); break
        except OSError: time.sleep(0.5)
    if server.is_alive(): show_panel(settings.port, settings.token, wait_for_server=False)
    server.join()


def show_panel(port, token, wait_for_server=True):
    """Open the control panel in its own app window; fall back to the browser if that is not possible."""
    from app import firstrun, window
    url = f"http://127.0.0.1:{int(port)}/panel#{token}"   # the token travels in the #hash: it never reaches the server
    if wait_for_server and not firstrun.wait_for_port(port): return firstrun.open_panel(port, token, wait_for_server=False)
    if window.open_window(url): return
    firstrun.open_panel(port, token, wait_for_server=False)
    import time; time.sleep(1.5)   # the browser thread is a daemon: give it time to start


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except BaseException: _report_crash(traceback.format_exc()); sys.exit(1)
