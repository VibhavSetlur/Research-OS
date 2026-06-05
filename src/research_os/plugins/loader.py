"""Plugin loader: discover entry-pointed packs and merge them into core.

Discovery flow (called once at server startup from `server.py`):

    1. Walk `entry_points(group='research_os.protocol_pack')`.
    2. For each entry-point, import its module and call `register()`.
    3. Validate the returned `PackRegistration`.
    4. Merge tools into `TOOL_DEFINITIONS` + `_HANDLERS`.
    5. Merge router entries into the in-memory router-index map.
    6. Note the pack's `protocols_dir` so the protocol loader picks
       up the pack's YAMLs alongside the core tree.
    7. Record diagnostics for `sys_packs_installed`.

Errors are isolated per-pack: a bad pack logs to `pack_errors.log`
and is skipped, but does NOT block server startup or other packs.

Namespace validation:
    * tool names must start with `tool_<pack>_`
    * router-entry keys must start with `<pack>/`
    * protocol files inside the pack's protocols_dir are loaded under
      the `<pack>/...` path (handled in `protocol.py` via the
      registered pack directories)

This module owns three globals:
    * `_DISCOVERED_PACKS` — successful PackLoadResult per pack name
    * `_PACK_ERRORS`      — list of (entry_point, exception) for diagnostics
    * `_PACK_PROTOCOL_DIRS` — name → Path for protocol-loader integration
"""
from __future__ import annotations

import importlib
import logging
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from research_os.plugins.pack_api import PackRegistration, PackTool

logger = logging.getLogger("research_os.plugins.loader")

ENTRY_POINT_GROUP = "research_os.protocol_pack"


@dataclass(frozen=True)
class PackLoadResult:
    """Successful registration record (returned by discover_packs)."""
    name: str
    version: str
    description: str
    protocols_dir: Path
    tools: tuple[PackTool, ...]
    router_entry_count: int
    has_domain_detector: bool


# ── module-level state populated by discover_packs() ─────────────────


_DISCOVERED_PACKS: dict[str, PackLoadResult] = {}
_PACK_ERRORS: list[tuple[str, str]] = []  # (entry_point_name, traceback)
_PACK_PROTOCOL_DIRS: dict[str, Path] = {}
_PACK_ROUTER_ENTRIES: dict[str, dict] = {}
_PACK_DOMAIN_DETECTORS: dict[str, Callable[[Path], dict]] = {}


# ── public surface ────────────────────────────────────────────────────


def discover_packs(
    *,
    tool_definitions: dict | None = None,
    handlers: dict | None = None,
    bundled: list[tuple[str, str]] | None = None,
) -> list[PackLoadResult]:
    """Discover and register all installed packs.

    Walks the `research_os.protocol_pack` entry-point group plus any
    `bundled` (name, module) pairs (used for in-tree packs that ship
    with the main wheel before they split out to separate PyPI packages).

    The function is idempotent: subsequent calls reset the registry
    and re-discover, so tests can monkey-patch entry points cleanly.

    Returns the list of `PackLoadResult` for successfully loaded packs.
    """
    # Reset per-discovery state. Tool / router merging into the
    # caller-provided dicts is one-shot per call.
    _DISCOVERED_PACKS.clear()
    _PACK_ERRORS.clear()
    _PACK_PROTOCOL_DIRS.clear()
    _PACK_ROUTER_ENTRIES.clear()
    _PACK_DOMAIN_DETECTORS.clear()

    entries = _iter_entry_points() + list(bundled or [])
    for ep_name, ep_target in entries:
        try:
            registration = _call_register(ep_target)
            _validate(registration)
            result = _merge(
                registration,
                tool_definitions=tool_definitions,
                handlers=handlers,
            )
            _DISCOVERED_PACKS[registration.name] = result
        except Exception:
            tb = traceback.format_exc()
            _PACK_ERRORS.append((ep_name, tb))
            logger.warning(
                "Pack '%s' failed to register; skipping. Traceback:\n%s",
                ep_name,
                tb,
            )
    return list(_DISCOVERED_PACKS.values())


def installed_packs() -> list[dict]:
    """Snapshot suitable for `sys_packs_installed` / `sys_boot`."""
    out: list[dict] = []
    for r in _DISCOVERED_PACKS.values():
        out.append({
            "name": r.name,
            "version": r.version,
            "description": r.description,
            "tool_count": len(r.tools),
            "router_entry_count": r.router_entry_count,
            "has_domain_detector": r.has_domain_detector,
            "protocols_dir": str(r.protocols_dir),
        })
    return out


def load_pack_errors() -> list[dict]:
    """Snapshot of registration errors (one entry per failing pack)."""
    return [{"entry_point": ep, "traceback": tb} for ep, tb in _PACK_ERRORS]


def pack_protocol_dirs() -> dict[str, Path]:
    """Map of pack-name → protocols_dir, used by the protocol loader."""
    return dict(_PACK_PROTOCOL_DIRS)


def pack_router_entries() -> dict[str, dict]:
    """All router entries contributed by packs (already namespace-prefixed)."""
    return dict(_PACK_ROUTER_ENTRIES)


