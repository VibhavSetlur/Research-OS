"""3.2.2 — the workflow mermaid is a real data-dependency DAG.

The old generator hung every step off a synthetic `init` node with no
real edges (the reaction-similarity project shipped exactly that). The
rich builder derives edges from data symlinks / sequential fallback,
labels nodes with status + a one-line purpose, and styles dead-ends.
"""
from __future__ import annotations

from pathlib import Path

from research_os.project_ops import (
    _build_workflow_mermaid,
    create_numbered_experiment,
    scaffold_minimal_workspace,
)


def _fill(step_dir: Path, goal: str) -> None:
    (step_dir / "README.md").write_text(
        f"# E\n## Goal\n{goal}\n## In plain English\nx\n## Input data\n- d\n"
        "## Methods (one line each)\n- m\n## Headline finding\n- h\n"
        "## Decision\n- proceed\n"
    )
    (step_dir / "conclusions.md").write_text("## Findings\n- f\n## Decision\nPROCEED\n")
    (step_dir / "plan.md").write_text(
        "## Where we are\na\n## What this step will do\nb\n"
        "## Why this step, why now\nc\n## Open questions for the researcher\nd\n"
        "## Progress & deviations from plan\ne\n## Anticipated next steps\nf\n"
    )


def test_mermaid_is_real_dag_not_init_fanout(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo", ide_flags=[], copy_agents=False)
    s1 = create_numbered_experiment(
        tmp_path, "biochem intake", enforce_predecessor_finalized=False
    )["path_id"]
    _fill(tmp_path / "workspace" / s1, "Profile the molecules table for QC")
    s2 = create_numbered_experiment(
        tmp_path, "profiling", enforce_predecessor_finalized=True
    )["path_id"]
    _fill(tmp_path / "workspace" / s2, "Characterize similarity")

    mer = _build_workflow_mermaid(tmp_path)
    # No synthetic init fan-out.
    assert "init -->" not in mer
    assert "init[" not in mer
    # Real sequential edge between the two steps.
    assert f"{s1.replace('-', '_')} --> {s2.replace('-', '_')}" in mer
    # Raw-data source node + ingest edge for the first step.
    assert "inputs/raw_data" in mer and f"raw --> {s1}" in mer
    # Purpose label is surfaced.
    assert "Profile the molecules table for QC" in mer
    # Status classes present.
    assert "classDef completed" in mer and "classDef dead_end" in mer


def test_mermaid_empty_project_is_safe(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo", ide_flags=[], copy_agents=False)
    mer = _build_workflow_mermaid(tmp_path)
    assert mer.startswith("graph TD")
    assert "No analysis steps yet" in mer


def test_hybrid_software_component_in_dag(tmp_path):
    """3.2.2 hybrid: an inner software component (build manifest / .git)
    appears in the DAG with an 'informs' edge from the latest step."""
    from research_os.project_ops import detect_software_components

    scaffold_minimal_workspace(tmp_path, "Hybrid", ide_flags=[], copy_agents=False)
    (tmp_path / "KBUtilLib").mkdir()
    (tmp_path / "KBUtilLib" / "pyproject.toml").write_text("[project]\nname='k'\n")
    s1 = create_numbered_experiment(
        tmp_path, "method spec", enforce_predecessor_finalized=False
    )["path_id"]
    _fill(tmp_path / "workspace" / s1, "Spec the clustering method")

    comps = detect_software_components(tmp_path)
    assert any(c["name"] == "KBUtilLib" and c["kind"] == "python" for c in comps)
    # RO scaffold dirs are never flagged as software.
    names = {c["name"] for c in comps}
    assert "workspace" not in names and "inputs" not in names and "docs" not in names

    mer = _build_workflow_mermaid(tmp_path)
    assert 'subgraph software_component["Software"]' in mer
    assert "KBUtilLib" in mer
    assert f"{s1.replace('-', '_')} -. informs .-> sw_KBUtilLib" in mer
