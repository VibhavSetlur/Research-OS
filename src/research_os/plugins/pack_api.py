"""Stable pack-author API.

Two surfaces:

1. `PackRegistration` — the dataclass every pack's `register()` must return.
2. `register_tool` — a decorator that pack modules use to capture tool
   metadata (name, schema, handler) in a module-level registry. The
   pack's `register()` function then pulls the captured tools via
   `captured_tools(<module>)` and includes them in the returned
   `PackRegistration`.

Why the decorator pattern? Pack authors should be able to define
tools inline alongside their handler functions without manually
maintaining a parallel mapping. The decorator gives them
ergonomic syntax while the loader merges everything into core
`TOOL_DEFINITIONS` + `_HANDLERS` at startup.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("research_os.plugins.pack_api")


@dataclass(frozen=True)
class PackTool:
    """A single tool contributed by a pack."""
    name: str
    handler: Callable[..., Any]
    schema: dict


@dataclass(frozen=True)
class PackRegistration:
    """Everything a pack contributes to the core registries.

    Attributes
    ----------
    name : str
        Pack name (lowercase, used as the namespace prefix). E.g. "humanities".
    version : str
        Pack version (semver).
    protocols_dir : Path
        Filesystem path to the pack's protocols/ directory. Each YAML in
        the tree is loaded with the pack name as the top-level category
        prefix (e.g. `<pack>/<category>/<name>`).
    tools : tuple[PackTool, ...]
        Tools to merge into core `TOOL_DEFINITIONS` + `_HANDLERS`. The
        loader will accept the name as-is — packs are responsible for
        prefixing with `tool_<pack>_` per convention.
    router_entries : dict[str, dict]
        Entries to merge into the core router-index `protocols:` section.
        Keys must be prefixed with the pack name (`<pack>/...`).
    domain_detector : callable | None
        Optional `(inputs_dir: Path) -> dict` returning
        `{"pack": <name>, "confidence": float, "signals": [...]}`.
        Called by `tool_intake_autofill` when domain is ambiguous.
    description : str
        One-line human-readable summary, shown in `sys_packs_installed`.
    paper_sections : tuple[str, ...]
        Optional ordered tuple of section IDs declaring the pack's
        preferred paper schema. When empty (the default), the synthesis
        pipeline falls back to the IMRAD section order
        (abstract → introduction → methods → results → discussion →
        references). A pack like `theory_math` whose deliverable is a
        proof-shaped paper can declare e.g. ``("introduction",
        "preliminaries", "main_theorems", "proofs", "discussion")`` so
        `tool_synthesize` stops forcing IMRAD on it.
    """
    name: str
    version: str
    protocols_dir: Path
    tools: tuple[PackTool, ...] = ()
    router_entries: dict = field(default_factory=dict)
    domain_detector: Callable[[Path], dict] | None = None
    description: str = ""
    paper_sections: tuple[str, ...] = ()


# ── @register_tool decorator + module-level capture ───────────────────


# Keyed by module __name__; each value is a list of PackTool.
_TOOL_REGISTRY: dict[str, list[PackTool]] = {}


def register_tool(name: str, *, schema: dict, description: str = ""):
    """Decorator: capture this handler as a pack tool.

    Usage in a pack module::

        from research_os.plugins import register_tool

        @register_tool(
            "tool_humanities_archive_lookup",
            schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            description="Query Internet Archive / HathiTrust / DPLA / Europeana.",
        )
        def archive_lookup(name, arguments, root):
            ...

    Then in the pack's ``register()`` function::

        from research_os.plugins import PackRegistration, captured_tools
        from research_os_humanities import tools as humanities_tools

        def register() -> PackRegistration:
            return PackRegistration(
                name="humanities",
                ...,
                tools=captured_tools(humanities_tools.__name__),
                ...,
            )
    """
    def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        module_name = fn.__module__
        merged_schema = dict(schema)
        if description:
            merged_schema.setdefault("description", description)
            merged_schema.setdefault("short", description[:120])
        _TOOL_REGISTRY.setdefault(module_name, []).append(
            PackTool(name=name, handler=fn, schema=merged_schema)
        )
        return fn
    return _decorator


def captured_tools(module_name: str) -> tuple[PackTool, ...]:
    """Return all tools captured by @register_tool in the named module.

    Order is registration order (decorator evaluation order).
    """
    return tuple(_TOOL_REGISTRY.get(module_name, ()))


def reset_captured_tools(module_name: str | None = None) -> None:
    """Test helper: drop captured tools for a module (or all modules)."""
    if module_name is None:
        _TOOL_REGISTRY.clear()
        return
    _TOOL_REGISTRY.pop(module_name, None)
