"""3.2.1 — plan.md is a LIVING document.

The step's plan.md is written before the work AND must be reconciled
(plan-vs-actual) during/at the end of the step. finalize nudges the AI
when the "Progress & deviations from plan" section was never filled.
"""
from __future__ import annotations

from pathlib import Path

from research_os.project_ops import (
    create_numbered_experiment,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.state.path import finalize_path


def _step(tmp_path: Path) -> tuple[Path, str]:
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    sid = create_numbered_experiment(
        tmp_path, "eda", enforce_predecessor_finalized=False,
    )["path_id"]
    step = tmp_path / "workspace" / sid
    (step / "conclusions.md").write_text(
        "## Findings\n\n- a real finding.\n\n## Decision\n\nPROCEED.\n"
    )
    return step, sid


def test_plan_has_progress_section_on_creation(tmp_path):
    step, _ = _step(tmp_path)
    plan = (step / "plan.md").read_text()
    assert "## Progress & deviations from plan" in plan
    assert "LIVING plan" in plan


def test_finalize_nudges_when_plan_not_updated(tmp_path):
    step, sid = _step(tmp_path)
    # plan.md left as the unfilled seed.
    res = finalize_path(sid, tmp_path)
    assert any(
        "plan.md" in w and "Progress & deviations" in w
        for w in res.get("warnings", [])
    ), f"expected a plan.md reconcile nudge; got {res.get('warnings')}"


def test_finalize_quiet_when_plan_reconciled(tmp_path):
    step, sid = _step(tmp_path)
    plan = (step / "plan.md").read_text()
    plan = plan.replace(
        "## Progress & deviations from plan\n"
        "*(Update this AS YOU WORK and at finalize: what changed from the "
        "plan above and why (a method swap, a dropped sub-analysis, an "
        "added robustness check), so plan.md ends as a true record of the "
        "step. \"Went exactly to plan\" is a valid entry.)*",
        "## Progress & deviations from plan\nWent exactly to plan; no "
        "deviations. Swapped the default cutoff after the QC pass.",
    )
    (step / "plan.md").write_text(plan)
    res = finalize_path(sid, tmp_path)
    assert not any(
        "plan.md" in w and "Progress & deviations" in w
        for w in res.get("warnings", [])
    ), f"plan reconciled, but still nagged: {res.get('warnings')}"
