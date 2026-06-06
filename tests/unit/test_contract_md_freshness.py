"""Keep docs/CONTRACT.md fresh against the runtime surface it pins.

CONTRACT.md is part of the public API — clients pin a SemVer range
against the STABLE section. If the runtime grows a new public-tool
prefix or the researcher_config schema grows a new top-level section
and CONTRACT.md isn't updated, the contract silently drifts and
integrators get burned on the next MINOR bump.

This test catches the drift mechanically. Add the missing item to
CONTRACT.md (likely § A.1 or § A.3) and the test will pass.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _contract_text() -> str:
    path = _repo_root() / "docs" / "CONTRACT.md"
    assert path.exists(), f"docs/CONTRACT.md not found at {path}"
    return path.read_text(encoding="utf-8")


def _public_tool_prefixes() -> set[str]:
    """Return the set of public top-level tool prefixes from the live server."""
    from research_os import server as srv

    defs = srv.TOOL_DEFINITIONS
    # TOOL_DEFINITIONS is a dict keyed by tool name.
    names = list(defs.keys())
    assert names, "TOOL_DEFINITIONS is empty — server import broken"
    prefixes: set[str] = set()
    for n in names:
        head = n.split("_", 1)[0]
        if head in {"sys", "tool", "mem"}:
            prefixes.add(head)
    return prefixes


def _researcher_config_top_level_sections() -> set[str]:
    """Top-level keys in templates/researcher_config.yaml."""
    path = _repo_root() / "templates" / "researcher_config.yaml"
    assert path.exists(), f"researcher_config.yaml not found at {path}"
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        # A top-level key starts at column 0, ends with ':', is not a comment,
        # and is not a list marker. ruamel-style YAML.
        if not raw or raw.startswith("#") or raw.startswith(" "):
            continue
        if ":" not in raw:
            continue
        key = raw.split(":", 1)[0].strip()
        if not key or not key[0].isalpha():
            continue
        # Skip anything that looks like a flow / sequence indicator
        if any(ch in key for ch in "[]{}-"):
            continue
        keys.add(key)
    assert keys, "Failed to parse any top-level keys from researcher_config.yaml"
    return keys


def test_contract_mentions_every_public_tool_prefix() -> None:
    text = _contract_text()
    prefixes = _public_tool_prefixes()
    missing = sorted(p for p in prefixes if f"`{p}_" not in text and f"{p}_*" not in text)
    assert not missing, (
        f"docs/CONTRACT.md does not mention these public tool prefixes: {missing}. "
        "Add them to section A.1 (Public tool names + input schemas)."
    )


def test_contract_mentions_every_researcher_config_section() -> None:
    text = _contract_text()
    sections = _researcher_config_top_level_sections()
    # Allow either backticked field name or bare in a bulleted list.
    missing: list[str] = []
    for key in sections:
        if f"`{key}`" in text or f"* {key}" in text or f"  * {key}" in text:
            continue
        missing.append(key)
    missing.sort()
    assert not missing, (
        f"docs/CONTRACT.md does not mention these researcher_config top-level "
        f"sections: {missing}. Add them to section A.3."
    )


def test_contract_lists_intent_class_enum() -> None:
    """The intent_class enum is part of section A.5 — keep CONTRACT.md in sync."""
    text = _contract_text()
    # The ten v2 intent_class values, all of which must appear in CONTRACT.md.
    required = [
        "session", "discover", "plan", "execute", "synthesize",
        "audit_wrap", "methodology", "literature", "memory", "review",
    ]
    missing = [v for v in required if v not in text]
    assert not missing, (
        f"docs/CONTRACT.md is missing intent_class values: {missing}. "
        "Update section A.5 to match src/research_os/protocols/_router_index.yaml."
    )


def test_contract_has_all_four_required_sections() -> None:
    """The CONTRACT.md structure itself is contract: STABLE / MINOR / PATCH / OUT-OF-SCOPE."""
    text = _contract_text()
    required_headers = [
        "## A. STABLE",
        "## B. MINOR",
        "## C. PATCH",
        "## D. OUT-OF-SCOPE",
    ]
    missing = [h for h in required_headers if h not in text]
    assert not missing, (
        f"docs/CONTRACT.md is missing required section headers: {missing}. "
        "Don't restructure — the four-section layout is part of the contract."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
