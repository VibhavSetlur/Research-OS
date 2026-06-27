"""Self-improving skill distillation — distill / promote / list.

Verifies the loop on top of tool_lessons: recorded lessons cluster by
tag, recurring patterns crystallize into reusable SKILL.md cards, and
project/methodology-scoped skills promote into the cross-project profile
so the same researcher inherits them in a new project.
"""
from __future__ import annotations

import os

import pytest

from research_os.tools.actions.research.lessons import lessons_record
from research_os.tools.actions.research.skills import (
    distill_skills,
    list_skills,
    promote_skills,
)


@pytest.fixture
def root(tmp_path):
    return tmp_path


@pytest.fixture
def profile_home(tmp_path, monkeypatch):
    """Isolate the cross-project profile + Hermes home under temp dirs."""
    cfg = tmp_path / "xdg"
    cfg.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    # Isolate the Hermes home so promote's loadable-card write never touches
    # the real ~/.hermes/skills during tests.
    hh = tmp_path / "hermes_home"
    (hh / "skills").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hh))
    return cfg


def _record(root, tag, outcome="failure", scope="step", rec="do X"):
    return lessons_record(
        root,
        outcome=outcome,
        reflection=f"something about {tag}",
        what_worked="approach A",
        what_didnt="approach B",
        recommendation=rec,
        tags=[tag],
        scope=scope,
    )


class TestDistill:
    def test_no_lessons_yields_nothing(self, root):
        res = distill_skills(root)
        assert res["status"] == "success"
        assert res["skills_written"] == 0

    def test_single_occurrence_below_threshold(self, root):
        _record(root, "clustering")
        res = distill_skills(root)
        assert res["skills_written"] == 0
        assert any(s["tag"] == "clustering" for s in res["skipped_below_threshold"])

    def test_recurring_tag_becomes_skill(self, root):
        _record(root, "clustering", rec="use silhouette score")
        _record(root, "clustering", rec="standardize features first")
        res = distill_skills(root)
        assert res["skills_written"] == 1
        skill = res["skills"][0]
        assert skill["tag"] == "clustering"
        assert skill["lessons_count"] == 2
        # Card written to disk, Hermes-compatible frontmatter.
        card = (root / "workspace" / ".skills" / f"{skill['slug']}.SKILL.md")
        assert card.exists()
        text = card.read_text()
        assert text.startswith("---")
        assert "name: ro-clustering" in text
        assert "use silhouette score" in text
        assert "standardize features first" in text

    def test_idempotent_rewrite(self, root):
        _record(root, "stats")
        _record(root, "stats")
        first = distill_skills(root)
        n_files_1 = len(list((root / "workspace" / ".skills").glob("*.SKILL.md")))
        second = distill_skills(root)
        n_files_2 = len(list((root / "workspace" / ".skills").glob("*.SKILL.md")))
        assert first["skills_written"] == second["skills_written"] == 1
        assert n_files_1 == n_files_2 == 1

    def test_min_occurrences_override(self, root):
        _record(root, "viz")
        _record(root, "viz")
        assert distill_skills(root, min_occurrences=3)["skills_written"] == 0
        assert distill_skills(root, min_occurrences=2)["skills_written"] == 1


class TestPromote:
    def test_only_project_methodology_scope_promotes(self, root, profile_home):
        # step-scoped lessons should NOT promote.
        _record(root, "local", scope="step")
        _record(root, "local", scope="step")
        res = promote_skills(root)
        assert res["promoted"] == 0

    def test_project_scope_promotes_to_profile(self, root, profile_home):
        _record(root, "rigor", scope="project", rec="preregister analyses")
        _record(root, "rigor", scope="project", rec="log every override")
        res = promote_skills(root)
        assert res["promoted"] == 1
        prof = profile_home / "research-os" / "profile.yaml"
        assert prof.exists()
        import yaml
        data = yaml.safe_load(prof.read_text())
        learned = data["learned_skills"]
        assert "rigor" in learned
        recs = learned["rigor"]["recommendations"]
        assert "preregister analyses" in recs
        assert "log every override" in recs

    def test_promote_merges_recommendations(self, root, profile_home):
        _record(root, "rigor", scope="methodology", rec="rec one")
        _record(root, "rigor", scope="methodology", rec="rec one")
        promote_skills(root)
        _record(root, "rigor", scope="methodology", rec="rec two")
        _record(root, "rigor", scope="methodology", rec="rec two")
        promote_skills(root)
        import yaml
        prof = profile_home / "research-os" / "profile.yaml"
        data = yaml.safe_load(prof.read_text())
        recs = data["learned_skills"]["rigor"]["recommendations"]
        assert "rec one" in recs and "rec two" in recs

    @pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
    def test_profile_is_chmod_600(self, root, profile_home):
        _record(root, "x", scope="project")
        _record(root, "x", scope="project")
        promote_skills(root)
        prof = profile_home / "research-os" / "profile.yaml"
        assert (prof.stat().st_mode & 0o777) == 0o600


class TestList:
    def test_list_reports_both_scopes(self, root, profile_home):
        _record(root, "alpha", scope="project")
        _record(root, "alpha", scope="project")
        distill_skills(root)
        promote_skills(root)
        res = list_skills(root)
        assert res["n_project"] >= 1
        assert res["n_cross_project"] >= 1
        assert any(s["tag"] == "alpha" for s in res["cross_project_skills"])


def test_promote_writes_loadable_hermes_card(root, profile_home, monkeypatch):
    """Promoted lessons become real SKILL.md cards in the (isolated) Hermes home."""
    import os
    from pathlib import Path
    # enough project-scoped lessons on one tag to clear the threshold
    for _ in range(3):
        _record(root, "rnaseq", outcome="failure", scope="project",
                rec="always check library size normalization")
    res = promote_skills(root)
    assert res["promoted"] >= 1
    hh = Path(os.environ["HERMES_HOME"])
    cards = list((hh / "skills" / "research-os-learned").glob("*/SKILL.md"))
    assert cards, "no loadable Hermes card written"
    text = cards[0].read_text()
    assert text.startswith("---")
    assert "ro-learned-" in text
    assert res["hermes_cards_written"]


def test_promote_no_cards_when_disabled(root, profile_home):
    import os
    from pathlib import Path
    for _ in range(3):
        _record(root, "viz", outcome="failure", scope="project", rec="use okabe-ito")
    res = promote_skills(root, write_hermes_cards=False)
    hh = Path(os.environ["HERMES_HOME"])
    assert not list((hh / "skills" / "research-os-learned").glob("*/SKILL.md"))
    assert res["hermes_cards_written"] == []
