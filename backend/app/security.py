import hmac
from fastapi import Header, HTTPException
from .config import settings

def verify_token(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    if not hmac.compare_digest(authorization[7:].strip().encode(), settings.token.encode()):
        raise HTTPException(401, "Invalid token")

async def require_auth(authorization: str | None = Header(default=None)):
    verify_token(authorization)
