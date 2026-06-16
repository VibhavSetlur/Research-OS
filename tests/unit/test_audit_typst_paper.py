"""Dual-format (Typst) coverage for the structural audit family.

Synthesis is authored as ``synthesis/paper.typ`` (Typst), but the audit
family historically parsed only Markdown — it hardcoded
``synthesis/paper.md`` and matched ``## heading`` / ``![](…)`` syntax,
so on a real Typst project every structural gate silently no-op'd.

These tests prove the audits now (a) resolve the ``.typ`` paper without
being told its path and (b) find sections, figures, the bibliography,
and numeric claims in Typst markup. The pre-existing Markdown tests in
the other audit test modules are the regression guard for the Markdown
path; this file is the proof for Typst. Topic-named + flat per the
test-layout convention.
"""

from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.audit._paper import (
    figure_refs,
    has_references,
    has_section,
    is_typst,
    resolve_paper_path,
    section_body,
)
from research_os.tools.actions.audit.audit import audit_synthesis
from research_os.tools.actions.audit.claim_grounding import (
    audit_claims,
    extract_claims,
)
from research_os.tools.actions.audit.coherence import audit_coherence
from research_os.tools.actions.audit.content_depth import (
    section_substantiveness,
)
from research_os.tools.actions.audit.redteam import redteam_scaffold


# A small but complete Typst paper. Sections are ``=`` headings; the
# abstract lives in the template ``conf(abstract: [ … ])`` block; the
# figure uses the canonical ``#figure(image("…"))`` form; references are
# an external ``#bibliography(…)`` directive. The ``//`` comment carries
# a number (999) that must NOT be picked up as a claim.
_PAPER_TYP = """\
#import "_typst_templates/generic_two_column.typ": template, conf
#show: template.with(conf(
  title: [A Study of Things],
  abstract: [
    We applied PCA and found a 42% reduction in noise across n = 100
    samples (p < 0.01). We demonstrate this holds out of sample.
  ],
))

= Introduction

Per (Smith 2024). Per (Jones 2023). Per (Doe 2024). In this study, we
report a 42% reduction in noise. // target ~999 words eventually

= Methods

We ran the alpha, beta, and gamma steps in sequence.

= Results

The effect was strong (p = 0.01, 95% CI [0.1, 0.3]).
#figure(image("figures/fig1.png"), caption: [Noise reduction.]) <fig:a>

= Discussion

Our findings extend prior work in the area.

== Limitations

The cohort is limited; we cannot fully generalize. Caveats remain.

Future work should replicate the result in a larger sample.

#bibliography("biblio.yml")
"""


def _seed_typst_paper(root: Path) -> Path:
    p = root / "synthesis" / "paper.typ"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_PAPER_TYP)
    return p


# ---------------------------------------------------------------------------
# _paper helpers
# ---------------------------------------------------------------------------


def test_resolve_prefers_typ_over_md(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "synthesis" / "paper.md").write_text("# md\n")
    (tmp_path / "synthesis" / "paper.typ").write_text("= typ\n")
    assert resolve_paper_path(tmp_path) == "synthesis/paper.typ"


def test_resolve_falls_back_to_typ_when_nothing_present(tmp_path: Path):
    # No paper on disk → default to the canonical authored path, NOT the
    # legacy markdown name.
    assert resolve_paper_path(tmp_path) == "synthesis/paper.typ"


def test_resolve_finds_legacy_markdown(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "synthesis" / "report.md").write_text("# report\n")
    assert resolve_paper_path(tmp_path) == "synthesis/report.md"


def test_section_and_figure_helpers_parse_typst():
    assert is_typst("synthesis/paper.typ")
    assert has_section(_PAPER_TYP, "methods", True)
    assert has_section(_PAPER_TYP, "discussion", True)
    # Sub-heading kept inside the parent section body.
    disc = section_body(_PAPER_TYP, "discussion", True)
    assert "Limitations" in disc
    assert "Future work" in disc
    assert figure_refs(_PAPER_TYP, True) == ["figures/fig1.png"]
    assert has_references(_PAPER_TYP, True)


# ---------------------------------------------------------------------------
# audit_synthesis (dual-format structural gate)
# ---------------------------------------------------------------------------


def test_audit_synthesis_finds_typst_sections_and_figure(tmp_path: Path):
    (tmp_path / "workspace" / "logs").mkdir(parents=True)
    _seed_typst_paper(tmp_path)
    res = audit_synthesis("synthesis/paper.typ", tmp_path)
    report = res["report"]
    # All five IMRAD sections detected (abstract via conf block, the rest
    # via ``=`` headings) — previously all five were reported missing.
    assert report["missing_sections"] == []
    # The #figure(image(...)) form is counted.
    assert report["figures_referenced"] == 1
    # The #bibliography(...) directive satisfies the bibliography gate.
    assert report["has_bibliography"] is True


