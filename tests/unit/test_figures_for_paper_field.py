"""Tests for preflight check #23 — figures_for_paper field enforcement.

Confirms the check:
  - PASSES when every captioned figure has the field set explicitly
    (either on the caption sidecar OR the step-level step_summary.yaml).
  - FAILS when a captioned figure lacks the field in both places.
  - Skips figures without a caption sidecar (that's a different gate).
  - Honours sidecar-level overrides regardless of step-level value.
  - Returns a count in the detail line.

Also confirms the field landed in templates/step_summary.yaml.template so
new projects scaffold with the contract built in.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_PATH = REPO_ROOT / "scripts" / "_preflight_figures_for_paper.py"
TEMPLATE_PATH = REPO_ROOT / "templates" / "step_summary.yaml.template"


def _load_check_module():
    spec = importlib.util.spec_from_file_location(
        "_preflight_figures_for_paper", CHECK_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_preflight_figures_for_paper"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def check_mod():
    assert CHECK_PATH.exists(), f"missing helper: {CHECK_PATH}"
    return _load_check_module()


# ──────────────────────────────────────────────────────────────────────
# Fixture helpers
# ──────────────────────────────────────────────────────────────────────


def _make_step(
    fixtures_root: Path,
    project: str,
    step: str,
    *,
    figures: list[str] | None = None,
    captions: dict[str, str] | None = None,
    step_summary: str | None = None,
) -> Path:
    """Build a minimal fixture project/step under ``fixtures_root``.

    figures: list of figure file names (e.g. ['01_volcano.png']).
    captions: dict mapping figure name -> sidecar body. Sidecars are written
              as ``<stem>.caption.md``. Pass an empty body for a sidecar
              that lacks the field; pass an explicit body containing
              ``figures_for_paper: true|false`` to satisfy the check.
    step_summary: literal step_summary.yaml body. Omit to skip writing it.
    """
    step_dir = fixtures_root / project / "workspace" / step
    figs_dir = step_dir / "outputs" / "figures"
    figs_dir.mkdir(parents=True, exist_ok=True)
    for fig_name in figures or []:
        fig_path = figs_dir / fig_name
        fig_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    for fig_name, body in (captions or {}).items():
        stem = Path(fig_name).stem
        (figs_dir / f"{stem}.caption.md").write_text(body, encoding="utf-8")
    if step_summary is not None:
        (step_dir / "step_summary.yaml").write_text(step_summary, encoding="utf-8")
    return step_dir


# ──────────────────────────────────────────────────────────────────────
# Template-file contract
# ──────────────────────────────────────────────────────────────────────


def test_template_declares_figures_for_paper():
    """The step_summary template MUST ship the field so new projects inherit it."""
    text = TEMPLATE_PATH.read_text()
    assert "figures_for_paper:" in text, (
        "templates/step_summary.yaml.template must declare figures_for_paper "
        "so scaffolded steps carry the contract by default."
    )


# ──────────────────────────────────────────────────────────────────────
# Check function
# ──────────────────────────────────────────────────────────────────────


def test_check_passes_when_field_on_step_summary(tmp_path, check_mod):
    """Step-level field present → check passes for that step."""
    fixtures = tmp_path / "projects"
    _make_step(
        fixtures,
        "demo_project",
        "01_baseline",
        figures=["01_volcano.png"],
        captions={"01_volcano.png": "Volcano of DEGs.\n"},
        step_summary="figures_for_paper: true\nfigure_required: true\n",
    )
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert ok, detail
    assert "1 captioned figure" in detail


def test_check_passes_when_field_on_sidecar(tmp_path, check_mod):
    """Sidecar frontmatter alone is sufficient."""
    fixtures = tmp_path / "projects"
    _make_step(
        fixtures,
        "demo_project",
        "01_baseline",
        figures=["01_volcano.png"],
        captions={
            "01_volcano.png": (
                "---\nfigures_for_paper: true\n---\n"
                "Volcano of DEGs.\n"
            ),
        },
        # Intentionally omit step_summary.yaml.
    )
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert ok, detail


def test_check_fails_when_field_absent_everywhere(tmp_path, check_mod):
    """Caption sidecar present + neither location has the field → FAIL."""
    fixtures = tmp_path / "projects"
    _make_step(
        fixtures,
        "demo_project",
        "01_baseline",
        figures=["01_volcano.png"],
        captions={"01_volcano.png": "Volcano of DEGs.\n"},
        step_summary="figure_required: true\nliterature_required: false\n",
    )
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert not ok
    assert "figures_for_paper" in detail
    assert "01_volcano.png" in detail


def test_check_skips_figures_without_sidecar(tmp_path, check_mod):
    """Figure with NO caption sidecar is not this check's problem."""
    fixtures = tmp_path / "projects"
    _make_step(
        fixtures,
        "demo_project",
        "01_baseline",
        figures=["01_volcano.png"],
        captions={},  # no sidecar
        step_summary="figure_required: true\n",  # no field, but also no sidecar
    )
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert ok, detail
    assert "0 captioned figure" in detail


