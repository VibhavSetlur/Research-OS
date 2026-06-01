"""Override-audit trail + quality_gate_policy + sys_file_list lazy-dir tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research_os.project_ops import (
    create_numbered_experiment,
    log_override,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.audit.audit import audit_step_completeness
from research_os.tools.actions.state.config import get_interaction_policy


def _scaffold(tmp_path: Path) -> Path:
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    return tmp_path


# ── log_override is the canonical write path ────────────────────────────


def test_log_override_creates_log_with_header(tmp_path):
    root = _scaffold(tmp_path)
    log = log_override(
        root, tool="tool_synthesize", gate="quality_full",
        rationale="WIP preview", extra={"section": "abstract"},
    )
    assert log.exists()
    text = log.read_text()
    assert "Quality-gate bypass log" in text
    assert "tool_synthesize" in text
    assert "quality_full" in text
    assert "WIP preview" in text


def test_log_override_records_missing_rationale_for_audit(tmp_path):
    root = _scaffold(tmp_path)
    log_override(root, tool="tool_dashboard_create",
                 gate="step_completeness", rationale=None)
    assert "no rationale provided" in (root / "workspace" / "logs"
                                       / "override_log.md").read_text()


# ── researcher_config policy knobs actually drive behaviour ────────────


def test_interaction_policy_defaults(tmp_path):
    root = _scaffold(tmp_path)
    pol = get_interaction_policy(root)
    assert pol["quality_gate_policy"] == "enforce"
    assert pol["ambiguity_posture"] == "ask_when_uncertain"


def test_interaction_policy_reads_warn_only(tmp_path):
    root = _scaffold(tmp_path)
    cfg = root / "inputs" / "researcher_config.yaml"
    data = yaml.safe_load(cfg.read_text())
    data.setdefault("interaction", {})["quality_gate_policy"] = "warn_only"
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    assert get_interaction_policy(root)["quality_gate_policy"] == "warn_only"


def test_interaction_policy_rejects_garbage_value(tmp_path):
    """Unknown policy values fall back to the safe default, not crash."""
    root = _scaffold(tmp_path)
    cfg = root / "inputs" / "researcher_config.yaml"
    data = yaml.safe_load(cfg.read_text())
    data.setdefault("interaction", {})["quality_gate_policy"] = "nonsense"
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    assert get_interaction_policy(root)["quality_gate_policy"] == "enforce"


# ── sys_file_list on lazy dirs returns empty, not error ─────────────────


def _payload(result):
    """Unwrap the JSON payload from a TextContent list returned by handlers."""
    return json.loads(result[0].text)


def test_sys_file_list_lazy_dir_returns_empty(tmp_path):
    """Bug: sys_file_list on a lazy dir that hasn't been materialised
    returned 'Directory not found', breaking protocols that probe
    inputs/raw_data on a fresh project. Now: empty list + lazy hint."""
    from research_os.server import _handle_sys_file_list

    root = _scaffold(tmp_path)
    res = _handle_sys_file_list(
        "sys_file_list", {"directory": "inputs/raw_data"}, root,
    )
    payload = _payload(res)
    assert payload["status"] == "success", payload
    data = payload["data"]
    assert data.get("files") == []
    assert data.get("lazy_dir") is True
    assert data.get("empty") is True


def test_sys_file_list_unknown_dir_still_errors(tmp_path):
    """Non-lazy missing paths must still surface as errors so typos
    aren't masked."""
    from research_os.server import _handle_sys_file_list

    root = _scaffold(tmp_path)
    res = _handle_sys_file_list(
        "sys_file_list", {"directory": "not_a_real_dir"}, root,
    )
    payload = _payload(res)
    assert payload["status"] == "error"


def test_pre_submission_checklist_protocol_reads_override_log(tmp_path):
    """The pre-submission protocol must contain an explicit step that
    surfaces override_log.md entries — otherwise bypasses are written
    but never read."""
    import importlib.resources as r

    proto = (Path(__file__).resolve().parents[2] /
             "src" / "research_os" / "protocols" / "audit"
             / "pre_submission_checklist.yaml").read_text()
    assert "override_log.md" in proto
    assert "override_completeness_gate" in proto
