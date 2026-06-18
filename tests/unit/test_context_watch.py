"""3.2.2 — live context drop-zone detection + glossary nudge.

inputs/context/ (and per-step context/) is a free drop-zone the researcher
fills at any time. detect_new_context surfaces NEW/CHANGED files since the
last seen snapshot; the first scan establishes a baseline silently.
"""
from __future__ import annotations

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.state.context_watch import (
    detect_new_context,
    glossary_unfilled,
)


def test_first_scan_is_silent_baseline(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo", ide_flags=[], copy_agents=False)
    (tmp_path / "inputs" / "context" / "brief.md").write_text("project brief")
    res = detect_new_context(tmp_path, update_marker=True)
    assert res["first_scan"] is True
    assert res["new_files"] == [] and res["changed_files"] == []


def test_new_drop_detected_after_baseline(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo", ide_flags=[], copy_agents=False)
    (tmp_path / "inputs" / "context" / "brief.md").write_text("project brief")
    detect_new_context(tmp_path, update_marker=True)  # baseline
    # Researcher drops a paper mid-session.
    (tmp_path / "inputs" / "context" / "paper.txt").write_text("a dropped paper")
    res = detect_new_context(tmp_path, update_marker=True)
    assert "inputs/context/paper.txt" in res["new_files"]
    assert "context/" in res["hint"] and "READ them" in res["hint"]
    # Consumed: a second scan with no change reports nothing.
    res2 = detect_new_context(tmp_path, update_marker=True)
    assert res2["new_files"] == [] and res2["changed_files"] == []


def test_peek_does_not_consume(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo", ide_flags=[], copy_agents=False)
    detect_new_context(tmp_path, update_marker=True)  # baseline
    (tmp_path / "inputs" / "context" / "note.md").write_text("note")
    peek = detect_new_context(tmp_path, update_marker=False)
    assert "inputs/context/note.md" in peek["new_files"]
    # Still reported on the next (consuming) call because peek didn't mark it.
    consume = detect_new_context(tmp_path, update_marker=True)
    assert "inputs/context/note.md" in consume["new_files"]


def test_readme_seed_not_flagged(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo", ide_flags=[], copy_agents=False)
    detect_new_context(tmp_path, update_marker=True)
    (tmp_path / "inputs" / "context" / "README.md").write_text("# seed changed")
    res = detect_new_context(tmp_path, update_marker=True)
    assert res["new_files"] == [] and res["changed_files"] == []


def test_glossary_unfilled(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo", ide_flags=[], copy_agents=False)
    g = tmp_path / "docs" / "glossary.md"
    g.parent.mkdir(parents=True, exist_ok=True)
    g.write_text("# Glossary\n\n| Term | Definition | Source |\n|---|---|---|\n")
    assert glossary_unfilled(tmp_path) is True
    g.write_text(
        "# Glossary\n\n| Term | Definition | Source |\n|---|---|---|\n"
        "| DRFP | reaction fingerprint | Probst 2022 |\n"
    )
    assert glossary_unfilled(tmp_path) is False
