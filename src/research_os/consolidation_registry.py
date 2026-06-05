"""Consolidation registry — v2.0.0 tool consolidation scaffold.

This module formalises the consolidation pattern that ``server.py`` has
been growing organically since v1.6.x (``tool_search``, ``tool_plan``,
``tool_ground`` …) into a single declarative registry.

Every entry binds:

* ``new_name`` — the consolidated tool name (e.g. ``tool_audit``).
* ``old_names`` — the legacy tool names that now route to ``new_name``.
* ``arg_transform`` — a callable ``(old_name, arguments) -> arguments``
  that injects the dispatch parameter(s) implied by the legacy name
  (e.g. ``tool_audit_evalue`` → inject ``scope='step', dimension='evalue'``).
* ``schema`` — the JSON Schema for the consolidated tool's input.
* ``handler`` — the consolidated dispatch callable. Optional at registry
  time; populated when ``server.py`` imports the registry and binds its
  real handler functions. The registry stores callables verbatim so unit
  tests can inject stubs.

The registry is intentionally append-only at runtime and the public
helper :func:`register_consolidated` is the single mutation point.

Why a separate module?
----------------------
``server.py`` is 7.4K lines and growing. Pulling the registry into its
own module lets Phase 9b's parallel agents append cluster entries
without serialising on server.py edits, and gives Phase 10 (TOOL_DEFINITIONS
refactor) a clean import target.

The orchestrator's brief specified ``src/research_os/server/consolidation_registry.py``;
we cannot create a ``server/`` subpackage without first moving the
existing ``server.py`` file, which is out of scope for Phase 9a. The
module is therefore a sibling of ``server.py``; the import path
(``research_os.consolidation_registry``) is the same length and the
intent (one canonical registry) is preserved.
"""

from __future__ import annotations

from typing import Any, Callable

# ---------------------------------------------------------------------------
# Type aliases — read these before scrolling down.
# ---------------------------------------------------------------------------

# Argument transform: takes (legacy_tool_name, arguments_dict) and returns
# the mutated arguments dict the consolidated handler expects. MUST be pure
# (no side effects, no I/O) and MUST `setdefault` (caller-supplied kwargs
# always win over the alias-injected default).
ArgTransform = Callable[[str, dict[str, Any]], dict[str, Any]]

# Handler: takes (arguments_dict, root_path) and returns the tool response.
# The exact return shape is whatever the consolidated tool produces — the
# registry doesn't constrain it; server.py wraps it in MCP TextContent.
ToolHandler = Callable[..., Any]


# ---------------------------------------------------------------------------
# Registry state.
# ---------------------------------------------------------------------------

# CONSOLIDATED_TOOLS: new_tool_name → consolidation spec.
# Phase 9a leaves this empty; Phase 9b agents populate one cluster each.
CONSOLIDATED_TOOLS: dict[str, dict[str, Any]] = {}

# REMOVED_TOOLS: tools fully removed in v2.0.0 (NOT aliased, NOT routed).
# Invariant: every entry MUST have been in ``_DEPRECATED_ALIASES`` for at
# least three MINOR releases (e.g. flagged in 1.8.x, still aliased through
# 1.9.x and 1.10.x, removable in 2.0.0). Maintained by Phase 9b agents +
# release-prep audit.
#
# Format: tool_name → user-facing error message pointing at the replacement.
# The dispatcher in server.py reads this dict in ``_REMOVED_TOOLS`` checks.
REMOVED_TOOLS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Helpers — the only intended way to mutate the registry.
# ---------------------------------------------------------------------------


