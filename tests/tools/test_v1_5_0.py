"""v1.5.0 regression tests.

Covers the surfaces introduced in v1.5.0:

* Theme 1 (gap 1): discussion_from_verdicts emits one paragraph per
  non-AGREES verdict (DISAGREES / EXTENDS).
* Theme 1 (gap 2): audit_synthesis BLOCKs when papers_downloaded == 0
  across every literature-required step (override via override_no_pdfs).
* Theme 9: reliability log append + report.
* Theme 11: state_freshness_check fires after stale_after_days.
* Theme 12: paywall_memory is_known_bad short-circuits known-bad URLs.
* Theme 14: intake_freshness returns 'skip' when intake.md is fresh +
  substantive, 'full' when missing.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace


# ---------------------------------------------------------------------------
# Theme 1, gap 1 — discussion paragraphs per non-AGREES verdict
# ---------------------------------------------------------------------------


def _make_step_with_verdicts(root: Path, step_id: str, verdicts: list[dict]) -> Path:
    """Create a workspace step with a populated findings_vs_literature.md."""
    step = root / "workspace" / step_id
    (step / "literature").mkdir(parents=True)
    blocks = []
    for v in verdicts:
        block = (
            f"## Claim: {v['claim']}\n\n"
            f"**Verdict:** {v['verdict']}\n\n"
            f"**Citation:** {v.get('citation', 'Smith 2024')}\n\n"
        )
        if v.get("discussion"):
            block += f"**Discussion implication:** {v['discussion']}\n\n"
        blocks.append(block)
    (step / "literature" / "findings_vs_literature.md").write_text(
        "# Literature\n\n" + "\n".join(blocks)
    )
    return step


def test_discussion_from_verdicts_emits_paragraph_per_non_agrees(tmp_path):
    """v1.5.0 Theme 1: each DISAGREES / EXTENDS verdict gets one Discussion paragraph."""
    from research_os.tools.actions.synthesis.discussion_from_verdicts import (
        emit_discussion_paragraphs,
    )

    scaffold_minimal_workspace(tmp_path, "Test")
    _make_step_with_verdicts(
        tmp_path,
        "02_baseline",
        [
            {
                "claim": "Method A outperforms Method B on cohort X",
                "verdict": "DISAGREES",
                "citation": "Jones 2022",
                "discussion": (
                    "Jones et al. (2022) reported no significant "
                    "difference on a smaller cohort; our larger n "
                    "may explain the divergent estimate."
                ),
            },
            {
                "claim": "Effect persists under stratified analysis",
                "verdict": "EXTENDS",
                "citation": "Doe 2023",
                "discussion": (
                    "Doe (2023) tested only the marginal estimate; "
                    "we extend with subgroup-level results."
                ),
            },
            {
                "claim": "Baseline rates align with prior cohorts",
                "verdict": "AGREES",
                "citation": "Roe 2021",
                "discussion": "Consistent with the field; no paragraph needed.",
            },
        ],
    )

    result = emit_discussion_paragraphs(tmp_path)
    assert result["status"] == "success", result
    assert result["appended_paragraphs"] == 2, (
        f"expected 2 paragraphs (one per DISAGREES / EXTENDS), got "
        f"{result['appended_paragraphs']}"
    )

    disc_text = (tmp_path / "synthesis" / "discussion.md").read_text()
    assert "DISAGREES" in disc_text
    assert "EXTENDS" in disc_text
    # AGREES verdict must NOT produce a paragraph.
    assert "Roe 2021" not in disc_text, (
        "AGREES verdict accidentally emitted a paragraph"
    )

    # Idempotent — re-running replaces the auto-section, not duplicates it.
    result2 = emit_discussion_paragraphs(tmp_path)
    disc_text_2 = (tmp_path / "synthesis" / "discussion.md").read_text()
    assert disc_text_2.count("ro:discussion_from_verdicts") == 2, (
        "auto-section markers should appear exactly once (top + footer)"
    )
    assert result2["appended_paragraphs"] == 2


# ---------------------------------------------------------------------------
# Theme 1, gap 2 — audit_synthesis default-deny on zero PDFs
# ---------------------------------------------------------------------------


def test_audit_synthesis_blocks_on_zero_pdfs(tmp_path):
    """v1.5.0 Theme 1: synthesis BLOCKs when papers_downloaded == 0 across all literature-required steps."""
    import yaml as _yaml
    from research_os.tools.actions.audit.audit import audit_synthesis

    scaffold_minimal_workspace(tmp_path, "Test")

    # Two steps, both literature-required, neither with any PDFs downloaded.
    for sid in ("02_baseline", "03_followup"):
        step = tmp_path / "workspace" / sid
        step.mkdir(parents=True, exist_ok=True)
        (step / "conclusions.md").write_text(
            "## Findings\n\nSubstantive prose " + ("blah " * 40)
            + "\n\n## Decision\n\nProceed.\n"
        )
        (step / "step_summary.yaml").write_text(
            _yaml.safe_dump({
                "step_id": sid,
                "literature_required": True,
                "literature": {"papers_downloaded": 0, "claims_grounded": 0},
            })
        )
        # NO literature/*.pdf

    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_text(
        "## Abstract\n\n" + "abc " * 80
        + "\n\n## Introduction\n\n" + "intro " * 80
        + "\n\n## Methods\n\n" + "method " * 100
        + "\n\n## Results\n\n" + "result " * 100
        + "\n\n## Discussion\n\n" + "discussion " * 80
        + "\n\n## References\n\n- ref\n"
    )

    # WITHOUT override: must BLOCK.
    res = audit_synthesis("synthesis/paper.md", tmp_path)
    blockers = res.get("blockers", [])
    assert any("papers_downloaded" in b.lower() or "zero pdf" in b.lower() or "no pdf" in b.lower() for b in blockers), (
        f"expected zero-PDF blocker; got blockers={blockers}"
    )

    # WITH override: clears the zero-PDF gate (but other gates may still apply).
    res_ovr = audit_synthesis(
        "synthesis/paper.md", tmp_path,
        override_no_pdfs=True, override_rationale="known-low-PDF audit",
    )
    ovr_blockers = res_ovr.get("blockers", [])
    assert not any("papers_downloaded" in b.lower() or "zero pdf" in b.lower() or "no pdf" in b.lower() for b in ovr_blockers), (
        f"override should clear zero-PDF blocker; got blockers={ovr_blockers}"
    )


# ---------------------------------------------------------------------------
# Theme 9 — reliability log append + report
# ---------------------------------------------------------------------------


def test_reliability_log_event_and_report(tmp_path):
    """v1.5.0 Theme 9: log_event appends + reliability_report aggregates."""
    from research_os.tools.actions.state.reliability import (
        log_event,
        reliability_report,
    )

    scaffold_minimal_workspace(tmp_path, "Test")

    # Log a few events.
    r1 = log_event(
        tmp_path, "gate_fire",
        protocol_name="audit_and_validation",
        payload={"gate": "completeness", "step_id": "03_eda"},
    )
    assert r1["status"] == "success"
    log_path = tmp_path / r1["log_path"]
    assert log_path.exists()

    log_event(tmp_path, "tool_error", protocol_name="writing_results")
    log_event(tmp_path, "gate_fire", protocol_name="audit_and_validation")

    # Bad event_type returns an error.
    bad = log_event(tmp_path, "unknown_event_type")
    assert bad["status"] == "error"

    # Report aggregates.
    rep = reliability_report(tmp_path)
    assert rep["status"] == "success"
    assert rep["events_total"] == 3
    assert rep["by_type"].get("gate_fire") == 2
    assert rep["by_type"].get("tool_error") == 1
    report_md = (tmp_path / "workspace" / "logs" / "reliability_report.md").read_text()
    assert "gate_fire" in report_md
    assert "tool_error" in report_md


# ---------------------------------------------------------------------------
# Theme 11 — stale-state detection
# ---------------------------------------------------------------------------


def test_state_freshness_fires_after_threshold(tmp_path):
    """v1.5.0 Theme 11: state_freshness_check detects state.json > threshold days."""
    from research_os.tools.actions.state.freshness import state_freshness_check

    scaffold_minimal_workspace(tmp_path, "Test")
    state = tmp_path / "workspace" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text('{"current_path": "main"}')

    # Backdate state.json by 45 days.
    old = time.time() - 45 * 86400
    os.utime(state, (old, old))

    res = state_freshness_check(tmp_path, stale_after_days=30)
    assert res["status"] == "success"
    assert res["is_stale"] is True, f"should be stale; got {res}"
    assert any("state.json" in s.lower() for s in res["signals"])
    assert res["prompt_for_ai"], "stale state must surface a prompt"

    # Fresh state (touch to now) should clear.
    now = time.time()
    os.utime(state, (now, now))
    res2 = state_freshness_check(tmp_path, stale_after_days=30)
    assert res2["is_stale"] is False, f"fresh state.json should not be stale; got {res2}"


# ---------------------------------------------------------------------------
# Theme 12 — paywall memory short-circuit
# ---------------------------------------------------------------------------


def test_paywall_memory_skips_known_bad(tmp_path):
    """v1.5.0 Theme 12: is_known_bad short-circuits future download attempts."""
    from research_os.tools.actions.state.paywall_memory import (
        is_known_bad,
        list_failures,
        record_failure,
    )

    scaffold_minimal_workspace(tmp_path, "Test")

    bad_url = "https://elsevier.example.com/article/10.1016/j.cell.2024.05.001"

    # Initially: not known-bad.
    assert is_known_bad(tmp_path, bad_url) == {"known_bad": False, "prior_attempts": 0}

    # Record a permanent paywall.
    rec = record_failure(
        tmp_path,
        tool="tool_literature_download",
        target=bad_url,
        reason="paywall",
        error_text="Unpaywall: closed access",
        permanent=True,
    )
    assert rec["status"] == "success"

    # Now it must short-circuit.
    check = is_known_bad(tmp_path, bad_url)
    assert check["known_bad"] is True
    assert check["reason"] == "paywall"

    # DOI normalisation: same DOI in a different URL shape also hits.
    same_doi_url = "https://doi.org/10.1016/j.cell.2024.05.001"
    check2 = is_known_bad(tmp_path, same_doi_url)
    assert check2["known_bad"] is True, (
        f"DOI normalisation should match; got {check2}"
    )

    # list_failures returns the recorded failure.
    listed = list_failures(tmp_path)
    assert listed["status"] == "success"
    assert listed["permanent_count"] == 1


# ---------------------------------------------------------------------------
# Theme 14 — intake_freshness recommendation
# ---------------------------------------------------------------------------


def test_intake_freshness_skip_when_fresh(tmp_path):
    """v1.5.0 Theme 14: substantive + fresh intake → 'skip'; missing → 'full'."""
    from research_os.tools.actions.data.intake_freshness import intake_freshness

    scaffold_minimal_workspace(tmp_path, "Test")

    # Missing intake → 'full'.
    res = intake_freshness(tmp_path)
    assert res["status"] == "success"
    assert res["recommended_depth"] == "full"

    # Substantive + fresh → 'skip'.
    intake = tmp_path / "inputs" / "intake.md"
    intake.parent.mkdir(parents=True, exist_ok=True)
    intake.write_text(
        "# Intake\n\n## Question\n\n"
        + "We investigate whether feature X drives outcome Y in cohort Z. "
        + "This is a substantive description of the project. "
        * 30
        + "\n\n## Data\n\n"
        + "We have 500 patient records covering 2019-2023 across 3 sites. "
        * 20
    )

    res = intake_freshness(tmp_path, fresh_window_days=90)
    assert res["recommended_depth"] == "skip", (
        f"substantive + fresh intake should skip; got {res}"
    )

    # Older than window → 'refresh-only'.
    old = time.time() - 120 * 86400
    os.utime(intake, (old, old))
    res_old = intake_freshness(tmp_path, fresh_window_days=90)
    assert res_old["recommended_depth"] == "refresh-only", (
        f"old but substantive intake should refresh-only; got {res_old}"
    )


# ---------------------------------------------------------------------------
# Theme 11 (bonus) — audit_coherence flags orphan paragraphs
# ---------------------------------------------------------------------------


def test_audit_coherence_flags_orphan_paragraphs(tmp_path):
    """v1.5.0 Theme 11: audit_coherence flags Discussion paragraphs not grounded in any step."""
    from research_os.tools.actions.audit.coherence import audit_coherence

    scaffold_minimal_workspace(tmp_path, "Test")

    # Step about ribosome biogenesis.
    step = tmp_path / "workspace" / "02_ribosome_qc"
    step.mkdir(parents=True)
    (step / "conclusions.md").write_text(
        "## Findings\n\n"
        "Ribosome biogenesis factors RPS6 and RPL10 were enriched in "
        "the upregulated gene set across all three replicates of the "
        "knockout-versus-control comparison. The enrichment was stable "
        "under bootstrap resampling and recapitulated when we filtered "
        "for transcripts with TPM > 5.\n\n"
        "## Decision\n\nProceed to translation-rate measurements.\n"
    )

    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_text(
        "## Results\n\n"
        "Ribosome biogenesis factors RPS6 and RPL10 were enriched in "
        "the upregulated gene set across all three replicates of the "
        "knockout-versus-control comparison.\n\n"
        "## Discussion\n\n"
        "Mitochondrial fission factors regulate apoptosis in hepatocytes "
        "via cytochrome-c release, which has been characterised in "
        "primary liver organoids.\n\n"
    )

    res = audit_coherence(tmp_path)
    assert res["status"] in ("success", "warning")
    assert res["orphan_count"] >= 1, (
        f"orphan discussion paragraph should be flagged; got {res}"
    )
    flagged_texts = " ".join(o["preview"] for o in res["orphan_paragraphs"])
    assert "mitochondrial" in flagged_texts.lower()
