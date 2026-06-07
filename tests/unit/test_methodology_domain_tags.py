"""Regression test: general-purpose methodology protocols must have scope_tags.domain = [any].

Closes FIX-17 from the v2.1.0 backlog. Twelve methodology protocols had spurious
biology/engineering/qualitative/humanities domain tags that biased the router
against qualitative + clinical + engineering users when those users asked for
field-agnostic methodology guidance (power analysis, preregistration, etc.).

These protocols are reasoning scaffolds that apply across every research domain;
their domain MUST stay as [any] so the router doesn't filter them out for
non-biology projects.
"""

from pathlib import Path

import pytest
import yaml

PROTOCOLS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "research_os"
    / "protocols"
    / "methodology"
)

# Protocols re-tagged as part of FIX-17. Each is a general-purpose
# methodological scaffold (no field-specific language in the body).
GENERAL_PURPOSE_METHODOLOGY_PROTOCOLS = [
    "bootstrapping_design",
    "causal_inference_deep",
    "multiple_comparisons",
    "power_analysis",
    "reproduction_attempt",
    "data_ethics_review",
    "data_management_plan",
    "methodology_selection",
    "pick_tool_stack",
    "preregistration",
    "mixed_language_orchestration",
]


@pytest.mark.parametrize("protocol_name", GENERAL_PURPOSE_METHODOLOGY_PROTOCOLS)
def test_methodology_protocol_domain_is_any(protocol_name: str) -> None:
    """Each named general-purpose methodology protocol has domain == [any]."""
    path = PROTOCOLS_DIR / f"{protocol_name}.yaml"
    assert path.exists(), f"Protocol file missing: {path}"

    with path.open() as f:
        data = yaml.safe_load(f)

    scope_tags = data.get("scope_tags", {})
    domain = scope_tags.get("domain")
    assert domain == ["any"], (
        f"{protocol_name}: expected scope_tags.domain == ['any'] "
        f"(general-purpose methodology scaffold), got {domain!r}. "
        f"See FIX-17 — these protocols must not be filtered out for "
        f"qualitative / clinical / engineering projects."
    )
