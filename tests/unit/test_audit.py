"""Audit tool tests."""

import pytest

from research_os.tools.actions.audit import audit_figure, audit_synthesis


@pytest.fixture
def workspace_root(tmp_path):
    (tmp_path / "workspace" / "logs").mkdir(parents=True)
    return tmp_path


def test_audit_synthesis_success_when_complete(workspace_root):
    paper_path = "synthesis/paper.md"
    p = workspace_root / paper_path
    p.parent.mkdir(parents=True)
    p.write_text(
        "# Title\n\n"
        "## Abstract\nbody\n\n"
        "## Introduction\nbody\n\n"
        "## Methods\nbody\n\n"
        "## Results\nbody\n\n"
        "## Discussion\nbody\n\n"
        "## References\n[1] Doe 2024.\n"
    )
    res = audit_synthesis(paper_path, workspace_root)
    assert res["status"] in {"success", "warning"}
    assert res["report"]["has_bibliography"] is True


def test_audit_synthesis_flags_missing_sections(workspace_root):
    p = workspace_root / "synthesis" / "p2.md"
    p.parent.mkdir(parents=True)
    p.write_text("# Title\n\n## Abstract\nminimal.\n")
    res = audit_synthesis("synthesis/p2.md", workspace_root)
    assert res["status"] == "warning"
    assert "methods" in res["report"]["missing_sections"]


def test_audit_synthesis_flags_causal_language(workspace_root):
    p = workspace_root / "synthesis" / "p3.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "## Abstract\n\n## Methods\n\n## Results\n"
        "The treatment causes improvement.\n\n## Discussion\nThis proves efficacy.\n\n## References\n[1]\n"
    )
    res = audit_synthesis("synthesis/p3.md", workspace_root)
    assert res["status"] == "warning"
    assert len(res["report"]["causal_language_hits"]) > 0


def test_audit_synthesis_paper_not_found(workspace_root):
    res = audit_synthesis("synthesis/no.md", workspace_root)
    assert res["status"] == "error"


def test_audit_figure_missing_file(workspace_root):
    res = audit_figure("workspace/01_eda/outputs/figures/ghost.png", workspace_root)
    assert res["status"] == "error"


# ---------------------------------------------------------------------------
# v1.3.4 regression — audit_synthesis aggregates per-step warnings,
# blocks pending-verification citations, counts author-year refs,
# doesn't truncate at ### sub-sections.
# ---------------------------------------------------------------------------


def test_audit_synthesis_aggregates_step_warnings_to_blocker(tmp_path):
    """v1.3.4: if N step_summary.yaml files each carry a literature-
    deferred warning, audit_synthesis must propagate them as a BLOCKER,
    not silently pass. The 22-turn stress test surfaced 10 deferred-
    literature warnings that the v1.3.3 audit ignored."""
    from research_os.tools.actions.audit.audit import audit_synthesis
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    ws = tmp_path / "workspace"
    # Make 4 fake step folders each carrying a literature-deferred warning.
    import yaml
    for i in range(1, 5):
        step_dir = ws / f"{i:02d}_test"
        step_dir.mkdir(parents=True, exist_ok=True)
        (step_dir / "step_summary.yaml").write_text(yaml.dump({
            "step_id": f"{i:02d}_test",
            "warnings": ["literature grounding deferred — will batch at synthesis"],
        }))
    # Write a long-enough paper so the size gate fires.
    syn = tmp_path / "synthesis"
    syn.mkdir(exist_ok=True)
    body = " ".join(["This is real prose."] * 200)  # ~600 words
    (syn / "paper.md").write_text(
        f"# Paper\n## Abstract\n{body}\n## Introduction\n{body}\n"
        f"## Methods\n{body}\n## Results\n{body}\n## Discussion\n{body}\n"
        f"## References\n[1] Doe 2024.\n"
    )
    res = audit_synthesis("synthesis/paper.md", tmp_path)
    assert res["status"] == "error", (
        f"recurring literature-deferred warning across 4 steps must BLOCK, "
        f"got {res['status']}; blockers={res.get('blockers')}"
    )
    # The recurring-blockers field is populated.
    rec = res["report"].get("recurring_blockers", [])
    assert any("literature" in b.lower() for b in rec), (
        f"expected literature-deferred entry in recurring_blockers, got {rec}"
    )