def pack_domain_detectors() -> dict[str, Callable[[Path], dict]]:
    """Map of pack-name → domain detector callable."""
    return dict(_PACK_DOMAIN_DETECTORS)


def write_pack_errors_log(root: Path) -> Path | None:
    """Persist pack errors to `<root>/workspace/logs/pack_errors.log`."""
    if not _PACK_ERRORS:
        return None
    log_dir = root / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "pack_errors.log"
    with open(path, "a") as f:
        for ep, tb in _PACK_ERRORS:
            f.write(f"=== {ep} ===\n{tb}\n\n")
    return path


# ── internals ─────────────────────────────────────────────────────────


def _iter_entry_points() -> list[tuple[str, Any]]:
    """Return (name, callable-or-string-target) for every research_os.protocol_pack entry."""
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover - py<3.10 fallback
        return []
    eps = entry_points()
    if hasattr(eps, "select"):
        selected = eps.select(group=ENTRY_POINT_GROUP)
    else:  # pragma: no cover - py<3.10
        selected = eps.get(ENTRY_POINT_GROUP, [])
    out: list[tuple[str, Any]] = []
    for ep in selected:
        # Pass the loaded callable directly so _call_register doesn't
        # need to re-resolve dotted strings.
        try:
            out.append((ep.name, ep.load()))
        except Exception:
            tb = traceback.format_exc()
            _PACK_ERRORS.append((ep.name, tb))
            logger.warning("Entry-point %s failed to load: %s", ep.name, tb)
    return out


def _call_register(target: Any) -> PackRegistration:
    """Resolve `target` to a callable and invoke it."""
    if callable(target):
        result = target()
    elif isinstance(target, str):
        # "module:name" style — useful for bundled packs.
        mod_name, _, attr = target.partition(":")
        attr = attr or "register"
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, attr)
        result = fn()
    else:
        raise TypeError(
            f"Pack target must be callable or 'module:name' string; got {type(target)!r}"
        )
    if not isinstance(result, PackRegistration):
        raise TypeError(
            f"Pack register() must return PackRegistration; got {type(result).__name__}"
        )
    return result


def _validate(reg: PackRegistration) -> None:
    """Enforce namespace conventions before merging into core."""
    if not reg.name or not reg.name.replace("_", "").isalnum():
        raise ValueError(
            f"Pack name must be lowercase alphanumeric (underscores ok); got {reg.name!r}"
        )
    if reg.name != reg.name.lower():
        raise ValueError(f"Pack name must be lowercase; got {reg.name!r}")
    if reg.name in _DISCOVERED_PACKS:
        raise ValueError(f"Pack name '{reg.name}' already registered")
    expected_tool_prefix = f"tool_{reg.name}_"
    for t in reg.tools:
        if not t.name.startswith(expected_tool_prefix):
            raise ValueError(
                f"Pack '{reg.name}' tool '{t.name}' must start with "
                f"'{expected_tool_prefix}' (namespace convention)"
            )
    expected_router_prefix = f"{reg.name}/"
    for key in reg.router_entries:
        if not key.startswith(expected_router_prefix):
            raise ValueError(
                f"Pack '{reg.name}' router entry '{key}' must start with "
                f"'{expected_router_prefix}' (namespace convention)"
            )
    if not reg.protocols_dir.exists():
        raise ValueError(
            f"Pack '{reg.name}' protocols_dir does not exist: {reg.protocols_dir}"
        )


def _merge(
    reg: PackRegistration,
    *,
    tool_definitions: dict | None,
    handlers: dict | None,
) -> PackLoadResult:
    """Merge a pack's contributions into core registries."""
    if tool_definitions is not None and handlers is not None:
        for t in reg.tools:
            if t.name in tool_definitions:
                raise ValueError(
                    f"Pack '{reg.name}' tool '{t.name}' collides with an "
                    f"existing tool. Rename the pack tool."
                )
            # The pack-author API stores the inputSchema fields (type,
            # properties, required) flat alongside description / short.
            # Core TOOL_DEFINITIONS expects an `inputSchema` nested
            # dict — repackage here.
            sch = dict(t.schema)
            description = sch.pop("description", "")
            short = sch.pop("short", description[:160] if description else "")
            input_schema = {k: v for k, v in sch.items()
                            if k not in {"description", "short", "category"}}
            input_schema.setdefault("type", "object")
            tool_definitions[t.name] = {
                "description": description,
                "short": short,
                "category": sch.get("category", reg.name),
                "inputSchema": input_schema,
            }
            handlers[t.name] = t.handler
    _PACK_PROTOCOL_DIRS[reg.name] = reg.protocols_dir
    _PACK_ROUTER_ENTRIES.update(reg.router_entries)
    if reg.domain_detector is not None:
        _PACK_DOMAIN_DETECTORS[reg.name] = reg.domain_detector
    return PackLoadResult(
        name=reg.name,
        version=reg.version,
        description=reg.description,
        protocols_dir=reg.protocols_dir,
        tools=reg.tools,
        router_entry_count=len(reg.router_entries),
        has_domain_detector=reg.domain_detector is not None,
    )
