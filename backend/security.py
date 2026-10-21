"""
Runtime safety switches shared by the whole backend.

`is_production()` is true on Railway (or with ENV=production). Development shortcuts such as
LOCAL_DEV only ever work outside production, so a stray environment variable can't open
another workspace's data on the live server.
"""
import os
import re


def is_production() -> bool:
    if (os.getenv("ENV") or os.getenv("APP_ENV") or "").lower() == "production":
        return True
    return bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))


def local_dev() -> bool:
    """The developer's local-only shortcuts (SQLite, skipped checks). Never on in production."""
    return os.getenv("LOCAL_DEV", "false").lower() == "true" and not is_production()


def mask_url(url: str) -> str:
    """postgresql://user:secret@host/db -> postgresql://user:***@host/db (safe to log)."""
    return re.sub(r"(://[^:/@]+:)[^@]*@", r"\1***@", url or "")


# ─── HTTP hardening (ASGI middleware) ─────────────────────────────
UPLOAD_PATH = re.compile(r"^/api/(bots/[^/]+/(logo|background|knowledge/upload)|voice/numbers/[^/]+/documents)$")
LARGE_PATH = re.compile(r"^/api/(bots/|voice/campaigns|knowledge/)")  # knowledge text, flows, calling lists
SITE_UPLOAD_PATH = re.compile(r"^/api/sites/[^/]+/deploys$")  # a website's files
MAX_BODY = 2 * 1024 * 1024          # everything else (JSON and forms)
MAX_LARGE_BODY = 10 * 1024 * 1024
MAX_UPLOAD_BODY = 25 * 1024 * 1024  # file uploads (each route enforces its own, lower, limit too)
MAX_SITE_BODY = 102 * 1024 * 1024   # the largest plan's deployment (plans.PAID) plus form overhead


class SecurityMiddleware:
    """
    - Refuses request bodies over the limit (by Content-Length, and while streaming when there is none),
      so one request can't exhaust the server's memory.
    - Adds browser security headers. Uploaded files under /static are served sandboxed and never
      sniffed as HTML, so a file can't run script on our domain.
    """

    def __init__(self, app):
        self.app = app
        self.production = is_production()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        limit = (MAX_SITE_BODY if SITE_UPLOAD_PATH.match(path) else MAX_UPLOAD_BODY if UPLOAD_PATH.match(path)
                 else MAX_LARGE_BODY if LARGE_PATH.match(path) else MAX_BODY)
        headers = dict(scope.get("headers") or [])
        try:
            declared = int(headers.get(b"content-length", b"0") or 0)
        except ValueError:
            declared = 0
        if declared > limit:
            return await _too_large(send)

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge()
            return message

        static = path.startswith("/static/")
        docs = path in ("/docs", "/redoc") or path.startswith("/docs/")  # development only; off in production
        started = False

        async def send_with_headers(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ]
                if static:
                    extra += [(b"content-security-policy", b"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"),
                              (b"cross-origin-resource-policy", b"cross-origin")]
                elif not docs:
                    extra += [(b"content-security-policy", b"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
                              (b"x-frame-options", b"DENY")]
                if self.production:
                    extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                present = {k.lower() for k, _ in message.get("headers", [])}
                message = {**message, "headers": list(message.get("headers", [])) + [h for h in extra if h[0] not in present]}
            await send(message)

        try:
            await self.app(scope, limited_receive, send_with_headers)
        except _BodyTooLarge:
            if not started:
                await _too_large(send)


class _BodyTooLarge(Exception):
    pass


async def _too_large(send):
    body = b'{"detail":"That request is too large"}'
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
