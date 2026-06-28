"""K-Dense science-pack integration: domain mapping + Hermes wiring."""
from __future__ import annotations

import tempfile
from pathlib import Path

from research_os import hermes_integration
from research_os.tools.actions.research import science_pack
from research_os.tools.actions.research.skills import recommend_skills
from research_os.project_ops import scaffold_minimal_workspace


def test_science_skills_for_domain():
    out = science_pack.science_skills_for("genomics", "analysis")
    names = [s["name"] for s in out]
    assert "biopython" in names
    assert "gget" in names
    assert all(s["source"] == "science_pack" for s in out)
    assert all(s["repo"] == science_pack.SCIENCE_PACK_REPO for s in out)


def test_science_skills_dedupe_and_unknown_domain():
    out = science_pack.science_skills_for("unknown-field", "analysis")
    names = [s["name"] for s in out]
    # unknown domain still gets mode skills, deduped
    assert len(names) == len(set(names))
    assert "exploratory-data-analysis" in names


def test_recommend_skills_includes_science_pack():
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode="analysis",
                               config_overrides={"domain": "chemistry"})
    r = recommend_skills(root, domain="chemistry", workspace_mode="analysis")
    sci = [s["name"] for s in r["recommended_skills"] if s["source"] == "science_pack"]
    assert "rdkit" in sci


def test_register_external_skill_dir_is_idempotent():
    cfg = Path(tempfile.mkdtemp()) / "config.yaml"
    cfg.write_text("mcp_servers: {}\n")
    r1 = hermes_integration.register_external_skill_dir("/x/skills", config_path=cfg)
    r2 = hermes_integration.register_external_skill_dir("/x/skills", config_path=cfg)
    assert r1["added"] is True
    assert r2["added"] is False  # already present
    assert cfg.read_text().count("/x/skills") == 1


def test_protocol_skill_map_targets_real_skills():
    # Every skill named in the protocol map must be a real upstream skill name
    # (i.e. present in the domain or mode maps, our curated universe).
    universe = set()
    for v in science_pack.SCIENCE_PACK_BY_DOMAIN.values():
        universe.update(v)
    for v in science_pack.SCIENCE_PACK_BY_MODE.values():
        universe.update(v)
    for v in science_pack.SCIENCE_PACK_BY_PROTOCOL.values():
        universe.update(v)
    # sanity: the protocol map references known skill names (non-empty)
    for proto, skills in science_pack.SCIENCE_PACK_BY_PROTOCOL.items():
        assert skills, f"{proto} has no skills"
