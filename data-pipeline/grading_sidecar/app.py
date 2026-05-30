"""FastAPI app factory.

Host-header allowlist defends against DNS-rebinding on 127.0.0.1:53775
(see spec → Auth → Host-header allowlist + CORS). CORS is same-origin only.
"""
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .routes import healthz

ALLOWED_HOSTS = {
    "metaforge-next.julianit.me",
    "localhost:53775",
    "localhost:5173",
    "127.0.0.1:53775",
    "testserver",  # FastAPI TestClient default
}

def create_app() -> FastAPI:
    app = FastAPI(title="Metaforge Grading Sidecar", version="0.1.0")

    @app.middleware("http")
    async def host_allowlist(request: Request, call_next):
        host = request.headers.get("host", "").lower()
        if host not in ALLOWED_HOSTS:
            return JSONResponse(
                {"error": "Misdirected request"}, status_code=421
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_methods=["GET", "POST"],
        allow_headers=["X-Grading-Secret"],
    )

    app.include_router(healthz.router)
    return app
