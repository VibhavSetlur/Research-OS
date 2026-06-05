"""Regression tests for v1.5.0 — close audit gaps + reliability + paywall + freshness.

Covers the 6 surfaces listed in the v1.5.0 release plan:
  (a) Discussion synthesis emits paragraph per non-AGREES verdict
  (b) audit_synthesis default-deny when zero PDFs across literature-required steps
  (c) stale-state detection fires after 30 days
  (d) paywall memory skips known-bad URLs
  (e) intake_freshness returns 'skip' when intake is fresh + substantive
  (f) reliability log appends event lines
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _scaffold(tmp_path: Path) -> Path:
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    (tmp_path / "workspace" / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inputs" / "literature").mkdir(parents=True, exist_ok=True)
    return tmp_path


# -----------------------------------------------------------------
# (a) Discussion-from-verdicts emits paragraph per non-AGREES verdict
# -----------------------------------------------------------------

def test_discussion_from_verdicts_emits_paragraph_per_non_agrees(tmp_path):
    from research_os.tools.actions.synthesis.discussion_from_verdicts import (
        emit_discussion_paragraphs,
    )

    root = _scaffold(tmp_path)
    step = root / "workspace" / "02_dge"
    (step / "literature").mkdir(parents=True)
    (step / "literature" / "findings_vs_literature.md").write_text(
        "## Claim: HER2-positive samples cluster with TNBC under our embedding\n"
        "**Our finding:** Cluster K3 contains 12 HER2+ samples.\n"
        "**Literature says:** Wang 2023 reports HER2+ cluster with luminal subtypes.\n"
        "**Verdict:** DISAGREES\n"
        "**Citation:** Wang et al. 2023\n"
        "**Discussion implication:** The disagreement may reflect our use of "
        "stromal-deconvolved expression rather than bulk RNA. Reviewers will "
        "ask whether the deconvolution drove the clustering.\n"
        "\n"
        "## Claim: Pathway X is uniformly down-regulated\n"
        "**Our finding:** All 6 cohorts show downregulation of pathway X.\n"
        "**Literature says:** Smith 2024 also observed pathway X downregulation.\n"
        "**Verdict:** AGREES\n"
        "**Citation:** Smith 2024\n"
        "**Discussion implication:** Adds confirmatory evidence.\n"
    )

    res = emit_discussion_paragraphs(root)
    assert res["status"] == "success"
    # Only the DISAGREES verdict should generate a paragraph.
    assert res["appended_paragraphs"] == 1
    disc = (root / "synthesis" / "discussion.md").read_text()
    assert "HER2-positive samples" in disc
    assert "DISAGREES" in disc
    # AGREES claim should not appear in the auto-generated paragraph.
    assert "Pathway X is uniformly down-regulated" not in disc

    # Idempotent re-run replaces the auto-section without duplicating.
    res2 = emit_discussion_paragraphs(root)
    assert res2["status"] == "success"
    disc2 = (root / "synthesis" / "discussion.md").read_text()
    assert disc2.count("HER2-positive samples") == 1


# -----------------------------------------------------------------
# (b) audit_synthesis default-deny when zero PDFs
# -----------------------------------------------------------------

def test_audit_synthesis_default_denies_zero_pdfs(tmp_path):
    from research_os.tools.actions.audit import audit_synthesis

    root = _scaffold(tmp_path)
    paper = root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(
        "## Abstract\nWe report results that engage with the literature.\n"
        "## Introduction\nBackground context here.\n"
        "## Methods\nApproach detail here.\n"
        "## Results\nFindings here.\n"
        "## Discussion\nInterpretation here.\n"
        + "Lorem ipsum " * 100  # push word count past stub threshold
    )
    # One literature-required step with NO PDFs.
    step = root / "workspace" / "01_baseline"
    step.mkdir(parents=True)
    (step / "conclusions.md").write_text("## Findings\nReal findings.\n")
    (step / "literature").mkdir()  # empty

    res = audit_synthesis("synthesis/paper.md", root)
    assert any(
        "DEFAULT-DENY" in b or "zero PDFs" in b
        for b in res.get("blockers", [])
    ), f"expected DEFAULT-DENY blocker; got {res.get('blockers')}"

    # Override path: status should not include the zero-PDF blocker.
    res_ovr = audit_synthesis(
        "synthesis/paper.md",
        root,
        override_no_pdfs=True,
        override_rationale="closed field, structural unavailability",
    )
    assert not any(
        "DEFAULT-DENY" in b for b in res_ovr.get("blockers", [])
    )


# -----------------------------------------------------------------
# (c) stale-state detection fires after 30 days
# -----------------------------------------------------------------

def test_state_freshness_detects_stale_state(tmp_path):
    from research_os.tools.actions.state.freshness import state_freshness_check

    root = _scaffold(tmp_path)
    state_path = root / "workspace" / "state.json"
    state_path.write_text(json.dumps({"current_path": "main"}))
    old_ts = time.time() - 45 * 86400  # 45 days old
    os.utime(state_path, (old_ts, old_ts))

    res = state_freshness_check(root, stale_after_days=30)
    assert res["status"] == "success"
    assert res["is_stale"] is True
    assert any("state.json" in s for s in res["signals"])
    assert res["prompt_for_ai"]


def test_state_freshness_fresh_state_is_silent(tmp_path):
    from research_os.tools.actions.state.freshness import state_freshness_check

    root = _scaffold(tmp_path)
    state_path = root / "workspace" / "state.json"
    state_path.write_text(json.dumps({"current_path": "main"}))

    res = state_freshness_check(root, stale_after_days=30)
    assert res["status"] == "success"
    assert res["is_stale"] is False
    assert not res["signals"]


# -----------------------------------------------------------------
# (d) paywall memory skips known-bad URLs
# -----------------------------------------------------------------

def test_paywall_memory_skips_permanent_failure(tmp_path):
    from research_os.tools.actions.state.paywall_memory import (
        is_known_bad,
        record_failure,
    )

    root = _scaffold(tmp_path)
    url = "https://example.com/paywalled.pdf"

    pre = is_known_bad(root, url)
    assert pre["known_bad"] is False

    rec = record_failure(
        root,
        tool="tool_literature_download",
        target=url,
        reason="paywall",
        error_text="HTTP 402 Payment Required",
    )
    assert rec["status"] == "success"

    post = is_known_bad(root, url)
    assert post["known_bad"] is True
    assert post["reason"] == "paywall"


# -----------------------------------------------------------------
# (e) intake_freshness returns 'skip' when intake is fresh + substantive
# -----------------------------------------------------------------

def test_intake_freshness_skip_when_fresh_and_substantive(tmp_path):
    from research_os.tools.actions.data.intake_freshness import intake_freshness

    root = _scaffold(tmp_path)
    intake = root / "inputs" / "intake.md"
    body = (
        "# Project Intake\n\n"
        "## Research Question\n\n"
        "We are investigating whether stromal-deconvolved expression alters "
        "subtype clustering in breast cancer cohorts. Specifically we test "
        "whether HER2 positive tumors cluster with triple negative breast "
        "cancer after stromal removal, and we measure whether cluster "
        "membership predicts overall survival better than the PAM50 subtype "
        "classification across two independent cohorts. The deconvolution "
        "uses xCell signatures applied to bulk RNA seq from TCGA and METABRIC. "
        "Survival analysis uses Cox proportional hazards with standard "
        "covariate adjustment for age, stage, and treatment arm.\n\n"
        "## Data\n\nTCGA breast cancer cohort with paired clinical follow up, "
        "and METABRIC bulk RNA seq with matched survival outcomes. Both "
        "preprocessed via standard xCell deconvolution pipeline.\n\n"
        "## Hypotheses\n\n"
        "H1: HER2 positive tumors cluster with triple negative breast cancer "
        "subtype after stromal removal, distinct from the bulk RNA pattern.\n"
        "H2: Cluster membership predicts overall survival better than the "
        "PAM50 subtype classification across both cohorts.\n"
    )
    intake.write_text(body)

    res = intake_freshness(root, fresh_window_days=90)
    assert res["status"] == "success"
    assert res["recommended_depth"] == "skip", (
        f"expected skip for fresh substantive intake; got {res}"
    )

    # Force-age the intake → should become refresh-only.
    old_ts = time.time() - 120 * 86400
    os.utime(intake, (old_ts, old_ts))
    res2 = intake_freshness(root, fresh_window_days=90)
    assert res2["recommended_depth"] == "refresh-only"


def test_intake_freshness_full_when_missing(tmp_path):
    from research_os.tools.actions.data.intake_freshness import intake_freshness

    root = _scaffold(tmp_path)
    res = intake_freshness(root)
    assert res["status"] == "success"
    assert res["recommended_depth"] == "full"


# -----------------------------------------------------------------
# (f) reliability log appends event lines
# -----------------------------------------------------------------

def test_reliability_log_appends_event_and_report(tmp_path):
    from research_os.tools.actions.state.reliability import (
        log_event,
        reliability_report,
    )

    root = _scaffold(tmp_path)

    rec1 = log_event(
        root,
        "gate_fire",
        protocol_name="writing_discussion",
        payload={"gate": "tool_discussion_coverage_audit", "count": 1},
    )
    rec2 = log_event(
        root,
        "tool_error",
        protocol_name="literature_search",
        payload={"tool": "tool_literature_download", "reason": "paywall"},
    )
    rec3 = log_event(root, "protocol_complete", protocol_name="writing_discussion")
    assert rec1["status"] == "success"
    assert rec2["status"] == "success"
    assert rec3["status"] == "success"

    log = root / "workspace" / ".os_state" / "reliability.jsonl"
    assert log.exists()
    lines = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert len(lines) == 3
    assert lines[0]["event"] == "gate_fire"
    assert lines[1]["event"] == "tool_error"

    # Unknown event types are rejected.
    bad = log_event(root, "unknown_event_type")
    assert bad["status"] == "error"

    report = reliability_report(root)
    assert report["status"] == "success"
    assert report["events_total"] == 3
    assert report["by_type"]["gate_fire"] == 1
    assert report["by_type"]["tool_error"] == 1
    assert "reliability_report.md" in report["report_path"]


# -----------------------------------------------------------------
# Bonus: coherence audit flags an orphan paragraph
# -----------------------------------------------------------------

def test_audit_coherence_flags_orphan_paragraph(tmp_path):
    from research_os.tools.actions.audit.coherence import audit_coherence

    root = _scaffold(tmp_path)
    step = root / "workspace" / "01_dge"
    step.mkdir(parents=True)
    (step / "conclusions.md").write_text(
        "## Findings\n\n"
        "We performed differential expression on the TCGA breast cancer "
        "cohort using DESeq2. We identified 412 genes differentially "
        "expressed between HER2-positive and HER2-negative subtypes at "
        "FDR less than 0.05. The volcano plot shows clear separation.\n"
    )

    paper = root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(
        "## Results\n\n"
        "The differential expression analysis on TCGA breast cancer cohort "
        "with DESeq2 identified 412 differentially expressed genes at FDR "
        "less than 0.05 between HER2-positive and HER2-negative tumors.\n\n"
        "## Discussion\n\n"
        "The Mongolian capital of Ulaanbaatar experiences extreme winter "
        "temperatures that affect the gobi camel population in the steppes "
        "of central Asia. The yurts provide insulation during nomadic herding.\n"
    )

    res = audit_coherence(root, paper_path="synthesis/paper.md")
    assert res["status"] in {"success", "warning"}
    # The Mongolia paragraph is unrelated to the step's conclusions.
    assert res["orphan_count"] >= 1
    previews = " ".join(o["preview"] for o in res["orphan_paragraphs"])
    assert "Mongolian" in previews or "Ulaanbaatar" in previews
