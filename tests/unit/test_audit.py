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


# ---------------------------------------------------------------------------
# v1.4.0 regression — literature loop gate (audit_step_literature) +
# audit_synthesis surfaces per-step literature_deferred + zero-grounding.
# ---------------------------------------------------------------------------


def test_audit_step_literature_blocks_when_findings_vs_literature_missing(tmp_path):
    """v1.4.0: a step with non-stub Findings but no
    workspace/<step>/literature/findings_vs_literature.md must block."""
    from research_os.tools.actions.audit.step_literature import audit_step_literature
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    step_dir = tmp_path / "workspace" / "03_run_deseq2"
    step_dir.mkdir(parents=True)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n- APOE significantly down-regulated in AD vs CTRL "
        "(log2FC=-1.4, padj=2e-5).\n- 247 DE genes pass FDR<0.05.\n"
    )
    res = audit_step_literature(tmp_path, step_id="03_run_deseq2")
    assert res["status"] == "error", (
        "step with findings but no findings_vs_literature.md must block"
    )
    assert any("findings_vs_literature.md" in b for b in res["blockers"])


def test_audit_step_literature_blocks_disagrees_without_discussion(tmp_path):
    """v1.4.0: a DISAGREES verdict without **Discussion implication:**
    block must block — disagreements MUST be addressed."""
    from research_os.tools.actions.audit.step_literature import audit_step_literature
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    step_dir = tmp_path / "workspace" / "04_pathway"
    step_dir.mkdir(parents=True)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n- Pathway X enriched at FDR<0.01 in our cohort.\n"
    )
    lit_dir = step_dir / "literature"
    lit_dir.mkdir()
    (lit_dir / "findings_vs_literature.md").write_text(
        "## Claim: Pathway X enriched in AD\n\n"
        "**Our finding:** Pathway X significant at FDR<0.01.\n\n"
        "**Literature says:** Doe 2023 reports Pathway X NOT enriched in AD.\n\n"
        "**Verdict:** DISAGREES\n\n"
        "**Evidence:**\n- [@doe2023] (2023) - Pathway X not significant.\n"
    )
    res = audit_step_literature(tmp_path, step_id="04_pathway")
    assert res["status"] == "error"
    assert any("DISAGREES" in b for b in res["blockers"])


def test_audit_step_literature_passes_with_complete_loop(tmp_path):
    """v1.4.0: complete findings_vs_literature.md with AGREES verdict +
    grounding record + literature: block in step_summary.yaml = pass."""
    from research_os.tools.actions.audit.step_literature import audit_step_literature
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    step_dir = tmp_path / "workspace" / "05_hub_genes"
    step_dir.mkdir(parents=True)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n- APOE up-regulated 1.4-fold, padj=1e-6.\n"
    )
    lit_dir = step_dir / "literature"
    lit_dir.mkdir()
    (lit_dir / "findings_vs_literature.md").write_text(
        "## Claim: APOE up-regulated in AD hippocampus\n\n"
        "**Our finding:** log2FC=1.4, padj=1e-6.\n\n"
        "**Literature says:** Smith 2024 reports the same direction.\n\n"
        "**Verdict:** AGREES\n\n"
        "**Evidence:**\n- [@smith2024] (2024) - confirms direction.\n\n"
        "**Discussion implication:** anchor the discussion paragraph.\n"
    )
    (step_dir / "step_summary.yaml").write_text(
        "literature:\n"
        "  claims_grounded: 1\n"
        "  claims_deferred: 0\n"
        "  papers_downloaded: 1\n"
        "  verdicts: {agrees: 1, disagrees: 0, extends: 0}\n"
    )
    res = audit_step_literature(tmp_path, step_id="05_hub_genes")
    assert res["status"] in {"success", "warning"}
    assert not any("missing" in b.lower() for b in res["blockers"])


def test_audit_step_literature_skips_data_engineering_steps(tmp_path):
    """v1.4.0: literature_required: false in step_summary.yaml skips."""
    from research_os.tools.actions.audit.step_literature import audit_step_literature
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    step_dir = tmp_path / "workspace" / "01_ingest_qc"
    step_dir.mkdir(parents=True)
    (step_dir / "conclusions.md").write_text("## Findings\n\n- 90 samples passed QC.\n")
    (step_dir / "step_summary.yaml").write_text("literature_required: false\n")
    res = audit_step_literature(tmp_path, step_id="01_ingest_qc")
    assert res["status"] == "success"
    assert not res["blockers"]


