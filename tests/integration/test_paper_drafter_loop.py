"""Integration test for the Phase-5 review-rewrite drafter loop on
``tool_paper_compile_typst``.

Runs the full handler against a tiny on-disk paper, then asserts:

  * The handler returns a successful envelope with a ``drafter_loop``
    sub-dict describing the iterations.
  * Per-iteration logs land under
    ``workspace/logs/drafter_loops/paper_iter_<N>.{md,json}``.
  * The cumulative ``quality_progression.md`` table exists and names
    the ``paper`` drafter.
  * project_tier=throwaway clamps iteration count to 1.
  * drafter_loop_enabled=false bypasses the loop entirely (no
    ``drafter_loop`` key on the envelope; no drafter_loops/ directory
    created).

The test stubs out ``paper_compile_typst`` so it does not require the
Typst binary or any LaTeX setup; the stub returns a realistic
envelope including a ``source_text`` field the metric routines can
score against.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from research_os.tools.actions.state.config import CONFIG_TEMPLATE


SAMPLE_PAPER = """# Title

## Abstract

We measured p = 0.03 across n = 42 subjects; 12.5% effect size.

## Introduction

Prior work by Smith showed something. We extend that.

## Methods

We ran a t-test. The setup was straightforward.

## Results

The effect was strong [@smith2020]. We saw 95% confidence.

## Discussion

This may matter for practice. Future work could explore more.
"""


def _scaffold_project(
    tmp_path: Path, project_tier: str = "production",
    drafter_loop_enabled: bool = True,
    max_iter: int = 3,
) -> Path:
    """Write minimal researcher_config.yaml + a stub paper.md."""
    (tmp_path / "inputs").mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(CONFIG_TEMPLATE.format(project_name="paper_loop_test")) or {}
    cfg.setdefault("researcher", {})["name"] = "Test User"
    cfg.setdefault("research_goal", {})["output_types"] = ["paper"]
    cfg["project_tier"] = project_tier
    synth = cfg.setdefault("synthesis", {})
    synth["drafter_loop_enabled"] = drafter_loop_enabled
    synth["drafter_loop_max_iterations"] = max_iter
    synth["drafter_loop_quality_threshold"] = 0.10
    (tmp_path / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump(cfg, default_flow_style=False, sort_keys=False)
    )
    (tmp_path / "synthesis").mkdir(parents=True, exist_ok=True)
    (tmp_path / "synthesis" / "paper.md").write_text(
        SAMPLE_PAPER, encoding="utf-8"
    )
    return tmp_path


def _stub_compile(root, paper_path="synthesis/paper.md", venue=None,
                  output="synthesis/paper.pdf"):
    """Deterministic stub that mimics paper_compile_typst's envelope.

    The ``source_text`` field is what the metric routines actually
    score against — we attach the paper.md contents so the metrics are
    populated as if Typst had run.
    """
    text = (Path(root) / paper_path).read_text(encoding="utf-8")
    return {
        "status": "success",
        "pdf_path": str(Path(root) / output),
        "typst_path": str(Path(root) / "synthesis" / "paper.typ"),
        "biblio_path": str(Path(root) / "synthesis" / "biblio.yml"),
        "venue": venue or "generic_two_column",
        "page_count": 4,
        "citation_count": 1,
        "typst_warnings": [],
        "typst_errors": [],
        "message": None,
        "source_text": text,
    }


def _call_handler(root: Path, arguments: dict | None = None) -> dict:
    """Invoke the paper-compile handler and return the parsed envelope."""
    from research_os.server import _handle_tool_paper_compile_typst

    with patch(
        "research_os.tools.actions.synthesis.typst.paper_compile_typst",
        side_effect=_stub_compile,
    ):
        result = _handle_tool_paper_compile_typst(
            "tool_paper_compile_typst", arguments or {}, root
        )
    # Handler returns a list of TextContent envelopes from _text(...).
    # Walk to the JSON body via the .text attribute.
    assert isinstance(result, list) and result, result
    body = result[0].text
    parsed = json.loads(body)
    return parsed


@pytest.mark.integration
def test_paper_loop_runs_and_writes_iter_logs(tmp_path):
    root = _scaffold_project(tmp_path)
    envelope = _call_handler(root)
    assert envelope["status"] == "success", envelope

    loop = envelope["data"].get("drafter_loop")
    assert loop is not None, envelope
    assert loop["iterations"] >= 1
    assert isinstance(loop["quality_progression"], list)

    log_dir = root / "workspace" / "logs" / "drafter_loops"
    assert (log_dir / "paper_iter_1.md").exists()
    assert (log_dir / "paper_iter_1.json").exists()
    assert (log_dir / "quality_progression.md").exists()
    progression = (log_dir / "quality_progression.md").read_text()
    assert "paper" in progression
    assert "quality_score" in progression


@pytest.mark.integration
def test_paper_loop_throwaway_tier_clamps_to_one_iter(tmp_path):
    root = _scaffold_project(tmp_path, project_tier="throwaway", max_iter=5)
    envelope = _call_handler(root)
    loop = envelope["data"].get("drafter_loop")
    assert loop is not None
    assert loop["iterations"] == 1, (
        f"throwaway tier must clamp iterations to 1; got {loop['iterations']}"
    )


@pytest.mark.integration
def test_paper_loop_disabled_skips_wrapper(tmp_path):
    root = _scaffold_project(tmp_path, drafter_loop_enabled=False)
    envelope = _call_handler(root)
    payload = envelope["data"]
    assert "drafter_loop" not in payload, (
        "drafter_loop_enabled=false must skip the loop wrapper entirely"
    )
    # No log directory should be created when the loop is off.
    log_dir = root / "workspace" / "logs" / "drafter_loops"
    assert not log_dir.exists(), (
        f"loop disabled but log dir was created: {log_dir}"
    )


@pytest.mark.integration
def test_paper_loop_per_call_disable_via_argument(tmp_path):
    """Caller can pass drafter_loop=false to bypass even with config on."""
    root = _scaffold_project(tmp_path, drafter_loop_enabled=True)
    envelope = _call_handler(root, arguments={"drafter_loop": False})
    payload = envelope["data"]
    assert "drafter_loop" not in payload
