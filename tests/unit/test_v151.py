"""Regression tests for v1.5.1 — adaptive friction + quick mode + carried-forward stress-audit fixes.

Coverage:
- (a) tool_rigor_signals_scan returns trust_score + recommended strictness
- (b) tool_self_certify persists + has_active_certification reads back
- (c) per-step skip annotation detected from conclusions.md
- (d) tool_quick_route detects quick triggers, bypasses normal routing
- (e) tool_promote_to_step wraps scratch result in proper provenance
- (f) tool_project_tier_strictness maps tier → strictness
- (g) audit_synthesis override_no_pdfs requires non-empty rationale
- (h) coherence excludes numbered-list items 2-N and code-block bodies
- (i) discussion_coverage_audit accepts single-keyword claims when covered
"""

from __future__ import annotations

from pathlib import Path


def _scaffold(tmp_path: Path) -> Path:
    (tmp_path / "workspace").mkdir()
    (tmp_path / "inputs" / "literature").mkdir(parents=True)
    (tmp_path / "synthesis").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# (a) rigor_signals_scan
# ---------------------------------------------------------------------------


def test_rigor_signals_scan_returns_score(tmp_path):
    from research_os.tools.actions.state.rigor_signals import rigor_signals_scan

    root = _scaffold(tmp_path)
    # Empty project: low score → strict.
    res = rigor_signals_scan(root)
    assert res["status"] == "success"
    assert res["trust_score"] == 0
    assert res["recommended_strictness"] == "strict"
    assert len(res["signals"]) == 6

    # Add substantive methods.md + a few PDFs to lift the score.
    methods = root / "workspace" / "methods.md"
    methods.write_text(
        "# Methods\n\n"
        "- DESeq2 (Love et al. 2014) for differential expression\n"
        "- Cox PH (Cox 1972) for survival analysis\n"
        "- xCell (Aran 2017) for stromal deconvolution\n"
        "- Bonferroni correction (Bonferroni 1936) for multiple testing\n"
        "- Bootstrap CIs (Efron 1979) for effect-size uncertainty\n"
        + ("Detailed methodological narrative. " * 30)
    )
    for i in range(5):
        (root / "inputs" / "literature" / f"paper{i}.pdf").write_bytes(b"\x25PDF-")
    res2 = rigor_signals_scan(root)
    assert res2["trust_score"] > res["trust_score"]


# ---------------------------------------------------------------------------
# (b) self_certify + has_active_certification
# ---------------------------------------------------------------------------


def test_self_certify_persists_and_recall(tmp_path):
    from research_os.tools.actions.state.certifications import (
        has_active_certification,
        list_certifications,
        self_certify,
    )

    root = _scaffold(tmp_path)

    pre = has_active_certification(root, "literature_loop", step_id="03_dge")
    assert pre["active"] is False

    res = self_certify(
        root,
        domain="literature_loop",
        scope="all steps",
        rationale="15+ years in this field; have read the canonical literature",
    )
    assert res["status"] == "success"
    assert res["active_count"] == 1

    post = has_active_certification(root, "literature_loop", step_id="03_dge")
    assert post["active"] is True
    assert "15+ years" in post["certification"]["rationale"]

    # Wrong domain rejected.
    bad = self_certify(root, domain="quantum_entanglement", scope="x", rationale="y")
    assert bad["status"] == "error"

    listed = list_certifications(root)
    assert listed["count"] == 1


# ---------------------------------------------------------------------------
# (c) per-step skip annotation
# ---------------------------------------------------------------------------


def test_step_skip_annotation_honoured(tmp_path):
    from research_os.tools.actions.state.certifications import (
        step_has_skip_annotation,
    )

    root = _scaffold(tmp_path)
    step = root / "workspace" / "02_qc"
    step.mkdir()
    (step / "conclusions.md").write_text(
        "## Findings\n\nQC metrics within expected ranges.\n\n"
        "<!-- ro:skip lit_loop, reason: pure data engineering, no claims to ground -->\n\n"
        "## Decision\n\nProceed to step 3.\n"
    )
    res = step_has_skip_annotation(root, "02_qc", "lit_loop")
    assert res["has_skip"] is True
    assert "pure data engineering" in res["reason"]

    # Different gate name: no skip.
    res2 = step_has_skip_annotation(root, "02_qc", "stack_plan")
    assert res2["has_skip"] is False


# ---------------------------------------------------------------------------
# (d) tool_quick_route detects + bypasses
# ---------------------------------------------------------------------------


