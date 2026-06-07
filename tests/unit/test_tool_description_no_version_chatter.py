"""Tool descriptions must not carry version-history chatter.

References to specific phase names ('Phase-4', 'Phase 10'), legacy version
markers ('as of v1.6'), or migration verbiage ('historically',
'consolidated from') confuse small models scanning descriptions for
capability — and they go stale the moment the codebase evolves.

This test fails CI if any tool's description or short includes the
forbidden tokens. The narrow exceptions (BAAI/bge-small-en-v1.5, etc.)
are model identifiers, NOT version chatter.
"""
from __future__ import annotations

import re

from research_os.server.tool_definitions import TOOL_DEFINITIONS

# Tokens that mark version-history chatter. Each pattern is a regex that
# matches the start of a chatter phrase — not generic version strings like
# "v1.5" embedded in a model name (those are checked separately below).
_FORBIDDEN_PATTERNS = [
    (re.compile(r"\bPhase[- ]?\d"), "Phase-N chatter"),
    (re.compile(r"\bin Phase[- ]?N\b", re.IGNORECASE), "'in Phase-N' chatter"),
    (re.compile(r"\bhistorically\b", re.IGNORECASE), "'historically' chatter"),
    (re.compile(r"\bconsolidated from\b", re.IGNORECASE),
     "'consolidated from' chatter"),
    (re.compile(r"\bas of v\d", re.IGNORECASE), "'as of vX' chatter"),
]

# Patterns that look like version chatter but are model / library identifiers.
# These are allowed to appear inside tool descriptions.
_MODEL_ID_ALLOWLIST = re.compile(
    r"(BAAI/bge-[a-z0-9.-]+|"  # embedding model id
    r"Reveal\.js v\d+|"  # vendored Reveal.js
    r"reveal v\d+)",
    re.IGNORECASE,
)


def _strip_allowed(text: str) -> str:
    """Remove model-id strings so they don't trigger the v1./v2. check."""
    return _MODEL_ID_ALLOWLIST.sub("", text)


def test_no_phase_chatter_in_descriptions():
    """No tool description or short may reference Phase-N / historically / etc."""
    offenders: dict[str, list[str]] = {}
    for name, td in TOOL_DEFINITIONS.items():
        for field in ("short", "description"):
            text = td.get(field, "")
            if not isinstance(text, str):
                continue
            for pat, label in _FORBIDDEN_PATTERNS:
                if pat.search(text):
                    offenders.setdefault(name, []).append(
                        f"{field}: {label}"
                    )
    assert not offenders, (
        f"{len(offenders)} tool(s) carry forbidden version chatter "
        f"in description/short. Replace with timeless capability statements: "
        f"{offenders}"
    )


def test_no_legacy_version_marker_in_descriptions():
    """Reject standalone 'v1.' / 'v2.' tokens outside model-id allowlist."""
    pat = re.compile(r"\bv[12]\.\b")
    offenders: dict[str, list[str]] = {}
    for name, td in TOOL_DEFINITIONS.items():
        for field in ("short", "description"):
            text = td.get(field, "")
            if not isinstance(text, str):
                continue
            stripped = _strip_allowed(text)
            if pat.search(stripped):
                offenders.setdefault(name, []).append(field)
    assert not offenders, (
        f"{len(offenders)} tool(s) reference legacy 'v1.' / 'v2.' tokens "
        f"outside the model-id allowlist: {offenders}"
    )