def test_audit_synthesis_blocks_on_pending_verification_citations(tmp_path):
    """v1.3.4: if citations.md has `pending verification` entries, audit
    must BLOCK the assembly until they're resolved."""
    from research_os.tools.actions.audit.audit import audit_synthesis
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    (tmp_path / "workspace" / "citations.md").write_text(
        "# Citations\n\n### `doe2024`\n- Status: ⏳ pending verification\n\n"
        "### `smith2023`\n- Status: ⏳ pending verification\n"
    )
    syn = tmp_path / "synthesis"
    syn.mkdir(exist_ok=True)
    body = " ".join(["Lots of words."] * 200)
    (syn / "paper.md").write_text(
        f"# Paper\n## Abstract\n{body}\n## Introduction\n{body}\n"
        f"## Methods\n{body}\n## Results\n{body}\n## Discussion\n{body}\n"
        f"## References\n(Doe 2024)\n"
    )
    res = audit_synthesis("synthesis/paper.md", tmp_path)
    assert res["status"] == "error"
    assert res["report"].get("unverified_citations", 0) >= 2
    assert any(
        "pending verification" in b.lower() for b in res["report"].get("recurring_blockers", [])
    )


def test_audit_synthesis_counts_author_year_refs(tmp_path):
    """v1.3.4: a paper using author-year prose form `(Doe 2024)` shouldn't
    show citation_count=0; we now count BOTH Pandoc [@key] AND author-year."""
    from research_os.tools.actions.audit.audit import audit_synthesis
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    syn = tmp_path / "synthesis"
    syn.mkdir(exist_ok=True)
    body = (
        "We used DESeq2 (Love et al. 2014) and WGCNA (Langfelder & Horvath, 2008). "
        "ComBat-seq (Zhang 2020) was applied; Schoenfeld 1980 was the PH test. "
        + "Filler. " * 200
    )
    (syn / "paper.md").write_text(
        f"# Paper\n## Abstract\n{body}\n## Introduction\n{body}\n"
        f"## Methods\n{body}\n## Results\n{body}\n## Discussion\n{body}\n"
        f"## References\n- Love et al. 2014\n- Langfelder 2008\n"
    )
    res = audit_synthesis("synthesis/paper.md", tmp_path)
    assert res["report"]["citation_count_authoryear"] >= 3, (
        f"expected ≥3 author-year refs, got {res['report']['citation_count_authoryear']}"
    )
    # citation_count is the SUM of both forms.
    assert res["report"]["citation_count"] >= 3


def test_audit_synthesis_section_regex_doesnt_truncate_at_subsections(tmp_path):
    r"""v1.3.4: `### 2.1 Subsection` headers must NOT terminate the parent
    `## Methods` section. v1.3.3 used `(?=^##|\Z)` which clobbered."""
    from research_os.tools.actions.audit.audit import audit_synthesis
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    syn = tmp_path / "synthesis"
    syn.mkdir(exist_ok=True)
    methods_body = " ".join(["Method detail sentence."] * 100)  # 300 words
    sub_body = " ".join(["Sub-section detail."] * 100)  # 200 words
    short = " ".join(["x"] * 200)
    (syn / "paper.md").write_text(
        f"# Paper\n## Abstract\n{short}\n## Introduction\n{short}\n"
        f"## Methods\n{methods_body}\n\n### 2.1 Data ingest\n{sub_body}\n\n"
        f"### 2.2 Normalization\n{sub_body}\n\n"
        f"## Results\n{short}\n## Discussion\n{short}\n## References\n- Doe 2024\n"
    )
    res = audit_synthesis("synthesis/paper.md", tmp_path)
    # Methods word count should include the ### sub-sections (300 + 200 + 200 = 700).
    methods_words = res["report"]["quality_gates"]["word_counts"]["methods"]
    assert methods_words >= 600, (
        f"Methods word count should include ### sub-sections; got {methods_words}"
    )
