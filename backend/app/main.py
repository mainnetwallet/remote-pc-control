from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, WebSocket, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .config import settings, validate_settings
from .security import require_auth
from . import monitor, control, unlock
from fastapi.exceptions import RequestValidationError
from pydantic import Field
from .screen import screen_socket, input_socket
import threading
from .webrtc import rtc_socket, shutdown_all as rtc_shutdown, warm_up as rtc_warm_up
app=FastAPI(title="Remote PC Control",docs_url=None,redoc_url=None)
class PowerRequest(BaseModel): confirm: bool=False
@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    # FastAPI's default 422 body echoes the submitted value ("input"); that could leak a Windows PIN/password.
    return JSONResponse({"detail":[{"loc":list(e.get("loc",())),"msg":e.get("msg",""),"type":e.get("type","")} for e in exc.errors()]},status_code=422)
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
# ---- Secure Windows unlock (feature-flagged; see docs/UNLOCK.md). Credentials only travel in these POST bodies. ----
async def small_body(request: Request):
    if int(request.headers.get("content-length") or 0) > 4096: raise HTTPException(413,"Request too large")
class EnrollRequest(BaseModel): name:str=Field(max_length=40); public_key:str=Field(min_length=80,max_length=200)
class ChallengeRequest(BaseModel): device_id:str=Field(pattern=r"^[0-9a-f]{16}$")
class PasswordUnlockRequest(BaseModel): credential:str=Field(min_length=1,max_length=unlock.MAX_CREDENTIAL_CHARS,repr=False)
class BiometricUnlockRequest(BaseModel):
    device_id:str=Field(pattern=r"^[0-9a-f]{16}$"); challenge_id:str=Field(pattern=r"^[0-9a-f]{16}$")
    signature:str=Field(min_length=8,max_length=200); credential:str=Field(min_length=1,max_length=unlock.MAX_CREDENTIAL_CHARS,repr=False)
def _unlock_call(fn,*a,**kw):
    try: return fn(*a,**kw)
    except unlock.UnlockError as e:
        raise HTTPException(unlock.HTTP_FOR.get(e.code,400),{"ok":False,"result":e.code,"message":e.detail})
@app.get("/api/v1/unlock/status",dependencies=[Depends(require_auth)])
def unlock_status(): return unlock.service.status()
@app.get("/api/v1/unlock/devices",dependencies=[Depends(require_auth)])
def unlock_devices(): return {"devices":unlock.service.list_devices()}
@app.post("/api/v1/unlock/devices",dependencies=[Depends(require_auth),Depends(small_body)])
def unlock_enroll(r:EnrollRequest): return _unlock_call(unlock.service.enroll,r.name,r.public_key)
@app.delete("/api/v1/unlock/devices/{device_id}",dependencies=[Depends(require_auth)])
def unlock_revoke(device_id:str):
    if not unlock.service.revoke(device_id): raise HTTPException(404,"Unknown device")
    return {"ok":True}
@app.post("/api/v1/unlock/challenge",dependencies=[Depends(require_auth),Depends(small_body)])
def unlock_challenge(r:ChallengeRequest): return _unlock_call(unlock.service.new_challenge,r.device_id)
@app.post("/api/v1/unlock/password",dependencies=[Depends(require_auth),Depends(small_body)])
def unlock_password(r:PasswordUnlockRequest):
    _unlock_call(unlock.service.unlock,r.credential); return {"ok":True,"result":unlock.SUCCESS}
@app.post("/api/v1/unlock/biometric",dependencies=[Depends(require_auth),Depends(small_body)])
def unlock_biometric(r:BiometricUnlockRequest):
    _unlock_call(unlock.service.unlock,r.credential,device_id=r.device_id,challenge_id=r.challenge_id,signature=r.signature); return {"ok":True,"result":unlock.SUCCESS}
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
