from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

def test_health_public():
    with TestClient(app) as c:
        r=c.get("/api/health"); assert r.status_code==200 and r.json()["ok"]

def test_status_requires_token():
    with TestClient(app) as c: assert c.get("/api/v1/status").status_code==401

def test_status_rejects_wrong_token():
    with TestClient(app) as c: assert c.get("/api/v1/status",headers={"Authorization":"Bearer bad"}).status_code==401

def test_power_requires_confirmation(monkeypatch):
    monkeypatch.setattr(settings,"token","z"*40)
    with TestClient(app) as c:
        r=c.post("/api/v1/control/shutdown",headers={"Authorization":"Bearer "+"z"*40},json={"confirm":False}); assert r.status_code==400
