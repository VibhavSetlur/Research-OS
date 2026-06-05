"""Tests for the v2 dashboard qualitative-pack section renderer.

Covers AUDIT-073 closure: codebook table, themes hierarchy, saturation
grid, member-checking log. Each section renders valid HTML, degrades
gracefully on missing data, and the top-level renderer dispatches via
``detect_active_pack`` when a researcher_config.yaml or workspace
marker tags the project as qualitative.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from research_os.tools.actions.synthesis.dashboard_v2_qualitative import (
    _build_codebook_section,
    _build_member_check_section,
    _build_saturation_section,
    _build_themes_section,
    render_qualitative_section,
)
from research_os.tools.actions.synthesis.dashboard_v2 import detect_active_pack


# ── helpers ───────────────────────────────────────────────────────────


def _write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data))


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


# ── codebook ──────────────────────────────────────────────────────────


def test_codebook_section_missing_workspace(tmp_path):
    html = _build_codebook_section(tmp_path)
    assert '<section' in html and 'qual-codebook' in html
    assert 'No workspace/codebooks' in html


def test_codebook_section_with_codes(tmp_path):
    _write_yaml(
        tmp_path / "workspace" / "codebooks" / "codebook_v3.yaml",
        {
            "codes": [
                {
                    "code": "stigma",
                    "definition": "Felt or anticipated devaluation.",
                    "inclusion": "Self-reported shame or hiding.",
                    "exclusion": "External discrimination accounts.",
                    "applied_count": 42,
                    "kappa": 0.82,
                },
                {
                    "code": "disclosure",
                    "definition": "Telling someone about the condition.",
                    "applied_count": 19,
                    "kappa": 0.71,
                },
            ]
        },
    )
    # Add an older codebook to confirm we pick the highest N
    _write_yaml(
        tmp_path / "workspace" / "codebooks" / "codebook_v1.yaml",
        {"codes": [{"code": "old", "definition": "should not appear"}]},
    )
    html = _build_codebook_section(tmp_path)
    assert "codebook_v3.yaml" in html
    assert "stigma" in html and "disclosure" in html
    assert "0.82" in html
    assert "<th>code</th>" in html
    assert "old" not in html  # v1 was overridden


def test_codebook_section_malformed_yaml(tmp_path):
    _write(tmp_path / "workspace" / "codebooks" / "codebook_v2.yaml",
           ": not valid yaml: [")
    html = _build_codebook_section(tmp_path)
    assert "qual-codebook" in html
    # Either malformed or no-codes message — both are graceful.
    assert "malformed" in html or "carries no codes" in html


# ── themes ────────────────────────────────────────────────────────────


def test_themes_section_missing(tmp_path):
    html = _build_themes_section(tmp_path)
    assert "qual-themes" in html
    assert "No themes file yet" in html


def test_themes_section_falls_back_to_candidates_md(tmp_path):
    _write(tmp_path / "workspace" / "memos" / "candidate_themes_v1.md",
           "# Candidate themes\n\n- Stigma as moving target\n- Disclosure as repair\n")
    html = _build_themes_section(tmp_path)
    assert "qual-themes" in html
    assert "candidate_themes_v1.md" in html
    assert "Stigma as moving target" in html


def test_themes_section_with_final_themes(tmp_path):
    _write_yaml(
        tmp_path / "workspace" / "themes" / "final_themes.yaml",
        {
            "themes": [
                {
                    "name": "The hidden cost of disclosure",
                    "central_organising_concept":
                        "Disclosure as ongoing labour, not a one-time act.",
                    "definition":
                        "Participants treat disclosure as a recurring tax.",
                    "subthemes": [
                        {"name": "Sequencing", "definition": "Who first, who later."},
                    ],
                },
                {"name": "Stigma as moving target"},
            ]
        },
    )
    html = _build_themes_section(tmp_path)
    assert "The hidden cost of disclosure" in html
    assert "Sequencing" in html
    assert "Stigma as moving target" in html
    assert "themes-tree" in html


# ── saturation ────────────────────────────────────────────────────────


def test_saturation_section_missing(tmp_path):
    html = _build_saturation_section(tmp_path)
    assert "qual-saturation" in html
    assert "No saturation evidence yet" in html


def test_saturation_section_with_initial_codes(tmp_path):
    _write_yaml(
        tmp_path / "workspace" / "coding" / "initial_codes.yaml",
        {
            "codes": [
                {"code": "stigma", "first_seen_in": "T01"},
                {"code": "disclosure", "first_seen_in": "T01"},
                {"code": "stigma_anticipated", "first_seen_in": "T02"},
                {"code": "stigma", "first_seen_in": "T02"},  # not novel
                {"code": "repair_work", "first_seen_in": "T03"},
            ]
        },
    )
    html = _build_saturation_section(tmp_path)
    assert "saturation-grid" in html
    assert "T01" in html and "T02" in html and "T03" in html
    # cumulative monotonic + new-codes per row
    assert "<td>2</td>" in html  # T01 introduces 2
    assert "<td>3</td>" in html  # cumulative after T02 = 3 (anticipated added)


def test_saturation_section_with_curve_png(tmp_path):
    fig = tmp_path / "workspace" / "figures" / "saturation_curve.png"
    fig.parent.mkdir(parents=True, exist_ok=True)
    fig.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    html = _build_saturation_section(tmp_path)
    assert "saturation-curve" in html
    assert "saturation_curve.png" in html


# ── member checking ───────────────────────────────────────────────────


def test_member_check_section_missing(tmp_path):
    html = _build_member_check_section(tmp_path)
    assert "qual-member-checks" in html
    assert "No workspace/member_checks" in html


def test_member_check_section_with_rounds(tmp_path):
    r1 = tmp_path / "workspace" / "member_checks" / "round_1"
    r1.mkdir(parents=True)
    (r1 / "contact_log.md").write_text(
        "# Round 1 contacts\n\n- P01 (email, 2025-09-12)\n- P02 (email, 2025-09-13)\n"
    )
    (r1 / "divergences.md").write_text(
        "# Divergences\n\n- P01 challenged the 'stigma as deficit' framing.\n"
    )
    (r1 / "P01").mkdir()
    (r1 / "P02").mkdir()
    r2 = tmp_path / "workspace" / "member_checks" / "round_2"
    r2.mkdir()
    html = _build_member_check_section(tmp_path)
    assert "Round 1" in html and "Round 2" in html
    # 2 participant dirs in round 1
    assert "2 participant dir" in html
    assert "P01 challenged" in html
    assert "P01 (email" in html


# ── top-level renderer ────────────────────────────────────────────────


def test_render_qualitative_section_combines_all(tmp_path):
    _write_yaml(
        tmp_path / "workspace" / "codebooks" / "codebook_v1.yaml",
        {"codes": [{"code": "x", "definition": "y"}]},
    )
    html = render_qualitative_section(tmp_path, spec={}, state={})
    # All four section IDs are present
    for anchor in ("qual-codebook", "qual-themes",
                   "qual-saturation", "qual-member-checks"):
        assert anchor in html, anchor
    # Must look like HTML
    assert html.count("<section") == 4


def test_render_qualitative_section_handles_empty_root(tmp_path):
    html = render_qualitative_section(tmp_path)
    assert html.count("<section") == 4
    # Each section degraded to a stub but is still present
    assert "Codebook" in html
    assert "Themes" in html
    assert "Saturation" in html
    assert "Member checking" in html


# ── detection plumbing ───────────────────────────────────────────────


def test_detect_active_pack_via_config(tmp_path):
    cfg = tmp_path / "inputs" / "researcher_config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump({"pack": "qualitative"}))
    assert detect_active_pack(tmp_path) == "qualitative"


def test_detect_active_pack_via_workspace_markers(tmp_path):
    (tmp_path / "workspace" / "codebooks").mkdir(parents=True)
    (tmp_path / "workspace" / "themes").mkdir(parents=True)
    assert detect_active_pack(tmp_path) == "qualitative"


def test_detect_active_pack_returns_none_for_generic(tmp_path):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "01_step").mkdir()
    assert detect_active_pack(tmp_path) is None


@pytest.mark.parametrize("root_type", ["path", "str"])
def test_render_qualitative_section_accepts_str_root(tmp_path, root_type):
    root = tmp_path if root_type == "path" else str(tmp_path)
    html = render_qualitative_section(root)
    assert isinstance(html, str)
    assert "<section" in html