def test_audit_synthesis_blocks_on_step_literature_deferred(tmp_path):
    """v1.4.0: audit_synthesis aggregates per-step literature_deferred
    and blocks final assembly even when paper looks complete."""
    from research_os.tools.actions.audit.audit import audit_synthesis

    syn = tmp_path / "synthesis"
    syn.mkdir()
    body = "body. " * 120
    (syn / "paper.md").write_text(
        f"# T\n## Abstract\n{body}\n## Introduction\n{body}\n"
        f"## Methods\n{body}\n## Results\n{body}\n"
        f"## Discussion\n{body}\n## References\n- Doe 2024\n"
    )
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "logs").mkdir()
    for n in ("03_deseq2", "04_pathway"):
        sd = ws / n
        sd.mkdir()
        (sd / "step_summary.yaml").write_text(
            "literature_deferred:\n  - 'claim_1: no relevant publications found'\n"
        )
    res = audit_synthesis("synthesis/paper.md", tmp_path)
    assert res["status"] == "error"
    assert any("literature_deferred" in b for b in res["report"]["gate_blockers"])


def test_caption_synthesise_extracts_prose_findings_when_no_bullets(tmp_path):
    """v1.4.0: figures.py caption_synthesise must pull a 'Why it matters'
    sentence from prose Findings when no bullets exist (same fix as
    v1.3.4 path._bullet_lines, ported to figures.caption_synthesise)."""
    from research_os.tools.actions.viz.figures import caption_synthesise

    step = tmp_path / "workspace" / "07_cox_ph"
    step.mkdir(parents=True)
    (step / "conclusions.md").write_text(
        "## Findings\n\n"
        "APOE hazard ratio is 1.8 (95% CI 1.2-2.7, p=0.004) for the "
        "AD-vs-control contrast. The signal is consistent across the "
        "ROSMAP and Mayo cohorts.\n"
    )
    figs = step / "outputs" / "figures"
    figs.mkdir(parents=True)
    fig = figs / "01_apoe_km_curve.png"
    fig.write_bytes(b"\x89PNG\r\n")
    (figs / "01_apoe_km_curve.caption.md").write_text(
        "**Figure 1.** Kaplan-Meier survival curves for APOE carriers.\n"
    )
    res = caption_synthesise(
        figure_path=str(fig.relative_to(tmp_path)),
        root=tmp_path,
    )
    assert res["status"] == "success"
    summary_path = tmp_path / res["summary_path"]
    text = summary_path.read_text()
    assert "**Why it matters.**" in text, (
        f"summary should pull a prose sentence; got:\n{text}"
    )


def test_audit_missing_summary_md_now_blocks(tmp_path):
    """v1.4.0: audit_step_completeness changed missing .summary.md from
    WARN to BLOCK to match the visualization_workflow.yaml protocol
    doctrine."""
    from research_os.tools.actions.audit.audit import audit_step_completeness
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    step = tmp_path / "workspace" / "02_eda"
    step.mkdir(parents=True)
    (step / "scripts").mkdir()
    (step / "scripts" / "01_eda.py").write_text("import pandas as pd\n")
    (step / "conclusions.md").write_text(
        "## Findings\n\nDetailed prose findings " + ("more text " * 30)
        + "\n\n## Decision\n\nProceed to step 3.\n"
    )
    figs = step / "outputs" / "figures"
    figs.mkdir(parents=True)
    fig = figs / "01_dist.png"
    fig.write_bytes(b"\x89PNG\r\n")
    (figs / "01_dist.caption.md").write_text("**Figure 1.** distribution\n")
    # Intentionally no .summary.md
    res = audit_step_completeness(tmp_path, step_id="02_eda")
    blockers = res.get("steps", [{}])[0].get("blockers", [])
    assert any("summary" in b.lower() for b in blockers), (
        f"missing .summary.md must be a BLOCKER in v1.4.0; got {blockers}"
    )


def test_audit_step_completeness_warns_on_missing_stack_plan(tmp_path):
    """v1.4.0 (audit fix B-lite): step with scripts but no
    scratch/stack_plan.md gets a WARNING (BLOCKER in v1.5.0)."""
    from research_os.tools.actions.audit.audit import audit_step_completeness
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    step = tmp_path / "workspace" / "03_run_deseq2"
    step.mkdir(parents=True)
    (step / "scripts").mkdir()
    (step / "scripts" / "01_deseq2.R").write_text("library(DESeq2)\n")
    (step / "conclusions.md").write_text(
        "## Findings\n\nDetailed prose findings " + ("more text " * 30)
        + "\n\n## Decision\n\nProceed to step 4.\n"
    )
    figs = step / "outputs" / "figures"
    figs.mkdir(parents=True)
    fig = figs / "01_volcano.png"
    fig.write_bytes(b"\x89PNG\r\n")
    (figs / "01_volcano.caption.md").write_text("**Figure 1.** Volcano plot.\n")
    (figs / "01_volcano.summary.md").write_text("**What it shows.** Volcano.\n")
    # Intentionally no scratch/stack_plan.md
    res = audit_step_completeness(tmp_path, step_id="03_run_deseq2")
    warns = res.get("steps", [{}])[0].get("warnings", [])
    assert any("stack_plan" in w.lower() for w in warns), (
        f"missing stack_plan.md must WARN in v1.4.0; got {warns}"
    )
