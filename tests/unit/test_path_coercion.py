"""v1.11.1 known-issue regression: handlers must accept ``root`` as ``str``.

Several theory_math and audit-pipeline callers pass ``root`` in as a
plain string rather than a ``pathlib.Path``. Before the v1.11.1 fix,
those entry points would hit ``str / "workspace"`` and raise a
``TypeError: unsupported operand type(s) for /: 'str' and 'str'``.

This module pins that contract by calling every public entry point in
:mod:`research_os.tools.actions.state.config` and
:mod:`research_os.tools.actions.audit.audit` with a ``str`` root and
asserting no ``TypeError`` escapes. The handlers may return an error
envelope (workspace missing, file missing) — that's fine — but they
must NOT raise the path-coercion ``TypeError``.
"""

from __future__ import annotations

import pytest

from research_os.tools.actions.audit.audit import (
    _is_humanities_project,
    _report_path,
    audit_citations,
    audit_figure,
    audit_quality_full,
    audit_reproducibility_full,
    audit_step_completeness,
    audit_synthesis,
    get_current_path,
)
from research_os.tools.actions.state.config import (
    _config_path,
    get_config,
    get_interaction_policy,
    get_research_config,
    init_config,
    set_config,
    validate_config,
)


@pytest.fixture
def str_root(tmp_path):
    """Project root as a ``str`` (not a ``Path``)."""
    (tmp_path / "workspace" / "logs").mkdir(parents=True)
    (tmp_path / "inputs").mkdir(parents=True)
    return str(tmp_path)


# ---------------------------------------------------------------------------
# state/config.py — entry points that take ``root``
# ---------------------------------------------------------------------------


def test_config_path_accepts_str_root(str_root):
    """``_config_path`` must coerce ``str`` → ``Path`` before joining."""
    p = _config_path(str_root)
    assert str(p).endswith("inputs/researcher_config.yaml")


def test_get_interaction_policy_accepts_str_root(str_root):
    """``get_interaction_policy`` falls back to defaults when no file —
    but it must not raise ``TypeError`` on a str root."""
    pol = get_interaction_policy(str_root)
    assert pol["quality_gate_policy"] in {"enforce", "allow_override", "warn_only"}


def test_get_config_accepts_str_root(str_root):
    """``get_config`` returns an error envelope when the file is missing;
    accepting a str root is the contract being pinned."""
    res = get_config(str_root)
    assert res["status"] in {"success", "error"}


def test_get_research_config_accepts_str_root(str_root):
    """Compatibility shim must accept a str root and return ``{}`` if
    the file is missing rather than raising."""
    cfg = get_research_config(str_root)
    assert isinstance(cfg, dict)


def test_set_config_accepts_str_root(str_root):
    """``set_config`` writes inputs/researcher_config.yaml — must accept
    str root."""
    res = set_config("researcher.name", "Test", str_root)
    assert res["status"] == "success"


def test_init_config_accepts_str_root(str_root):
    """``init_config`` is the wizard's main entry point — must accept
    str root."""
    res = init_config(str_root)
    assert res["status"] in {"success", "error"}


def test_validate_config_accepts_str_root(str_root):
    """``validate_config`` reads the config file — must accept str root."""
    init_config(str_root)
    res = validate_config(str_root)
    assert res["status"] in {"success", "error", "warning"}


# ---------------------------------------------------------------------------
# audit/audit.py — entry points that take ``root``
# ---------------------------------------------------------------------------


def test_get_current_path_accepts_str_root(str_root):
    """``get_current_path`` walks ``workspace/`` — must accept str root."""
    result = get_current_path(str_root)
    assert isinstance(result, str)


def test_report_path_accepts_str_root(str_root):
    """``_report_path`` joins ``root / "workspace" / ...`` — must accept
    str root."""
    p = _report_path(str_root, "smoke.md")
    assert "workspace" in str(p)


def test_audit_synthesis_accepts_str_root(str_root):
    """``audit_synthesis`` reads paper.md under root — must accept str
    root; returns error envelope when paper missing."""
    res = audit_synthesis("synthesis/missing.md", str_root)
    assert res["status"] == "error"


def test_audit_figure_accepts_str_root(str_root):
    """``audit_figure`` reads PNG under root — must accept str root;
    returns error envelope when figure missing."""
    res = audit_figure("workspace/01/outputs/figures/missing.png", str_root)
    assert res["status"] == "error"


def test_audit_citations_accepts_str_root(str_root):
    """``audit_citations`` reads ``workspace/citations.md`` — must accept
    str root; returns error envelope when file missing."""
    res = audit_citations(str_root)
    assert res["status"] == "error"


def test_audit_reproducibility_full_accepts_str_root(str_root):
    """``audit_reproducibility_full`` iterates ``workspace/`` — must
    accept str root."""
    res = audit_reproducibility_full(str_root)
    assert res["status"] in {"success", "error", "warning"}


def test_is_humanities_project_accepts_str_root(str_root):
    """``_is_humanities_project`` reads config + walks workspace — must
    accept str root."""
    result = _is_humanities_project(str_root)
    assert isinstance(result, bool)


def test_audit_step_completeness_accepts_str_root(str_root):
    """``audit_step_completeness`` walks numbered step dirs — must
    accept str root."""
    res = audit_step_completeness(str_root)
    assert res["status"] in {"success", "error", "warning"}


def test_audit_quality_full_accepts_str_root(str_root):
    """``audit_quality_full`` is the master aggregator called by
    tool_synthesis_check — must accept str root without crashing on
    path arithmetic."""
    res = audit_quality_full(str_root, skip=["claims", "code_quality", "prose_quality"])
    # Master aggregator returns its unified verdict envelope; the
    # specific status depends on what sub-audits found, but a
    # ``TypeError`` would never get this far.
    assert "status" in res or "results" in res