def test_quick_route_detects_quick_triggers(tmp_path):
    from research_os.tools.actions.state.quick_mode import (
        detect_quick_intent,
        quick_route,
    )

    root = _scaffold(tmp_path)
    assert detect_quick_intent("just make me a plot of survival vs age")["is_quick"]
    assert detect_quick_intent("sanity check the missingness")["is_quick"]
    assert detect_quick_intent("rough draft of the abstract")["is_quick"]
    assert not detect_quick_intent("run differential expression on the cohort")["is_quick"]

    res = quick_route(root, "just make me a plot")
    assert res["is_quick"] is True
    assert res["complexity"] == "quick"
    assert res["recommended_tool"] == "tool_scratch_write"
    assert (root / "workspace" / "scratch").is_dir()

    # Non-quick prompt routes normally.
    res2 = quick_route(root, "run cox regression")
    assert res2["is_quick"] is False


# ---------------------------------------------------------------------------
# (e) tool_promote_to_step wraps in proper provenance
# ---------------------------------------------------------------------------


def test_promote_to_step_creates_numbered_step(tmp_path):
    from research_os.tools.actions.state.quick_mode import promote_to_step

    root = _scaffold(tmp_path)
    scratch = root / "workspace" / "scratch"
    scratch.mkdir()
    fig = scratch / "fig_quicklook.png"
    fig.write_bytes(b"\x89PNG-")

    res = promote_to_step(
        root,
        scratch_path="workspace/scratch/fig_quicklook.png",
        step_slug="quick_eda_promotion",
        rationale="The quicklook surfaced a real outlier — promoting for audit.",
    )
    assert res["status"] == "success"
    assert res["step_id"].startswith("01_")
    step_dir = root / res["step_dir"]
    assert (step_dir / "conclusions.md").exists()
    assert (step_dir / "step_summary.yaml").exists()
    assert (step_dir / "outputs" / "figures" / "fig_quicklook.png").exists()
    prov = step_dir / "outputs" / "figures" / "fig_quicklook.png.prov.json"
    assert prov.exists()
    assert "scratch" in prov.read_text()


# ---------------------------------------------------------------------------
# (f) project_tier → strictness mapping
# ---------------------------------------------------------------------------


def test_project_tier_strictness_mapping(tmp_path):
    from research_os.tools.actions.state.quick_mode import project_tier_strictness

    root = _scaffold(tmp_path)
    # No config → defaults to production → strict.
    res = project_tier_strictness(root)
    assert res["status"] == "success"
    assert res["project_tier"] == "production"
    assert res["default_gate_strictness"] == "strict"

    # Set throwaway.
    cfg_path = root / "inputs" / "researcher_config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("project_tier: throwaway\n")
    res2 = project_tier_strictness(root)
    assert res2["project_tier"] == "throwaway"
    assert res2["default_gate_strictness"] == "light"


# ---------------------------------------------------------------------------
# (g) audit_synthesis override_no_pdfs requires non-empty rationale
# ---------------------------------------------------------------------------


def test_audit_synthesis_override_requires_rationale(tmp_path):
    from research_os.tools.actions.audit.audit import audit_synthesis

    root = _scaffold(tmp_path)
    step = root / "workspace" / "01_step_a"
    step.mkdir()
    (step / "conclusions.md").write_text(
        "## Findings\n\nReal finding.\n\n## Decision\n\nProceed.\n"
    )
    paper = root / "synthesis" / "paper.md"
    paper.write_text(
        "## Abstract\n\n" + ("word " * 200)
        + "\n\n## Introduction\n\n" + ("word " * 200)
        + "\n\n## Methods\n\n" + ("word " * 200)
        + "\n\n## Results\n\n" + ("word " * 200)
        + "\n\n## Discussion\n\n" + ("word " * 200)
        + "\n\n## References\n\n[@x] X.\n"
    )

    # override=true + empty rationale → still blocks (with a distinct
    # message explaining the rationale is required).
    res = audit_synthesis(
        "synthesis/paper.md", root,
        override_no_pdfs=True, override_rationale="",
    )
    joined = " ".join(res.get("blockers", []))
    assert "rationale" in joined.lower() or "DEFAULT-DENY" in joined

    # Both supplied → no zero-PDF blocker.
    res2 = audit_synthesis(
        "synthesis/paper.md", root,
        override_no_pdfs=True,
        override_rationale="closed field; literature structurally unavailable",
    )
    blockers = " ".join(res2.get("blockers", []))
    assert "zero PDFs" not in blockers


# ---------------------------------------------------------------------------
# (h) coherence excludes numbered-list items + code-block bodies
# ---------------------------------------------------------------------------


