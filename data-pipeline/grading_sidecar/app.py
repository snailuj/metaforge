"""FastAPI app factory.

Host-header allowlist defends against DNS-rebinding on 127.0.0.1:53775
(see spec → Auth → Host-header allowlist + CORS). CORS is same-origin only.

Middleware ordering note: Starlette's add_middleware() prepends to the stack,
so the LAST registered middleware ends up outermost. Registration order is CORS,
CrossSiteWriteGuard, HostAllowlistMiddleware: the host check is the outer gate
(unknown Host returns 421 first), then the write guard, then CORS and routing.
"""
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send
from .autocommit import autocommit_loop
from . import paths as paths_mod
from .routes import healthz, judgements, chains, topics, stats, calibration, design_notes, walk, signal_report, glosses, regrade, sense_check, guided_walk, senses

log = logging.getLogger(__name__)


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


ALLOWED_ORIGINS = {
    "https://metaforge-next.julianit.me",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}


STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CrossSiteWriteGuard:
    """Refuse state-changing requests that did not come from the site's own page.

    Caddy adds X-Grading-Secret to every request that passed basic auth, and the
    browser attaches basic-auth credentials to cross-site requests too, so the
    secret cannot tell our page from another site's. FastAPI also parses a body
    with a missing or text/plain Content-Type as JSON, which lets a `no-cors`
    cross-site POST reach a handler. So, before routing or body parsing:
      * a present Origin must be allowlisted (403);
      * a present Sec-Fetch-Site must be same-origin or none (403);
      * Content-Type must be application/json (415).
    Requests with no Origin and no Sec-Fetch-Site (curl, tests) pass on the
    content-type rule alone. Pure ASGI so no body is read or buffered here.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in STATE_CHANGING_METHODS:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        fetch_site = headers.get("sec-fetch-site")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            await self._refuse(scope, receive, send, 403, "Origin", origin)
            return
        if fetch_site is not None and fetch_site not in ("same-origin", "none"):
            await self._refuse(scope, receive, send, 403, "Sec-Fetch-Site", fetch_site)
            return
        content_type = headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            await self._refuse(scope, receive, send, 415, "Content-Type", content_type)
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _refuse(scope, receive, send, status: int, header: str, value: str) -> None:
        log.warning("refused %s %s: %s=%r", scope["method"], scope["path"], header, value)
        detail = ("Unsupported media type" if status == 415
                  else "Cross-site request refused")
        await JSONResponse({"error": detail}, status_code=status)(scope, receive, send)


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
    # Cross-site write guard: inner to the host check, outer to CORS and routing.
    app.add_middleware(CrossSiteWriteGuard)
    # Register host allowlist last — it becomes outermost in the stack.
    app.add_middleware(HostAllowlistMiddleware)

    app.include_router(healthz.router)
    app.include_router(judgements.router)
    app.include_router(chains.router)
    app.include_router(walk.router)
    app.include_router(guided_walk.router)
    app.include_router(topics.router)
    app.include_router(stats.router)
    app.include_router(calibration.router)
    app.include_router(design_notes.router)
    app.include_router(signal_report.router)
    app.include_router(glosses.router)
    app.include_router(regrade.router)
    app.include_router(sense_check.router)
    app.include_router(senses.router)
    return app
