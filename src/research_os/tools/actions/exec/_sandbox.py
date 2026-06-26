"""Shared resource-bounding preexec for the agent's code-execution surface.

docs/RESOURCE_BUDGET.md.

The daemon's run_command path is bounded by daemon/runners.py + sandbox.py. But
the agent ALSO executes code directly through the reasoning-side exec tools
(scripts.py R/Julia/bash, notebook.py, sensitivity.py, step_pipeline.py, the
background tasks.py). The stress test proved those spawned children with ONLY a
wall timeout — no memory/CPU/file rlimits — so on a shared node a runaway script
could OOM other users' work. This module gives the reasoning layer its OWN
stdlib-only rlimit preexec so every exec path is bounded uniformly, WITHOUT
importing daemon/ (that would reverse the v4 seam arrow).

Policy (mirrors daemon/dynamic_limits.py, kept independent for the seam):
  * Read ``runtime.resource_budget`` (memory_mb / cpu_seconds / file_size_mb) and
    ``runtime.shared_server`` / ``runtime.dynamic_resources`` from researcher_config.
  * Memory ceiling = min(declared cap if any, live free-RAM headroom) so a run
    scales DOWN on a busy box and never starves others. The declared cap is the
    hard maximum; headroom only shrinks it.
  * SHARED-SERVER SAFETY DEFAULT: when ``shared_server: true`` and the project
    declared NO explicit memory cap, apply a headroom-derived cap anyway (never
    leave a shared-node run unbounded). On a private box with no cap + no
    shared_server, stay unbounded (the researcher opted out).

Never raises into the caller; returns None when nothing should be bounded
(then the caller spawns normally).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

_MB = 1024 * 1024


def _load_runtime(root: Path | str | None) -> dict[str, Any]:
    """Read the runtime block from researcher_config. Fail-safe to {}."""
    if root is None:
        return {}
    try:
        from research_os.tools.actions.state.config import get_research_config

        cfg = get_research_config(Path(root)) or {}
        rt = cfg.get("runtime") or {}
        return rt if isinstance(rt, dict) else {}
    except Exception:
        return {}


def _free_ram_mb() -> int | None:
    """Best-effort live free RAM in MB. psutil fast-path, /proc fallback,
    None when neither is available (caller then uses the declared cap only)."""
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().available / _MB)
    except Exception:
        pass
    try:
        # /proc/meminfo MemAvailable (kB)
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(int(line.split()[1]) / 1024)
    except Exception:
        pass
    return None


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def resolve_mem_cap_mb(runtime_cfg: dict[str, Any]) -> int | None:
    """Compute the memory ceiling (MB) to apply, or None for unbounded.

    min(declared cap, live-headroom). Shared-server with no declared cap still
    gets a headroom-derived cap (never unbounded on a shared node).
    """
    budget = runtime_cfg.get("resource_budget") or {}
    declared = budget.get("memory_mb")
    try:
        declared = int(declared) if declared else 0
    except (TypeError, ValueError):
        declared = 0

    shared = _as_bool(runtime_cfg.get("shared_server"))
    dyn = runtime_cfg.get("dynamic_resources") or {}
    dyn_enabled = _as_bool(dyn.get("enabled", True))  # on by default

    # Headroom: a safe fraction of live free RAM, minus a reserve for others.
    headroom = None
    if dyn_enabled or shared:
        free = _free_ram_mb()
        if free and free > 0:
            try:
                frac = float(dyn.get("mem_fraction", 0.80))
            except (TypeError, ValueError):
                frac = 0.80
            frac = min(max(frac, 0.05), 0.95)  # clamp to a sane band
            try:
                reserve = int(dyn.get("mem_reserve_mb", 2048))
            except (TypeError, ValueError):
                reserve = 2048
            reserve = max(reserve, 256)  # always hold something back for others
            headroom = max(int(free * frac) - reserve, 512)  # never below a floor

    caps = [c for c in (declared or None, headroom) if c]
    if not caps:
        # No declared cap AND no headroom signal. On a shared server we still
        # refuse to run unbounded — but with no signal we can't size it, so use
        # a conservative absolute fallback. On a private box, stay unbounded.
        if shared:
            return 4096  # 4 GB conservative shared-node default
        return None
    return min(caps)


def make_preexec(root: Path | str | None) -> Callable[[], None] | None:
    """Build a preexec_fn that applies CPU / memory / file-size rlimits in the
    child, sized from researcher_config + live headroom. None → spawn normally
    (nothing to bound). Stdlib-only; never imports daemon/.
    """
    rt = _load_runtime(root)
    budget = rt.get("resource_budget") or {}

    mem_cap_mb = resolve_mem_cap_mb(rt)
    try:
        cpu_s = int(budget.get("cpu_seconds") or 0) or None
    except (TypeError, ValueError):
        cpu_s = None
    try:
        fsize_mb = int(budget.get("file_size_mb") or 0) or None
    except (TypeError, ValueError):
        fsize_mb = None

    if not any((mem_cap_mb, cpu_s, fsize_mb)):
        return None

    def _preexec() -> None:
        import resource  # POSIX-only; imported in-child to stay portable

        if cpu_s:
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
            except (ValueError, OSError):
                pass
        if mem_cap_mb:
            try:
                cap = int(mem_cap_mb) * _MB
                resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
            except (ValueError, OSError):
                pass
        if fsize_mb:
            try:
                cap = int(fsize_mb) * _MB
                resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))
            except (ValueError, OSError):
                pass

    return _preexec


def run_bounded(cmd, *, root, timeout, cwd=None, **kwargs):
    """subprocess.run with the shared resource-bounding preexec applied.

    The single entry point every reasoning-side exec path should use so a
    script/notebook/pipeline honours the project's resource_budget + shared-
    server floor. Falls back to a plain run when nothing to bound or on a
    platform without preexec. Extra kwargs pass through to subprocess.run.
    """
    import subprocess as _sp

    try:
        preexec = make_preexec(root)
    except Exception:
        preexec = None
    call_kwargs: dict[str, Any] = dict(
        capture_output=True, text=True, errors="replace", timeout=timeout
    )
    if cwd is not None:
        call_kwargs["cwd"] = cwd
    call_kwargs.update(kwargs)
    if preexec is not None:
        call_kwargs["preexec_fn"] = preexec
        call_kwargs["start_new_session"] = True
    return _sp.run(cmd, **call_kwargs)
