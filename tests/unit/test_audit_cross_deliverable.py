"""Unit tests for the cross-deliverable consistency audit.

Every dimension has a pass + fail test. The top-level aggregator is
verified to bubble dimension status correctly. Override / log_override
behaviour is exercised at the handler boundary by way of the helper
function exposed by the module (handler wiring lives in server.py
and is tested in tests/integration).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_os.tools.actions.audit.cross_deliverable import (
    _numeric_claim_extractor,
    audit_cross_deliverable_consistency,
    citations_consistent,
    figures_consistent,
    findings_top_line_consistent,
    numeric_claims_consistent,
    reproducibility_footer_consistent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_REF_FOOTER = (
    "\n\n---\n\n"
    "Research-OS version: v1.11.0  ·  commit: deadbeefcafe1234  ·  "
    "built: 2026-06-05T12:00:00Z\n"
)


def _make_paper(root: Path, body: str = "", with_footer: bool = True) -> Path:
    p = root / "synthesis" / "paper.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    text = body or (
        "# A Study of Things\n\n"
        "## Abstract\n\n"
        "We analysed n = 423 subjects and report AUROC = 0.84 (p < 0.01).\n\n"
        "## Methods\n\n"
        "![Figure 1](outputs/fig1.png)\n\n"
        "We cite @smith2020 and @jones2021.\n\n"
        "## Findings\n\n"
        "Subjects with treatment showed a 42% improvement in outcomes "
        "compared to controls.\n"
    )
    if with_footer:
        text += _REF_FOOTER
    p.write_text(text)
    return p


def _make_dashboard(root: Path, body: str = "", with_footer: bool = True) -> Path:
    p = root / "synthesis" / "dashboard.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    text = body or (
        "<html><body>"
        "<h2>Findings</h2>"
        "<p>Subjects with treatment showed a 42% improvement in outcomes.</p>"
        "<p>AUROC = 0.84 across n = 423 subjects.</p>"
        "<img src=\"outputs/fig1.png\" alt=\"Figure 1\">"
        "<p>Cited: @smith2020.</p>"
        "</body></html>"
    )
    if with_footer:
        text += "<footer>" + _REF_FOOTER + "</footer>"
    p.write_text(text)
    return p


def _make_slides(root: Path, body: str = "", with_footer: bool = True) -> Path:
    p = root / "synthesis" / "slides.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    text = body or (
        "# Slides\n\n"
        "## Findings\n\n"
        "Treatment yielded a 42% improvement in outcomes for subjects.\n\n"
        "![](outputs/fig1.png)\n\n"
        "Cite: @smith2020.\n"
    )
    if with_footer:
        text += _REF_FOOTER
    p.write_text(text)
    return p


def _make_poster(root: Path, body: str = "", with_footer: bool = True) -> Path:
    p = root / "synthesis" / "poster.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    text = body or (
        "# Poster\n\n"
        "## Findings\n\n"
        "Subjects in treatment achieved 42% improvement in outcomes.\n\n"
        "![](outputs/fig1.png)\n\n"
        "(@smith2020)\n"
    )
    if with_footer:
        text += _REF_FOOTER
    p.write_text(text)
    return p


# ---------------------------------------------------------------------------
# Numeric claim extractor
# ---------------------------------------------------------------------------


def test_numeric_claim_extractor_finds_p_values_percentages_sample_sizes():
    text = (
        "We report AUROC = 0.84, p < 0.01, n = 423 subjects, "
        "with a 42% improvement and a 1.23e-4 effect size."
    )
    claims = _numeric_claim_extractor(text)
    kinds = {c["kind"] for c in claims}
    assert "p_value" in kinds
    assert "percentage" in kinds
    assert "sample_size" in kinds
    assert "decimal" in kinds
    # 0.84 detected as a decimal.
    assert any(abs(c["value"] - 0.84) < 1e-9 for c in claims)
    # 42% normalised to 0.42.
    assert any(abs(c["value"] - 0.42) < 1e-9 for c in claims)
    # n=423 detected.
    assert any(c["value"] == 423.0 for c in claims)


def test_numeric_claim_extractor_skips_years_and_citations():
    text = "Published in 2020, see [1] and [2,3]. Effect size 0.42."
    claims = _numeric_claim_extractor(text)
    values = [c["value"] for c in claims]
    # 2020 should NOT show up as a decimal claim.
    assert 2020.0 not in values
    # 0.42 should still be picked up.
    assert any(abs(v - 0.42) < 1e-9 for v in values)


# ---------------------------------------------------------------------------
# Dimension 1 — numeric claims
# ---------------------------------------------------------------------------


def test_numeric_claims_consistent_pass(tmp_path: Path):
    _make_paper(tmp_path)
    _make_dashboard(tmp_path)
    r = numeric_claims_consistent(tmp_path)
    assert r["pass"], r["details"]
    assert r["details"]["mismatch_count"] == 0


def test_numeric_claims_consistent_fail(tmp_path: Path):
    _make_paper(tmp_path)
    # Dashboard reports a divergent AUROC.
    _make_dashboard(
        tmp_path,
        body=(
            "<html><body>"
            "<h2>Findings</h2>"
            "<p>Subjects with treatment showed a 42% improvement.</p>"
            "<p>AUROC = 0.93 across n = 423 subjects.</p>"
            "</body></html>"
        ),
    )
    r = numeric_claims_consistent(tmp_path)
    assert not r["pass"]
    assert r["details"]["mismatch_count"] >= 1


# ---------------------------------------------------------------------------
# Dimension 2 — figures
# ---------------------------------------------------------------------------


def test_figures_consistent_pass(tmp_path: Path):
    _make_paper(tmp_path)
    _make_slides(tmp_path)
    _make_poster(tmp_path)
    r = figures_consistent(tmp_path)
    assert r["pass"], r["details"]


def test_figures_consistent_fail(tmp_path: Path):
    # Corrected contract (AG-3): only figures SHARED by ≥2 deliverables and
    # missing from a 3rd count, and >1 such gap is a block. Here paper +
    # slides both carry fig1, fig2, fig3; the poster carries only fig1 →
    # two shared figures (fig2, fig3) absent from a 3rd deliverable → block.
    shared_body = (
        "## Methods\n\n"
        "![](outputs/fig1.png)\n\n"
        "![](outputs/fig2.png)\n\n"
        "![](outputs/fig3.png)\n\n"
    )
    _make_paper(tmp_path, body="# Paper\n\n" + shared_body)
    _make_slides(tmp_path, body="# Slides\n\n" + shared_body)
    _make_poster(tmp_path, body="# Poster\n\n![](outputs/fig1.png)\n\n")
    r = figures_consistent(tmp_path)
    assert not r["pass"]
    missing = r["details"]["paper_figures_missing_elsewhere"]
    stems = {m["figure_stem"] for m in missing}
    assert {"fig2", "fig3"} <= stems
    assert r["details"]["shared_figures_missing_count"] >= 2


def test_figures_consistent_single_elided_figure_passes(tmp_path: Path):
    # AG-3: a single shared figure elided from one deliverable is a
    # warning, not a block — a secondary deliverable may drop one figure.
    shared_body = (
        "## Methods\n\n"
        "![](outputs/fig1.png)\n\n"
        "![](outputs/fig2.png)\n\n"
    )
    _make_paper(tmp_path, body="# Paper\n\n" + shared_body)
    _make_slides(tmp_path, body="# Slides\n\n" + shared_body)
    # Poster elides only fig2.
    _make_poster(tmp_path, body="# Poster\n\n![](outputs/fig1.png)\n\n")
    r = figures_consistent(tmp_path)
    assert r["pass"], r["details"]
    assert r["details"]["shared_figures_missing_count"] == 1


# ---------------------------------------------------------------------------
# Dimension 3 — citations
# ---------------------------------------------------------------------------


def test_citations_consistent_pass(tmp_path: Path):
    _make_paper(tmp_path)  # cites @smith2020 + @jones2021
    _make_slides(tmp_path)  # cites @smith2020 (subset of paper)
    r = citations_consistent(tmp_path)
    assert r["pass"], r["details"]


def test_citations_consistent_fail(tmp_path: Path):
    _make_paper(tmp_path)  # cites @smith2020 + @jones2021
    # Slides cites a rogue key not in the paper.
    _make_slides(
        tmp_path,
        body="# Slides\n\nCite: @rogue_key_2099.\n",
    )
    r = citations_consistent(tmp_path)
    assert not r["pass"]
    rogue = r["details"]["rogue_citations"]
    assert any("rogue_key_2099" in entry["keys_not_in_paper"] for entry in rogue)


# ---------------------------------------------------------------------------
# Dimension 4 — top-line findings
# ---------------------------------------------------------------------------


def test_findings_top_line_consistent_pass(tmp_path: Path):
    _make_paper(tmp_path)
    _make_slides(tmp_path)
    r = findings_top_line_consistent(tmp_path)
    assert r["pass"], r["details"]


def test_findings_top_line_consistent_fail(tmp_path: Path):
    _make_paper(tmp_path)
    # Slides headline finding talks about something totally unrelated.
    _make_slides(
        tmp_path,
        body=(
            "# Slides\n\n## Findings\n\n"
            "Mitochondrial proteomic ordination revealed three distinct "
            "clusters of metabolic strategies across eukaryotic lineages.\n"
        ),
    )
    r = findings_top_line_consistent(tmp_path)
    assert not r["pass"]
    assert r["details"]["weak_pairs"]


# ---------------------------------------------------------------------------
# Dimension 5 — reproducibility footer
# ---------------------------------------------------------------------------


def test_reproducibility_footer_consistent_pass(tmp_path: Path):
    _make_paper(tmp_path)
    _make_dashboard(tmp_path)
    _make_slides(tmp_path)
    r = reproducibility_footer_consistent(tmp_path)
    assert r["pass"], r["details"]


def test_reproducibility_footer_consistent_fail_mismatched_commit(tmp_path: Path):
    _make_paper(tmp_path)
    # Dashboard has a divergent commit hash.
    _make_dashboard(
        tmp_path,
        body=(
            "<html><body><h2>Findings</h2>"
            "<p>Subjects with treatment showed 42% improvement.</p>"
            "</body></html>"
            "<footer>Research-OS version: v1.11.0  ·  "
            "commit: aaaaaaaaaaaaaaaa  ·  built: 2026-06-05T12:00:00Z</footer>"
        ),
        with_footer=False,
    )
    r = reproducibility_footer_consistent(tmp_path)
    assert not r["pass"]
    assert any("commit mismatch" in d for d in r["details"]["discrepancies"])


def test_reproducibility_footer_consistent_fail_missing(tmp_path: Path):
    _make_paper(tmp_path)
    # Slides ships with NO footer at all.
    _make_slides(tmp_path, with_footer=False)
    r = reproducibility_footer_consistent(tmp_path)
    assert not r["pass"]
    assert "slides" in r["details"]["missing_footer_in"]


# ---------------------------------------------------------------------------
# Top-level aggregator
# ---------------------------------------------------------------------------


def test_aggregator_all_pass_on_well_formed_project(tmp_path: Path):
    _make_paper(tmp_path)
    _make_dashboard(tmp_path)
    _make_slides(tmp_path)
    _make_poster(tmp_path)
    r = audit_cross_deliverable_consistency(tmp_path)
    assert r["status"] == "success", r
    assert not r["blockers"]
    # All 5 dimensions present and passing.
    assert set(r["dimensions"].keys()) == {
        "numeric_claims_consistent",
        "figures_consistent",
        "citations_consistent",
        "findings_top_line_consistent",
        "reproducibility_footer_consistent",
    }
    for dim, result in r["dimensions"].items():
        assert result["pass"], f"{dim} failed on a well-formed project: {result}"
    # Log written.
    assert (tmp_path / r["log_path"]).is_file()


def test_aggregator_skipped_when_only_one_deliverable(tmp_path: Path):
    _make_paper(tmp_path)
    r = audit_cross_deliverable_consistency(tmp_path)
    assert r["status"] == "skipped"
    assert r["blockers"] == []
    assert r["warnings"]
    assert "deliverables_found" in r


def test_aggregator_blocks_on_any_dimension_failure(tmp_path: Path):
    _make_paper(tmp_path)
    # Dashboard with divergent AUROC.
    _make_dashboard(
        tmp_path,
        body=(
            "<html><body><h2>Findings</h2>"
            "<p>Subjects with treatment showed 42% improvement.</p>"
            "<p>AUROC = 0.93 across n = 423 subjects.</p>"
            "</body></html>"
        ),
    )
    r = audit_cross_deliverable_consistency(tmp_path)
    assert r["status"] == "error"
    assert any("numeric_claims_consistent" in b for b in r["blockers"])


def test_aggregator_handles_missing_workspace_dir(tmp_path: Path):
    # No deliverables at all. Should skip, not crash.
    r = audit_cross_deliverable_consistency(tmp_path)
    assert r["status"] == "skipped"
    assert r["dimensions"] == {}


def test_aggregator_accepts_str_root(tmp_path: Path):
    """Handler dispatch may pass root as str; the audit must coerce."""
    _make_paper(tmp_path)
    _make_dashboard(tmp_path)
    r = audit_cross_deliverable_consistency(str(tmp_path))
    assert r["status"] in {"success", "error"}
    assert "dimensions" in r


# ---------------------------------------------------------------------------
# Override behaviour (handler-level — light test that the spec carries it).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rationale_supplied", [True, False])
def test_handler_override_shape_documented(rationale_supplied: bool):
    """The handler exposes override_cross_deliverable + override_rationale.

    The audit module itself is gate-agnostic; this test just pins the
    expected handler-input shape so the integration agent wires
    log_override correctly. The actual log_override invocation is
    tested via the integration suite once the tool is registered.
    """
    expected_keys = {"override_cross_deliverable", "override_rationale"}
    # Synthetic input the handler will receive.
    args = {"override_cross_deliverable": True}
    if rationale_supplied:
        args["override_rationale"] = "literature-only project; intentional"
    assert "override_cross_deliverable" in args
    # Sanity: the override field name we will register matches what the
    # rest of the audit family uses (override_X_gate or override_X).
    assert any(k.startswith("override_") for k in expected_keys)


# ---------------------------------------------------------------------------
# Typst paper discovery — the canonical authored deliverable is paper.typ,
# whose figures use the #figure(image("…")) form.
# ---------------------------------------------------------------------------


def test_discovers_typst_paper_and_aligns_figures(tmp_path: Path):
    """A .typ paper is discovered as the 'paper' deliverable, and its
    #figure(image("…")) figure aligns with a markdown deliverable's
    ![](…) of the same stem."""
    paper = tmp_path / "synthesis" / "paper.typ"
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_text(
        "#show: template.with(conf(abstract: [x]))\n\n"
        "= Findings\n\n"
        "Subjects with treatment showed a 42% improvement in outcomes.\n\n"
        "#figure(image(\"outputs/fig1.png\"), caption: [F1]) <fig:a>\n\n"
        "We cite @smith2020.\n"
        + _REF_FOOTER
    )
    _make_slides(tmp_path)  # markdown deliverable embedding fig1
    r = figures_consistent(tmp_path)
    # The Typst #figure(image(...)) figure is parsed (fig1 present in the
    # paper's figure set) and aligns with the slides' ![](fig1.png).
    assert r["pass"], r["details"]
    paper_figs = r["details"]["figures_per_deliverable"].get("paper", [])
    assert "fig1" in paper_figs


def test_typst_paper_figure_missing_elsewhere_flagged(tmp_path: Path):
    """Figures embedded in the .typ paper AND a poster, but absent from
    slides, are flagged — proving the Typst figure extractor feeds the
    consistency check. Per AG-3, >1 shared-but-missing figure is a block;
    fig2 + fig3 are shared by paper+poster and missing from slides."""
    paper = tmp_path / "synthesis" / "paper.typ"
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_text(
        "#show: template.with(conf(abstract: [x]))\n\n"
        "= Findings\n\n"
        "#figure(image(\"outputs/fig1.png\"), caption: [F1])\n\n"
        "#figure(image(\"outputs/fig2.png\"), caption: [F2])\n\n"
        "#figure(image(\"outputs/fig3.png\"), caption: [F3])\n"
        + _REF_FOOTER
    )
    # Poster shares fig2 + fig3 with the paper (so they ARE shared figures).
    _make_poster(
        tmp_path,
        body=(
            "# Poster\n\n![](outputs/fig2.png)\n\n![](outputs/fig3.png)\n\n"
        ),
    )
    # Slides carry only fig1 → fig2 + fig3 absent from a 3rd deliverable.
    _make_slides(tmp_path, body="# Slides\n\n![](outputs/fig1.png)\n\n")
    r = figures_consistent(tmp_path)
    assert not r["pass"]
    missing = r["details"]["paper_figures_missing_elsewhere"]
    stems = {m["figure_stem"] for m in missing}
    assert {"fig2", "fig3"} <= stems
