"""v1.11.0 — researcher_config ``synthesis:`` block.

The synthesis pipeline (paper / slides / poster compilers) reads its
knobs from a top-level ``synthesis:`` block in
``inputs/researcher_config.yaml``. These tests pin:

  1. The template file ships the block with documented defaults.
  2. ``get_config`` returns the parsed block.
  3. ``validate_config`` accepts the template defaults.
  4. ``validate_config`` rejects off-enum values (slide_engine, poster_engine,
     figures_auto_embed_mode, slide_template, poster_template, poster_theme).
  5. ``validate_config`` rejects non-bool values for bool toggles
     (figures_auto_embed, figure_xref_rewrite, slide_speaker_notes_enabled,
     slide_print_handout, poster_handout_pdf).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from research_os.tools.actions.state.config import (
    CONFIG_TEMPLATE,
    get_config,
    validate_config,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _scaffold(tmp_path: Path, extra: dict | None = None) -> Path:
    """Drop a researcher_config.yaml at inputs/. Optionally merge ``extra``
    into the synthesis: block to override defaults."""
    (tmp_path / "inputs").mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(CONFIG_TEMPLATE.format(project_name="test")) or {}
    cfg.setdefault("researcher", {})["name"] = "Test User"
    cfg.setdefault("research_goal", {})["output_types"] = ["paper"]
    if extra:
        synth = cfg.setdefault("synthesis", {})
        synth.update(extra)
    (tmp_path / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump(cfg, default_flow_style=False, sort_keys=False)
    )
    return tmp_path


# ── 1. Template ships the block + defaults ─────────────────────────────


def test_template_file_carries_synthesis_block():
    """templates/researcher_config.yaml must declare the synthesis block."""
    template = (_repo_root() / "templates" / "researcher_config.yaml").read_text()
    parsed = yaml.safe_load(template) or {}
    assert "synthesis" in parsed, (
        "templates/researcher_config.yaml must declare a top-level synthesis: block"
    )
    block = parsed["synthesis"]
    # Defaults documented in the v1.11.0 spec.
    assert block["figures_auto_embed"] is True
    assert block["figures_auto_embed_mode"] == "append_to_section"
    assert block["figure_xref_rewrite"] is True
    assert block["slide_engine"] == "reveal"
    assert block["slide_template"] == "conference_15min"
    assert block["slide_theme"] == ""
    assert block["slide_speaker_notes_enabled"] is True
    assert block["slide_print_handout"] is True
    assert block["poster_engine"] == "typst"
    assert block["poster_template"] == "academic_36x48"
    assert block["poster_theme"] == "light"
    assert block["poster_qr_url"] == ""
    assert block["poster_handout_pdf"] is True


def test_config_template_constant_carries_synthesis_block():
    """CONFIG_TEMPLATE (in-code) must also carry the block — kept in sync
    with the file via test_config_template_matches_file.py."""
    parsed = yaml.safe_load(CONFIG_TEMPLATE.format(project_name="x")) or {}
    assert "synthesis" in parsed
    assert parsed["synthesis"]["slide_engine"] == "reveal"
    assert parsed["synthesis"]["poster_engine"] == "typst"


# ── 2. get_config returns the block ────────────────────────────────────


def test_get_config_returns_synthesis_block(tmp_path):
    root = _scaffold(tmp_path)
    res = get_config(root)
    assert res["status"] == "success", res
    synth = res["config"].get("synthesis")
    assert isinstance(synth, dict), "synthesis block must round-trip through get_config"
    assert synth["slide_engine"] == "reveal"
    assert synth["figures_auto_embed_mode"] == "append_to_section"


# ── 3. validate_config accepts template defaults ───────────────────────


def test_validate_config_accepts_template_defaults(tmp_path):
    root = _scaffold(tmp_path)
    res = validate_config(root)
    assert res["status"] == "success"
    # No synthesis-related enum violations on the documented defaults.
    synth_violations = [
        v for v in res["enum_violations"] if v["field"].startswith("synthesis.")
    ]
    assert synth_violations == [], (
        f"template defaults must validate clean; got: {synth_violations}"
    )


# ── 4. validate_config rejects off-enum values ─────────────────────────


def test_validate_config_rejects_bad_slide_engine(tmp_path):
    root = _scaffold(tmp_path, {"slide_engine": "powerpoint"})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.slide_engine" in fields


def test_validate_config_rejects_bad_poster_engine(tmp_path):
    root = _scaffold(tmp_path, {"poster_engine": "indesign"})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.poster_engine" in fields


def test_validate_config_rejects_bad_embed_mode(tmp_path):
    root = _scaffold(tmp_path, {"figures_auto_embed_mode": "scatter_randomly"})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.figures_auto_embed_mode" in fields


def test_validate_config_rejects_bad_slide_template(tmp_path):
    root = _scaffold(tmp_path, {"slide_template": "60min_keynote"})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.slide_template" in fields


def test_validate_config_rejects_bad_poster_template(tmp_path):
    root = _scaffold(tmp_path, {"poster_template": "billboard"})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.poster_template" in fields


def test_validate_config_rejects_bad_poster_theme(tmp_path):
    root = _scaffold(tmp_path, {"poster_theme": "neon"})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.poster_theme" in fields


# ── 5. validate_config rejects non-bool toggles ────────────────────────


def test_validate_config_rejects_non_bool_figures_auto_embed(tmp_path):
    root = _scaffold(tmp_path, {"figures_auto_embed": "yes"})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.figures_auto_embed" in fields


def test_validate_config_rejects_non_bool_handout(tmp_path):
    root = _scaffold(tmp_path, {"poster_handout_pdf": 1})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.poster_handout_pdf" in fields


def test_validate_config_accepts_blank_optional_strings(tmp_path):
    """Blank ``slide_theme`` / ``poster_qr_url`` are valid (template defaults)."""
    root = _scaffold(tmp_path, {"slide_theme": "", "poster_qr_url": ""})
    res = validate_config(root)
    synth_violations = [
        v for v in res["enum_violations"] if v["field"].startswith("synthesis.")
    ]
    assert synth_violations == []


# ── 6. Phase-5 drafter-loop fields ─────────────────────────────────────


def test_template_carries_drafter_loop_block():
    """templates/researcher_config.yaml + CONFIG_TEMPLATE must declare the
    Phase-5 drafter-loop fields with the documented defaults."""
    parsed_file = yaml.safe_load(
        (_repo_root() / "templates" / "researcher_config.yaml").read_text()
    ) or {}
    synth_file = parsed_file["synthesis"]
    assert synth_file["drafter_loop_enabled"] is True
    assert synth_file["drafter_loop_max_iterations"] == 3
    assert synth_file["drafter_loop_quality_threshold"] == 0.10

    parsed_code = yaml.safe_load(CONFIG_TEMPLATE.format(project_name="x")) or {}
    synth_code = parsed_code["synthesis"]
    assert synth_code["drafter_loop_enabled"] is True
    assert synth_code["drafter_loop_max_iterations"] == 3
    assert synth_code["drafter_loop_quality_threshold"] == 0.10


def test_validate_config_rejects_non_bool_drafter_loop_enabled(tmp_path):
    root = _scaffold(tmp_path, {"drafter_loop_enabled": "yes"})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.drafter_loop_enabled" in fields


def test_validate_config_rejects_out_of_range_max_iterations(tmp_path):
    root = _scaffold(tmp_path, {"drafter_loop_max_iterations": 99})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.drafter_loop_max_iterations" in fields


def test_validate_config_rejects_negative_quality_threshold(tmp_path):
    root = _scaffold(tmp_path, {"drafter_loop_quality_threshold": -0.5})
    res = validate_config(root)
    fields = {v["field"] for v in res["enum_violations"]}
    assert "synthesis.drafter_loop_quality_threshold" in fields


def test_validate_config_accepts_drafter_loop_defaults(tmp_path):
    """Template defaults must validate clean — no enum violations."""
    root = _scaffold(tmp_path)
    res = validate_config(root)
    bad = [
        v for v in res["enum_violations"]
        if v["field"].startswith("synthesis.drafter_loop_")
    ]
    assert bad == [], f"defaults must validate; got {bad}"
