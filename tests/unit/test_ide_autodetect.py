"""4.0.3: `research-os init --ide` defaults to auto-detect ONE IDE, never all."""
from __future__ import annotations

import pytest

from research_os.cli import VALID_IDES, _detect_ide, _ide_choice

_IDE_ENV = [
    "RESEARCH_OS_IDE", "TERM_PROGRAM", "CURSOR_TRACE_ID", "WINDSURF_ENV",
    "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "VSCODE_PID",
    "VSCODE_GIT_IPC_HANDLE",
]


@pytest.fixture
def _clean_ide_env(monkeypatch):
    for k in _IDE_ENV:
        monkeypatch.delenv(k, raising=False)
    # Make PATH detection deterministic (no IDE binaries).
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)
    return monkeypatch


def test_auto_with_no_signal_wires_nothing(_clean_ide_env):
    # The whole point: auto must NOT fall back to all 8 IDEs.
    assert _ide_choice("auto") == []
    assert _ide_choice(None) == []


def test_explicit_all_still_wires_everything():
    assert len(_ide_choice("all")) == len(VALID_IDES)


def test_explicit_none_wires_nothing():
    assert _ide_choice("none") == []


def test_explicit_list_is_honoured():
    assert _ide_choice("cursor,vscode") == ["cursor", "vscode"]


def test_env_override_detects_single_ide(_clean_ide_env):
    _clean_ide_env.setenv("RESEARCH_OS_IDE", "cursor")
    assert _detect_ide() == ["cursor"]


def test_claude_code_env_detected(_clean_ide_env):
    _clean_ide_env.setenv("CLAUDECODE", "1")
    assert _detect_ide() == ["claude"]


def test_cursor_term_program_detected(_clean_ide_env):
    _clean_ide_env.setenv("TERM_PROGRAM", "cursor")
    assert _detect_ide() == ["cursor"]
