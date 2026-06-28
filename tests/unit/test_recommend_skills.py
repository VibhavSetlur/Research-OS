"""Active intake-driven skill recommendation (forward-looking, first-turn)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.research.skills import recommend_skills
from research_os.tools.actions.router import sys_boot


def _proj(domain: str = "", mode: str = "analysis") -> Path:
    root = Path(tempfile.mkdtemp()) / "p"
    overrides = {"domain": domain} if domain else None
    scaffold_minimal_workspace(root, "T", mode=mode, config_overrides=overrides)
    return root


def test_recommend_combines_domain_and_mode():
    root = _proj()
    r = recommend_skills(root, domain="clinical", workspace_mode="analysis")
    names = [s["name"] for s in r["recommended_skills"]]
    assert "survival-analysis" in names      # domain
    assert "viz" in names or "stats" in names  # mode
    assert len(names) == len(set(names))     # deduped


def test_recommend_unknown_domain_still_gives_mode_skills():
    root = _proj()
    r = recommend_skills(root, domain="basket-weaving", workspace_mode="tool_build")
    names = [s["name"] for s in r["recommended_skills"]]
    assert "software-testing" in names  # mode map still applies


def test_recommend_capped():
    root = _proj()
    r = recommend_skills(root, domain="clinical", workspace_mode="analysis")
    assert len(r["recommended_skills"]) <= 12


def test_sys_boot_surfaces_recommended_skills_on_fresh_project():
    root = _proj(domain="genomics")
    b = sys_boot(root)
    assert "recommended_skills" in b
    assert len(b["recommended_skills"]) >= 1
    names = [s["name"] for s in b["recommended_skills"]]
    assert "bioinformatics" in names


# ── Per-task (universal) skill-pull ──────────────────────────────────────


def test_task_specific_skill_leads_for_visualize():
    root = _proj(domain="genomics")
    r = recommend_skills(
        root, domain="genomics", workspace_mode="analysis",
        task_intent="viz_build", protocol="visualization/figure_guidelines",
    )
    names = [s["name"] for s in r["recommended_skills"]]
    # The task-specific capability leads the list.
    assert names[0] == "scientific-visualization"
    assert r["task_intent"] == "viz_build"
    assert r["protocol"] == "visualization/figure_guidelines"


def test_task_specific_skill_leads_for_paper():
    root = _proj(domain="clinical")
    r = recommend_skills(
        root, domain="clinical", workspace_mode="analysis",
        task_intent="paper", protocol="synthesis/synthesis_paper",
    )
    assert r["recommended_skills"][0]["name"] == "scientific-writing"


def test_task_intent_tags_apply_without_protocol():
    root = _proj()
    r = recommend_skills(
        root, domain="", workspace_mode="analysis",
        task_intent="per_step_grounding",
    )
    names = [s["name"] for s in r["recommended_skills"]]
    assert "literature-review" in names
    assert "citation-management" in names


def test_recommend_backward_compatible_without_task_args():
    # Old call shape (no task_intent/protocol) must still work.
    root = _proj()
    r = recommend_skills(root, domain="clinical", workspace_mode="analysis")
    assert r["status"] == "success"
    assert r["task_intent"] is None
    assert len(r["recommended_skills"]) >= 1

