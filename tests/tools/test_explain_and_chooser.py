"""Tests for the beginner↔PI gradient tools.

* tool_explain  — grounded, layered tutor scaffold (no canned answers).
* tool_deliverable_chooser — output_types-gated 'what now?' recommender.

Doctrine assertions baked in:
  - tool_explain never returns a memorised answer; it returns questions +
    an explicit grounding instruction naming tool_research_method.
  - tool_deliverable_chooser respects research_goal.output_types: it asks
    when empty, and never recommends a deliverable outside the declared set.
"""
from __future__ import annotations

import json
import re

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.research.gradient import (
    deliverable_chooser,
    explain_scaffold,
)


# ---------------------------------------------------------------------------
# tool_explain
# ---------------------------------------------------------------------------


def test_explain_default_depth_all_layers():
    res = explain_scaffold("logistic regression")
    assert res["status"] == "success"
    assert res["depth"] == "all"
    layer_keys = [layer["layer"] for layer in res["layers"]]
    assert layer_keys == ["intuition", "mechanics", "caveats", "when_not", "reading"]
    assert res["layer_count"] == 5


def test_explain_depth_presets_are_cumulative():
    intu = explain_scaffold("kappa", depth="intuition")
    mech = explain_scaffold("kappa", depth="mechanics")
    cav = explain_scaffold("kappa", depth="caveats")
    assert [layer["layer"] for layer in intu["layers"]] == ["intuition"]
    assert [layer["layer"] for layer in mech["layers"]] == ["intuition", "mechanics"]
    assert [layer["layer"] for layer in cav["layers"]] == [
        "intuition", "mechanics", "caveats",
    ]


def test_explain_unknown_depth_falls_back_to_all():
    res = explain_scaffold("PCA", depth="wat")
    assert res["status"] == "success"
    assert res["depth"] == "all"


def test_explain_is_grounded_not_canned():
    """Doctrine: the tool must NOT answer from memory.

    Each layer carries QUESTIONS to answer, never an 'answer' field, and
    the grounding instruction must name the grounding tools.
    """
    res = explain_scaffold("instrumental variables")
    for layer in res["layers"]:
        assert "questions_to_answer" in layer
        assert isinstance(layer["questions_to_answer"], list)
        assert layer["questions_to_answer"]
        # No layer should hand back a precomputed answer.
        assert "answer" not in layer
    assert "tool_research_method" in res["grounding_instruction"]
    assert "tool_search" in res["grounding_instruction"]
    # The topic the AI must research is echoed into the instruction.
    assert "instrumental variables" in res["grounding_instruction"]


def test_explain_audience_tunes_delivery_note_only():
    res = explain_scaffold("survival analysis", audience="PI new to the method")
    assert "PI new to the method" in res["delivery_note"]
    # Audience does not change the layer set.
    assert res["depth"] == "all"


def test_explain_empty_topic_errors():
    res = explain_scaffold("")
    assert res["status"] == "error"
    res2 = explain_scaffold("   ")
    assert res2["status"] == "error"


def test_explain_handler_envelope(tmp_path):
    from research_os.server import _HANDLERS

    res = _HANDLERS["tool_explain"](
        "tool_explain", {"topic": "mixed effects models", "depth": "caveats"}, tmp_path,
    )
    payload = json.loads(res[0].text)
    assert payload["status"] == "success"
    data = payload["data"]
    assert data["topic"] == "mixed effects models"
    assert data["depth"] == "caveats"


def test_explain_handler_missing_topic_errors(tmp_path):
    from research_os.server import _HANDLERS

    res = _HANDLERS["tool_explain"]("tool_explain", {}, tmp_path)
    payload = json.loads(res[0].text)
    assert payload["status"] == "error"


# ---------------------------------------------------------------------------
# tool_deliverable_chooser
# ---------------------------------------------------------------------------


def _set_output_types(root, value: str) -> None:
    """Rewrite research_goal.output_types in the scaffolded config."""
    cfg = root / "inputs" / "researcher_config.yaml"
    txt = cfg.read_text()
    txt = re.sub(r"output_types:.*", f"output_types: {value}", txt, count=1)
    cfg.write_text(txt)


def test_chooser_empty_output_types_asks_not_assumes(tmp_path):
    """Anti-scope-creep: empty output_types ⇒ ask, never default to a paper."""
    scaffold_minimal_workspace(tmp_path, "Demo")
    res = deliverable_chooser(tmp_path)
    assert res["status"] == "success"
    assert res["decision"] == "ask_researcher"
    assert res["declared_output_types"] == []
    assert res.get("ask_user")
    assert res.get("options")
    # It must NOT have silently recommended anything.
    assert "recommendations" not in res
    # And it must tell the AI how to record the answer.
    assert "sys_config" in res["record_choice_with"]


def test_chooser_declared_single_type_recommends_only_that(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo")
    _set_output_types(tmp_path, "[dashboard]")
    res = deliverable_chooser(tmp_path)
    assert res["status"] == "success"
    assert res["decision"] == "recommend"
    assert res["declared_output_types"] == ["dashboard"]
    kinds = [r["kind"] for r in res["recommendations"]]
    assert kinds == ["dashboard"]
    # The anti-scope-creep invariant: a paper must NOT be recommended.
    assert "paper" not in kinds
    # The recommended deliverable maps to the right synthesis protocol.
    dash = res["recommendations"][0]
    assert dash["protocol"] == "synthesis/synthesis_dashboard"


def test_chooser_multiple_types_preserves_order(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo")
    _set_output_types(tmp_path, "[poster, paper]")
    res = deliverable_chooser(tmp_path)
    kinds = [r["kind"] for r in res["recommendations"]]
    assert kinds == ["poster", "paper"]
    assert res["scope_note"]


def test_chooser_reports_readiness_and_counts(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo")
    _set_output_types(tmp_path, "[report]")
    res = deliverable_chooser(tmp_path)
    assert "readiness" in res
    assert "ready_to_synthesize" in res["readiness"]
    assert "artifact_counts" in res
    # Fresh project: no steps with conclusions ⇒ not ready, with gaps listed.
    assert res["readiness"]["ready_to_synthesize"] is False
    assert res["readiness"]["gaps"]


def test_chooser_already_done_flag(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Demo")
    _set_output_types(tmp_path, "[report]")
    # Seed a finished report on disk so the done-predicate fires.
    (tmp_path / "synthesis").mkdir(exist_ok=True)
    (tmp_path / "synthesis" / "report.md").write_text("# Report\n\nFindings.\n")
    res = deliverable_chooser(tmp_path)
    rep = next(r for r in res["recommendations"] if r["kind"] == "report")
    assert rep["already_done"] is True
    # Nothing pending ⇒ next_deliverable is None.
    assert res["next_deliverable"] is None


def test_chooser_handler_envelope(tmp_path):
    from research_os.server import _HANDLERS

    scaffold_minimal_workspace(tmp_path, "Demo")
    _set_output_types(tmp_path, "[paper]")
    res = _HANDLERS["tool_deliverable_chooser"](
        "tool_deliverable_chooser", {}, tmp_path,
    )
    payload = json.loads(res[0].text)
    assert payload["status"] == "success"
    assert payload["data"]["decision"] == "recommend"
    assert payload["data"]["declared_output_types"] == ["paper"]
