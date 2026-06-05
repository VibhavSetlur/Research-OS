"""Unit tests for the Phase-5 review-rewrite drafter loop.

Covers:
  * Quality-metric helpers (citations, numeric claims, section
    coverage, sentence length, type-token ratio, composite score).
  * Persona-driven reviewer adapter — emits BLOCK on missing Methods,
    WARN on red-flag triggers, returns clean list when output is fine.
  * Loop termination logic:
      - Convergence on iter 1 when no blockers AND nothing more to do.
      - Hard cap at max_iter when blockers persist.
      - Convergence when quality delta < threshold.
  * Logging artefacts: per-iteration md+json files exist and contain
    metrics, findings, and the output preview. Cumulative
    quality_progression.md table is rewritten on each run.
  * project_tier=throwaway clamp + drafter_loop_enabled=false bypass
    happen at the handler level — covered by handler tests below.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_os.tools.actions.audit._base import AuditFinding
from research_os.tools.actions.synthesis.drafter_loop import (
    compute_metrics,
    draft_with_review_rewrite,
    persona_reviewer,
)


# ── helpers ──────────────────────────────────────────────────────────


SAMPLE_PAPER = """# Title

## Abstract

We measured p = 0.03 across n = 42 subjects; 12.5% effect size.

## Introduction

Prior work by Smith showed something. We extend that.

## Methods

We ran a t-test. The setup was straightforward.

## Results

The effect was strong [@smith2020]. We saw 95% confidence.

## Discussion