def test_coherence_handles_numbered_lists_and_code_blocks(tmp_path):
    from research_os.tools.actions.audit.coherence import audit_coherence

    root = _scaffold(tmp_path)
    step = root / "workspace" / "01_eda"
    step.mkdir()
    (step / "conclusions.md").write_text(
        "## Findings\n\nDifferential expression analysis identified 412 genes "
        "at FDR less than 0.05 between HER2-positive and HER2-negative tumors.\n"
    )

    paper = root / "synthesis" / "paper.md"
    paper.write_text(
        "## Results\n\n"
        "Differential expression analysis identified 412 genes at FDR less "
        "than 0.05 between HER2-positive and HER2-negative tumors.\n\n"
        "Steps performed:\n"
        "1. Load count matrix from TCGA breast cancer cohort\n"
        "2. Filter low-count genes (DESeq2 default thresholds)\n"
        "3. Normalize via DESeq2 median-of-ratios\n"
        "4. Fit Wald model with subtype as predictor\n"
        "\n"
        "```r\n"
        "library(DESeq2)\n"
        "dds <- DESeqDataSetFromMatrix(counts, coldata, ~subtype)\n"
        "dds <- DESeq(dds)\n"
        "results(dds)\n"
        "```\n"
        "\n"
        "## Discussion\n\n"
        "The 412 differentially expressed genes between HER2-positive and "
        "HER2-negative subtypes confirm prior findings.\n"
    )
    res = audit_coherence(root)
    # Lists + code blocks must NOT be flagged as orphans.
    previews = " ".join(o["preview"] for o in res["orphan_paragraphs"])
    assert "library(DESeq2)" not in previews
    assert "Filter low-count genes" not in previews


# ---------------------------------------------------------------------------
# (i) discussion_coverage_audit accepts single-keyword claims when covered
# ---------------------------------------------------------------------------


def test_discussion_coverage_single_keyword_claim(tmp_path):
    """A short claim with only 1-2 keywords used to be unprovably uncovered."""
    from research_os.tools.actions.synthesis.discussion_from_verdicts import (
        discussion_coverage_audit,
    )

    root = _scaffold(tmp_path)
    step = root / "workspace" / "01_step"
    (step / "literature").mkdir(parents=True)
    (step / "conclusions.md").write_text(
        "## Findings\n\nReal finding.\n\n## Decision\n\nProceed.\n"
    )
    (step / "literature" / "findings_vs_literature.md").write_text(
        "## Claim: BMI rises\n"
        "**Our finding:** BMI rose in cohort.\n"
        "**Literature says:** Prior work shows stable BMI.\n"
        "**Verdict:** DISAGREES\n"
        "**Citation:** Smith 2024\n"
        "**Discussion implication:** Our cohort skews older.\n"
    )
    # Discussion mentions "rises" — should cover the single-keyword claim.
    (root / "synthesis" / "discussion.md").write_text(
        "BMI rises in older cohorts and that is what we observed.\n"
    )
    res = discussion_coverage_audit(root)
    assert res["status"] == "success"
    assert res["uncovered_count"] == 0


# (j) adaptive friction — stack_plan BLOCKER downgrades to WARN with cert.
def test_stack_plan_gate_downgrades_with_certification(tmp_path):
    from research_os.project_ops import scaffold_minimal_workspace
    from research_os.tools.actions.audit import audit_step_completeness
    from research_os.tools.actions.state.certifications import self_certify

    scaffold_minimal_workspace(tmp_path, "Test")
    step = tmp_path / "workspace" / "04_run_de"
    step.mkdir(parents=True)
    (step / "scripts").mkdir()
    (step / "scripts" / "01_de.R").write_text("library(DESeq2)\n")
    (step / "conclusions.md").write_text(
        "## Findings\n\n" + ("More substantive text. " * 30)
        + "\n\n## Decision\n\nProceed.\n"
    )
    figs = step / "outputs" / "figures"
    figs.mkdir(parents=True)
    (figs / "01_v.png").write_bytes(b"\x89PNG\r\n")
    (figs / "01_v.caption.md").write_text("**Figure 1.** Volcano.\n")
    (figs / "01_v.summary.md").write_text("**What.** Volcano.\n")
    # Intentionally NO scratch/stack_plan.md.

    res_no_cert = audit_step_completeness(tmp_path, step_id="04_run_de")
    blockers_no_cert = res_no_cert.get("steps", [{}])[0].get("blockers", [])
    assert any("stack_plan" in b.lower() for b in blockers_no_cert), (
        f"without cert, stack_plan must BLOCK; got {blockers_no_cert}"
    )

    # Add a self-certification → BLOCKER should downgrade to WARN.
    self_certify(
        tmp_path,
        domain="stack_plan",
        scope="all steps",
        rationale="Lab-wide standard: R Bioconductor for bulk DE",
    )
    res_with_cert = audit_step_completeness(tmp_path, step_id="04_run_de")
    blockers_with_cert = res_with_cert.get("steps", [{}])[0].get("blockers", [])
    warns_with_cert = res_with_cert.get("steps", [{}])[0].get("warnings", [])
    assert not any("stack_plan" in b.lower() for b in blockers_with_cert), (
        f"with cert, stack_plan should NOT BLOCK; got {blockers_with_cert}"
    )
    assert any("stack_plan" in w.lower() for w in warns_with_cert), (
        f"with cert, stack_plan should still WARN; got {warns_with_cert}"
    )
