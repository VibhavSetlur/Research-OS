"""Stable adapter-author API.

Two surfaces:

1. `AdapterRegistration` — the dataclass every adapter's `register()`
   must return.
2. `register_adapter()` — convenience constructor + validator. Adapter
   authors can build the dataclass directly OR call this helper which
   compiles the tools_md regex patterns up-front and rejects malformed
   ones early.

`AdapterTool` mirrors `PackTool` from the plugin system: each tool is
captured as (name, handler, schema) and merged into core
`TOOL_DEFINITIONS` + `_HANDLERS` at startup.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ── canonical adapter envelope helpers ────────────────────────────────
# The envelope is the one thing every adapter MUST emit identically for
# the dispatcher. Historically the bundled adapters copy-pasted a byte-identical
# `_ok`/`_err` (~156 duplicated lines); these shared helpers are the single
# source of truth. Adapters keep thin local `_ok`/`_err` aliases for
# back-compat with any test that imports them directly.


def _envelope(payload: dict) -> list:
    text = json.dumps(payload, indent=2, default=str)
    try:
        from mcp.types import TextContent
        return [TextContent(type="text", text=text)]
    except ImportError:  # pragma: no cover
        class _Stub:
            def __init__(self, t: str) -> None:
                self.type, self.text = "text", t
        return [_Stub(text)]


def ok_envelope(data: dict) -> list:
    """Canonical adapter success envelope: ``[{status:success, data}]``."""
    return _envelope({"status": "success", "data": data})


def err_envelope(message: str) -> list:
    """Canonical adapter error envelope: ``[{status:error, error}]``."""
    return _envelope({"status": "error", "error": str(message)})


@dataclass(frozen=True)
class AdapterTool:
    """A single tool contributed by an adapter."""
    name: str
    handler: Callable[..., Any]
    schema: dict


@dataclass(frozen=True)
class AdapterRegistration:
    """Everything an adapter contributes to the core registries.

    Attributes
    ----------
    name : str
        Adapter name (lowercase, alphanumeric + underscores).
        Used as the provenance-file basename (`<adapter>.yaml`) and
        as the `tool_<adapter>_` namespace prefix.
    version : str
        Adapter version (semver).
    description : str
        One-line summary, shown in `sys_adapters_installed`.
    detect : callable
        `(root: Path) -> bool` — True if the project uses this infra.
        Must be fast (filesystem scans only; no network).
    extract : callable
        `(root: Path, step_id: str | None) -> dict` — reads the
        project state, returns a structured provenance dict. The
        runner serialises this to YAML at
        `workspace/<step>/provenance/<adapter>.yaml`.
    describe : callable | None
        `() -> dict` — returns adapter-specific config / capabilities.
        Defaults to `lambda: {"name": <name>, "version": <version>}`.
    tools_md_patterns : tuple[tuple[str, str], ...]
        Regex → human-template patterns to feed the tools.md extractor.
        Each entry is `(compiled_regex_source, template)` where template
        may reference capture groups via `{0}`, `{1}`, etc.
    tools : tuple[AdapterTool, ...]
        Optional tools to merge into core dispatcher.
    """
    name: str
    version: str
    description: str
    detect: Callable[[Path], bool]
    extract: Callable[..., dict]
    describe: Callable[[], dict] | None = None
    tools_md_patterns: tuple[tuple[str, str], ...] = ()
    tools: tuple[AdapterTool, ...] = field(default_factory=tuple)


_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")


def register_adapter(
    *,
    name: str,
    version: str,
    description: str,
    detect: Callable[[Path], bool],
    extract: Callable[..., dict],
    describe: Callable[[], dict] | None = None,
    tools_md_patterns: tuple[tuple[str, str], ...] = (),
    tools: tuple[AdapterTool, ...] = (),
) -> AdapterRegistration:
    """Validate + construct an AdapterRegistration in one call.

    Validation:
        * `name` is lowercase alphanumeric (underscores allowed).
        * `detect` + `extract` are callable.
        * Every `tools_md_patterns` regex compiles (raises early if not).
        * Every `tools` entry has a name starting with `tool_<adapter>_`.
    """
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(
            f"Adapter name must be lowercase alphanumeric (underscores ok); got {name!r}"
        )
    if not callable(detect):
        raise TypeError(f"Adapter '{name}' detect must be callable")
    if not callable(extract):
        raise TypeError(f"Adapter '{name}' extract must be callable")
    expected_prefix = f"tool_{name}_"
    for t in tools:
        if not t.name.startswith(expected_prefix):
            raise ValueError(
                f"Adapter '{name}' tool '{t.name}' must start with "
                f"'{expected_prefix}' (namespace convention)"
            )
    for pat_source, _ in tools_md_patterns:
        # The contract is (regex_source: str, template: str). Reject a
        # pre-compiled re.Pattern (or anything non-str) here so an adapter
        # can't smuggle one through on CPython's lenient re.compile(pattern)
        # behaviour and then break when a flag is added downstream.
        if not isinstance(pat_source, str):
            raise TypeError(
                f"Adapter '{name}' tools_md_patterns source must be a str "
                f"(use an inline flag like '(?i)…'); got {type(pat_source).__name__}"
            )
        # Compile up-front; surface bad regex at registration not at extract.
        re.compile(pat_source)
    return AdapterRegistration(
        name=name,
        version=version,
        description=description,
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=tools_md_patterns,
        tools=tuple(tools),
    )
