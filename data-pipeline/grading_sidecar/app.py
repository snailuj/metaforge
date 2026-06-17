"""FastAPI app factory.

Host-header allowlist defends against DNS-rebinding on 127.0.0.1:53775
(see spec → Auth → Host-header allowlist + CORS). CORS is same-origin only.

Middleware ordering note: Starlette's add_middleware() prepends to the stack,
so the LAST registered middleware ends up outermost. We register CORS first
and HostAllowlistMiddleware second so the host check is the outer gate —
unknown Host returns 421 before CORS ever sees the request.
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from .autocommit import autocommit_loop
from . import paths as paths_mod
from .routes import healthz, judgements, chains, topics, stats, calibration, design_notes, walk, signal_report, glosses, regrade, sense_check

def autocommit_target() -> tuple[str, str]:
    """(git_root, subdir) the autocommit writes to. In deploy these resolve to the
    SEPARATE data worktree via GRADING_DATA_GIT_ROOT; in dev they default to the
    main repo, preserving today's behaviour."""
    return paths_mod.GRADING_DATA_GIT_ROOT, "data-pipeline/grading/"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the 15-min auto-commit background task; cancel cleanly on shutdown."""
    git_root, subdir = autocommit_target()
    task = asyncio.create_task(
        autocommit_loop(git_root, subdir)
    )
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


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

    # BaseHTTPMiddleware buffers request body for streaming responses; this
    # sidecar is JSON-only so the trade-off is acceptable in exchange for
    # explicit add_middleware ordering control.
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        if host not in ALLOWED_HOSTS:
            return JSONResponse(
                {"error": "Misdirected request"}, status_code=421
            )
        return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(title="Metaforge Grading Sidecar", version="0.1.0", lifespan=lifespan)

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
    app.include_router(judgements.router)
    app.include_router(chains.router)
    app.include_router(walk.router)
    app.include_router(topics.router)
    app.include_router(stats.router)
    app.include_router(calibration.router)
    app.include_router(design_notes.router)
    app.include_router(signal_report.router)
    app.include_router(glosses.router)
    app.include_router(regrade.router)
    app.include_router(sense_check.router)
    return app
