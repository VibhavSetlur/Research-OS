"""Multi-root supervision: PI roll-up across projects (run_self_check_all)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.daemon.health_notes import run_self_check_all


def _proj(mode: str) -> Path:
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode=mode)
    return root


def test_rollup_aggregates_multiple_projects():
    roots = [str(_proj("notebook")), str(_proj("multi_study"))]
    agg = run_self_check_all(roots)
    assert len(agg["projects"]) == 2
    assert set(agg["totals"]) == {"block", "warn", "info"}
    assert "needs_attention" in agg


def test_rollup_flags_needs_attention_on_warn():
    # tool_build with empty eval/ produces a WARN → should appear in needs_attention.
    tb = _proj("tool_build")
    agg = run_self_check_all([str(tb)])
    proj = agg["projects"][str(tb)]
    assert proj["counts"].get("warn", 0) >= 1
    assert str(tb) in agg["needs_attention"]
    assert proj["worst"]  # worst findings surfaced for the PI


def test_rollup_fail_open_on_bad_root():
    # A nonexistent root must not raise — it's handled gracefully (the
    # aggregate still returns a well-formed payload).
    agg = run_self_check_all(["/nonexistent/path/xyz"])
    assert "projects" in agg and "totals" in agg
    assert agg["totals"]["block"] == 0  # no crash, no false block


def test_rollup_empty_roots():
    agg = run_self_check_all([])
    assert agg["projects"] == {}
    assert agg["needs_attention"] == []