def test_audit_synthesis_typst_missing_section_detected(tmp_path: Path):
    (tmp_path / "workspace" / "logs").mkdir(parents=True)
    # Drop the Methods heading entirely.
    p = tmp_path / "synthesis" / "paper.typ"
    p.parent.mkdir(parents=True)
    p.write_text(
        _PAPER_TYP.replace("= Methods\n\n"
                           "We ran the alpha, beta, and gamma steps in "
                           "sequence.\n\n", "")
    )
    res = audit_synthesis("synthesis/paper.typ", tmp_path)
    assert "methods" in res["report"]["missing_sections"]


# ---------------------------------------------------------------------------
# claim grounding (Typst claims, comment numbers excluded)
# ---------------------------------------------------------------------------


def test_extract_claims_from_typst_excludes_comment_numbers(tmp_path: Path):
    p = _seed_typst_paper(tmp_path)
    tokens = {c["token"] for c in extract_claims(p)}
    # Real claims surface.
    assert "42%" in tokens
    assert "0.01" in tokens
    # The number inside the ``// … 999 …`` comment must NOT be a claim.
    assert "999" not in tokens


def test_audit_claims_targets_typst_paper(tmp_path: Path):
    # Corpus grounds the 42 reduction; the paper's other numbers don't
    # appear in any output, so they surface as ungrounded.
    ws = tmp_path / "workspace" / "01_eda" / "outputs" / "reports"
    ws.mkdir(parents=True)
    (ws / "summary.md").write_text("noise reduction = 42%\n")
    _seed_typst_paper(tmp_path)
    res = audit_claims(tmp_path)
    assert res["target"] == "synthesis/paper.typ"
    assert res["total_claims"] >= 2


# ---------------------------------------------------------------------------
# coherence (Typst paragraphs grouped by ``=`` sections)
# ---------------------------------------------------------------------------


def test_audit_coherence_flags_orphan_in_typst(tmp_path: Path):
    step = tmp_path / "workspace" / "01_eda"
    step.mkdir(parents=True)
    (step / "conclusions.md").write_text(
        "The PCA reduced noise substantially across all splits in the "
        "evaluation dataset using standard preprocessing."
    )
    p = tmp_path / "synthesis" / "paper.typ"
    p.parent.mkdir(parents=True)
    p.write_text(
        "#show: template.with(conf(abstract: [x]))\n\n"
        "= Results\n\n"
        "The PCA reduced noise substantially across all splits in the "
        "evaluation dataset using standard preprocessing here.\n\n"
        "= Discussion\n\n"
        "An entirely unrelated orphan paragraph about quantum "
        "chromodynamics and lattice gauge field simulations appears here.\n"
    )
    res = audit_coherence(tmp_path)
    # Both paragraphs scored; the unrelated one is flagged orphan.
    assert res["paragraphs_scored"] == 2
    assert res["orphan_count"] == 1


# ---------------------------------------------------------------------------
# content depth (Typst abstract / sections / limitations)
# ---------------------------------------------------------------------------


def test_section_substantiveness_passes_on_full_typst_paper(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    _seed_typst_paper(tmp_path)
    res = section_substantiveness(tmp_path)
    assert res["status"] == "success", res["blockers"]


def test_section_substantiveness_blocks_thin_typst_paper(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    p = tmp_path / "synthesis" / "paper.typ"
    p.parent.mkdir(parents=True)
    # No abstract numbers, no citations, no limitations / future work.
    p.write_text(
        "#show: template.with(conf(abstract: [Qualitative things only.]))\n\n"
        "= Introduction\n\nWe did stuff.\n\n"
        "= Methods\n\nThings.\n\n"
        "= Results\n\nWe saw things.\n\n"
        "= Discussion\n\nMore generic words with no caveats.\n"
    )
    res = section_substantiveness(tmp_path)
    assert res["status"] == "error"
    assert res["blockers"]


# ---------------------------------------------------------------------------
# redteam (inventories the Typst paper)
# ---------------------------------------------------------------------------


def test_redteam_scaffold_finds_typst_paper(tmp_path: Path):
    _seed_typst_paper(tmp_path)
    res = redteam_scaffold(tmp_path)
    assert res["status"] == "success"
    assert res["inventory"]["paper"] == "synthesis/paper.typ"


def test_redteam_scaffold_errors_without_paper(tmp_path: Path):
    res = redteam_scaffold(tmp_path)
    assert res["status"] == "error"
    # The error must NOT reference the removed tool_synthesize.
    assert "tool_synthesize" not in res["message"]
    assert "paper.typ" in res["message"]
