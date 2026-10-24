"""API-key authentication and per-key rate limiting. Keys are compared by SHA-256 digest in constant time."""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, WebSocket

import config

_DIGESTS: dict[bytes, str] = {}


def reload_keys():
    global _DIGESTS
    _DIGESTS = {hashlib.sha256(k.encode()).digest(): op for k, op in config.API_KEYS.items()}


reload_keys()


def operator_for(token: str | None) -> str | None:
    if not token:
        return None
    d = hashlib.sha256(token.encode()).digest()
    found = None
    for known, op in _DIGESTS.items():          # no early exit: timing does not reveal which key matched
        if hmac.compare_digest(known, d):
            found = op
    return found


def bearer(header: str | None) -> str | None:
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, who: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[who]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


limiter = RateLimiter(config.RATE_PER_MIN)


def _open() -> bool:
    return not config.PRODUCTION and not config.API_KEYS


def require_operator(request: Request) -> str:
    """HTTP dependency. Demo mode with no keys configured is open and reports operator 'demo'."""
    if _open():
        return "demo"
    op = operator_for(bearer(request.headers.get("authorization")))
    if op is None:
        raise HTTPException(status_code=401, detail="missing or invalid API key", headers={"WWW-Authenticate": "Bearer"})
    if not limiter.allow(op):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    return op


def _ws_token(ws: WebSocket) -> str | None:
    tok = bearer(ws.headers.get("authorization"))
    if tok is None:
        for sp in (ws.headers.get("sec-websocket-protocol") or "").split(","):
            sp = sp.strip()
            if sp.startswith("bearer."):
                tok = sp[len("bearer."):]
    return tok


def ws_operator(ws: WebSocket) -> str | None:
    """Browsers cannot set headers on a WebSocket, so the key may travel as the subprotocol 'bearer.<key>'
    (never in the query string: URLs end up in proxy and access logs). Gateways may use the Authorization header."""
    if _open():
        return "demo"
    return operator_for(_ws_token(ws))


def ws_subprotocol(ws: WebSocket) -> str | None:
    for sp in (ws.headers.get("sec-websocket-protocol") or "").split(","):
        sp = sp.strip()
        if sp.startswith("bearer."):
            return sp
    return None
