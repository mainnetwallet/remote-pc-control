import sys
if "--lock-overlay" in sys.argv:   # packaged exe: the PIN lock screen runs as a second copy of this program
    import lock_overlay
    sys.exit(lock_overlay.main())
from app import firstrun
firstrun.prepare()   # packaged exe: create .env on first start; must run before app.config is imported
import uvicorn
from app.config import settings
from app.main import app   # imported (not a string) so PyInstaller bundles the whole app
if __name__ == "__main__":
    background = "--background" in sys.argv   # started by the Windows autostart task: do not open the browser
    if firstrun.already_running(settings.port):
        if not background: firstrun.open_panel(settings.port, settings.token, wait_for_server=False)
        import time; time.sleep(1.5)   # the browser thread is a daemon: give it time to start
        sys.exit(0)
    if firstrun.first_run() or (not background and firstrun.frozen()): firstrun.open_panel(settings.port, settings.token)
    uvicorn.run(app,host=settings.host,port=settings.port,reload=False,ws_per_message_deflate=False)
