import json
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings

# /api/health has to stay reachable without a token: it's used for
# unauthenticated container healthchecks (see docker-compose.yml).
_EXEMPT_PATHS = {"/api/health"}


class BearerTokenAuthMiddleware:
    """Pure ASGI middleware (not BaseHTTPMiddleware) so it can also guard
    WebSocket upgrades, not just regular HTTP requests. No-op unless
    AUTH_ENABLED=true — see app/core/config.py.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        settings = get_settings()
        if not settings.auth_enabled or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/api") or path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        token = self._extract_token(scope)
        if token != settings.api_secret_key:
            await self._reject(scope, receive, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _extract_token(scope: Scope) -> str | None:
        headers = dict(scope.get("headers") or [])
        auth_header = headers.get(b"authorization", b"").decode()
        if auth_header.startswith("Bearer "):
            return auth_header.removeprefix("Bearer ")

        # Browsers can't set custom headers on a WebSocket handshake, so
        # WS connections authenticate via a query param instead.
        query_string = scope.get("query_string", b"").decode()
        token_values = parse_qs(query_string).get("token")
        return token_values[0] if token_values else None

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            # Per the ASGI spec, the app must receive the initial
            # "websocket.connect" event before responding, even to reject.
            await receive()
            await send({"type": "websocket.close", "code": 4401})
            return

        body = json.dumps({"detail": "invalid or missing bearer token"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})
