import hmac, math, time, threading
from collections import defaultdict, deque
from fastapi import Header, HTTPException, Request
from .config import settings

# Brute-force protection: after MAX_FAILS wrong tokens within WINDOW_SECONDS from one client,
# that client is locked out (even with the right token) until the window passes.
MAX_FAILS = 8
WINDOW_SECONDS = 300
_fails: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()

# Extra guard for short passwords: attackers who rotate IP addresses still share one global budget.
# After GLOBAL_MAX_FAILS wrong tokens (from anyone) within GLOBAL_WINDOW_SECONDS every login is refused
# until the window passes, even with the right token.
GLOBAL_MAX_FAILS = 40
GLOBAL_WINDOW_SECONDS = 600
_global_fails: deque = deque()


# Repeated-failure limiter (any request, with or without a token): the same request failing again and again from one
# client is answered with 429 + Retry-After until the window passes. Covers missing/garbled Authorization headers,
# wrong paths, rejected bodies and scanners, none of which the wrong-token lockout above counts.
ROUTE_MAX_FAILS = 10          # same client + method + path failing this often within ROUTE_WINDOW_SECONDS ...
ROUTE_WINDOW_SECONDS = 60     # ... is refused for the rest of the window
CLIENT_MAX_FAILS = 60         # any failed requests from one client (e.g. a scanner trying random paths) ...
CLIENT_WINDOW_SECONDS = 60    # ... within this window block that client for the rest of it
MAX_TRACKED = 5000            # memory bound: expired entries are dropped when the tables grow past this
_route_fails: dict[tuple, deque] = {}
_client_fails: dict[str, deque] = {}


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def client_key(headers, client) -> str:
    # Behind a Cloudflare tunnel every request comes from localhost; Cloudflare puts the real client IP in
    # cf-connecting-ip. That header is only believed when the connection itself is local (the tunnel): the server also
    # listens on 0.0.0.0, and anyone who reaches it directly could otherwise invent a new "IP" for every guess and
    # dodge the per-client lockout.
    peer = client.host if client else "unknown"
    if peer in LOOPBACK:
        forwarded = (headers.get("cf-connecting-ip") or "").strip()
        if forwarded: return forwarded[:64]
    return peer


def is_blocked(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        dq = _fails[key]
        while dq and now - dq[0] > WINDOW_SECONDS: dq.popleft()
        while _global_fails and now - _global_fails[0] > GLOBAL_WINDOW_SECONDS: _global_fails.popleft()
        return len(dq) >= MAX_FAILS or len(_global_fails) >= GLOBAL_MAX_FAILS


def record_fail(key: str) -> None:
    with _lock:
        now = time.monotonic()
        _fails[key].append(now); _global_fails.append(now)


def record_success(key: str) -> None:
    with _lock: _fails.pop(key, None)


def reset_all() -> None:
    with _lock: _fails.clear(); _global_fails.clear(); _route_fails.clear(); _client_fails.clear()


def _trim(dq: deque, now: float, window: float) -> None:
    while dq and now - dq[0] > window: dq.popleft()


def _prune(now: float) -> None:
    for table, window in ((_route_fails, ROUTE_WINDOW_SECONDS), (_client_fails, CLIENT_WINDOW_SECONDS)):
        if len(table) <= MAX_TRACKED: continue
        for k in [k for k, dq in table.items() if not dq or now - dq[-1] > window]: table.pop(k, None)
        if len(table) > MAX_TRACKED:   # still full of fresh entries (a flood): forget the oldest half
            for k in sorted(table, key=lambda k: table[k][-1] if table[k] else 0)[:len(table) // 2]: table.pop(k, None)


def request_blocked(key: str, method: str, path: str) -> int:
    """Seconds to wait before this client may repeat this request, or 0 when it is allowed."""
    now = time.monotonic(); wait = 0.0
    with _lock:
        route = _route_fails.get((key, method, path))
        if route is not None:
            _trim(route, now, ROUTE_WINDOW_SECONDS)
            if len(route) >= ROUTE_MAX_FAILS: wait = max(wait, ROUTE_WINDOW_SECONDS - (now - route[0]))
        client = _client_fails.get(key)
        if client is not None:
            _trim(client, now, CLIENT_WINDOW_SECONDS)
            if len(client) >= CLIENT_MAX_FAILS: wait = max(wait, CLIENT_WINDOW_SECONDS - (now - client[0]))
    return max(1, math.ceil(wait)) if wait > 0 else 0


def record_request_result(key: str, method: str, path: str, status: int) -> None:
    """Call after every HTTP response. 4xx answers count as failures (429 and 5xx do not); a success clears that route."""
    now = time.monotonic(); route_key = (key, method, path)
    with _lock:
        if status < 400: _route_fails.pop(route_key, None); return
        if status == 429 or status >= 500: return
        _route_fails.setdefault(route_key, deque()).append(now)
        _client_fails.setdefault(key, deque()).append(now)
        _prune(now)


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
