"""sys_path(operation='rename') — meaningful step labels + symlink re-pointing."""
from __future__ import annotations

import os

from research_os.project_ops import create_numbered_experiment, scaffold_minimal_workspace
from research_os.tools.actions.state.path import _slugify_step_label, rename_path


def _project(tmp_path):
    root = tmp_path / "proj"
    scaffold_minimal_workspace(root, "Rename Test", ide_flags=["cursor"])
    return root


def test_slugify():
    assert _slugify_step_label("Baseline EDA!") == "baseline_eda"
    assert _slugify_step_label("  ") == "step"


def test_rename_keeps_number_and_repoints_downstream(tmp_path):
    root = _project(tmp_path)
    create_numbered_experiment(root, "old step", enforce_predecessor_finalized=False)
    # second step consumes the first via an absolute data/input symlink
    create_numbered_experiment(
        root, "next step", from_step="01_old_step",
        enforce_predecessor_finalized=False,
    )
    ws = root / "workspace"
    assert (ws / "01_old_step").is_dir()
    downstream_link = ws / "02_next_step" / "data" / "past_step_input"
    # Sanity: the downstream link targets the old step's output.
    assert downstream_link.is_symlink()
    assert "01_old_step" in os.readlink(downstream_link)

    res = rename_path("01_old_step", "Cleaned Baseline", root)
    assert res["status"] == "success"
    assert res["renamed_to"] == "01_cleaned_baseline"
    # Folder renamed, number preserved.
    assert not (ws / "01_old_step").exists()
    assert (ws / "01_cleaned_baseline").is_dir()
    # Downstream symlink re-pointed and still resolves.
    assert "01_cleaned_baseline" in os.readlink(downstream_link)
    assert downstream_link.resolve().exists()
    assert res["symlinks_repointed"] >= 1


def test_rename_does_not_clobber_prefix_sibling(tmp_path):
    root = _project(tmp_path)
    ws = root / "workspace"
    # Two steps whose names share a prefix: 01_eda vs 01_eda_extra.
    (ws / "01_eda" / "data" / "next_step_output").mkdir(parents=True)
    (ws / "01_eda_extra" / "data" / "next_step_output").mkdir(parents=True)
    # A downstream link points (absolutely) into the LONGER-named sibling.
    dlink = ws / "02_next" / "data"
    dlink.mkdir(parents=True)
    (dlink / "past_step_input").symlink_to((ws / "01_eda_extra" / "data" / "next_step_output").absolute())

    rename_path("01_eda", "cleaned", root)
    # The sibling's link must be untouched (prefix-match bug would clobber it).
    assert "01_eda_extra" in os.readlink(dlink / "past_step_input")
    assert (dlink / "past_step_input").resolve().exists()


def test_rename_rejects_dead_end(tmp_path):
    root = _project(tmp_path)
    (root / "workspace" / "01_x__DEAD_END").mkdir(parents=True)
    res = rename_path("01_x__DEAD_END", "y", root)
    assert res["status"] == "error" and "abandoned" in res["message"].lower()


def test_rename_rejects_unnumbered(tmp_path):
    root = _project(tmp_path)
    (root / "workspace" / "loose_dir").mkdir(parents=True)
    res = rename_path("loose_dir", "x", root)
    assert res["status"] == "error"


def test_rename_rejects_missing(tmp_path):
    root = _project(tmp_path)
    assert rename_path("99_nope", "x", root)["status"] == "error"


def test_rename_rejects_collision(tmp_path):
    root = _project(tmp_path)
    create_numbered_experiment(root, "alpha", enforce_predecessor_finalized=False)
    # Renaming to the same slug it already has is rejected.
    res = rename_path("01_alpha", "alpha", root)
    assert res["status"] == "error"
