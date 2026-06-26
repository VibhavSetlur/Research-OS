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
