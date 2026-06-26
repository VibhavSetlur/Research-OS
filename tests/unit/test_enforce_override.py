"""F2.3: the enforce_override() helper + step_complete override journaling.

Before 4.0.1 the override sequence was copy-pasted across gate handlers and had
drifted — notably tool_step_complete applied a literature/grounding override but
NEVER journaled it to override_log.md, so the bypass was invisible to the
pre-submission audit.
"""
from __future__ import annotations

from pathlib import Path

from research_os.project_ops import enforce_override, scaffold_minimal_workspace


def _proj(tmp_path: Path) -> Path:
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    return tmp_path


def test_enforce_override_rejects_empty_rationale(tmp_path):
    err = enforce_override(_proj(tmp_path), requested=True, rationale="",
                           tool="t", gate="g", blocked=True)
    assert err is not None and err.get("status") == "error"


def test_enforce_override_rejects_thin_rationale(tmp_path):
    err = enforce_override(_proj(tmp_path), requested=True, rationale="TODO",
                           tool="t", gate="g", blocked=True)
    assert err is not None


def test_enforce_override_journals_when_blocked(tmp_path):
    root = _proj(tmp_path)
    err = enforce_override(
        root, requested=True,
        rationale="3pm preview for the PI; methods.md still a stub but figures final",
        tool="tool_x", gate="my_gate", blocked=True,
    )
    assert err is None
    log = root / "workspace" / "logs" / "override_log.md"
    assert log.exists() and "gate=my_gate" in log.read_text()


def test_enforce_override_noop_when_not_requested(tmp_path):
    root = _proj(tmp_path)
    err = enforce_override(root, requested=False, rationale="",
                           tool="t", gate="quiet", blocked=True)
    assert err is None
    log = root / "workspace" / "logs" / "override_log.md"
    # nothing journaled for a non-requested override
    assert (not log.exists()) or "gate=quiet" not in log.read_text()
