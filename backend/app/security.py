import hmac, time, threading
from collections import defaultdict, deque
from fastapi import Header, HTTPException, Request
from .config import settings

# Brute-force protection: after MAX_FAILS wrong tokens within WINDOW_SECONDS from one client,
# that client is locked out (even with the right token) until the window passes.
MAX_FAILS = 8
WINDOW_SECONDS = 300
_fails: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def client_key(headers, client) -> str:
    # Behind a Cloudflare tunnel every request comes from localhost; Cloudflare puts the real client IP here.
    return headers.get("cf-connecting-ip") or (client.host if client else "unknown")


def is_blocked(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        dq = _fails[key]
        while dq and now - dq[0] > WINDOW_SECONDS: dq.popleft()
        return len(dq) >= MAX_FAILS


def record_fail(key: str) -> None:
    with _lock: _fails[key].append(time.monotonic())


def record_success(key: str) -> None:
    with _lock: _fails.pop(key, None)


def reset_all() -> None:
    with _lock: _fails.clear()


def token_ok(candidate: str) -> bool:
    return hmac.compare_digest(candidate.encode(), settings.token.encode())


def verify_token(authorization: str | None, key: str = "unknown"):
    if is_blocked(key): raise HTTPException(429, "Too many failed attempts; try again later")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    if not token_ok(authorization[7:].strip()):
        record_fail(key); raise HTTPException(401, "Invalid token")
    record_success(key)


async def require_auth(request: Request, authorization: str | None = Header(default=None)):
    verify_token(authorization, client_key(request.headers, request.client))
