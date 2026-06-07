"""Every tool in TOOL_DEFINITIONS must have a 'short' field <= 120 chars.

Small models scan list_tools on every turn. Without a concise short field,
they fall back to scanning multi-sentence descriptions for every tool, which
wastes context and hurts routing accuracy. The 120-char cap matches the
small-model scan budget per tool.
"""
from __future__ import annotations

from research_os.server.tool_definitions import TOOL_DEFINITIONS


def test_every_tool_has_short_field():
    """Every entry in TOOL_DEFINITIONS must declare a 'short' field."""
    missing = sorted(name for name, td in TOOL_DEFINITIONS.items()
                     if "short" not in td)
    assert not missing, (
        f"{len(missing)} tool(s) missing 'short' field: {missing}"
    )


def test_short_field_is_nonempty_string():
    """The 'short' field must be a non-empty string."""
    bad = []
    for name, td in TOOL_DEFINITIONS.items():
        s = td.get("short")
        if not isinstance(s, str) or not s.strip():
            bad.append(name)
    assert not bad, f"{len(bad)} tool(s) have empty / non-string 'short': {bad}"


def test_short_field_within_length_budget():
    """'short' must be <= 120 chars (small-model scan budget per tool)."""
    too_long = sorted(
        (name, len(td["short"]))
        for name, td in TOOL_DEFINITIONS.items()
        if isinstance(td.get("short"), str) and len(td["short"]) > 120
    )
    assert not too_long, (
        f"{len(too_long)} tool(s) have 'short' > 120 chars: {too_long}"
    )
