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
  GET /v1/domain          detected research field + field-aware defaults
  GET /v1/lineage         content-addressed run dependency graph (?run_id=)
  GET /v1/staleness       freshness verdict over the lineage DAG
  GET /v1/rebuild/plan    what a rebuild WOULD re-run, in order (dry-run)
  GET /v1/jobs            background task queue snapshot
  GET /v1/jobs/{job_id}   one job

The transport sits behind this thin module by design (docs/v4/ROADMAP.md
§6) so a judge phase can swap starlette for something else without
touching the Daemon or the registry/queue.
"""
from __future__ import annotations

import json
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

    async def get_runs(request):
        # Durable run journal — the permanent record (survives restarts).
        # /v1/jobs is the live in-memory view; /v1/runs is the archive.
        if daemon.runstore is None:
            return JSONResponse({"runs": [], "available": False})
        limit_raw = request.query_params.get("limit", "50")
        try:
            limit = max(0, int(limit_raw))
        except ValueError:
            return JSONResponse({"error": "limit must be an integer"}, status_code=400)
        return JSONResponse({"runs": daemon.runstore.list_runs(limit=limit), "available": True})

    async def get_run(request):
        if daemon.runstore is None:
            return JSONResponse({"error": "run journal unavailable"}, status_code=404)
        run_id = request.path_params["run_id"]
        manifest = daemon.runstore.read_manifest(run_id)
        if manifest is None:
            return JSONResponse({"error": "run not found"}, status_code=404)
        # Optional full log via ?log=1 (&tail=N for the last N lines).
        if request.query_params.get("log"):
            tail_raw = request.query_params.get("tail")
            tail = None
            if tail_raw is not None:
                try:
                    tail = max(0, int(tail_raw))
                except ValueError:
                    return JSONResponse({"error": "tail must be an integer"}, status_code=400)
            manifest = dict(manifest)
            manifest["log"] = daemon.runstore.read_log(run_id, tail=tail)
        return JSONResponse(manifest)

    async def get_events_recent(request):
        # JSON snapshot of recent events (poll-friendly fallback for clients
        # that can't hold an SSE stream open).
        kinds = _parse_kinds(request.query_params.get("kinds"))
        root = request.query_params.get("root")
        after_raw = request.query_params.get("after")
        limit_raw = request.query_params.get("limit")
        try:
            after = int(after_raw) if after_raw else 0
            limit = max(1, int(limit_raw)) if limit_raw else 100
        except ValueError:
            return JSONResponse({"error": "after/limit must be integers"}, status_code=400)
        events = daemon.events.recent(limit=limit, kinds=kinds, root=root, after_seq=after)
        return JSONResponse(
            {
                "events": [e.to_dict() for e in events],
                "last_seq": daemon.events.last_seq,
                "stats": daemon.events.stats(),
            }
        )

    async def stream_events(request):
        # Server-Sent Events stream. Reconnecting clients pass Last-Event-ID
        # (or ?after=N) to resume without gaps. The bus generator blocks, so
        # we pump it from a worker thread via anyio and yield into the ASGI
        # event loop.
        import anyio
        from starlette.responses import StreamingResponse

        kinds = _parse_kinds(request.query_params.get("kinds"))
        root = request.query_params.get("root")
        last_event_id = request.headers.get("last-event-id")
        after_q = request.query_params.get("after")
        after_seq = 0
        for candidate in (last_event_id, after_q):
            if candidate:
                try:
                    after_seq = int(candidate)
                    break
                except ValueError:
                    pass
        backfill = 0 if after_seq else 20

        send_stream, receive_stream = anyio.create_memory_object_stream(64)

        def _pump():
            gen = daemon.events.subscribe(
                kinds=kinds, root=root, backfill=backfill, after_seq=after_seq
            )
            try:
                for event in gen:
                    anyio.from_thread.run(send_stream.send, event)
            except anyio.BrokenResourceError:
                pass  # client disconnected
            finally:
                gen.close()
                anyio.from_thread.run_sync(send_stream.close)

        async def event_publisher():
            async with anyio.create_task_group() as tg:
                tg.start_soon(anyio.to_thread.run_sync, _pump)
                async with receive_stream:
                    async for event in receive_stream:
                        if event.kind == "heartbeat":
                            yield ": keepalive\n\n"
                            continue
                        payload = json.dumps(event.to_dict())
                        yield f"id: {event.seq}\nevent: {event.kind}\ndata: {payload}\n\n"

        return StreamingResponse(
            event_publisher(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def get_domain(request):
        # Field-awareness: detect (or read) the project's research domain
        # and return its profile + sensible defaults. Read-only; safe to
        # poll. ?root= overrides the daemon's resolved root.
        from pathlib import Path as _Path

        from .domains import detect

        root_q = request.query_params.get("root")
        root = _Path(root_q) if root_q else daemon.root
        if root is None:
            return JSONResponse({"available": False,
                                 "error": "no project root resolved"})
        result = detect(root)
        out = result.as_dict()
        out["root"] = str(root)
        out["available"] = True
        return JSONResponse(out)

    def _runstore_or_none(request):
        # Resolve the runstore for an optional ?root= override, else the
        # daemon's own runstore. Returns (runstore, error_response|None).
        root_q = request.query_params.get("root")
        if root_q:
            ws = daemon.registry.get(root_q) or daemon.registry.register(root_q)
            store = getattr(ws, "runstore", None)
        else:
            store = daemon.runstore
        return store

    def _limit_param(request, default=200):
        raw = request.query_params.get("limit")
        if raw is None:
            return default, None
        try:
            return max(0, int(raw)), None
        except ValueError:
            return None, JSONResponse(
                {"error": "limit must be an integer"}, status_code=400
            )

    async def get_lineage(request):
        # The content-addressed run dependency graph (who fed whom).
        from .lineage import ancestors, build_lineage, descendants

        store = _runstore_or_none(request)
        if store is None:
            return JSONResponse({"available": False,
                                 "error": "no run journal for this root"})
        limit, err = _limit_param(request)
        if err is not None:
            return err
        manifests = store.recent_manifests(limit=limit or 200)
        graph = build_lineage(manifests)
        # Optional focus on one run's up/downstream cone.
        rid = request.query_params.get("run_id")
        if rid:
            graph = dict(graph)
            graph["focus"] = {
                "run_id": rid,
                "ancestors": sorted(ancestors(graph, rid)),
                "descendants": sorted(descendants(graph, rid)),
            }
        graph["available"] = True
        return JSONResponse(graph)

    async def get_staleness(request):
        # Freshness verdict over the lineage DAG — which results were built
        # from inputs that have since changed on disk.
        from . import provenance as _prov
        from . import staleness as _stale

        store = _runstore_or_none(request)
        if store is None:
            return JSONResponse({"available": False,
                                 "error": "no run journal for this root"})
        limit, err = _limit_param(request)
        if err is not None:
            return err
        manifests = store.recent_manifests(limit=limit or 200)
        # Resolve hashes against the right root (override or daemon root).
        root_q = request.query_params.get("root")
        root = root_q or getattr(daemon, "root", None)
        hash_file = _prov.hash_fn_for_root(root)
        report = _stale.assess(manifests, hash_file)
        report["available"] = True
        return JSONResponse(report)

    async def get_rebuild_plan(request):
        # The plan only — what WOULD be rebuilt, in dependency order.
        # Read-only by design: actual rebuild is a mutation and stays on
        # the CLI / a future authenticated POST.
        if daemon.runstore is None and not request.query_params.get("root"):
            return JSONResponse({"available": False,
                                 "error": "no run journal resolved"})
        store = _runstore_or_none(request)
        if store is None:
            return JSONResponse({"available": False,
                                 "error": "no run journal for this root"})
        limit, err = _limit_param(request)
        if err is not None:
            return err
        from . import provenance as _prov
        from . import staleness as _stale
        from .lineage import build_lineage, topo_order

        manifests = store.recent_manifests(limit=limit or 200)
        root_q = request.query_params.get("root")
        root = root_q or getattr(daemon, "root", None)
        hash_file = _prov.hash_fn_for_root(root)
        report = _stale.assess(manifests, hash_file)
        stale_ids = set(report["stale"])
        if stale_ids:
            graph = build_lineage(manifests)
            plan = topo_order(graph, stale_ids)
        else:
            plan = []
        return JSONResponse({
            "available": True,
            "plan": plan,
            "counts": {"stale": len(stale_ids), "planned": len(plan)},
            "note": "dry-run only; POST rebuild requires auth (not yet enabled)",
        })

    routes = [
        Route("/healthz", healthz, methods=["GET"]),
        Route("/v1/state", get_state, methods=["GET"]),
        Route("/v1/domain", get_domain, methods=["GET"]),
        Route("/v1/lineage", get_lineage, methods=["GET"]),
        Route("/v1/staleness", get_staleness, methods=["GET"]),
        Route("/v1/rebuild/plan", get_rebuild_plan, methods=["GET"]),
        Route("/v1/jobs", get_jobs, methods=["GET"]),
        Route("/v1/jobs/{job_id}", get_job, methods=["GET"]),
        Route("/v1/runs", get_runs, methods=["GET"]),
        Route("/v1/runs/{run_id}", get_run, methods=["GET"]),
        Route("/v1/events", stream_events, methods=["GET"]),
        Route("/v1/events/recent", get_events_recent, methods=["GET"]),
    ]
    return Starlette(routes=routes)


def _parse_kinds(raw: str | None) -> set[str] | None:
    """Parse a comma-separated ?kinds= filter into a set, or None for all."""
    if not raw:
        return None
    kinds = {k.strip() for k in raw.split(",") if k.strip()}
    return kinds or None


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
