"""Recurring meeting/event deliverables route into documented subfolders.

A researcher makes many posters/slides/updates over a project's life; the
``label`` arg keeps them from overwriting the flat synthesis/<kind> file and
documents each one (order in the chaos).
"""
from __future__ import annotations

from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.synthesis.scaffold import synthesis_scaffold


def test_labeled_deliverables_get_own_documented_folder(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    r1 = synthesis_scaffold(tmp_path, kind="poster", label="2026-06-lab-meeting", confirmed=True)
    assert r1["status"] == "success"
    assert r1["path"].endswith("synthesis/deliverables/2026-06-lab-meeting/poster.typ")
    # documented
    assert (tmp_path / "synthesis" / "deliverables" / "2026-06-lab-meeting" / "README.md").exists()


def test_labeled_deliverables_do_not_collide(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    a = synthesis_scaffold(tmp_path, kind="poster", label="lab-meeting-week1", confirmed=True)
    b = synthesis_scaffold(tmp_path, kind="poster", label="lab-meeting-week2", confirmed=True)
    assert a["path"] != b["path"]
    assert Path(a["path"]).exists() and Path(b["path"]).exists()


def test_canonical_paper_stays_flat(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    r = synthesis_scaffold(tmp_path, kind="paper", confirmed=True)
    assert r["path"].endswith("synthesis/paper.typ")
    assert "deliverables" not in r["path"]


def test_scratch_routes_to_synthesis_scratch(tmp_path):
    """Dashboards/slides iterate in synthesis/scratch/ (gitignored), not a step."""
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    r = synthesis_scaffold(tmp_path, kind="dashboard", scratch=True, confirmed=True)
    assert r["status"] == "success"
    assert r["path"].endswith("synthesis/scratch/dashboard.html")
    # never a numbered workspace step
    assert "workspace/0" not in r["path"]


def test_meeting_routes_to_dated_folder_with_readme(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    r = synthesis_scaffold(tmp_path, kind="slides", meeting="2026-06-29", confirmed=True)
    assert r["status"] == "success"
    assert r["path"].endswith("synthesis/meetings/2026-06-29/slides.typ")
    assert (tmp_path / "synthesis" / "meetings" / "2026-06-29" / "README.md").exists()


def test_meeting_label_is_slugified(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    r = synthesis_scaffold(tmp_path, kind="dashboard", meeting="Lab Meeting!! June 29", confirmed=True)
    assert r["path"].endswith("synthesis/meetings/lab-meeting-june-29/dashboard.html")


def test_scratch_takes_precedence_over_meeting(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    r = synthesis_scaffold(
        tmp_path, kind="poster", scratch=True, meeting="2026-06-29", confirmed=True
    )
    assert r["path"].endswith("synthesis/scratch/poster.typ")


def test_paper_ignores_scratch_and_meeting(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    r = synthesis_scaffold(tmp_path, kind="paper", scratch=True, meeting="2026-06-29", confirmed=True)
    assert r["path"].endswith("synthesis/paper.typ")