def test_check_passes_when_no_fixtures_present(tmp_path, check_mod):
    """An empty fixtures dir is a pass (nothing to audit)."""
    fixtures = tmp_path / "projects"
    fixtures.mkdir()
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert ok, detail
    assert "0 captioned figure" in detail


def test_check_passes_when_fixtures_root_missing(tmp_path, check_mod):
    """A non-existent fixtures root is also a pass (test ergonomics)."""
    fixtures = tmp_path / "does_not_exist"
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert ok, detail


def test_check_accepts_false_value(tmp_path, check_mod):
    """`figures_for_paper: false` is a valid explicit declaration."""
    fixtures = tmp_path / "projects"
    _make_step(
        fixtures,
        "scratch_project",
        "02_diagnostic",
        figures=["02_qc.png"],
        captions={"02_qc.png": "figures_for_paper: false\nQC histogram.\n"},
    )
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert ok, detail


def test_check_detects_multiple_missing(tmp_path, check_mod):
    """Multiple offenders are aggregated in the failure detail."""
    fixtures = tmp_path / "projects"
    _make_step(
        fixtures,
        "demo_project",
        "01_baseline",
        figures=["01_a.png", "02_b.png"],
        captions={
            "01_a.png": "Caption A.\n",
            "02_b.png": "Caption B.\n",
        },
        step_summary="figure_required: true\n",
    )
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert not ok
    assert "2 captioned figure" in detail


def test_check_handles_multiple_steps_and_projects(tmp_path, check_mod):
    """One offending step among many is still detected."""
    fixtures = tmp_path / "projects"
    # Project A: clean.
    _make_step(
        fixtures, "proj_a", "01_clean",
        figures=["01_x.png"],
        captions={"01_x.png": "Caption.\n"},
        step_summary="figures_for_paper: true\n",
    )
    # Project B: offending.
    _make_step(
        fixtures, "proj_b", "01_dirty",
        figures=["01_y.png"],
        captions={"01_y.png": "Caption.\n"},
        step_summary="figure_required: true\n",
    )
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert not ok
    assert "01_y.png" in detail
    assert "01_x.png" not in detail


def test_check_ignores_non_figure_files(tmp_path, check_mod):
    """README.md inside outputs/figures/ is not a figure; skip it."""
    fixtures = tmp_path / "projects"
    step_dir = _make_step(
        fixtures, "demo", "01_baseline",
        figures=["01_real.png"],
        captions={"01_real.png": "Caption.\n"},
        step_summary="figures_for_paper: true\n",
    )
    (step_dir / "outputs" / "figures" / "README.md").write_text("notes\n")
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert ok, detail


def test_find_missing_returns_relative_paths(tmp_path, check_mod):
    """``find_missing_figures_for_paper`` returns a path-flavoured list."""
    fixtures = tmp_path / "projects"
    _make_step(
        fixtures, "demo", "01_baseline",
        figures=["01_a.png"],
        captions={"01_a.png": "Caption.\n"},
        step_summary="figure_required: true\n",
    )
    missing = check_mod.find_missing_figures_for_paper(fixtures)
    assert len(missing) == 1
    assert "01_a.png" in missing[0]


def test_sidecar_field_overrides_when_step_summary_missing_field(
    tmp_path, check_mod
):
    """Sidecar value is sufficient even when step_summary.yaml omits the field."""
    fixtures = tmp_path / "projects"
    _make_step(
        fixtures, "demo", "01_baseline",
        figures=["01_a.png"],
        captions={"01_a.png": "figures_for_paper: false\nDiagnostic.\n"},
        step_summary="figure_required: true\n",  # no figures_for_paper field
    )
    ok, detail = check_mod.check_figures_for_paper_field(fixtures)
    assert ok, detail
