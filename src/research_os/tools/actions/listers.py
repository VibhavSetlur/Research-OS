"""Flat protocol + tool listers for routing UX.

Two public surfaces:

* ``list_protocols_flat`` — re-exported from
  ``research_os.tools.actions.protocol`` for module-locality;
  re-exposed here so callers can ``from research_os.tools.actions.listers
  import list_protocols_flat`` without crossing into the protocol
  loader.

* ``list_tools_flat`` — flat catalog of every registered MCP tool.
  Built at call time from ``TOOL_DEFINITIONS`` and the alias / deprecation
  registries in ``server.py``. The output drops the verbose per-tool
  description in favour of a short ``summary_first_line``; the AI can
  fetch the full description via ``sys_tool_describe`` when it actually
  needs it.

Both listers are read-only and side-effect free; safe to call from any
handler or test.
"""
from __future__ import annotations

from typing import Any

from research_os.tools.actions.protocol import (  # noqa: F401  — re-export
    list_protocols_flat,
)


# ---------------------------------------------------------------------------
# tool catalog
# ---------------------------------------------------------------------------


def _first_line(text: str, limit: int = 200) -> str:
    """Return the first line of ``text``, hard-capped at ``limit`` chars."""
    if not text:
        return ""
    first = str(text).strip().split("\n", 1)[0].strip()
    if len(first) > limit:
        first = first[: limit - 1].rstrip() + "…"
    return first


def _input_required_fields(schema: dict | None) -> list[str]:
    """Pull the ``required`` list out of a tool input schema."""
    if not isinstance(schema, dict):
        return []
    req = schema.get("required")
    if isinstance(req, list):
        return [str(x) for x in req]
    return []


def _scope_for_tool(
    tool_name: str,
    tool_def: dict[str, Any],
    pack_names: set[str],
) -> str:
    """Classify a tool by namespace.

    * Pack tools follow the ``tool_<pack>_*`` convention (enforced by
      the loader). When the second underscore-separated segment matches
      a registered pack name, return that pack name.
    * Everything else is ``core``.
    """
    # Pack tool name convention is `tool_<pack>_*` — pluck the segment.
    if tool_name.startswith("tool_"):
        rest = tool_name[len("tool_"):]
        # Try longest pack name first (handles e.g. `theory_math`).
        for pack in sorted(pack_names, key=len, reverse=True):
            if rest.startswith(f"{pack}_"):
                return pack
    # Pack-supplied category is set to the pack name by the loader; use
    # it as a fallback when name-matching missed.
    cat = (tool_def or {}).get("category")
    if isinstance(cat, str) and cat in pack_names:
        return cat
    return "core"


def list_tools_flat(
    tool_definitions: dict[str, dict[str, Any]],
    aliases: dict[str, str] | None = None,
    deprecated_aliases: set[str] | None = None,
    *,
    scope: str = "all",
    include_deprecated: bool = False,
    match_substring: str | None = None,
    pack_names: set[str] | None = None,
) -> list[dict]:
    """Flat tool catalog.

    Each entry::

        {
          "name": "tool_route",
          "scope": "core",                       # or pack name
          "summary_first_line": "Prompt → protocol + decomposition.",
          "input_schema_required_fields": ["prompt"],
          "deprecated": False,
          "alias_of": None,
        }

    Args:
      tool_definitions:    The live ``TOOL_DEFINITIONS`` map from
                           ``server.py``.
      aliases:             ``_ALIASES`` map. Optional; aliases NOT in
                           ``deprecated_aliases`` are surfaced as
                           secondary entries with ``alias_of`` set, so
                           the catalog is complete from a caller's view.
      deprecated_aliases:  ``_DEPRECATED_ALIASES`` set.
      scope:    ``"all"`` | ``"core"`` | a pack name. Default ``"all"``.
      include_deprecated:  When ``True``, include alias entries flagged
                           as deprecated. Default ``False`` — most
                           callers want the canonical surface.
      match_substring:     When set, restrict to tools whose
                           ``name`` OR ``summary_first_line`` contains
                           the lowercased substring.
      pack_names:          Optional set of pack names. When omitted,
                           the function looks up live pack registrations.
    """
    aliases = aliases or {}
    deprecated_aliases = deprecated_aliases or set()

    if pack_names is None:
        try:
            from research_os.plugins.loader import pack_protocol_dirs
            pack_names = set(pack_protocol_dirs().keys())
        except Exception:
            pack_names = set()

    needle = match_substring.lower().strip() if isinstance(match_substring, str) and match_substring.strip() else None

    out: list[dict] = []

    # 1) Canonical tools. A few legacy names persist in TOOL_DEFINITIONS
    # AND in _DEPRECATED_ALIASES — flag those as deprecated so callers
    # can hide them with include_deprecated=False.
    emitted: set[str] = set()
    for name, defn in sorted(tool_definitions.items()):
        defn = defn or {}
        is_deprecated_self = name in deprecated_aliases
        alias_target = aliases.get(name) if is_deprecated_self else None
        if is_deprecated_self and not include_deprecated:
            continue
        tool_scope = _scope_for_tool(name, defn, pack_names)
        if scope != "all" and tool_scope != scope:
            continue
        summary = _first_line(defn.get("short") or defn.get("description") or "")
        if needle and needle not in name.lower() and needle not in summary.lower():
            continue
        out.append({
            "name": name,
            "scope": tool_scope,
            "summary_first_line": summary,
            "input_schema_required_fields": _input_required_fields(
                defn.get("inputSchema")
            ),
            "deprecated": is_deprecated_self,
            "alias_of": alias_target if alias_target and alias_target != name else None,
        })
        emitted.add(name)

    # 2) Aliases that AREN'T already in TOOL_DEFINITIONS (nickname-only
    # entries, e.g. ``view_workspace_tree`` → ``sys_workspace_tree``).
    # Skip aliases that point at a missing target — they'd be dead
    # lookups for the AI.
    for alias_name, target in sorted(aliases.items()):
        if alias_name == target:
            continue
        if alias_name in emitted:
            # Already covered by the canonical pass above.
            continue
        is_deprecated = alias_name in deprecated_aliases
        if is_deprecated and not include_deprecated:
            continue
        target_def = tool_definitions.get(target) or {}
        if not target_def:
            continue
        tool_scope = _scope_for_tool(target, target_def, pack_names)
        if scope != "all" and tool_scope != scope:
            continue
        summary = _first_line(target_def.get("short") or target_def.get("description") or "")
        if needle and needle not in alias_name.lower() and needle not in summary.lower():
            continue
        out.append({
            "name": alias_name,
            "scope": tool_scope,
            "summary_first_line": summary,
            "input_schema_required_fields": _input_required_fields(
                target_def.get("inputSchema")
            ),
            "deprecated": is_deprecated,
            "alias_of": target,
        })

    out.sort(key=lambda e: (e["scope"], e["name"]))
    return out
