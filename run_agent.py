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
    from app.config import settings
    background = "--background" in sys.argv   # started by the Windows autostart task or by the app window: no window
    state = firstrun.server_state(settings.port)
    if state == "old":   # an older version (e.g. the PowerShell/source one) still holds the port: replace it
        if not firstrun.stop_old_server(settings.port):
            firstrun.message(f"An older Remote PC Control still uses port {settings.port} and could not be stopped.\nRestart the PC, then open Remote PC Control again.")
            sys.exit(1)
        state = "none"
    if state == "other":
        firstrun.message(f"Port {settings.port} is used by another program, so Remote PC Control cannot start.\nClose that program (or restart the PC) and open Remote PC Control again.")
        sys.exit(1)
    if state == "current":   # the server already runs: just show the app window, then leave the server alone
        if not background: show_panel(settings.port, settings.token)
        sys.exit(0)
    if not background and firstrun.frozen():
        # Opened by the user and the server is off: start it as its own background program, then show the app window.
        # The window can turn the server off and on; closing the window leaves the server as it is.
        from app import gui
        try: gui.start_server()
        except Exception as e: print("Could not start the server:", e)
        show_panel(settings.port, settings.token, starting=True)
        return
    import uvicorn
    from app.main import app   # imported (not a string) so PyInstaller bundles the whole app
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False, ws_per_message_deflate=False)


def show_panel(port, token, starting=False):
    """Show the app window (a real desktop UI)."""
    from app import firstrun, gui
    if gui.run(port, token, starting=starting): return
    firstrun.message("The Remote PC Control window could not be opened.\nThe server keeps running in the background; the phone app still works.\nDetails are in agent.log.")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except BaseException: _report_crash(traceback.format_exc()); sys.exit(1)
