"""F-005: AI_GUIDE.md + TOOLS.md must mention every override_<gate> kwarg
that the server actually accepts.

The override path is a researcher-authorised quality-gate bypass.
Every bypass kwarg defined on the server.py side MUST be documented
in BOTH user-facing guides so the AI can find it before guessing.

This grep-asserts the inventory rather than parsing the JSON schema —
the docs need to mention the literal kwarg string ("override_foo"),
which is exactly what we grep server.py for.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_PY = REPO_ROOT / "src" / "research_os" / "server.py"
TOOLS_MD = REPO_ROOT / "docs" / "TOOLS.md"
AI_GUIDE_MD = REPO_ROOT / "docs" / "AI_GUIDE.md"

# Internal-only override identifiers that are part of the server's
# RESPONSE shape (not request kwargs). These do not need to appear in
# user-facing docs as call-site kwargs.
_RESPONSE_ONLY = {
    "override_applied",   # server emits in res dict to flag "we honoured it"
    "override_requested", # local var in handler
    "override_used",      # reliability event_type, not a kwarg
    "override_lit",       # local var alias for override_literature_gate
    "override_log",       # the log-file token (override_log.md)
}


def _override_kwargs_from_server() -> set[str]:
    """Return every override_<name> token used as a kwarg on server.py.

    Excludes response-shape / local-variable tokens that are not
    user-facing call-site kwargs.
    """
    src = SERVER_PY.read_text()
    # Match override_<lowercase_word> tokens.
    tokens = set(re.findall(r"override_[a-z_]+", src))
    return tokens - _RESPONSE_ONLY


def test_tools_md_mentions_every_override_kwarg():
    """docs/TOOLS.md must mention every override_<gate> kwarg."""
    kwargs = _override_kwargs_from_server()
    assert kwargs, "no override_* kwargs found in server.py — grep broke?"
    text = TOOLS_MD.read_text()
    missing = sorted(k for k in kwargs if k not in text)
    assert not missing, (
        f"docs/TOOLS.md is missing these override kwargs: {missing}. "
        "Add them to the 'Per-step audit overrides' section."
    )


def test_ai_guide_mentions_every_override_kwarg():
    """docs/AI_GUIDE.md must mention every override_<gate> kwarg."""
    kwargs = _override_kwargs_from_server()
    assert kwargs, "no override_* kwargs found in server.py — grep broke?"
    text = AI_GUIDE_MD.read_text()
    missing = sorted(k for k in kwargs if k not in text)
    assert not missing, (
        f"docs/AI_GUIDE.md is missing these override kwargs: {missing}. "
        "Add them to the 'When to override a gate' section."
    )


def test_override_rationale_documented_in_both_guides():
    """override_rationale + workspace/logs/override_log.md must appear in
    both guides (the requirement-and-log story is the spine of the
    whole subsystem)."""
    for doc in (TOOLS_MD, AI_GUIDE_MD):
        text = doc.read_text()
        assert "override_rationale" in text, (
            f"{doc.name} must mention override_rationale (mandatory companion kwarg)."
        )
        assert "workspace/logs/override_log.md" in text, (
            f"{doc.name} must reference workspace/logs/override_log.md "
            "(where every bypass is recorded)."
        )


def test_tools_md_has_per_step_audit_overrides_section():
    """The TOOLS.md catalog needs a discoverable section anchor."""
    text = TOOLS_MD.read_text()
    assert "## Per-step audit overrides" in text, (
        "docs/TOOLS.md must have a '## Per-step audit overrides' section "
        "so the AI can find the override kwarg table by name."
    )


def test_ai_guide_has_when_to_override_section():
    """AI_GUIDE.md needs a worked-examples section with a discoverable
    anchor."""
    text = AI_GUIDE_MD.read_text()
    assert "## When to override a gate" in text, (
        "docs/AI_GUIDE.md must have a '## When to override a gate' "
        "section with worked examples."
    )


def test_ai_guide_has_at_least_four_worked_examples():
    """The 'When to override a gate' section must carry the five
    canonical worked examples (data-engineering, literature unreachable,
    methodology pending, pre-publication final pass, researcher
    discretion). We assert >= 4 numbered subsections to leave room for
    natural rewording but catch wholesale deletions."""
    text = AI_GUIDE_MD.read_text()
    # Subsections under "When to override a gate" use H3 numbered headers.
    # We look for "### N." patterns after the section anchor.
    anchor = "## When to override a gate"
    idx = text.find(anchor)
    assert idx >= 0, "missing 'When to override a gate' section"
    # Slice the next ~12K chars (the section), look for ### N.
    section = text[idx:idx + 12000]
    numbered = re.findall(r"^### \d+\.", section, flags=re.MULTILINE)
    assert len(numbered) >= 4, (
        f"expected >= 4 numbered worked examples under "
        f"'When to override a gate', found {len(numbered)}"
    )
