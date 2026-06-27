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