def register_consolidated(
    new_name: str,
    old_names: list[str],
    arg_transform: ArgTransform,
    schema: dict[str, Any],
    handler: ToolHandler | None = None,
    *,
    overwrite: bool = False,
) -> None:
    """Register a consolidated tool + its legacy aliases.

    Wires:
      * ``CONSOLIDATED_TOOLS[new_name]`` — the spec.
      * Each name in ``old_names`` is bound as an alias that will, at
        dispatch time, run ``arg_transform(old_name, args)`` and forward
        to ``handler``.

    Parameters
    ----------
    new_name
        The new, consolidated tool name (e.g. ``"tool_audit"``).
    old_names
        Legacy tool names that should route to ``new_name``. May be empty
        for brand-new consolidated tools with no prior surface.
    arg_transform
        Callable invoked when a legacy name is called. MUST be pure and
        MUST use ``setdefault`` semantics so caller-supplied kwargs win.
    schema
        JSON Schema for the consolidated tool's input. Becomes the
        ``inputSchema`` on the TOOL_DEFINITIONS entry.
    handler
        Optional dispatch callable. Most Phase 9b agents will leave this
        ``None`` at registration time and let ``server.py`` bind the real
        handler when it imports the registry (avoids circular imports).
    overwrite
        If ``True``, replace an existing entry. Default ``False`` raises
        ``ValueError`` on collision — duplicate registration is almost
        always a bug.

    Raises
    ------
    ValueError
        If ``new_name`` is already registered and ``overwrite`` is False.
        If any name in ``old_names`` collides with an existing alias for
        a *different* consolidated tool (silent overrides hide bugs).
    """
    if not new_name or not isinstance(new_name, str):
        raise ValueError(f"new_name must be a non-empty str, got {new_name!r}")
    if not isinstance(old_names, list):
        raise ValueError(f"old_names must be a list, got {type(old_names).__name__}")
    if not callable(arg_transform):
        raise ValueError("arg_transform must be callable")
    if not isinstance(schema, dict):
        raise ValueError(f"schema must be a dict, got {type(schema).__name__}")
    if handler is not None and not callable(handler):
        raise ValueError("handler must be callable or None")

    if new_name in CONSOLIDATED_TOOLS and not overwrite:
        raise ValueError(
            f"tool {new_name!r} already registered; pass overwrite=True to replace"
        )

    # Collision check: any old_name already claimed by a DIFFERENT new_name?
    for old in old_names:
        for other_new, spec in CONSOLIDATED_TOOLS.items():
            if other_new == new_name:
                continue
            if old in spec.get("old_names", ()):
                raise ValueError(
                    f"alias {old!r} already routes to {other_new!r}; "
                    f"cannot also route to {new_name!r}"
                )

    CONSOLIDATED_TOOLS[new_name] = {
        "old_names": list(old_names),
        "arg_transform": arg_transform,
        "schema": schema,
        "handler": handler,
    }


def register_removed(tool_name: str, message: str) -> None:
    """Mark a tool as hard-removed in v2.0.0.

    Use ONLY for tools that have been deprecated for ≥3 MINOR cycles.
    See module docstring for the deprecation cadence rule.
    """
    if not tool_name or not isinstance(tool_name, str):
        raise ValueError(f"tool_name must be a non-empty str, got {tool_name!r}")
    if not message or not isinstance(message, str):
        raise ValueError("message must be a non-empty str")
    REMOVED_TOOLS[tool_name] = message


def bind_handler(new_name: str, handler: ToolHandler) -> None:
    """Late-bind the dispatch handler for a previously-registered tool.

    Phase 9b agents typically register the spec first (during module
    import) and then let ``server.py`` call this to bind the real
    handler after its own ``_handle_*`` functions are defined. Avoids
    circular imports.
    """
    if new_name not in CONSOLIDATED_TOOLS:
        raise ValueError(f"tool {new_name!r} not registered; cannot bind handler")
    if not callable(handler):
        raise ValueError("handler must be callable")
    CONSOLIDATED_TOOLS[new_name]["handler"] = handler


def resolve_alias(name: str) -> str | None:
    """Return the consolidated tool name for a legacy alias, or None.

    O(n_consolidated * n_aliases_per_cluster). Called once per tool
    invocation; the alias surface is small (<400) so a linear scan is
    fast enough and avoids maintaining a parallel reverse index that
    can drift out of sync with the registry.
    """
    for new_name, spec in CONSOLIDATED_TOOLS.items():
        if name in spec["old_names"]:
            return new_name
    return None


def apply_transform(old_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Apply the arg_transform for a legacy alias.

    Returns ``arguments`` unchanged if ``old_name`` is not an alias for
    any consolidated tool — lets the dispatcher call this unconditionally.
    """
    new_name = resolve_alias(old_name)
    if new_name is None:
        return arguments
    transform = CONSOLIDATED_TOOLS[new_name]["arg_transform"]
    return transform(old_name, arguments)


def all_aliases() -> dict[str, str]:
    """Flatten the registry into an old_name → new_name mapping.

    Convenience for server.py to merge into ``_ALIASES``. The returned
    dict is a fresh copy — mutating it does not affect the registry.
    """
    flat: dict[str, str] = {}
    for new_name, spec in CONSOLIDATED_TOOLS.items():
        for old in spec["old_names"]:
            flat[old] = new_name
    return flat


def consolidated_names() -> list[str]:
    """List of all registered consolidated tool names."""
    return list(CONSOLIDATED_TOOLS.keys())


def removed_names() -> list[str]:
    """List of all hard-removed tool names."""
    return list(REMOVED_TOOLS.keys())


__all__ = [
    "ArgTransform",
    "CONSOLIDATED_TOOLS",
    "REMOVED_TOOLS",
    "ToolHandler",
    "all_aliases",
    "apply_transform",
    "bind_handler",
    "consolidated_names",
    "register_consolidated",
    "register_removed",
    "removed_names",
    "resolve_alias",
]
