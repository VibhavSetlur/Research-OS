"""Adapter loader — mirrors the v1.7.0 plugin loader pattern.

Discovery flow (called once at server startup from `server.py`):

    1. Walk `entry_points(group='research_os.adapter')` + any in-tree
       bundled adapters declared in `discover_adapters(bundled=...)`.
    2. For each entry-point, import the module and call `register()`.
    3. Validate the returned `AdapterRegistration`.
    4. Merge optional tools into `TOOL_DEFINITIONS` + `_HANDLERS`.
    5. Record diagnostics for `sys_adapters_installed`.

Errors are isolated per-adapter — a bad adapter logs to
`workspace/logs/adapter_errors.log` and is skipped, but does NOT
block server startup or other adapters.
"""
from __future__ import annotations

import importlib
import logging
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from research_os.adapters.base import AdapterRegistration, AdapterTool

logger = logging.getLogger("research_os.adapters.loader")

ENTRY_POINT_GROUP = "research_os.adapter"


@dataclass(frozen=True)
class AdapterLoadResult:
    """Successful registration record (returned by discover_adapters)."""
    name: str
    version: str
    description: str
    tools: tuple[AdapterTool, ...]
    tools_md_pattern_count: int
    detect: Callable[[Path], bool]
    extract: Callable[..., dict]
    describe: Callable[[], dict] | None


# ── module-level state populated by discover_adapters() ──────────────


_DISCOVERED_ADAPTERS: dict[str, AdapterLoadResult] = {}
_ADAPTER_ERRORS: list[tuple[str, str]] = []  # (entry_point, traceback)
_ADAPTER_EXTRACTORS: dict[str, tuple[tuple[str, str], ...]] = {}


def discover_adapters(
    *,
    tool_definitions: dict | None = None,
    handlers: dict | None = None,
    bundled: list[tuple[str, str]] | None = None,
) -> list[AdapterLoadResult]:
    """Discover and register every installed adapter."""
    _DISCOVERED_ADAPTERS.clear()
    _ADAPTER_ERRORS.clear()
    _ADAPTER_EXTRACTORS.clear()

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
            _DISCOVERED_ADAPTERS[registration.name] = result
            _ADAPTER_EXTRACTORS[registration.name] = registration.tools_md_patterns
        except Exception:
            tb = traceback.format_exc()
            _ADAPTER_ERRORS.append((ep_name, tb))
            logger.warning(
                "Adapter '%s' failed to register; skipping. Traceback:\n%s",
                ep_name, tb,
            )
    return list(_DISCOVERED_ADAPTERS.values())


def installed_adapters() -> list[dict]:
    """Snapshot suitable for `sys_adapters_installed` / `sys_boot`."""
    return [
        {
            "name": r.name,
            "version": r.version,
            "description": r.description,
            "tool_count": len(r.tools),
            "tools_md_pattern_count": r.tools_md_pattern_count,
        }
        for r in _DISCOVERED_ADAPTERS.values()
    ]


def load_adapter_errors() -> list[dict]:
    """Snapshot of registration errors."""
    return [{"entry_point": ep, "traceback": tb} for ep, tb in _ADAPTER_ERRORS]


def active_adapter_extractors() -> dict[str, tuple[tuple[str, str], ...]]:
    """Return adapter-name → tools_md_patterns map for the extractor pipeline."""
    return dict(_ADAPTER_EXTRACTORS)


def adapter_registrations() -> dict[str, AdapterLoadResult]:
    """Map of adapter-name → AdapterLoadResult for runtime callers."""
    return dict(_DISCOVERED_ADAPTERS)


def write_adapter_errors_log(root: Path) -> Path | None:
    """Persist adapter registration errors to workspace/logs/adapter_errors.log."""
    if not _ADAPTER_ERRORS:
        return None
    log_dir = root / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "adapter_errors.log"
    with open(path, "a") as f:
        for ep, tb in _ADAPTER_ERRORS:
            f.write(f"=== {ep} ===\n{tb}\n\n")
    return path


# ── internals ─────────────────────────────────────────────────────────


def _iter_entry_points() -> list[tuple[str, Any]]:
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return []
    eps = entry_points()
    if hasattr(eps, "select"):
        selected = eps.select(group=ENTRY_POINT_GROUP)
    else:  # pragma: no cover
        selected = eps.get(ENTRY_POINT_GROUP, [])
    out: list[tuple[str, Any]] = []
    for ep in selected:
        try:
            out.append((ep.name, ep.load()))
        except Exception:
            tb = traceback.format_exc()
            _ADAPTER_ERRORS.append((ep.name, tb))
            logger.warning("Adapter entry-point %s failed to load: %s", ep.name, tb)
    return out


def _call_register(target: Any) -> AdapterRegistration:
    if callable(target):
        result = target()
    elif isinstance(target, str):
        mod_name, _, attr = target.partition(":")
        attr = attr or "register"
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, attr)
        result = fn()
    else:
        raise TypeError(
            f"Adapter target must be callable or 'module:name' string; got {type(target)!r}"
        )
    if not isinstance(result, AdapterRegistration):
        raise TypeError(
            f"Adapter register() must return AdapterRegistration; got {type(result).__name__}"
        )
    return result


def _validate(reg: AdapterRegistration) -> None:
    if reg.name in _DISCOVERED_ADAPTERS:
        raise ValueError(f"Adapter name '{reg.name}' already registered")
    # Adapter base.register_adapter already enforces tool name prefix +
    # regex compilation. Re-check name shape here so direct AdapterRegistration
    # constructors (bypassing register_adapter) still get caught.
    if not reg.name or not reg.name.replace("_", "").isalnum() or reg.name != reg.name.lower():
        raise ValueError(
            f"Adapter name must be lowercase alphanumeric (underscores ok); got {reg.name!r}"
        )
    expected_prefix = f"tool_{reg.name}_"
    for t in reg.tools:
        if not t.name.startswith(expected_prefix):
            raise ValueError(
                f"Adapter '{reg.name}' tool '{t.name}' must start with "
                f"'{expected_prefix}' (namespace convention)"
            )


def _merge(
    reg: AdapterRegistration,
    *,
    tool_definitions: dict | None,
    handlers: dict | None,
) -> AdapterLoadResult:
    if tool_definitions is not None and handlers is not None:
        for t in reg.tools:
            if t.name in tool_definitions:
                raise ValueError(
                    f"Adapter '{reg.name}' tool '{t.name}' collides with an "
                    f"existing tool (core or another adapter)."
                )
            sch = dict(t.schema)
            description = sch.pop("description", "")
            short = sch.pop("short", description[:160] if description else "")
            input_schema = {k: v for k, v in sch.items()
                            if k not in {"description", "short", "category"}}
            input_schema.setdefault("type", "object")
            tool_definitions[t.name] = {
                "description": description,
                "short": short,
                "category": sch.get("category", f"adapter:{reg.name}"),
                "inputSchema": input_schema,
            }
            handlers[t.name] = t.handler
    return AdapterLoadResult(
        name=reg.name,
        version=reg.version,
        description=reg.description,
        tools=reg.tools,
        tools_md_pattern_count=len(reg.tools_md_patterns),
        detect=reg.detect,
        extract=reg.extract,
        describe=reg.describe,
    )
