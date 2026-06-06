"""Phase 8 — tool_route populates the ``tier`` field from the matched protocol.

The tier is read from the YAML's top-level ``tier:`` key (written by
``scripts/backfill_tiers.py``); when the key is absent the router falls
back on ``infer_tier`` over the router-index metadata so pack protocols
don't break the pipeline.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from research_os.project_ops import scaffold_minimal_workspace
from research_os.protocols._tiers import TIERS, infer_tier
from research_os.tools.actions.router import _resolve_tier, route_request


def _scaffold(tmp_path: Path) -> Path:
    scaffold_minimal_workspace(tmp_path, "Tier Test")
    return tmp_path


def test_every_protocol_has_a_valid_tier_field():
    """Every shipped YAML must carry a top-level ``tier:`` field."""
    protocols_dir = Path(__file__).resolve().parents[2] / "src" / "research_os" / "protocols"
    bad: list[tuple[Path, str]] = []
    for f in protocols_dir.rglob("*.yaml"):
        if f.name.startswith("_"):
            continue
        data = yaml.safe_load(f.read_text()) or {}
        tier = data.get("tier")
        if tier not in TIERS:
            bad.append((f, repr(tier)))
    assert not bad, "protocols missing valid tier field: " + ", ".join(
        f"{p.name} ({t})" for p, t in bad[:10]
    )


def test_resolve_tier_reads_from_yaml():
    """``_resolve_tier`` returns the YAML's ``tier:`` value verbatim."""
    # Pick a protocol we know exists.
    tier = _resolve_tier("writing/writing_methods")
    assert tier in TIERS
    # Reading again hits the cache; result is stable.
    assert _resolve_tier("writing/writing_methods") == tier


def test_resolve_tier_for_unknown_protocol_returns_fallback_or_none():
    """Unknown ids fall back to ``infer_tier``; null/blank stay None."""
    # The infer fallback returns 'plan' for an unknown id with no
    # metadata — keeps the caller safe (always a valid tier when one
    # is returned) without misclaiming a real match.
    fallback = _resolve_tier("nonexistent/never_made")
    assert fallback in TIERS
    assert _resolve_tier(None) is None
    assert _resolve_tier("") is None


def test_route_response_has_valid_tier(tmp_path):
    """``tool_route`` populates the tier field on every match."""
    root = _scaffold(tmp_path)
    res = route_request("fill the intake", root, persist_plan=False)
    assert res["status"] == "success"
    assert res["tier"] in TIERS, res


def test_route_intake_prompt_lands_at_intake_tier(tmp_path):
    """Routing an intake-ish prompt resolves to the intake tier."""
    root = _scaffold(tmp_path)
    res = route_request(
        "i'm bringing in new raw data, fill the intake", root, persist_plan=False
    )
    assert res["tier"] == "intake", res


def test_route_synthesize_prompt_lands_at_synthesize_tier(tmp_path):
    """A draft-the-paper prompt resolves to the synthesize tier."""
    root = _scaffold(tmp_path)
    res = route_request("draft the paper", root, persist_plan=False)
    assert res["tier"] == "synthesize", res


def test_route_pure_shortcut_response_has_no_tier(tmp_path):
    """When a shortcut wins outright (no L1 protocol scored) tier is None."""
    from research_os.tools.actions.router import _shortcut_response

    root = _scaffold(tmp_path)
    fake_shortcut = {
        "intent_id": "progress_check",
        "tool": "tool_progress_digest",
        "matched": ["progress"],
        "score": 4,
    }
    res = _shortcut_response(
        fake_shortcut, root, "progress", is_complex=False, persist_plan=False,
    )
    assert res["status"] == "success"
    assert res["tier"] is None


def test_route_fallback_response_has_no_tier(tmp_path):
    """Unmatched prompts surface tier=None."""
    root = _scaffold(tmp_path)
    res = route_request("xyzzy plugh frobnicate", root, persist_plan=False)
    assert res["status"] == "success"
    assert res["tier"] is None


def test_infer_tier_falls_back_to_category():
    """The inference helper covers protocols missing intent_class."""
    # No (intent_class, sub_intent) provided — falls back on category.
    assert infer_tier(category="writing") == "synthesize"
    assert infer_tier(category="audit") == "review"
    # Truly unknown — last-resort 'plan'.
    assert infer_tier() == "plan"
