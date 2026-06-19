"""Regression tests for quality-gate false-block / false-pass bugs.

Each test pins a concrete scenario that previously produced the WRONG
verdict (a false ship-block or a silent pass) and now produces the right
one. Topic-named + flat, one section per finding.

* AG-1 — a "84%" claim grounded by a corpus value stored as `84` / `0.84`.
* AG-2 — two DIFFERENT metrics (AUROC 0.84 vs slope 0.86) must not BLOCK
         the cross-deliverable numeric-consistency gate (no shared anchor).
* AG-3 — a poster eliding ONE shared figure is a warning, not a block;
         >1 missing is a block.
* AG-4 — references under `# References` / `### References` (not `## `)
         must still ground cited keys.

No mocks: every test scaffolds a real project root on ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.audit.claim_grounding import audit_claims
from research_os.tools.actions.audit.content_depth import audit_references_present
from research_os.tools.actions.audit.cross_deliverable import (
    figures_consistent,
    numeric_claims_consistent,
)


# ---------------------------------------------------------------------------
# AG-1 — percent claim grounded by a non-percent corpus value
# ---------------------------------------------------------------------------


def test_ag1_percent_claim_grounded_by_raw_integer(tmp_path: Path):
    """A `84%` claim should be GROUNDED when the workspace stores it as
    the raw percent (`84`) — the old matcher divided the claim by 100
    (0.84) and never tried the ×100 variant, so it false-blocked."""
    ws = tmp_path / "workspace" / "01_eda" / "outputs" / "reports"
    ws.mkdir(parents=True)
    (ws / "summary.md").write_text("accuracy,84\nrecall,84\n")
    syn = tmp_path / "synthesis"
    syn.mkdir()
    (syn / "paper.md").write_text("# Paper\n\nAccuracy reached 84%.\n")

    res = audit_claims(tmp_path)
    assert res["ungrounded"] == 0, res.get("ungrounded_claims")
    assert res["status"] == "success"


def test_ag1_percent_claim_grounded_by_fraction(tmp_path: Path):
    """Same claim, but the corpus stores the fraction (`0.84`)."""
    ws = tmp_path / "workspace" / "01_eda" / "outputs" / "reports"
    ws.mkdir(parents=True)
    (ws / "summary.md").write_text("metric,value\nauroc,0.84\n")
    syn = tmp_path / "synthesis"
    syn.mkdir()
    (syn / "paper.md").write_text("# Paper\n\nAUROC was 84%.\n")

    res = audit_claims(tmp_path)
    assert res["ungrounded"] == 0, res.get("ungrounded_claims")


# ---------------------------------------------------------------------------
# AG-2 — different metrics must not be a numeric-inconsistency BLOCK
# ---------------------------------------------------------------------------


def test_ag2_different_metrics_do_not_block(tmp_path: Path):
    """AUROC 0.84 in the paper and slope 0.86 in the poster are two
    DIFFERENT metrics — within 10× tolerance but not the same claim, so
    the gate must PASS (downgrade to a warning at most)."""
    syn = tmp_path / "synthesis"
    syn.mkdir(parents=True)
    paper = syn / "paper.md"
    poster = syn / "poster.md"
    paper.write_text("# Paper\n\nThe model AUROC = 0.84 on the test set.\n")
    poster.write_text("# Poster\n\nThe fitted slope = 0.86 was positive.\n")

    res = numeric_claims_consistent(
        tmp_path, deliverables={"paper": paper, "poster": poster}
    )
    assert res["pass"], res["details"]
    assert res["details"]["mismatch_count"] == 0


def test_ag2_same_metric_still_blocks(tmp_path: Path):
    """The same metric (AUROC) at two near-but-different values across
    deliverables IS a genuine inconsistency → still a block."""
    syn = tmp_path / "synthesis"
    syn.mkdir(parents=True)
    paper = syn / "paper.md"
    poster = syn / "poster.md"
    paper.write_text("# Paper\n\nThe model AUROC = 0.84 on the test set.\n")
    poster.write_text("# Poster\n\nWe report AUROC = 0.86 overall.\n")

    res = numeric_claims_consistent(
        tmp_path, deliverables={"paper": paper, "poster": poster}
    )
    assert not res["pass"], res["details"]
    assert res["details"]["mismatch_count"] >= 1


# ---------------------------------------------------------------------------
# AG-3 — one elided shared figure is a warning, not a block
# ---------------------------------------------------------------------------


def test_ag3_one_missing_shared_figure_passes(tmp_path: Path):
    """fig1 + fig2 in paper & slides; the poster elides fig2 only. One
    shared figure missing from a 3rd deliverable = warning → PASS."""
    syn = tmp_path / "synthesis"
    syn.mkdir(parents=True)
    paper = syn / "paper.md"
    slides = syn / "slides.md"
    poster = syn / "poster.md"
    paper.write_text("![](figures/fig1.png)\n\n![](figures/fig2.png)\n")
    slides.write_text("![](figures/fig1.png)\n\n![](figures/fig2.png)\n")
    poster.write_text("![](figures/fig1.png)\n")

    res = figures_consistent(
        tmp_path, deliverables={"paper": paper, "slides": slides, "poster": poster}
    )
    assert res["pass"], res["details"]
    assert res["details"]["shared_figures_missing_count"] == 1


def test_ag3_two_missing_shared_figures_block(tmp_path: Path):
    """When >1 shared figure is missing from a 3rd deliverable, the
    deliverables genuinely disagree → block."""
    syn = tmp_path / "synthesis"
    syn.mkdir(parents=True)
    paper = syn / "paper.md"
    slides = syn / "slides.md"
    poster = syn / "poster.md"
    body = (
        "![](figures/fig1.png)\n\n![](figures/fig2.png)\n\n"
        "![](figures/fig3.png)\n"
    )
    paper.write_text(body)
    slides.write_text(body)
    poster.write_text("![](figures/fig1.png)\n")  # missing fig2 AND fig3

    res = figures_consistent(
        tmp_path, deliverables={"paper": paper, "slides": slides, "poster": poster}
    )
    assert not res["pass"], res["details"]
    assert res["details"]["shared_figures_missing_count"] >= 2


# ---------------------------------------------------------------------------
# AG-4 — References at a non-`## ` heading depth still grounds cites
# ---------------------------------------------------------------------------


def test_ag4_references_under_h1_heading(tmp_path: Path):
    """A `# References` heading (single hash) must ground the cited key —
    the old `^##\\s+references` regex saw an empty body and reported the
    key missing → block."""
    text = (
        "# Paper\n\nWe build on prior work [@smith2020].\n\n"
        "# References\n\n- @smith2020 — Smith et al., 2020.\n"
    )
    res = audit_references_present(text, typst=False)
    assert res["blockers"] == [], res["blockers"]


def test_ag4_references_under_h3_heading(tmp_path: Path):
    """A `### References` heading (three hashes) must ground the cited key."""
    text = (
        "## Body\n\nAs shown by [@jones2021].\n\n"
        "### References\n\n- @jones2021 — Jones, 2021.\n"
    )
    res = audit_references_present(text, typst=False)
    assert res["blockers"] == [], res["blockers"]


def test_ag4_missing_reference_still_blocks(tmp_path: Path):
    """Sanity: a cited key with NO matching References entry still blocks
    (the AG-4 fix widens heading matching, it does not weaken the check)."""
    text = (
        "# Paper\n\nWe rely on [@ghost1999].\n\n"
        "# References\n\n- @real2000 — Real, 2000.\n"
    )
    res = audit_references_present(text, typst=False)
    assert any("ghost1999" in b for b in res["blockers"]), res["blockers"]
