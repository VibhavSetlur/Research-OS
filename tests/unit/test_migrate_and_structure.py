"""Chaos→RO migration + structure integrity audit.

Covers the safety invariants (copy-only, never overwrite, verify) and the
structure checks. Uses real /tmp dirs via tmp_path.
"""
from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.state import migrate, structure_audit


def _messy_project(root: Path) -> Path:
    """Build a small messy source project."""
    src = root / "messy"
    src.mkdir()
    (src / "data.csv").write_text("a,b\n1,2\n")
    (src / "analysis.py").write_text("print('hi')\n")
    (src / "Untitled.ipynb").write_text("{}\n")
    (src / "notes.txt").write_text("some notes\n")
    (src / "requirements.txt").write_text("numpy\n")
    sub = src / "subdir"
    sub.mkdir()
    (sub / "more_data.csv").write_text("x\n1\n")
    # noise that must be skipped
    (src / ".git").mkdir()
    (src / ".git" / "config").write_text("[core]\n")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "x.pyc").write_text("junk")
    return src


# --- audit (read-only) -----------------------------------------------------

def test_audit_classifies_and_touches_nothing(tmp_path):
    src = _messy_project(tmp_path)
    res = migrate.audit_chaos(src)
    assert res["status"] == "success"
    cats = res["by_category"]
    assert cats.get("data") == 2          # data.csv + subdir/more_data.csv
    assert cats.get("code") == 1
    assert cats.get("notebook") == 1
    assert cats.get("environment") == 1
    # noise excluded
    assert all(".git" not in f["source"] for f in res["files"])
    assert all("__pycache__" not in f["source"] for f in res["files"])
    # source still fully intact
    assert (src / "data.csv").exists()


def test_plan_maps_to_ro_homes_and_flags_collisions(tmp_path):
    src = _messy_project(tmp_path)
    dest = tmp_path / "ro"
    plan = migrate.plan_migration(src, dest)
    assert plan["status"] == "success"
    homes = {m["target"] for m in plan["moves"]}
    assert any("inputs/raw_data" in h for h in homes)
    assert any("environment" in h for h in homes)
    # nested file keeps a parent prefix to avoid name clashes
    assert any("subdir__more_data.csv" in h for h in homes)
    assert plan["collisions"] == 0


# --- apply (copy-only, verified) ------------------------------------------

def test_apply_copies_and_leaves_source_intact(tmp_path):
    src = _messy_project(tmp_path)
    dest = tmp_path / "ro"
    res = migrate.apply_migration(src, dest)
    assert res["status"] == "success"
    assert res["copied"] >= 5
    assert res["failures"] == 0
    # destination has the data
    assert (dest / "inputs" / "raw_data" / "data.csv").exists()
    # SOURCE IS UNTOUCHED — the core safety contract
    assert (src / "data.csv").exists()
    assert (src / "analysis.py").exists()
    # manifest written
    assert (dest / ".os_state" / "migration_manifest.json").exists()


def test_apply_never_overwrites_existing_destination(tmp_path):
    src = _messy_project(tmp_path)
    dest = tmp_path / "ro"
    # pre-create a colliding destination with sentinel content
    target = dest / "inputs" / "raw_data" / "data.csv"
    target.parent.mkdir(parents=True)
    target.write_text("DO NOT OVERWRITE\n")
    res = migrate.apply_migration(src, dest)
    assert res["skipped"] >= 1
    # the existing file is preserved, not clobbered
    assert target.read_text() == "DO NOT OVERWRITE\n"


def test_audit_rejects_non_directory(tmp_path):
    res = migrate.audit_chaos(tmp_path / "does_not_exist")
    assert res["status"] == "error"


# --- structure integrity audit --------------------------------------------

def test_structure_audit_clean_project(tmp_path):
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Clean")
    res = structure_audit.audit_structure(tmp_path)
    assert res["status"] == "success"
    assert res["ok"] is True
    assert res["counts"]["block"] == 0


def test_structure_audit_flags_missing_core_dir(tmp_path):
    from research_os.project_ops import scaffold_minimal_workspace
    import shutil

    scaffold_minimal_workspace(tmp_path, "Broken")
    shutil.rmtree(tmp_path / "workspace")
    res = structure_audit.audit_structure(tmp_path)
    assert res["ok"] is False
    codes = {f["code"] for f in res["findings"]}
    assert "missing_core_dir" in codes


def test_structure_audit_flags_duplicate_step_number(tmp_path):
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Dups")
    ws = tmp_path / "workspace"
    (ws / "01_first").mkdir()
    (ws / "01_second").mkdir()
    res = structure_audit.audit_structure(tmp_path)
    codes = {f["code"] for f in res["findings"]}
    assert "duplicate_step_number" in codes
    assert res["ok"] is False


def test_structure_audit_warns_output_without_conclusions(tmp_path):
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "NoConcl")
    step = tmp_path / "workspace" / "01_step"
    out = step / "outputs"
    out.mkdir(parents=True)
    (out / "result.csv").write_text("x\n1\n")
    res = structure_audit.audit_structure(tmp_path)
    codes = {f["code"] for f in res["findings"]}
    assert "output_without_conclusions" in codes
