"""Tests for the v2 dashboard humanities-pack section renderer.

Covers AUDIT-073 closure: apparatus criticus table, close-reading
anchors, critical conversation map, manuscript witness list. Each
section renders valid HTML, degrades gracefully on missing data, and
the top-level renderer composes the four section IDs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from research_os.tools.actions.synthesis.dashboard_humanities import (
    _build_apparatus_section,
    _build_close_reading_section,
    _build_critical_conversation_section,
    _build_witness_section,
    _parse_apparatus_md,
    render_humanities_section,
)
from research_os.tools.actions.synthesis.dashboard_app import detect_active_pack


# ── helpers ───────────────────────────────────────────────────────────


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


# ── apparatus parser ──────────────────────────────────────────────────


def test_parse_apparatus_table_form():
    md = (
        "| Line | Lemma  | Variant | Witnesses | Decision |\n"
        "|------|--------|---------|-----------|----------|\n"
        "| 1.5  | mundi  | mondi   | M, B      | accept M |\n"
        "| 2.3  | luna   | lumina  | P         | reject   |\n"
    )
    rows = _parse_apparatus_md(md)
    assert len(rows) == 2
    assert rows[0]["line"] == "1.5"
    assert rows[0]["lemma"] == "mundi"
    assert rows[0]["witnesses"] == "M, B"
    assert rows[1]["decision"] == "reject"


def test_parse_apparatus_lemma_block_form():
    md = (
        "**1.5** mundi] mondi M B; lat. P\n"
        "**2.3** luna] lumina A C\n"
    )
    rows = _parse_apparatus_md(md)
    assert rows, "lemma-block form should parse"
    assert rows[0]["line"] == "1.5"
    assert rows[0]["lemma"] == "mundi"


def test_parse_apparatus_empty():
    assert _parse_apparatus_md("") == []
    assert _parse_apparatus_md("Just some prose.") == []


# ── apparatus section ────────────────────────────────────────────────


def test_apparatus_section_missing(tmp_path):
    html = _build_apparatus_section(tmp_path)
    assert "hum-apparatus" in html
    assert "No workspace/edition/apparatus.md" in html


def test_apparatus_section_with_edition_apparatus(tmp_path):
    _write(
        tmp_path / "workspace" / "edition" / "apparatus.md",
        (
            "| Line | Lemma  | Variant | Witnesses | Decision |\n"
            "|------|--------|---------|-----------|----------|\n"
            "| 1.5  | mundi  | mondi   | M, B      | accept M |\n"
            "| 2.3  | luna   | lumina  | P         | reject   |\n"
        ),
    )
    html = _build_apparatus_section(tmp_path)
    assert "apparatus-table" in html
    assert "mundi" in html and "luna" in html
    assert "2 entries" in html


def test_apparatus_section_close_reading_fallback(tmp_path):
    _write(
        tmp_path / "workspace" / "close_readings" / "PL_book4_apparatus.md",
        (
            "| Line | Lemma | Variant | Witnesses | Decision |\n"
            "|------|-------|---------|-----------|----------|\n"
            "| 4.301 | hand | hond | 1667 | retain 1674 |\n"
        ),
    )
    html = _build_apparatus_section(tmp_path)
    assert "PL_book4_apparatus.md" in html
    assert "hand" in html and "hond" in html


# ── close-reading anchors ────────────────────────────────────────────


def test_close_reading_section_missing_dir(tmp_path):
    html = _build_close_reading_section(tmp_path)
    assert "hum-close-reading" in html
    assert "No workspace/close_readings/ directory" in html


def test_close_reading_section_empty_dir(tmp_path):
    (tmp_path / "workspace" / "close_readings").mkdir(parents=True)
    html = _build_close_reading_section(tmp_path)
    assert "hum-close-reading" in html
    assert "no *_apparatus.md" in html or "no _apparatus.md" in html


def test_close_reading_section_parses_anchored_claims(tmp_path):
    _write(
        tmp_path / "workspace" / "close_readings" / "PL_book4_apparatus.md",
        (
            "# Apparatus for PL book 4 lines 297-311\n\n"
            "> hand in hand with wandering steps and slow\n\n"
            "1. (4.297) The diction enacts hesitation through the parenthetical.\n"
            "2. [4.298] The caesura performs the very hand-clasp it describes.\n"
            "3. (4.311) The verb 'wandering' resists the prior providential frame.\n"
        ),
    )
    html = _build_close_reading_section(tmp_path)
    assert "PL_book4" in html
    assert "close-reading-anchors" in html
    assert "3 anchored claims" in html
    assert "4.297" in html and "4.298" in html and "4.311" in html


# ── critical conversation map ────────────────────────────────────────


def test_critical_conversation_missing_dir(tmp_path):
    html = _build_critical_conversation_section(tmp_path)
    assert "hum-critical-conversation" in html
    assert "No workspace/citations/" in html


def test_critical_conversation_with_chains(tmp_path):
    _write(
        tmp_path / "workspace" / "citations" / "chain_hand_in_hand.md",
        (
            "# chain_hand_in_hand\n\n"
            "## Source\nMilton, PL 4.321 (1674 ed., facs. UMI).\n\n"
            "## Reader\nFish (1967), Surprised by Sin, ch. 4.\n\n"
            "## Transformation\nFish reads the line ironically; this paper resists.\n"
        ),
    )
    _write(
        tmp_path / "workspace" / "citations" / "chain_wandering_steps.md",
        "## Source\nPL 4.311.\n",
    )
    html = _build_critical_conversation_section(tmp_path)
    assert "hand_in_hand" in html
    assert "wandering_steps" in html
    assert "Source" in html
    assert "2 chains" in html


# ── manuscript witnesses ─────────────────────────────────────────────


def test_witness_section_missing(tmp_path):
    html = _build_witness_section(tmp_path)
    assert "hum-witnesses" in html
    assert "No workspace/edition/stemma.md" in html


def test_witness_section_parses_sigla(tmp_path):
    _write(
        tmp_path / "workspace" / "edition" / "stemma.md",
        (
            "# Stemma\n\n"
            "A = Paris, BnF, MS lat. 1234 (s. xii)\n"
            "B = London, BL, Harley 5678, ff. 1r-24v\n"
            "C = Vatican, BAV, Vat. lat. 99 (s. xiii)\n"
        ),
    )
    html = _build_witness_section(tmp_path)
    assert "witness-table" in html
    assert "3 sigla" in html
    assert "BnF" in html
    assert "Harley 5678" in html


def test_witness_section_collation_only(tmp_path):
    _write(
        tmp_path / "workspace" / "edition" / "collation_PL.md",
        (
            "X — 1667 first ed. (Beinecke copy)\n"
            "Y — 1674 second ed. (UMI facs.)\n"
        ),
    )
    html = _build_witness_section(tmp_path)
    assert "2 sigla" in html
    assert "1667 first ed." in html
    assert "1674 second ed." in html


def test_witness_section_unparseable_falls_back_to_raw(tmp_path):
    _write(
        tmp_path / "workspace" / "edition" / "stemma.md",
        "Just descriptive prose with no sigla format.\n",
    )
    html = _build_witness_section(tmp_path)
    assert "hum-witnesses" in html
    assert "no parseable sigla" in html
    assert "Just descriptive prose" in html


# ── top-level renderer ────────────────────────────────────────────────


def test_render_humanities_section_combines_all(tmp_path):
    _write(
        tmp_path / "workspace" / "edition" / "apparatus.md",
        "| Line | Lemma | Variant | Witnesses | Decision |\n"
        "|------|-------|---------|-----------|----------|\n"
        "| 1.1  | A     | B       | M         | retain   |\n",
    )
    html = render_humanities_section(tmp_path, spec={}, state={})
    for anchor in ("hum-apparatus", "hum-close-reading",
                   "hum-critical-conversation", "hum-witnesses"):
        assert anchor in html, anchor
    assert html.count("<section") == 4


def test_render_humanities_section_handles_empty_root(tmp_path):
    html = render_humanities_section(tmp_path)
    assert html.count("<section") == 4
    assert "Apparatus criticus" in html
    assert "Close-reading anchors" in html
    assert "Critical conversation map" in html
    assert "Manuscript witnesses" in html


# ── detection plumbing ───────────────────────────────────────────────


def test_detect_active_pack_humanities_via_config(tmp_path):
    cfg = tmp_path / "inputs" / "researcher_config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump({"domain": "humanities"}))
    assert detect_active_pack(tmp_path) == "humanities"


def test_detect_active_pack_humanities_via_workspace(tmp_path):
    (tmp_path / "workspace" / "edition").mkdir(parents=True)
    assert detect_active_pack(tmp_path) == "humanities"


def test_detect_active_pack_humanities_priority_over_qualitative(tmp_path):
    # Both markers present — humanities wins per the dispatch tie-break.
    (tmp_path / "workspace" / "transcripts").mkdir(parents=True)
    (tmp_path / "workspace" / "edition").mkdir(parents=True)
    assert detect_active_pack(tmp_path) == "humanities"


@pytest.mark.parametrize("root_type", ["path", "str"])
def test_render_humanities_section_accepts_str_root(tmp_path, root_type):
    root = tmp_path if root_type == "path" else str(tmp_path)
    html = render_humanities_section(root)
    assert isinstance(html, str)
    assert "<section" in html
