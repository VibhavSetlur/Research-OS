"""v1.11.0 — reference project manifests + figure / monograph fixtures.

These tests cover the v1.11.0 expansion of the reference-project
manifests under ``tests/fixtures/projects/`` and the supporting fixture
bundles under ``tests/fixtures/figures/`` and
``tests/fixtures/projects/humanities_ms_review/inputs/citations/``.

Scope:

* Every existing reference-project manifest still parses cleanly
  through ``load_reference_project`` (we don't break the v1.7.0
  stress-runner contract while adding new keys).
* The new ``synthesis_deliverables`` / ``cross_deliverable`` /
  ``reviewer_simulation`` / ``isbn_verifier_expectations`` /
  ``pii_redaction_expectations`` / ``coreq_checklist`` /
  ``routing_expectations`` / ``synthesis_behavior`` keys are present
  and well-shaped on the four updated manifests.
* The new ``theory_math_graph_proof`` fixture exists with its three
  inputs (research_question.md, conjecture.md, attempted_proof.md).
* The ``.caption.md`` sidecar fixtures parse (YAML frontmatter +
  body) and pair with a PNG of the same stem.
* The monograph citation fixtures expose ISBNs the
  ``_extract_isbn`` helper can read offline.

These tests are intentionally hermetic — they do NOT call the live
ISBN verifiers (no network in CI), nor do they execute the full
synthesis pipeline. They are a contract check: the manifests and
fixtures are correctly shaped so the integration agent and the
real-model stress runs can pick them up.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
PROJECTS_ROOT = FIXTURES_ROOT / "projects"
FIGURES_ROOT = FIXTURES_ROOT / "figures"


# ── reference-project manifests ───────────────────────────────────────


@pytest.mark.parametrize(
    "project_name",
    [
        "biology_genomics_mini",
        "humanities_ms_review",
        "qualitative_interviews",
        "theory_math_short_proof",
        "theory_math_graph_proof",
    ],
)
def test_manifest_loads_via_stress_runner(project_name):
    """``load_reference_project`` must succeed on every updated +
    newly-added fixture project."""
    from research_os.testing.stress_runner import load_reference_project

    proj = load_reference_project(PROJECTS_ROOT / project_name)
    assert proj.name == project_name
    assert proj.manifest, f"empty manifest for {project_name}"
    # protocols_expected is a list (may be empty for some fixtures).
    assert isinstance(proj.protocols_expected, list)
    assert proj.max_tool_calls >= 1
    assert proj.max_seconds >= 1


# ── synthesis_deliverables ────────────────────────────────────────────


@pytest.mark.parametrize(
    "project_name, expected_kinds",
    [
        ("biology_genomics_mini",
         {"paper", "slides_html", "slides_pdf", "poster"}),
        ("humanities_ms_review",
         {"scholarly_edition", "essay"}),
        ("qualitative_interviews",
         {"report", "slides_html"}),
        ("theory_math_short_proof", {"paper"}),
        ("theory_math_graph_proof", {"paper"}),
    ],
)
def test_synthesis_deliverables_declared(project_name, expected_kinds):
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / project_name / "manifest.yaml").read_text()
    )
    deliverables = manifest.get("synthesis_deliverables") or []
    assert deliverables, f"{project_name}: synthesis_deliverables missing"
    kinds = {entry["kind"] for entry in deliverables}
    missing = expected_kinds - kinds
    assert not missing, f"{project_name}: missing kinds {missing}; got {kinds}"
    for entry in deliverables:
        # Shape contract: every entry has path + tool + must_succeed.
        assert entry.get("path"), f"{project_name}: deliverable missing path"
        assert entry.get("tool"), f"{project_name}: deliverable missing tool"
        assert "must_succeed" in entry, (
            f"{project_name}: deliverable missing must_succeed"
        )


def test_biology_genomics_mini_deliverable_args_named_correctly():
    """The biology manifest's deliverables must use the canonical
    config-field values from researcher_config (conference_15min /
    academic_36x48 / reveal / touying)."""
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "biology_genomics_mini" / "manifest.yaml").read_text()
    )
    by_kind = {d["kind"]: d for d in manifest["synthesis_deliverables"]}
    assert by_kind["slides_html"]["args"]["slide_template"] == "conference_15min"
    assert by_kind["slides_html"]["args"]["slide_engine"] == "reveal"
    assert by_kind["slides_pdf"]["args"]["slide_engine"] == "touying"
    assert by_kind["poster"]["args"]["poster_template"] == "academic_36x48"


# ── cross_deliverable ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "project_name",
    [
        "biology_genomics_mini",
        "humanities_ms_review",
        "qualitative_interviews",
        "theory_math_short_proof",
        "theory_math_graph_proof",
    ],
)
def test_cross_deliverable_block_present(project_name):
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / project_name / "manifest.yaml").read_text()
    )
    cd = manifest.get("cross_deliverable")
    assert cd is not None, f"{project_name}: cross_deliverable missing"
    assert cd.get("title_match") is True
    assert cd.get("citation_set_match") is True


# ── reviewer_simulation (biology only) ────────────────────────────────


def test_reviewer_simulation_min_comments_and_persona_count():
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "biology_genomics_mini" / "manifest.yaml").read_text()
    )
    rs = manifest.get("reviewer_simulation")
    assert rs and rs.get("enabled") is True
    assert rs.get("min_total_comments", 0) >= 30
    personas = rs.get("personas") or []
    assert len(personas) >= 7, f"only {len(personas)} personas"
    assert rs.get("min_personas_responding", 0) >= 7


# ── humanities essay + ISBN + routing expectations ────────────────────


def test_humanities_essay_routing_declared():
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "humanities_ms_review" / "manifest.yaml").read_text()
    )
    routing = manifest.get("routing_expectations") or []
    essay_routings = [
        r for r in routing
        if r.get("output_type") == "essay"
    ]
    assert essay_routings, "no essay routing_expectation declared"
    # Must require humanities_essay_structure (the v1.11.0 protocol).
    target = essay_routings[0]
    assert target.get("requires_protocol") == (
        "humanities/output/humanities_essay_structure"
    )


def test_humanities_essay_deliverable_uses_humanities_essay_template():
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "humanities_ms_review" / "manifest.yaml").read_text()
    )
    essay = next(
        d for d in manifest["synthesis_deliverables"]
        if d["kind"] == "essay"
    )
    assert essay["args"]["venue_template"] == "humanities_essay"
    checks = essay["checks"]
    assert checks["margins_inches"] == 1.25
    assert checks["body_size_pt"] == 12
    assert checks["footnote_size_pt"] == 10
    assert checks["blockquote_indent_inches"] == 0.5
    assert checks["headings_unnumbered"] is True


def test_humanities_isbn_verifier_expectations():
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "humanities_ms_review" / "manifest.yaml").read_text()
    )
    iv = manifest.get("isbn_verifier_expectations")
    assert iv, "isbn_verifier_expectations block missing"
    assert iv.get("min_entries", 0) >= 3
    assert iv.get("all_must_verify") is True
    assert set(iv.get("acceptable_verifiers", [])) >= {
        "openlibrary", "worldcat", "loc"
    }
    # The monographs file the manifest points at must actually exist.
    src = PROJECTS_ROOT / "humanities_ms_review" / iv["source"]
    assert src.exists(), f"monographs source missing: {src}"


# ── qualitative additions: PII + COREQ + public_outreach slides ──────


def test_qualitative_pii_redaction_expectations():
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "qualitative_interviews" / "manifest.yaml").read_text()
    )
    pii = manifest.get("pii_redaction_expectations")
    assert pii, "pii_redaction_expectations block missing"
    assert pii.get("must_fire_before_synthesis") is True
    assert pii.get("hipaa_classes_covered_min", 0) >= 18


def test_qualitative_coreq_checklist_block():
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "qualitative_interviews" / "manifest.yaml").read_text()
    )
    coreq = manifest.get("coreq_checklist")
    assert coreq, "coreq_checklist block missing"
    assert coreq.get("min_items_walked", 0) >= 32


def test_qualitative_public_outreach_slides_declared():
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "qualitative_interviews" / "manifest.yaml").read_text()
    )
    slides = next(
        d for d in manifest["synthesis_deliverables"]
        if d["kind"] == "slides_html"
    )
    assert slides["args"]["slide_template"] == "public_outreach"


# ── theory_math synthesis enforcement ─────────────────────────────────


@pytest.mark.parametrize(
    "project_name",
    ["theory_math_short_proof", "theory_math_graph_proof"],
)
def test_theory_math_paper_template_is_non_imrad(project_name):
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / project_name / "manifest.yaml").read_text()
    )
    paper = next(
        d for d in manifest["synthesis_deliverables"]
        if d["kind"] == "paper"
    )
    assert paper["args"]["paper_template"] == "theory"
    checks = paper["checks"]
    # Must require non-IMRAD section names.
    sections = checks.get("sections_expected", [])
    assert "preliminaries" in sections
    assert "main_theorems" in sections
    assert "proofs" in sections
    # Must forbid IMRAD sections.
    forbidden = set(checks.get("sections_forbidden", []))
    assert {"methods", "results"} <= forbidden


@pytest.mark.parametrize(
    "project_name",
    ["theory_math_short_proof", "theory_math_graph_proof"],
)
def test_theory_math_synthesis_behavior_contract(project_name):
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / project_name / "manifest.yaml").read_text()
    )
    sb = manifest.get("synthesis_behavior")
    assert sb, f"{project_name}: synthesis_behavior block missing"
    assert sb.get("honor_figure_required_false_for_proof_steps") is True
    assert sb.get("citation_count_agreement") is True


# ── theory_math_graph_proof: new fixture exists ───────────────────────


def test_theory_math_graph_proof_fixture_present():
    root = PROJECTS_ROOT / "theory_math_graph_proof"
    assert root.is_dir(), f"missing fixture: {root}"
    assert (root / "manifest.yaml").exists()
    assert (root / "cleanup.sh").exists()
    inputs_ctx = root / "inputs" / "context"
    for fn in ("research_question.md", "conjecture.md", "attempted_proof.md"):
        assert (inputs_ctx / fn).exists(), f"missing input: {fn}"


def test_theory_math_graph_proof_routing_regression_target():
    """The graph-proof fixture must declare the exact prompt SMOKE GAPS
    flags as currently mis-routing to guidance/analysis_plan."""
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "theory_math_graph_proof" / "manifest.yaml").read_text()
    )
    routings = manifest.get("routing_expectations") or []
    assert routings, "no routing_expectations on graph-proof fixture"
    # The first routing expectation must be the smoke-gap prompt.
    target = routings[0]
    assert "maximum degree 3" in target["prompt"]
    assert target["expected_protocol"] == (
        "theory_math/proof/proof_verification_workflow"
    )
    forbidden = set(target.get("forbidden_protocols", []))
    assert "guidance/analysis_plan" in forbidden


# ── figure sidecar fixtures ───────────────────────────────────────────


CAPTION_FIXTURES = [
    "umap_microglia_braak",
    "volcano_de_tyrobp",
    "kappa_round_progression",
    "manuscript_f23v_thumb",
]


@pytest.mark.parametrize("stem", CAPTION_FIXTURES)
def test_caption_sidecar_paired_with_png(stem):
    png = FIGURES_ROOT / f"{stem}.png"
    cap = FIGURES_ROOT / f"{stem}.caption.md"
    assert png.exists(), f"missing PNG: {png}"
    assert cap.exists(), f"missing caption: {cap}"
    # PNG must be a valid PNG header (signature 89 50 4E 47).
    assert png.read_bytes()[:4] == b"\x89PNG", f"{png} not a valid PNG"


@pytest.mark.parametrize("stem", CAPTION_FIXTURES)
def test_caption_sidecar_frontmatter_parses(stem):
    cap = FIGURES_ROOT / f"{stem}.caption.md"
    text = cap.read_text()
    # Must open with a YAML frontmatter block.
    lines = text.splitlines()
    assert lines[0].strip() == "---", f"{stem}: no opening frontmatter"
    end = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == "---"),
        None,
    )
    assert end is not None, f"{stem}: no closing frontmatter"
    fm = yaml.safe_load("\n".join(lines[1:end]))
    assert isinstance(fm, dict), f"{stem}: frontmatter is not a dict"
    # Required-keys contract.
    for required in ("figure_id", "title", "license", "alt_text"):
        assert required in fm, f"{stem}: frontmatter missing {required!r}"
    # alt_text must be substantial (not just the title).
    assert len(fm["alt_text"]) >= 40, f"{stem}: alt_text too short"
    # Body (after frontmatter) must contain the W3C "What it shows" /
    # "How to read it" / "Why it matters" three-part structure that
    # caption_synthesise emits.
    body = "\n".join(lines[end + 1:])
    assert "**What it shows.**" in body
    assert "**How to read it.**" in body
    assert "**Why it matters.**" in body


def test_caption_body_consumed_by_existing_reader_unchanged():
    """``_read_caption_sidecar`` reads the WHOLE file (including the
    frontmatter — current behaviour). This test pins that behaviour:
    when the integration agent eventually adds frontmatter-stripping,
    this test should also be updated."""
    from research_os.tools.actions.synthesis.synthesize import (
        _read_caption_sidecar,
    )

    body = _read_caption_sidecar(FIGURES_ROOT / "umap_microglia_braak.png")
    assert body, "caption reader returned empty"
    # The body MUST include the W3C-style caption text the integration
    # agent will eventually surface to the dashboard.
    assert "What it shows" in body


# ── humanities monograph fixtures (ISBN-bearing, offline) ─────────────


def test_humanities_monographs_file_loads():
    p = PROJECTS_ROOT / "humanities_ms_review" / "inputs" / "citations" / "monographs.yaml"
    assert p.exists()
    data = yaml.safe_load(p.read_text())
    assert isinstance(data, dict)
    citations = data.get("citations") or []
    assert len(citations) >= 3, "need at least 3 monograph fixtures"


def test_humanities_monographs_all_have_isbn():
    """Offline check: every fixture exposes an ISBN that the existing
    ``_extract_isbn`` helper can read."""
    from research_os.tools.actions.research.citations_isbn import (
        _clean_isbn,
        _extract_isbn,
    )

    p = PROJECTS_ROOT / "humanities_ms_review" / "inputs" / "citations" / "monographs.yaml"
    data = yaml.safe_load(p.read_text())
    citations = data["citations"]

    for entry in citations:
        # _extract_isbn checks isbn / ISBN / isbn13 / isbn10 in order.
        # Our fixtures populate isbn13 + isbn10 — verify both.
        extracted = _extract_isbn(entry)
        assert extracted, f"{entry['id']}: no ISBN extracted"
        # Cleaned form must be 10 or 13 digits (possibly trailing X).
        assert re.fullmatch(r"[0-9]{9,12}[0-9X]", extracted), (
            f"{entry['id']}: extracted ISBN {extracted!r} bad shape"
        )
        # And isbn13 → 13 digits exactly when cleaned.
        if entry.get("isbn13"):
            cleaned13 = _clean_isbn(entry["isbn13"])
            assert len(cleaned13) == 13, (
                f"{entry['id']}: isbn13 cleans to {len(cleaned13)} digits"
            )


def test_humanities_monographs_artifact_required_in_manifest():
    """The humanities manifest's ``artifacts_required`` must list the
    monographs fixture so the stress runner verifies it exists."""
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / "humanities_ms_review" / "manifest.yaml").read_text()
    )
    required = manifest.get("artifacts_required", [])
    assert "inputs/citations/monographs.yaml" in required


# ── back-compat: the v1.7.0 contract still holds ──────────────────────


@pytest.mark.parametrize(
    "project_name",
    [
        "biology_genomics_mini",
        "humanities_ms_review",
        "qualitative_interviews",
    ],
)
def test_v170_canned_responses_still_present(project_name):
    """The mock-model stress runner reads canned_responses keyed by
    step_id. We must not have dropped them while adding v1.11.0 keys."""
    manifest = yaml.safe_load(
        (PROJECTS_ROOT / project_name / "manifest.yaml").read_text()
    )
    canned = manifest.get("canned_responses") or {}
    assert canned, f"{project_name}: canned_responses unexpectedly empty"
