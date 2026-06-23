"""Daemon HTTP server — the lazy ASGI layer (Phase 1, read-only endpoints).

This module is the ONLY place that touches starlette/uvicorn, and it does
so lazily: importing `research_os.daemon.server` must not import the web
stack. The deps live in the optional `[daemon]` extra; if they're missing
we raise a clear, actionable error telling the user to install it.

Phase 1 endpoints are READ ONLY — no mutation, no auth beyond the
127.0.0.1 bind:
  GET /healthz            liveness + version
  GET /v1/state           multi-root state snapshot (all registered roots)
  GET /v1/state/{...}     not yet — single-root lookup arrives with auth
  GET /v1/jobs            background task queue snapshot
  GET /v1/jobs/{job_id}   one job

The transport sits behind this thin module by design (docs/v4/ROADMAP.md
§6) so a judge phase can swap starlette for something else without
touching the Daemon or the registry/queue.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime web import
    from .core import Daemon

logger = logging.getLogger("research-os.daemon.server")

_INSTALL_HINT = (
    "The Research OS daemon HTTP server needs the optional web stack. "
    "Install it with:  pip install 'research-os[daemon]'"
)


def _require_web_stack():
    """Import starlette/uvicorn lazily; raise a clear error if absent."""
    try:
        import starlette  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised via missing dep
        raise RuntimeError(_INSTALL_HINT) from exc


def build_app(daemon: "Daemon"):
    """Build the Starlette ASGI app bound to a running ``daemon``.

    Imported lazily inside the function so module import stays web-free.
    """
    _require_web_stack()
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from research_os import __version__

    async def healthz(request):
        return JSONResponse(
            {
                "status": "ok",
                "service": "research-os-daemon",
                "version": __version__,
                "serving": daemon.serving,
                "roots": daemon.registry.roots(),
            }
        )

    async def get_state(request):
        # Multi-root snapshot. A ?root= filter returns just that workspace.
        root = request.query_params.get("root")
        if root:
            ws = daemon.registry.get(root) or daemon.registry.register(root)
            return JSONResponse({"root": ws.state()})
        return JSONResponse(daemon.registry.snapshot())

    async def get_jobs(request):
        root = request.query_params.get("root")
        limit_raw = request.query_params.get("limit")
        limit = None
        if limit_raw is not None:
            try:
                limit = max(0, int(limit_raw))
            except ValueError:
                return JSONResponse({"error": "limit must be an integer"}, status_code=400)
        return JSONResponse(daemon.tasks.snapshot(root=root, limit=limit))

    async def get_job(request):
        job = daemon.tasks.get(request.path_params["job_id"])
        if job is None:
            return JSONResponse({"error": "job not found"}, status_code=404)
        return JSONResponse(job.to_dict())

    routes = [
        Route("/healthz", healthz, methods=["GET"]),
        Route("/v1/state", get_state, methods=["GET"]),
        Route("/v1/jobs", get_jobs, methods=["GET"]),
        Route("/v1/jobs/{job_id}", get_job, methods=["GET"]),
    ]
    return Starlette(routes=routes)


def serve(daemon: "Daemon") -> None:
    """Run the daemon's HTTP server in the foreground (blocking).

    Binds to the configured host/port (localhost by default). Blocks until
    interrupted. Used by `research-os daemon start`.
    """
    _require_web_stack()
    import uvicorn

    app = build_app(daemon)
    cfg = daemon.config
    logger.info("Research OS daemon serving on %s", cfg.base_url)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning")
