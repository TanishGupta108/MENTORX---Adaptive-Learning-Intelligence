"""Security headers on every API response (NFR-SEC-01).

The API only serves JSON, so the Content-Security-Policy forbids everything; the
interactive docs (development only) get a policy that allows their CDN assets.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
DOCS_CSP = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data: "
    "https://fastapi.tiangolo.com; frame-ancestors 'none'"
)
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def install(app: FastAPI, production: bool) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        is_docs = request.url.path.startswith(DOCS_PATHS)
        h.setdefault("Content-Security-Policy", DOCS_CSP if is_docs else API_CSP)
        if request.url.path.startswith("/api/"):
            # Personal data: never store in shared caches or the browser's disk cache.
            h.setdefault("Cache-Control", "no-store")
        if production:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response
