"""3.2 PATH-container grouping — sys_path(operation='group').

Consolidating a run of steps into a descriptive ``<slug>_PATH_<k>/``
container must: move the step folders, keep every step discoverable
(list_paths / numbering / DAG), re-point absolute data symlinks, and
preserve continuous step numbering across the project.
"""
from __future__ import annotations

from pathlib import Path

from research_os.project_ops import (
    create_numbered_experiment,
    discover_step_dirs,
    resolve_step_dir,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.state.path import (
    finalize_path,
    group_paths,
    list_paths,
)


def _mk(tmp_path: Path) -> Path:
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    for slug in ("ingest", "clean", "model"):
        create_numbered_experiment(
            tmp_path, slug, enforce_predecessor_finalized=False,
        )
    return tmp_path


def test_group_moves_steps_into_container(tmp_path):
    root = _mk(tmp_path)
    ws = root / "workspace"
    res = group_paths("early_exploration", ["01_ingest", "02_clean"], root)
    assert res["status"] == "success"
    container = res["container"]
    assert container == "early_exploration_PATH_1"
    # Steps moved off the flat root, into the container.
    assert not (ws / "01_ingest").exists()
    assert (ws / container / "01_ingest").is_dir()
    assert (ws / container / "02_clean").is_dir()
    # The un-grouped step stays flat.
    assert (ws / "03_model").is_dir()


def test_grouped_steps_still_discoverable(tmp_path):
    root = _mk(tmp_path)
    group_paths("early_exploration", ["01_ingest", "02_clean"], root)
    found = {d.name for d in discover_step_dirs(root / "workspace")}
    assert found == {"01_ingest", "02_clean", "03_model"}
    # list_paths surfaces all three, tagging grouped ones with path_container.
    paths = {p["path_id"]: p for p in list_paths(root)["paths"]}
    assert set(paths) == {"01_ingest", "02_clean", "03_model"}
    assert paths["01_ingest"]["path_container"] == "early_exploration_PATH_1"
    assert "path_container" not in paths["03_model"]
    # resolve_step_dir finds a grouped step by id.
    rd = resolve_step_dir(root / "workspace", "02_clean")
    assert rd is not None and rd.parent.name == "early_exploration_PATH_1"


def test_group_repoints_symlinks(tmp_path):
    root = _mk(tmp_path)
    ws = root / "workspace"
    # 02_clean's past_step_input symlinks to 01_ingest's output. After
    # grouping BOTH, that intra-group link must still resolve.
    group_paths("early_exploration", ["01_ingest", "02_clean"], root)
    link = ws / "early_exploration_PATH_1" / "02_clean" / "data" / "past_step_input"
    assert link.is_symlink()
    assert link.resolve() == (
        ws / "early_exploration_PATH_1" / "01_ingest" / "data" / "next_step_output"
    ).resolve()


def test_numbering_stays_continuous_after_group(tmp_path):
    root = _mk(tmp_path)
    group_paths("early_exploration", ["01_ingest", "02_clean"], root)
    # The next step must be 04 — numbering spans grouped + flat steps and
    # never resets, so steps can be merged/moved without collisions.
    res = create_numbered_experiment(
        root, "followup", enforce_predecessor_finalized=False,
    )
    assert res["path_id"].startswith("04_")


def test_finalize_works_on_grouped_step(tmp_path):
    root = _mk(tmp_path)
    group_paths("early_exploration", ["01_ingest", "02_clean"], root)
    # conclusions for the grouped step, then finalize by id (resolves into
    # the container).
    step = root / "workspace" / "early_exploration_PATH_1" / "01_ingest"
    (step / "conclusions.md").write_text(
        "## Findings\n\n- grouped finding.\n\n## Decision\n\nPROCEED.\n"
    )
    res = finalize_path("01_ingest", root)
    assert res["status"] == "success"


def test_group_rejects_unknown_step(tmp_path):
    root = _mk(tmp_path)
    res = group_paths("x", ["99_nope"], root)
    assert res["status"] == "error"