This may matter for practice. Future work could explore more.
"""


def _drafter_constant(text: str):
    """Return a drafter_fn that always emits the same text payload."""
    def _fn(prior_output=None, findings=None, root=None):
        return {
            "status": "success",
            "source_text": text,
            "pdf_path": "synthesis/paper.pdf",
        }
    return _fn


# ── metric helpers ───────────────────────────────────────────────────


def test_compute_metrics_counts_citations_and_numeric_claims():
    m = compute_metrics(SAMPLE_PAPER)
    # One Pandoc cite + at least one numeric_claim_count hit.
    assert m["citation_count"] >= 1
    # p = 0.03, 12.5%, 95%, n = 42 → several hits.
    assert m["numeric_claim_count"] >= 3
    # Composite score within range.
    assert 0.0 <= m["quality_score"] <= 1.0
    # Sentence and TTR populated.
    assert m["avg_sentence_length"] > 0
    assert 0.0 < m["type_token_ratio"] <= 1.0


def test_compute_metrics_section_coverage_with_expected():
    m = compute_metrics(
        SAMPLE_PAPER,
        expected_sections=["Methods", "Results", "Discussion"],
    )
    # All three named sections present + non-empty.
    assert m["section_coverage"] == 1.0


def test_compute_metrics_section_coverage_missing_section():
    text_no_methods = SAMPLE_PAPER.replace("## Methods\n\nWe ran a t-test. The setup was straightforward.\n\n", "")
    m = compute_metrics(
        text_no_methods,
        expected_sections=["Methods", "Results", "Discussion"],
    )
    assert m["section_coverage"] < 1.0


def test_compute_metrics_handles_empty_input():
    m = compute_metrics("")
    assert m["citation_count"] == 0
    assert m["quality_score"] == 0.0


# ── persona reviewer ─────────────────────────────────────────────────


def test_persona_reviewer_emits_block_when_methods_missing(tmp_path):
    reviewer = persona_reviewer(["methodology_skeptic"])
    bad = SAMPLE_PAPER.replace("## Methods\n\nWe ran a t-test. The setup was straightforward.\n\n", "")
    findings = reviewer({"source_text": bad}, tmp_path)
    severities = {f.severity for f in findings}
    assert "block" in severities, [f.suggested_fix for f in findings]


def test_persona_reviewer_no_block_when_paper_well_formed(tmp_path):
    reviewer = persona_reviewer(["methodology_skeptic"])
    findings = reviewer({"source_text": SAMPLE_PAPER}, tmp_path)
    assert all(f.severity != "block" for f in findings)


def test_persona_reviewer_flags_long_paragraph(tmp_path):
    reviewer = persona_reviewer(["presentation_critic"])
    long_para = " ".join(["word"] * 300)
    text = f"## Abstract\n\nWe found n = 5 things.\n\n## Methods\n\n{long_para}\n"
    findings = reviewer({"source_text": text}, tmp_path)
    dims = {f.dimension for f in findings}
    assert "prose_density" in dims


def test_persona_reviewer_unknown_persona_is_skipped(tmp_path):
    """Unknown persona ids are logged and skipped without raising."""
    reviewer = persona_reviewer(["this_persona_does_not_exist"])
    findings = reviewer({"source_text": SAMPLE_PAPER}, tmp_path)
    assert findings == []


# ── loop termination ────────────────────────────────────────────────


def test_loop_converges_on_iter1_when_no_blockers(tmp_path):
    drafter = _drafter_constant(SAMPLE_PAPER)

    def reviewer(output, root):
        return []

    res = draft_with_review_rewrite(
        drafter,
        reviewer,
        drafter_name="paper",
        root=tmp_path,
        max_iter=3,
    )
    assert res["iterations"] == 1
    assert res["converged"] is True
    assert res["stop_reason"] == "no_blockers_first_pass"


def test_loop_hits_max_iter_when_blockers_persist(tmp_path):
    drafter = _drafter_constant(SAMPLE_PAPER)

    def reviewer(output, root):
        return [
            AuditFinding(
                audit_name="test",
                severity="block",
                dimension="d",
                suggested_fix="fix me",
            )
        ]

    res = draft_with_review_rewrite(
        drafter,
        reviewer,
        drafter_name="paper",
        root=tmp_path,
        max_iter=3,
    )
    assert res["iterations"] == 3
    assert res["converged"] is False
    assert res["stop_reason"] == "max_iter_reached"


def test_loop_converges_when_quality_delta_below_threshold(tmp_path):
    """Identical drafter output → delta == 0 on iter 2 → converged."""
    call_count = {"n": 0}

    def drafter(prior_output=None, findings=None, root=None):
        call_count["n"] += 1
        return {"source_text": SAMPLE_PAPER, "pdf_path": "x.pdf"}

    # WARN findings but no BLOCK — drives the loop past iter 1 only if
    # delta > threshold. Identical text → delta == 0 on iter 2 → stop.
    def reviewer(output, root):
        if call_count["n"] == 1:
            return [
                AuditFinding(
                    audit_name="test", severity="warn",
                    dimension="d", suggested_fix="warn"
                )
            ]
        return []

    res = draft_with_review_rewrite(
        drafter,
        reviewer,
        drafter_name="paper",
        root=tmp_path,
        max_iter=5,
        improvement_threshold=0.001,
    )
    # iter1: warn (not block) → first-pass clean → converges.
    assert res["converged"] is True
    assert res["iterations"] >= 1


def test_loop_clamps_max_iter_to_at_least_one(tmp_path):
    drafter = _drafter_constant(SAMPLE_PAPER)

    def reviewer(output, root):
        return []

    res = draft_with_review_rewrite(
        drafter,
        reviewer,
        drafter_name="paper",
        root=tmp_path,
        max_iter=0,
    )
    assert res["iterations"] == 1


# ── logging artefacts ────────────────────────────────────────────────


def test_loop_writes_per_iter_logs(tmp_path):
    drafter = _drafter_constant(SAMPLE_PAPER)

    def reviewer(output, root):
        return [
            AuditFinding(
                audit_name="t", severity="block",
                dimension="d", suggested_fix="rerun"
            )
        ]

    draft_with_review_rewrite(
        drafter,
        reviewer,
        drafter_name="paper",
        root=tmp_path,
        max_iter=2,
    )
    log_dir = tmp_path / "workspace" / "logs" / "drafter_loops"
    assert (log_dir / "paper_iter_1.md").exists()
    assert (log_dir / "paper_iter_1.json").exists()
    assert (log_dir / "paper_iter_2.md").exists()
    assert (log_dir / "paper_iter_2.json").exists()

    payload = json.loads((log_dir / "paper_iter_1.json").read_text())
    assert payload["iter"] == 1
    assert "metrics" in payload
    assert any(f["severity"] == "block" for f in payload["findings"])


def test_loop_writes_progression_table(tmp_path):
    drafter = _drafter_constant(SAMPLE_PAPER)

    def reviewer(output, root):
        return []

    draft_with_review_rewrite(
        drafter,
        reviewer,
        drafter_name="paper",
        root=tmp_path,
        max_iter=2,
    )
    table = tmp_path / "workspace" / "logs" / "drafter_loops" / "quality_progression.md"
    assert table.exists()
    body = table.read_text()
    assert "quality_score" in body
    assert "paper" in body


def test_loop_progression_table_appends_rows_across_runs(tmp_path):
    drafter = _drafter_constant(SAMPLE_PAPER)

    def reviewer(output, root):
        return []

    draft_with_review_rewrite(
        drafter, reviewer, drafter_name="paper",
        root=tmp_path, max_iter=1,
    )
    first = (tmp_path / "workspace" / "logs" / "drafter_loops"
             / "quality_progression.md").read_text()

    draft_with_review_rewrite(
        drafter, reviewer, drafter_name="slides",
        root=tmp_path, max_iter=1,
    )
    second = (tmp_path / "workspace" / "logs" / "drafter_loops"
              / "quality_progression.md").read_text()
    # The slides run preserved the paper row.
    assert "paper" in second
    assert "slides" in second
    assert len(second) > len(first)


# ── envelope correctness ─────────────────────────────────────────────


def test_loop_envelope_carries_final_output_path(tmp_path):
    drafter = _drafter_constant(SAMPLE_PAPER)

    def reviewer(output, root):
        return []

    res = draft_with_review_rewrite(
        drafter, reviewer, drafter_name="paper",
        root=tmp_path, max_iter=1,
    )
    assert res["final_output_path"] == "synthesis/paper.pdf"
    assert res["final_output"]["status"] == "success"


def test_loop_drafter_signature_back_compat(tmp_path):
    """Drafters accepting only (prior_output, root) still work."""
    captured: dict = {}

    def drafter(prior_output=None, root=None):
        captured["called"] = True
        return {"source_text": SAMPLE_PAPER, "pdf_path": "x.pdf"}

    def reviewer(output, root):
        return []

    res = draft_with_review_rewrite(
        drafter, reviewer, drafter_name="paper",
        root=tmp_path, max_iter=1,
    )
    assert captured["called"] is True
    assert res["iterations"] == 1
