"""Resource budget — a researcher-declared ceiling the daemon enforces.

docs/RESOURCE_BUDGET.md. The autopilot protocol says, in prose, to stay
within "the project's budget" — but no budget existed, so every run used
the sandbox's generic defaults. This resolves a ``resource_budget:`` block
from ``inputs/researcher_config.yaml`` into the ACTUAL ``ResourceLimits``
(rlimits + wallclock) applied to every submitted run, turning soft prose
into a hard, enforced bound.

Field semantics (each optional):
  * absent       → fall back to the base/default limit (today's behaviour)
  * a positive int → cap this dimension at that value
  * null or 0    → UNCAPPED (the researcher's explicit "no limit" choice)

Precedence (tightest intent first), applied by ``resolve_run_limits``:
  explicit per-run limit  >  project budget  >  sandbox default

stdlib only (+ the yaml dep config.py already uses). Pure functions — no
daemon state, trivially testable, never raises on a bad config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Map a budget config key -> the ResourceLimits field it sets. memory_mb is
# an alias for address_space_mb (the researcher thinks "memory", the rlimit
# is RLIMIT_AS / virtual address space).
_BUDGET_FIELD_MAP = {
    "memory_mb": "address_space_mb",
    "address_space_mb": "address_space_mb",
    "cpu_seconds": "cpu_seconds",
    "wall_seconds": "wall_seconds",
    "file_size_mb": "file_size_mb",
    "open_files": "open_files",
    "processes": "processes",
}

# A sentinel distinguishing "field absent" (use base) from "field set to
# null/0" (explicitly uncapped). load_budget emits None for uncapped and
# simply omits absent keys.
_UNCAPPED = object()


def _coerce_value(raw: Any) -> Any:
    """Coerce a budget value: None/0 → uncapped sentinel; int-like → int.

    Returns the _UNCAPPED sentinel for an explicit no-limit choice, an int
    for a real cap, or None to signal "ignore this key" (unparseable).
    """
    if raw is None:
        return _UNCAPPED
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return _UNCAPPED
    return val


def load_budget(root: str | Path) -> dict[str, Any]:
    """Read + validate the ``resource_budget:`` block. Fail-safe to {}.

    Returns a dict keyed by ResourceLimits FIELD name, where the value is
    either an int (cap) or the _UNCAPPED sentinel (explicit no-limit). An
    absent block, parse error, or non-mapping yields {} (no budget → base
    defaults apply). Unknown keys are ignored.
    """
    try:
        import yaml
    except Exception:  # noqa: BLE001
        return {}
    block: Any = None
    for rel in ("inputs/researcher_config.yaml", "researcher_config.yaml"):
        path = Path(root) / rel
        if path.exists():
            try:
                cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                return {}
            block = None
            if isinstance(cfg, dict):
                # Documented home is runtime.resource_budget (it's a compute
                # ceiling); also accept a top-level resource_budget for
                # back-compat. The nested form wins when both are present.
                rt = cfg.get("runtime")
                if isinstance(rt, dict) and isinstance(rt.get("resource_budget"), dict):
                    block = rt["resource_budget"]
                elif isinstance(cfg.get("resource_budget"), dict):
                    block = cfg["resource_budget"]
            break
    if not isinstance(block, dict):
        return {}
    out: dict[str, Any] = {}
    for key, raw in block.items():
        field = _BUDGET_FIELD_MAP.get(str(key))
        if field is None:
            continue
        coerced = _coerce_value(raw)
        if coerced is None:
            continue  # unparseable → ignore, fall back to base
        out[field] = coerced
    return out


def apply_budget(limits: Any, budget: dict[str, Any]) -> Any:
    """Overlay a loaded budget onto a base ResourceLimits, returning a copy.

    Field-by-field: a budget int caps that field; the _UNCAPPED sentinel
    sets it to None (no rlimit on that dimension); an absent field keeps the
    base value. Never mutates the input. Tolerates a base without a given
    attribute (defensive).
    """
    import dataclasses

    if not budget:
        return limits
    changes: dict[str, Any] = {}
    for field, value in budget.items():
        if not hasattr(limits, field):
            continue
        changes[field] = None if value is _UNCAPPED else value
    if not changes:
        return limits
    try:
        return dataclasses.replace(limits, **changes)
    except (TypeError, ValueError):
        return limits


def resolve_run_limits(root: str | Path, base: Any = None) -> Any:
    """Resolve the effective ResourceLimits for a run under ``root``.

    Precedence (tightest intent first): an explicit per-run ``base`` is the
    starting point (else the sandbox default), then the project budget
    overlays any dimension it declares. So an explicit submit-time limit
    survives unless the budget specifically overrides that dimension.
    """
    from . import sandbox as _sb

    limits = base if base is not None else _sb.ResourceLimits()
    budget = load_budget(root)
    return apply_budget(limits, budget)


def load_runtime(root: str | Path) -> dict[str, Any]:
    """Read the ``runtime:`` block from researcher_config (fail-safe to {}).

    Surfaces the execution-environment facts the daemon must respect on a
    shared cluster node:

      * ``shared_server`` (bool) — the host is a multi-tenant box (a shared
        HPC login/compute node). A runaway run here can take down OTHER
        users' work, so the daemon must bound every run and must NOT assume
        a private container runtime / unprivileged user namespaces exist.
      * ``compute_environment`` (str) — e.g. ``"conda"`` / ``"docker"`` /
        ``"native"``; a hint for which isolation strategy is even feasible.

    Returns a small normalized dict; an absent/malformed block yields {}.
    """
    try:
        import yaml
    except Exception:  # noqa: BLE001
        return {}
    for rel in ("inputs/researcher_config.yaml", "researcher_config.yaml"):
        path = Path(root) / rel
        if path.exists():
            try:
                cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                return {}
            rt = cfg.get("runtime") if isinstance(cfg, dict) else None
            if not isinstance(rt, dict):
                return {}
            out: dict[str, Any] = {}
            if "shared_server" in rt:
                out["shared_server"] = _as_bool(rt.get("shared_server"))
            ce = rt.get("compute_environment")
            if ce is not None:
                out["compute_environment"] = str(ce).strip().lower()
            return out
    return {}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def resolve_sandbox_tier(
    root: str | Path,
    *,
    sandbox_mode: str = "auto",
) -> str | None:
    """Decide the sandbox tier the daemon should request for a local run.

    Turns the daemon's ``sandbox_mode`` config + the project's ``runtime``
    block into the tier passed to the runner. The guiding rule on a shared
    node is: ALWAYS bound the run (resource tier is the universal floor),
    but never PRETEND to have isolation the host can't give.

      * ``sandbox_mode="off"``  → ``None`` (explicit opt-out: no bounding).
      * ``sandbox_mode="native"`` → ``"resource"`` (rlimits + wallclock only;
        never container/namespace, even if available).
      * ``sandbox_mode="auto"`` → ``"resource"`` when the project declares
        ``runtime.shared_server`` (no Docker / no usable userns on a shared
        HPC box — don't waste a probe, go straight to the enforceable floor)
        OR when ``compute_environment`` is conda/native; otherwise let the
        runner auto-detect the strongest tier (returns ``"container"`` as the
        request, which the sandbox detector degrades to what the host allows).

    The resource tier is what makes the resource_budget actually bind, so
    the default (auto, no shared flag) still returns a bounding tier — a
    daemon background run is never left completely unbounded unless the
    operator explicitly sets ``sandbox_mode: off``.
    """
    mode = (sandbox_mode or "auto").strip().lower()
    if mode == "off":
        return None
    if mode == "native":
        return "resource"
    # auto
    rt = load_runtime(root)
    if rt.get("shared_server"):
        return "resource"
    ce = rt.get("compute_environment")
    if ce in ("conda", "native", "venv", "pip"):
        return "resource"
    if ce == "docker":
        return "container"
    # No runtime hints: still bound the run (resource floor), but let the
    # detector promote to stronger isolation when the host genuinely offers
    # it by requesting the strongest tier — it degrades down on its own.
    return "container"


def budget_summary(root: str | Path) -> dict[str, Any]:
    """Human/agent-facing view of the active budget for capabilities/status.

    Returns ``{"configured": bool, "limits": {field: value|null}}`` where a
    null means that dimension is explicitly uncapped by the budget. When no
    budget block exists, ``configured`` is False and ``limits`` is empty
    (the sandbox defaults apply — reported elsewhere).
    """
    budget = load_budget(root)
    if not budget:
        return {"configured": False, "limits": {}}
    return {
        "configured": True,
        "limits": {
            field: (None if value is _UNCAPPED else value)
            for field, value in budget.items()
        },
    }
