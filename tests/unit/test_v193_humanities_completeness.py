"""v1.9.3 — humanities pack support in step_completeness audit
(AUDIT-v1.9.2-003).

Before this fix, the step_completeness gate hard-required a PNG/SVG/JPG
focal figure per numbered step. Humanities projects produce markdown
apparatus criticus / transcriptions / citation chains, not figures.
This test verifies humanities-mode detection and that markdown artefacts
satisfy the focal-artefact requirement.
"""

from __future__ import annotations

import yaml


def _scaffold(tmp_path):
    (tmp_path / "inputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _make_step(root, step_id: str = "01_close_reading"):
    step = root / "workspace" / step_id
    step.mkdir(parents=True, exist_ok=True)
    # conclusions.md must exist + have non-stub Findings + Decision to keep the
    # focus on the focal-artefact rule.
    (step / "conclusions.md").write_text(
        "## Findings\n\nReal finding text with detail and substance here.\n\n"
        "## Decision\n\nProceed to apparatus draft.\n"
    )
    (step / "scripts").mkdir(exist_ok=True)
    (step / "scripts" / "collate.py").write_text("# tool stub\n")
    return step


def test_humanities_mode_accepts_apparatus_markdown(tmp_path):
    """A humanities project with apparatus.md should NOT trigger the
    no-figure blocker."""
    from research_os.tools.actions.audit.audit import _step_completeness

    root = _scaffold(tmp_path)
    (root / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "domain": "humanities",
    }))
    step = _make_step(root)
    edition = step / "edition"
    edition.mkdir(exist_ok=True)
    (edition / "apparatus.md").write_text("# Apparatus criticus\n\n"
                                          "Line 1: ω] reading α reading\n")

    res = _step_completeness(step, root)
    blockers = res.get("blockers", [])
    # The no-figure / no-focal-artefact blocker should not fire.
    no_focal = [b for b in blockers if "focal" in b.lower() or "figure" in b.lower()]
    assert not no_focal, f"unexpected focal-artefact blocker: {no_focal}"
    assert res.get("humanities_mode") is True
    assert res.get("humanities_artefacts"), "expected humanities artefacts to be listed"


def test_humanities_mode_still_blocks_when_no_artefact(tmp_path):
    """Humanities mode without ANY focal artefact (no figure, no apparatus)
    must still block — the gate is real, only the accepted artefact widens."""
    from research_os.tools.actions.audit.audit import _step_completeness

    root = _scaffold(tmp_path)
    (root / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "domain": "humanities",
    }))
    step = _make_step(root)

    res = _step_completeness(step, root)
    blockers = res.get("blockers", [])
    assert any("focal artefact" in b for b in blockers), (
        f"expected humanities focal-artefact blocker, got: {blockers}"
    )


def test_non_humanities_project_still_requires_figure(tmp_path):
    """A non-humanities project (no domain/pack marker) keeps the figure
    requirement — humanities mode is opt-in via config."""
    from research_os.tools.actions.audit.audit import _step_completeness

    root = _scaffold(tmp_path)
    # No researcher_config.yaml or domain marker — default empirical.
    step = _make_step(root, step_id="01_eda")

    res = _step_completeness(step, root)
    blockers = res.get("blockers", [])
    assert any("No figure produced" in b for b in blockers), (
        f"expected figure blocker, got: {blockers}"
    )


def test_humanities_detection_via_transcriptions_dir(tmp_path):
    """Filesystem fallback: a transcriptions/ subdir under workspace is
    enough to opt in to humanities mode."""
    from research_os.tools.actions.audit.audit import _is_humanities_project

    root = _scaffold(tmp_path)
    transcriptions = root / "workspace" / "01_step" / "transcriptions"
    transcriptions.mkdir(parents=True, exist_ok=True)
    assert _is_humanities_project(root) is True
