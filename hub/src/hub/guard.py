"""ASGI middleware: optional bearer-token auth and request-size limit for /api/ routes.

If no token is configured (HUB_API_TOKEN empty) the endpoint is open and only the size
limit applies.

Runs before the body is parsed, so unauthenticated or oversized requests are
rejected cheaply. /health is left open.
"""

import hmac
import json

PROTECTED_PREFIX = "/api/"


class Guard:
    def __init__(self, app, token: str, max_body_bytes: int) -> None:
        self.app = app
        self.token = token.encode() if token else None
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(PROTECTED_PREFIX):
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])
        if self.token is not None:
            auth = headers.get(b"authorization", b"")
            scheme, _, supplied = auth.partition(b" ")
            if scheme.lower() != b"bearer" or not hmac.compare_digest(supplied.strip(), self.token):
                return await self._reject(send, 401, "invalid or missing token", [(b"www-authenticate", b"Bearer")])

        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body_bytes:
            return await self._reject(send, 413, "request body too large")

        received = 0
        too_large = False

        async def limited_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    too_large = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        response_started = False

        async def tracking_send(message):
            nonlocal response_started
            if too_large and not response_started:
                response_started = True
                return await self._reject(send, 413, "request body too large")
            if too_large:
                return
            response_started = True
            await send(message)

        await self.app(scope, limited_receive, tracking_send)

    @staticmethod
    async def _reject(send, status: int, detail: str, extra_headers=()):
        body = json.dumps({"detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()), *extra_headers],
        })
        await send({"type": "http.response.body", "body": body})
