"""Whole-project hygiene watch — the daemon watches beyond the step spine.

Covers project_hygiene_findings (governance / communication / docs / literature
/ per-step context / per-step environment) and confirms the signals reach the
shared structure_audit engine. All by-shape, fail-open, mostly info/warn —
Research-OS is a guidance system, so these nudge rather than block.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.state.project_hygiene import project_hygiene_findings
from research_os.tools.actions.state.structure_audit import audit_structure


def _proj() -> Path:
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode="analysis")
    return root


def _codes(findings):
    return [f.get("code") for f in findings]


def _make_step(root: Path, name: str, *, conclusions: bool = True,
               scripts: bool = False, outputs: bool = False,
               env: bool = False, literature: bool = False,
               context: bool = False) -> Path:
    step = root / "workspace" / name
    step.mkdir(parents=True, exist_ok=True)
    if conclusions:
        (step / "conclusions.md").write_text(
            "# Conclusions\n\n## Findings\nReal finding: mean = 0.94, n = 46133.\n"
            "## Decision\nproceed\n"
        )
    if scripts:
        sd = step / "scripts"
        sd.mkdir(exist_ok=True)
        (sd / f"{name.split('_')[0]}a_run_v1.py").write_text("print('x')\n")
    if outputs:
        od = step / "outputs" / "tables"
        od.mkdir(parents=True, exist_ok=True)
        (od / "result.csv").write_text("a,b\n1,2\n")
    if env:
        ed = step / "environment"
        ed.mkdir(exist_ok=True)
        (ed / "requirements.txt").write_text("pandas==2.0\n")
    if literature:
        ld = step / "literature"
        ld.mkdir(exist_ok=True)
        (ld / "paper.pdf").write_bytes(b"%PDF-1.4 fake")
    if context:
        (step / "context").mkdir(exist_ok=True)
    return step


# --------------------------------------------------------------------------
# Per-step environment snapshot
# --------------------------------------------------------------------------


def test_flags_step_that_ran_scripts_without_env_snapshot():
    root = _proj()
    _make_step(root, "01_canon", scripts=True, outputs=True, env=False)
    assert "step_no_env_snapshot" in _codes(project_hygiene_findings(root))


def test_no_env_flag_when_step_has_per_step_snapshot():
    root = _proj()
    _make_step(root, "01_canon", scripts=True, outputs=True, env=True)
    assert "step_no_env_snapshot" not in _codes(project_hygiene_findings(root))


def test_no_env_flag_when_step_ran_no_scripts():
    root = _proj()
    _make_step(root, "01_canon", scripts=False, outputs=False, env=False)
    assert "step_no_env_snapshot" not in _codes(project_hygiene_findings(root))


# --------------------------------------------------------------------------
# Literature: mid-step grounding + root corpus keeping pace
# --------------------------------------------------------------------------


def test_flags_step_with_conclusions_but_no_literature_and_no_inputs_corpus():
    root = _proj()
    _make_step(root, "01_canon", literature=False)
    assert "step_ungrounded_no_literature" in _codes(project_hygiene_findings(root))


def test_no_ungrounded_flag_when_step_opts_out_via_summary():
    root = _proj()
    step = _make_step(root, "01_canon", literature=False)
    (step / "step_summary.yaml").write_text("literature_required: false\n")
    assert "step_ungrounded_no_literature" not in _codes(
        project_hygiene_findings(root))


def test_flags_root_corpus_behind_step_literature():
    root = _proj()
    _make_step(root, "01_canon", literature=True)
    # The step has a paper but the root corpus/steps/01_canon has none → behind.
    assert "literature_corpus_behind" in _codes(project_hygiene_findings(root))


def test_root_corpus_not_behind_when_mirrored():
    root = _proj()
    _make_step(root, "01_canon", literature=True)
    mirrored = root / "literature" / "steps" / "01_canon"
    mirrored.mkdir(parents=True, exist_ok=True)
    (mirrored / "paper.pdf").write_bytes(b"%PDF-1.4 fake")
    assert "literature_corpus_behind" not in _codes(project_hygiene_findings(root))


# --------------------------------------------------------------------------
# Per-step context drop-zone
# --------------------------------------------------------------------------


def test_flags_missing_step_context_when_project_uses_context():
    root = _proj()
    # Project actively uses context (a file dropped in inputs/context).
    ctx = root / "inputs" / "context"
    ctx.mkdir(parents=True, exist_ok=True)
    (ctx / "brief.md").write_text("a PI note\n")
    _make_step(root, "01_canon", context=False)
    assert "step_context_dir_missing" in _codes(project_hygiene_findings(root))


def test_no_step_context_flag_when_project_does_not_use_context():
    root = _proj()
    _make_step(root, "01_canon", context=False)
    assert "step_context_dir_missing" not in _codes(project_hygiene_findings(root))


# --------------------------------------------------------------------------
# Governance: DECISIONS / STATE / GETTING_STARTED
# --------------------------------------------------------------------------


def test_flags_decisions_not_logged_after_multiple_started_steps():
    root = _proj()
    (root / "DECISIONS.md").write_text(
        "# Decisions\n\n## ADR-001 — initial setup\nfoo\n")
    _make_step(root, "01_a")
    _make_step(root, "02_b")
    assert "decisions_not_logged" in _codes(project_hygiene_findings(root))


def test_flags_stale_state_md():
    root = _proj()
    (root / "STATE.md").write_text("# State\nold\n")
    # Force STATE.md to be old, then make step work newer than it + grace.
    old = time.time() - 7200
    import os
    os.utime(root / "STATE.md", (old, old))
    _make_step(root, "01_a")
    assert "state_md_stale" in _codes(project_hygiene_findings(root))


# --------------------------------------------------------------------------
# Wiring + fail-open
# --------------------------------------------------------------------------


def test_structure_audit_surfaces_project_hygiene():
    root = _proj()
    _make_step(root, "01_canon", scripts=True, outputs=True, env=False)
    codes = _codes(audit_structure(root)["findings"])
    assert "step_no_env_snapshot" in codes


def test_fail_open_on_missing_root():
    root = Path(tempfile.mkdtemp()) / "nope"
    assert project_hygiene_findings(root) == []


def test_hygiene_findings_never_block():
    # Guidance system: hygiene findings are info/warn, never block.
    root = _proj()
    _make_step(root, "01_canon", scripts=True, outputs=True)
    for f in project_hygiene_findings(root):
        assert f["severity"] in ("info", "warn")
