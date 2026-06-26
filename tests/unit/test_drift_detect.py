"""4.0.4: mid-prompt off-protocol drift detection (self-correction)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.server.dispatch import _handle_tool_call
from research_os.server.drift_detect import drift_hint


def _proj() -> Path:
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode="analysis")
    return root


def _codes(env: dict) -> list:
    return [f.get("code") for f in (env.get("audit_findings") or []) if isinstance(f, dict)]


def test_freelance_step_write_gets_course_correct_hint():
    root = _proj()
    (root / "workspace" / "01_analysis" / "scripts").mkdir(parents=True, exist_ok=True)
    r = _handle_tool_call(
        "sys_file_write",
        {"filepath": "workspace/01_analysis/scripts/01_run_v1.py", "content": "x=1"},
        root,
    )
    env = json.loads(r[0].text)
    assert env.get("status") == "success"  # NON-blocking: write still succeeds
    assert "off_protocol_freelancing" in _codes(env)
    assert env.get("next_recommended_call")  # points at tool_route


def test_routed_write_gets_no_nudge():
    root = _proj()
    (root / ".os_state").mkdir(exist_ok=True)
    (root / ".os_state" / "active_plan.json").write_text('{"protocol":"x"}')
    (root / "workspace" / "01_analysis" / "scripts").mkdir(parents=True, exist_ok=True)
    r = _handle_tool_call(
        "sys_file_write",
        {"filepath": "workspace/01_analysis/scripts/01_run_v1.py", "content": "x=1"},
        root,
    )
    env = json.loads(r[0].text)
    assert "off_protocol_freelancing" not in _codes(env)


def test_non_step_writes_never_nudge():
    root = _proj()
    # scratch + inputs are NOT step-like → no nudge even with no routing
    assert drift_hint("sys_file_write",
                      {"filepath": "workspace/scratch/quick.py"}, root) is None
    assert drift_hint("sys_file_write",
                      {"filepath": "inputs/context/notes.md"}, root) is None
    assert drift_hint("sys_file_write",
                      {"filepath": "workspace/logs/x.md"}, root) is None


def test_non_step_producing_tool_never_nudges():
    root = _proj()
    assert drift_hint("sys_boot", {}, root) is None
    assert drift_hint("tool_route", {"prompt": "x"}, root) is None


def test_debounce_suppresses_repeat_nudge():
    root = _proj()
    a = {"filepath": "workspace/01_x/conclusions.md"}
    first = drift_hint("sys_file_write", a, root)
    second = drift_hint("sys_file_write", a, root)
    assert first is not None
    assert second is None  # debounced within the window
