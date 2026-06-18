"""3.2.4 — AGENTS.md is loaded into context every session, so it must stay
lean. It drifted to 372 lines by 3.2.3; the slim rewrite delegates deep
detail to `sys_help` topics. This guard keeps it from bloating back AND
verifies the safety-critical anchors never get dropped in the name of
brevity.
"""
from __future__ import annotations

from pathlib import Path


def _agents_md() -> Path:
    return Path(__file__).resolve().parents[2] / "templates" / "AGENTS.md"


def test_agents_md_stays_lean():
    text = _agents_md().read_text()
    n_lines = len(text.splitlines())
    # Budget with headroom over the slim rewrite (~160 lines). If a future
    # change pushes past this, move the new detail into a sys_help topic
    # instead of growing the always-loaded file.
    assert n_lines <= 200, (
        f"AGENTS.md is {n_lines} lines — it's loaded every session; keep it "
        "<=200. Move deep detail into a sys_help topic, not AGENTS.md."
    )


def test_agents_md_keeps_critical_anchors():
    """Slimming must never drop the must-know, always-on content."""
    text = _agents_md().read_text()
    required = [
        "sys_boot",                 # the session loop
        "tool_route",
        "## Hard rules",            # the safety rules header
        ".os_state",                # rule 1
        "invent citations",         # rule 2
        "Token economy",            # the efficiency contract
        "config_directives",        # the operating contract
        "sys_help",                 # the on-demand detail pointer
    ]
    missing = [r for r in required if r not in text]
    assert not missing, f"AGENTS.md dropped critical anchors: {missing}"
