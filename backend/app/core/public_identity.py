"""Apply the public identity boundary to dict and schema API responses alike."""

import json
from app.services.public_identity import public_references


class PublicIdentityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        start = None
        chunks = []

        async def wrapped(message):
            nonlocal start
            if message["type"] == "http.response.start":
                headers = dict(message["headers"])
                if b"application/json" in headers.get(b"content-type", b""):
                    start = message
                    return
            if start is not None and message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                body = json.dumps(
                    public_references(json.loads(b"".join(chunks))),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
                start["headers"] = [
                    (k, v) for k, v in start["headers"] if k != b"content-length"
                ] + [(b"content-length", str(len(body)).encode())]
                await send(start)
                await send(dict(message, body=body))
                start = None
                return
            await send(message)

        await self.app(scope, receive, wrapped)
