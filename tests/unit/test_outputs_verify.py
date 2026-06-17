"""tool_verify(scope='outputs') — declared outputs exist + are non-empty."""
from __future__ import annotations

from research_os.tools.actions.research import grounding
from research_os.tools.actions.research.grounding import _check_output, verify_outputs


def _w(p, text="content"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_check_output_present(tmp_path):
    _w(tmp_path / "workspace" / "a.txt", "real content")
    res = _check_output(tmp_path, "workspace/a.txt", 1)
    assert res["status"] == "present" and res["next_action"] is None


def test_check_output_empty(tmp_path):
    _w(tmp_path / "workspace" / "a.txt", "")
    res = _check_output(tmp_path, "workspace/a.txt", 1)
    assert res["status"] == "empty" and "regenerate" in res["next_action"].lower()


def test_check_output_missing(tmp_path):
    res = _check_output(tmp_path, "workspace/nope.txt", 1)
    assert res["status"] == "missing" and "re-run" in res["next_action"].lower()


def test_check_output_glob_present(tmp_path):
    _w(tmp_path / "workspace" / "figs" / "fig_1.png", "PNGDATA")
    res = _check_output(tmp_path, "workspace/figs/*.png", 1)
    assert res["status"] == "present"


def test_check_output_glob_missing(tmp_path):
    res = _check_output(tmp_path, "workspace/figs/*.png", 1)
    assert res["status"] == "missing"


def test_check_output_strips_parenthetical_annotation(tmp_path):
    # Real protocols annotate paths, e.g. "x.log (only on failures)" — the bare
    # path must still resolve (was reported missing before the fix).
    _w(tmp_path / "workspace" / "logs" / "x.log", "real content")
    res = _check_output(tmp_path, "workspace/logs/x.log (only on failures)", 1)
    assert res["status"] == "present"


def test_check_output_strips_two_space_annotation(tmp_path):
    _w(tmp_path / "COLLABORATOR.md", "hi")
    res = _check_output(tmp_path, "COLLABORATOR.md   top-level, share-safe", 1)
    assert res["status"] == "present"


def test_check_output_glob_matches_populated_directory(tmp_path):
    # A glob can resolve to a populated DIRECTORY (workspace/*/scripts) — that's
    # present, not empty (was a false hard blocker before the fix).
    _w(tmp_path / "workspace" / "01_eda" / "scripts" / "run.py", "code here")
    res = _check_output(tmp_path, "workspace/*/scripts", 1)
    assert res["status"] == "present"
    assert res["bytes"] > 0


def test_check_output_skips_pure_prose(tmp_path):
    assert _check_output(tmp_path, "(entries appended to methods.md)", 1) is None
    assert _check_output(tmp_path, "see the limitations section", 1) is None


def test_check_output_min_bytes(tmp_path):
    _w(tmp_path / "workspace" / "a.txt", "ab")  # 2 bytes
    assert _check_output(tmp_path, "workspace/a.txt", 200)["status"] == "empty"
    assert _check_output(tmp_path, "workspace/a.txt", 1)["status"] == "present"


def test_verify_outputs_all_present(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "research_os.tools.actions.protocol.load_protocol",
        lambda name: {"expected_outputs": ["workspace/a.txt", "workspace/b.csv"]},
    )
    _w(tmp_path / "workspace" / "a.txt", "x")
    _w(tmp_path / "workspace" / "b.csv", "1,2,3")
    res = verify_outputs(tmp_path, scope="protocol", protocol_name="x")
    assert res["status"] == "success"
    assert res["all_passed"] is True
    assert res["present"] == 2 and res["missing"] == 0 and res["empty"] == 0
    assert "safe to log" in res["guidance"].lower()


def test_verify_outputs_gaps_block(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "research_os.tools.actions.protocol.load_protocol",
        lambda name: {"expected_outputs": [
            "workspace/a.txt", "workspace/b.csv", "workspace/c.md",
        ]},
    )
    _w(tmp_path / "workspace" / "a.txt", "present")
    _w(tmp_path / "workspace" / "b.csv", "")  # empty
    # c.md missing
    res = verify_outputs(tmp_path, scope="protocol", protocol_name="x")
    assert res["all_passed"] is False
    assert res["present"] == 1 and res["empty"] == 1 and res["missing"] == 1
    assert "do not log" in res["guidance"].lower()


def test_verify_outputs_no_protocol_resolvable(tmp_path):
    res = verify_outputs(tmp_path, scope="protocol")
    assert res["status"] == "error"
    assert "no protocol" in res["message"].lower()


def test_verify_outputs_no_expected_outputs_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "research_os.tools.actions.protocol.load_protocol",
        lambda name: {"expected_outputs": []},
    )
    res = verify_outputs(tmp_path, scope="protocol", protocol_name="x")
    assert res["all_passed"] is True and res["total"] == 0


def test_verify_outputs_project_scope_reads_log(tmp_path, monkeypatch):
    # Two protocols logged; union of their outputs is checked.
    log = tmp_path / ".os_state" / "protocol_execution_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    import json
    log.write_text(
        json.dumps({"protocol": "p1", "status": "completed"}) + "\n"
        + json.dumps({"protocol": "p2", "status": "completed"}) + "\n"
    )
    outputs = {"p1": ["workspace/a.txt"], "p2": ["workspace/b.txt"]}
    monkeypatch.setattr(
        "research_os.tools.actions.protocol.load_protocol",
        lambda name: {"expected_outputs": outputs[name]},
    )
    _w(tmp_path / "workspace" / "a.txt", "x")
    # b.txt missing
    res = verify_outputs(tmp_path, scope="project")
    assert set(res["protocols_checked"]) == {"p1", "p2"}
    assert res["present"] == 1 and res["missing"] == 1


def test_verify_outputs_rejects_unknown_scope(tmp_path):
    assert verify_outputs(tmp_path, scope="bogus")["status"] == "error"


def test_grounding_module_exposes_verify_outputs():
    assert callable(getattr(grounding, "verify_outputs"))
