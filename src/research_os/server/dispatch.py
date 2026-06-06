"""Tool-call dispatcher: alias resolution, deprecation logging, param injection.

This module owns the request-routing pipeline:
    name → canonical_input (dots→underscores)
         → resolved (alias lookup)
         → optional param injection (legacy alias → consolidated kwargs)
         → handler dispatch

Errors from any handler are caught and converted into an error envelope.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .aliases import (
    _ALIAS_PARAM_INJECTION,
    _ALIASES,
    _DEPRECATED_ALIASES,
    _REMOVED_TOOLS,
)
from .envelopes import TextContent, _error, _text
from .errors import RoError, did_you_mean
from .rate_limiter import _rate_limiter


logger = logging.getLogger("research-os.server")


def _resolve_tool_name(name: str) -> str:
    """Normalize incoming tool name: dots→underscores, then alias lookup."""
    canonical = name.replace(".", "_")
    return _ALIASES.get(canonical, canonical)


def _inject_consolidation_param(source_name: str, arguments: dict) -> dict:
    """Inject the consolidation parameter(s) implied by a deprecated alias.

    Accepts either a single (key, value) tuple or a tuple of (key, value)
    pairs. No-op if the caller already supplied the parameter (caller wins).
    """
    spec = _ALIAS_PARAM_INJECTION.get(source_name)
    if not spec:
        return arguments
    # Multi-kwarg form: tuple of (key, value) pairs.
    if (
        isinstance(spec, tuple)
        and spec
        and all(isinstance(p, tuple) and len(p) == 2 for p in spec)
    ):
        for key, value in spec:
            arguments.setdefault(key, value)
        return arguments
    # Single-kwarg form: (key, value).
    if isinstance(spec, tuple) and len(spec) == 2 and not isinstance(spec[0], tuple):
        key, value = spec
        arguments.setdefault(key, value)
        return arguments
    return arguments


def _log_deprecation(root: Path, source: str, target: str) -> None:
    """Append an alias-invocation event to .os_state/deprecations.log."""
    try:
        log_dir = root / ".os_state"
        if not log_dir.exists():
            return
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "kind": "tool_alias",
            "source": source,
            "target": target,
        }
        with open(log_dir / "deprecations.log", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        # Best-effort telemetry — failing here must never break the dispatch.
        logger.debug("deprecation-log append failed: %s", exc)


def _handle_tool_call(name: str, arguments: dict, root: Path) -> list[TextContent]:
    if not _rate_limiter.is_allowed():
        return _text(_error("Rate limit exceeded — slow down."))
    canonical_input = name.replace(".", "_")
    resolved = _resolve_tool_name(name)
    logger.info(f"Tool call: {name} -> {resolved}")
    if canonical_input in _DEPRECATED_ALIASES and canonical_input != resolved:
        _log_deprecation(root, canonical_input, resolved)
        # Back-compat: inject the dispatch parameter the consolidated tool
        # expects, so a researcher (or older script) calling the legacy name
        # gets the legacy behaviour without specifying operation/kind/source.
        arguments = _inject_consolidation_param(canonical_input, dict(arguments or {}))
    if resolved in _REMOVED_TOOLS:
        return _text(_error(_REMOVED_TOOLS[resolved]))

    # Defer import to avoid circular at module load time.
    from .registry import _HANDLERS

    handler = _HANDLERS.get(resolved)
    if handler is None:
        suggestions = did_you_mean(resolved, list(_HANDLERS.keys()), n=3)
        suggestion_clause = (
            f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        )
        return _text(
            _error(
                what=f"unknown tool '{name}'",
                why=(
                    "no handler is registered for that name — it may be "
                    "deprecated, removed, or a typo"
                ),
                next_action=(
                    f"call sys_tools_list to see live tools.{suggestion_clause}"
                ),
            )
        )
    try:
        return handler(resolved, arguments, root)
    except RoError as ro:
        # Structured error from the handler: render its WHAT/WHY/NEXT
        # directly into the envelope.
        logger.info("RoError in %s: %s", name, ro.what)
        return _text(_error(**ro.to_envelope_kwargs()))
    except KeyError as ke:
        # KeyError(name) bubbling up from a dispatch lookup or arg
        # unpacking is almost always a missing-required-arg situation.
        missing = ke.args[0] if ke.args else "?"
        return _text(_error(
            what=f"missing required argument '{missing}' for {name}",
            why="the handler tried to read this key from arguments but it was absent",
            next_action=(
                f"call sys_tool_describe(name='{name}') to see the input schema"
            ),
        ))
    except TypeError as te:
        msg = str(te)
        # Distinguish "unexpected keyword argument" / "missing required" / other
        if "unexpected keyword argument" in msg or "missing" in msg and "required" in msg:
            return _text(_error(
                what=f"argument shape mismatch in {name}",
                why=f"the handler rejected the arguments: {msg}",
                next_action=(
                    f"call sys_tool_describe(name='{name}') to confirm the input schema"
                ),
            ))
        logger.exception(f"Tool {name} failed")
        return _text(_error(
            what=f"{name} raised a TypeError",
            why=msg,
            next_action="check tool inputs against sys_tool_describe; report the trace if shape looks right",
        ))
    except FileNotFoundError as fe:
        return _text(_error(
            what=f"{name} could not find a required file",
            why=str(fe),
            next_action=(
                "verify the workspace path; for protocol-not-found errors, "
                "call sys_protocols_list for the current names"
            ),
        ))
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return _text(_error(
            what=f"{name} raised an unexpected exception",
            why=f"{type(e).__name__}: {e}",
            next_action="re-run with simpler arguments to isolate; report trace if reproducible",
        ))
