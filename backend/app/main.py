import logging, os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .config import validate_settings
from .security import require_auth
from . import monitor, control, pinlock, panel, tailnet
from .screen import screen_socket, input_socket
import threading
from .webrtc import rtc_socket, shutdown_all as rtc_shutdown, warm_up as rtc_warm_up
@asynccontextmanager
async def lifespan(app):
    validate_settings()
    if not monitor.is_elevated(): logging.getLogger("uvicorn.error").warning("Not running as Administrator: mouse/keyboard will NOT work in Task Manager, admin terminals or other elevated windows. Run scripts\\install-autostart.ps1 -Admin from an Administrator PowerShell.")
    threading.Thread(target=rtc_warm_up,name="rtc-warm-up",daemon=True).start()   # first WebRTC connection after boot must not be slow
    from .config import settings
    threading.Thread(target=tailnet.autostart,args=(settings.port,),name="tailnet",daemon=True).start()   # built-in Tailscale, if the user turned it on
    yield
    tailnet.stop()
    await rtc_shutdown()   # close WebRTC sessions: tracks, capture handles, peer connections
app=FastAPI(title="Remote PC Control",docs_url=None,redoc_url=None,lifespan=lifespan)
app.include_router(panel.router)
@app.exception_handler(pinlock.StateFileError)
def _lock_state_error(request,exc): return JSONResponse({"detail":"Lock state file is unreadable or unwritable; see lock_overlay.log"},status_code=503)
class PowerRequest(BaseModel): confirm: bool=False
class PinRequest(BaseModel): pin: str
@app.get("/api/health")
def health(): return {"ok":True,"service":"remote-pc-control","panel":True}
@app.get("/api/v1/status",dependencies=[Depends(require_auth)])
def status(): return monitor.snapshot()
@app.get("/api/v1/metrics",dependencies=[Depends(require_auth)])
def metrics(): return monitor.snapshot()
@app.post("/api/v1/control/lock",dependencies=[Depends(require_auth)])
def lock():
    # With a PIN set, the app's Lock button uses the PIN lock screen: it is a normal desktop window, so remote
    # control keeps working and Unlock from the app works. Windows' own lock leads to the sign-in screen, which no
    # ordinary program can click or stream. Set REMOTE_PC_LOCK_BUTTON=windows to always use the Windows lock.
    if os.getenv("REMOTE_PC_LOCK_BUTTON","pin").strip().lower()!="windows" and pinlock.status()["pin_set"]:
        pinlock.lock(); return {"ok":True,"action":"lock","mode":"pin"}
    control.lock_workstation(); return {"ok":True,"action":"lock","mode":"windows"}
@app.post("/api/v1/control/sleep",dependencies=[Depends(require_auth)])
def sleep(): control.sleep_pc(); return {"ok":True,"action":"sleep-requested"}
@app.post("/api/v1/control/{action}",dependencies=[Depends(require_auth)])
def power(action:str,request:PowerRequest):
    if action not in {"shutdown","restart"}: raise HTTPException(404,"Unknown power action")
    control.power_action(action,request.confirm); return {"ok":True,"action":action,"delay_seconds":5}
@app.get("/api/v1/lock/status",dependencies=[Depends(require_auth)])
def lock_status(): return pinlock.status()
@app.post("/api/v1/lock/pin",dependencies=[Depends(require_auth)])
def lock_set_pin(request:PinRequest):
    try: pinlock.set_pin(request.pin)
    except ValueError as e: raise HTTPException(400,str(e))
    return {"ok":True}
@app.post("/api/v1/lock/lock",dependencies=[Depends(require_auth)])
def lock_engage():
    try: pinlock.lock()
    except ValueError as e: raise HTTPException(400,str(e))
    return {"ok":True,"locked":True}
@app.post("/api/v1/lock/unlock",dependencies=[Depends(require_auth)])
def lock_release(): pinlock.unlock(); return {"ok":True,"locked":False}
@app.get("/api/v1/wol/status",dependencies=[Depends(require_auth)])
def wol_status(): return {"supported":False,"configured":False,"detail":"Requires an always-on LAN relay; this PC cannot wake itself."}
@app.post("/api/v1/wol/wake",dependencies=[Depends(require_auth)])
def wol_wake(): raise HTTPException(501,"Configure a separately authenticated always-on LAN relay first")
@app.websocket("/ws/screen")
async def ws_screen(ws:WebSocket): await screen_socket(ws)
@app.websocket("/ws/rtc")
async def ws_rtc(ws:WebSocket): await rtc_socket(ws)
@app.websocket("/ws/input")
async def ws_input(ws:WebSocket): await input_socket(ws)
from fastapi import Response
@app.get("/favicon.ico",include_in_schema=False)
def favicon(): return Response(status_code=204)
static_dir=Path(__file__).resolve().parent/"static"
if static_dir.exists():
    app.mount("/assets",StaticFiles(directory=static_dir/"assets"),name="assets")
    @app.get("/")
    def frontend():
        index=static_dir/"index.html"
        return FileResponse(index) if index.exists() else JSONResponse({"message":"Build frontend first"})
else:
    @app.get("/")
    def frontend_missing(): return JSONResponse({"message":"Build frontend first"},status_code=503)
