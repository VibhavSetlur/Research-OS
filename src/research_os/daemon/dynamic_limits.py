"""Dynamic resource limits — scale a run's ceiling to BOTH what the user
asked for AND what the shared machine can currently spare, so a multi-gig
batch can run big on an idle box yet never starves other users on a busy one.

docs/RESOURCE_BUDGET.md (§ Dynamic budgets).

The static ``resource_budget`` (resource_budget.py) is a researcher-declared
*ceiling*. That ceiling alone is a blunt instrument on a shared HPC node:

  * Too low  → a legitimate 40 GB genomics batch is killed even though the
               node has 500 GB free.
  * Too high → one run grabs all the RAM the moment the node fills up and
               takes down everyone else's work.

This module computes an EFFECTIVE per-run limit each time a run is launched,
as the minimum of three independent bounds:

  1. **Requested**  — what the user/agent asked for this run (or the project
     budget). The run never gets *more* than it declared it needs.
  2. **Headroom**   — a safe fraction of what is CURRENTLY AVAILABLE on the
     box (free RAM, idle CPU), reserving an absolute floor for everyone else.
     This is the "don't break it for others" bound — it shrinks automatically
     as the node fills up.
  3. **Hard ceiling** — the project's declared absolute max (if any), so even
     an idle box can't hand a single run more than the researcher allows.

The result: limits breathe with the machine. Pure-ish (reads /proc + os),
stdlib-only with an optional psutil fast-path, and fail-OPEN to the static
budget on any error so a probe failure never blocks a run.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MB = 1024 * 1024

# Defaults for the headroom policy. Conservative on a shared box: a run may
# claim up to this FRACTION of currently-free memory, but we always hold back
# at least the RESERVE so the node never goes to zero free on one run's
# account. Operators tune these via runtime.dynamic_resources in config.
_DEFAULT_MEM_FRACTION = 0.80      # of currently-FREE memory
_DEFAULT_MEM_RESERVE_MB = 2048    # always leave this much for others
_DEFAULT_CPU_FRACTION = 0.75      # of currently-IDLE cores
_DEFAULT_MIN_MEM_MB = 512         # never hand a run less than this (or it's useless)


@dataclass(frozen=True)
class SystemCapacity:
    """A snapshot of what the host can currently spare. All best-effort."""

    total_mem_mb: int | None = None
    available_mem_mb: int | None = None
    cpu_count: int | None = None
    load_avg_1m: float | None = None
    source: str = "none"

    @property
    def idle_cpus(self) -> float | None:
        """Approximate currently-idle cores = cpu_count - 1m loadavg."""
        if self.cpu_count is None or self.load_avg_1m is None:
            return None
        return max(0.0, float(self.cpu_count) - float(self.load_avg_1m))


def probe_capacity() -> SystemCapacity:
    """Snapshot current host capacity. psutil fast-path, /proc fallback.

    Never raises: any failure yields an all-None capacity (source="none"),
    which the resolver treats as "no headroom signal" and falls back to the
    static budget. This is the fail-open contract — a probe failure must
    never block a run.
    """
    # Fast path: psutil if the host has it (not a hard dep).
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        try:
            load1 = os.getloadavg()[0]
        except (OSError, AttributeError):
            load1 = None
        return SystemCapacity(
            total_mem_mb=int(vm.total // _MB),
            available_mem_mb=int(vm.available // _MB),
            cpu_count=psutil.cpu_count() or os.cpu_count(),
            load_avg_1m=load1,
            source="psutil",
        )
    except Exception:  # noqa: BLE001 - psutil absent or failed; try /proc
        pass

    # Fallback: /proc/meminfo + /proc/loadavg (Linux). Fail-open to none.
    try:
        total_kb = avail_kb = None
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
                if total_kb is not None and avail_kb is not None:
                    break
        try:
            load1 = os.getloadavg()[0]
        except (OSError, AttributeError):
            load1 = None
        return SystemCapacity(
            total_mem_mb=(total_kb // 1024) if total_kb else None,
            available_mem_mb=(avail_kb // 1024) if avail_kb else None,
            cpu_count=os.cpu_count(),
            load_avg_1m=load1,
            source="proc",
        )
    except Exception:  # noqa: BLE001
        return SystemCapacity(source="none")


def load_dynamic_policy(root: str | Path) -> dict[str, Any]:
    """Read ``runtime.dynamic_resources`` from researcher_config (fail-safe).

    Recognized keys (all optional):
      * ``enabled`` (bool, default True) — turn dynamic scaling on/off.
      * ``mem_fraction`` (float 0–1) — max share of FREE memory a run may take.
      * ``mem_reserve_mb`` (int) — memory always held back for other users.
      * ``cpu_fraction`` (float 0–1) — max share of IDLE cores a run may take.
      * ``min_mem_mb`` (int) — floor below which we don't bother shrinking.

    An absent/malformed block yields the defaults (with enabled=True).
    """
    policy = {
        "enabled": True,
        "mem_fraction": _DEFAULT_MEM_FRACTION,
        "mem_reserve_mb": _DEFAULT_MEM_RESERVE_MB,
        "cpu_fraction": _DEFAULT_CPU_FRACTION,
        "min_mem_mb": _DEFAULT_MIN_MEM_MB,
    }
    try:
        import yaml
    except Exception:  # noqa: BLE001
        return policy
    for rel in ("inputs/researcher_config.yaml", "researcher_config.yaml"):
        path = Path(root) / rel
        if not path.exists():
            continue
        try:
            cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            return policy
        rt = cfg.get("runtime") if isinstance(cfg, dict) else None
        block = rt.get("dynamic_resources") if isinstance(rt, dict) else None
        if not isinstance(block, dict):
            return policy
        if "enabled" in block:
            policy["enabled"] = _as_bool(block.get("enabled"))
        for fkey in ("mem_fraction", "cpu_fraction"):
            if fkey in block:
                try:
                    v = float(block[fkey])
                    if 0.0 < v <= 1.0:
                        policy[fkey] = v
                except (TypeError, ValueError):
                    pass
        for ikey in ("mem_reserve_mb", "min_mem_mb"):
            if ikey in block:
                try:
                    iv = int(block[ikey])
                    if iv >= 0:
                        policy[ikey] = iv
                except (TypeError, ValueError):
                    pass
        return policy
    return policy


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _headroom_mem_mb(cap: SystemCapacity, policy: dict[str, Any]) -> int | None:
    """Safe memory a run may claim right now = fraction of free, minus reserve.

    Returns None when capacity is unknown (no headroom signal → caller keeps
    the static limit).
    """
    if cap.available_mem_mb is None:
        return None
    reserve = int(policy.get("mem_reserve_mb", _DEFAULT_MEM_RESERVE_MB))
    frac = float(policy.get("mem_fraction", _DEFAULT_MEM_FRACTION))
    spare = cap.available_mem_mb - reserve
    if spare <= 0:
        # Box is under memory pressure: hand out only the minimum so the run
        # can still start (and likely fail fast) without finishing off the node.
        return int(policy.get("min_mem_mb", _DEFAULT_MIN_MEM_MB))
    allowed = int(spare * frac)
    return max(allowed, int(policy.get("min_mem_mb", _DEFAULT_MIN_MEM_MB)))


def resolve_dynamic_limits(
    root: str | Path,
    base: Any = None,
    *,
    requested_mem_mb: int | None = None,
    capacity: SystemCapacity | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Compute the EFFECTIVE ResourceLimits for a run, scaled to live capacity.

    Combines the static budget (resource_budget.resolve_run_limits) with a
    live-headroom bound: the memory ceiling becomes the MINIMUM of
      (a) the static/declared limit (the hard ceiling — never exceeded),
      (b) ``requested_mem_mb`` if the caller asked for a specific size, and
      (c) the current safe headroom (fraction of free RAM minus the reserve).

    The headroom bound can only ever LOWER the static ceiling, never raise it
    above the researcher's declared max — so the project's hard cap is always
    respected, while a busy node automatically shrinks the run.

    BUT: when the static budget leaves memory UNCAPPED (the researcher's
    explicit "use what the box has"), dynamic headroom becomes the *active*
    ceiling — that's how a multi-gig batch safely uses a big idle node without
    a hand-tuned number, and automatically backs off when the node fills.

    Returns ``(limits, explain)`` where ``explain`` records each bound and the
    winner, for transparency in the run manifest. Fail-open: any error returns
    the static limits unchanged with ``explain={"dynamic": "error"}``.
    """
    from . import resource_budget as _budget

    try:
        static = _budget.resolve_run_limits(root, base=base)
    except Exception:  # noqa: BLE001
        from . import sandbox as _sb

        static = base if base is not None else _sb.ResourceLimits()

    explain: dict[str, Any] = {"dynamic": "off"}
    try:
        policy = load_dynamic_policy(root)
        if not policy.get("enabled", True):
            return static, {"dynamic": "disabled"}
        cap = capacity or probe_capacity()
        if cap.source == "none":
            return static, {"dynamic": "no_capacity_signal"}

        headroom = _headroom_mem_mb(cap, policy)
        static_mem = getattr(static, "address_space_mb", None)

        # Candidate ceilings (only those that are real numbers participate).
        candidates: list[int] = []
        if static_mem is not None:
            candidates.append(int(static_mem))
        if requested_mem_mb is not None and requested_mem_mb > 0:
            candidates.append(int(requested_mem_mb))
        if headroom is not None:
            candidates.append(int(headroom))

        explain = {
            "dynamic": "on",
            "source": cap.source,
            "available_mem_mb": cap.available_mem_mb,
            "headroom_mem_mb": headroom,
            "static_mem_mb": static_mem,
            "requested_mem_mb": requested_mem_mb,
        }

        if not candidates:
            # Everything uncapped and no headroom signal → leave as-is.
            explain["effective_mem_mb"] = None
            return static, explain

        effective_mem = min(candidates)
        explain["effective_mem_mb"] = effective_mem

        import dataclasses

        try:
            scaled = dataclasses.replace(static, address_space_mb=effective_mem)
        except (TypeError, ValueError):
            return static, explain

        # Also gently bound CPU time-slice intent by idle cores when the run
        # didn't pin its own — informational only (rlimit CPU is seconds, not
        # cores), so we record the idle estimate for schedulers/telemetry.
        explain["idle_cpus"] = cap.idle_cpus
        return scaled, explain
    except Exception:  # noqa: BLE001 - fail open to the static budget
        return static, {"dynamic": "error"}
