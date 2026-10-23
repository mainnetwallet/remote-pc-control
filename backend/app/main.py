from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .config import settings, validate_settings
from .security import require_auth
from . import monitor, control
from .screen import screen_socket, input_socket
import threading
from .webrtc import rtc_socket, shutdown_all as rtc_shutdown, warm_up as rtc_warm_up
app=FastAPI(title="Remote PC Control",docs_url=None,redoc_url=None)
class PowerRequest(BaseModel): confirm: bool=False
@app.on_event("startup")
def startup():
    validate_settings()
    threading.Thread(target=rtc_warm_up,name="rtc-warm-up",daemon=True).start()   # first WebRTC connection after boot must not be slow
@app.on_event("shutdown")
async def shutdown(): await rtc_shutdown()   # close WebRTC sessions: tracks, capture handles, peer connections
@app.get("/api/health")
def health(): return {"ok":True,"service":"remote-pc-control"}
@app.get("/api/v1/status",dependencies=[Depends(require_auth)])
def status(): return monitor.snapshot()
@app.get("/api/v1/metrics",dependencies=[Depends(require_auth)])
def metrics(): return monitor.snapshot()
@app.post("/api/v1/control/lock",dependencies=[Depends(require_auth)])
def lock(): control.lock_workstation(); return {"ok":True,"action":"lock"}
@app.post("/api/v1/control/sleep",dependencies=[Depends(require_auth)])
def sleep(): control.sleep_pc(); return {"ok":True,"action":"sleep-requested"}
@app.post("/api/v1/control/{action}",dependencies=[Depends(require_auth)])
def power(action:str,request:PowerRequest):
    if action not in {"shutdown","restart"}: raise HTTPException(404,"Unknown power action")
    control.power_action(action,request.confirm); return {"ok":True,"action":action,"delay_seconds":5}
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
