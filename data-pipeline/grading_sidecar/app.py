"""FastAPI app factory.

Host-header allowlist defends against DNS-rebinding on 127.0.0.1:53775
(see spec → Auth → Host-header allowlist + CORS). CORS is same-origin only.

Middleware ordering note: Starlette's add_middleware() prepends to the stack,
so the LAST registered middleware ends up outermost. We register CORS first
and HostAllowlistMiddleware second so the host check is the outer gate —
unknown Host returns 421 before CORS ever sees the request.
"""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from .routes import healthz

ALLOWED_HOSTS = {
    "metaforge-next.julianit.me",
    "localhost:53775",
    "localhost:5173",
    "127.0.0.1:53775",
    "testserver",  # FastAPI TestClient default
}


class HostAllowlistMiddleware(BaseHTTPMiddleware):
    """Outer gate: reject requests with an unrecognised Host header (421).

    Must be registered after CORSMiddleware so it ends up outermost in the
    Starlette middleware stack (add_middleware prepends, so last-registered
    is first-executed).
    """

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        if host not in ALLOWED_HOSTS:
            return JSONResponse(
                {"error": "Misdirected request"}, status_code=421
            )
        return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(title="Metaforge Grading Sidecar", version="0.1.0")

    # Register CORS first — it will be inner (host check must pass first).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_methods=["GET", "POST"],
        allow_headers=["X-Grading-Secret"],
    )
    # Register host allowlist second — it becomes outermost in the stack.
    app.add_middleware(HostAllowlistMiddleware)

    app.include_router(healthz.router)
    return app
