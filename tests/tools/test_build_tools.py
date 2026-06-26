"""Tests for the tool_build workspace-mode tools + scope='tool' audits.

Covers tool_git (init/status/commit/log on a tmp inner repo), tool_build
(a trivial configured echo command), and the three scope='tool' audit
dimensions (tests / git_hygiene / build) on a tmp tool_build project,
including mode-awareness (no-op outside tool_build).
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.audit.tool_build_audit import (
    audit_tool_build,
    audit_tool_git_hygiene,
    audit_tool_tests,
)
from research_os.tools.actions.exec.build_tools import (
    build_op,
    git_op,
    is_tool_build_mode,
)

_GIT = shutil.which("git") is not None
requires_git = pytest.mark.skipif(not _GIT, reason="git not on PATH")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _write_config(root, *, mode="tool_build", inner_repo="project", commands=None):
    """Write a researcher_config.yaml with the given workspace block."""
    cfg_path = root / "inputs" / "researcher_config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = {
        "project_name": "Build Tools Test",
        "workspace": {"mode": mode, "inner_repo": inner_repo},
    }
    if commands is not None:
        cfg["workspace"]["commands"] = commands
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))


def _git_identity(repo):
    """Set a local committer identity so commits work in a bare CI env."""
    subprocess.run(["git", "config", "user.email", "test@research-os"], cwd=str(repo))
    subprocess.run(["git", "config", "user.name", "Research OS Test"], cwd=str(repo))


def _tool_build_project(tmp_path, *, commands=None, inner_repo="project"):
    """Scaffold a tool_build project with an initialised inner git repo."""
    scaffold_minimal_workspace(tmp_path, "Build Tools Test")
    _write_config(
        tmp_path, mode="tool_build", inner_repo=inner_repo, commands=commands
    )
    res = git_op(tmp_path, "init")
    assert res["status"] == "success"
    repo = tmp_path / inner_repo
    _git_identity(repo)
    return repo


# ---------------------------------------------------------------------------
# tool_git
# ---------------------------------------------------------------------------


@requires_git
def test_git_init_creates_inner_repo(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T")
    _write_config(tmp_path)
    res = git_op(tmp_path, "init")
    assert res["status"] == "success"
    assert res["already_initialised"] is False
    assert (tmp_path / "project" / ".git").exists()
    # Idempotent.
    again = git_op(tmp_path, "init")
    assert again["status"] == "success"
    assert again["already_initialised"] is True


@requires_git
def test_git_status_clean_then_dirty(tmp_path):
    repo = _tool_build_project(tmp_path)
    clean = git_op(tmp_path, "status")
    assert clean["status"] == "success"
    assert clean["clean"] is True
    assert clean["changed_files"] == []

    (repo / "main.py").write_text("print('hi')\n")
    dirty = git_op(tmp_path, "status")
    assert dirty["clean"] is False
    assert "main.py" in dirty["changed_files"]


@requires_git
def test_git_commit_with_step_provenance(tmp_path):
    repo = _tool_build_project(tmp_path)
    (repo / "main.py").write_text("print('hi')\n")
    res = git_op(tmp_path, "commit", message="add main", step_id="01_bootstrap")
    assert res["status"] == "success"
    assert res["sha"]
    assert res["step_id"] == "01_bootstrap"
    # The provenance trailer is in the commit body.
    body = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=str(repo), capture_output=True, text=True,
    ).stdout
    assert "Research-OS-Step: 01_bootstrap" in body


@requires_git
def test_git_commit_nothing_to_commit_is_noop(tmp_path):
    _tool_build_project(tmp_path)
    # No staged changes after init.
    res = git_op(tmp_path, "commit", message="empty")
    assert res["status"] == "noop"
    assert "nothing to commit" in res["message"].lower()


@requires_git
def test_git_log_returns_commits(tmp_path):
    repo = _tool_build_project(tmp_path)
    (repo / "a.txt").write_text("a\n")
    git_op(tmp_path, "commit", message="first")
    (repo / "b.txt").write_text("b\n")
    git_op(tmp_path, "commit", message="second")
    res = git_op(tmp_path, "log", max_count=10)
    assert res["status"] == "success"
    assert res["commit_count"] == 2
    subjects = [c["subject"] for c in res["commits"]]
    assert subjects == ["second", "first"]


@requires_git
def test_git_branch_and_tag(tmp_path):
    repo = _tool_build_project(tmp_path)
    (repo / "a.txt").write_text("a\n")
    git_op(tmp_path, "commit", message="first")
    # branch create + list
    created = git_op(tmp_path, "branch", name="feature/x")
    assert created["status"] == "success"
    assert created["branch"] == "feature/x"
    listed = git_op(tmp_path, "branch")
    assert "feature/x" in listed["branches"]
    # tag create + list
    tagged = git_op(tmp_path, "tag", name="v0.1.0", message="first release")
    assert tagged["status"] == "success"
    assert tagged["created"] == "v0.1.0"
    tags = git_op(tmp_path, "tag")
    assert "v0.1.0" in tags["tags"]


@requires_git
def test_git_status_on_non_repo_errors(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T")
    _write_config(tmp_path)
    res = git_op(tmp_path, "status")
    assert res["status"] == "error"
    assert "not a git repository" in res["message"].lower()


def test_git_unknown_operation_errors(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T")
    _write_config(tmp_path)
    res = git_op(tmp_path, "frobnicate")
    assert res["status"] == "error"
    assert "unknown operation" in res["message"].lower()


# ---------------------------------------------------------------------------
# tool_build
# ---------------------------------------------------------------------------


def test_build_runs_configured_echo_command(tmp_path):
    # tool_build only needs the inner dir to exist — no git required.
    scaffold_minimal_workspace(tmp_path, "T")
    _write_config(tmp_path, commands={"test": "echo ran-the-tests"})
    (tmp_path / "project").mkdir(exist_ok=True)
    res = build_op(tmp_path, "test")
    assert res["status"] == "success"
    assert res["passed"] is True
    assert res["configured"] is True
    assert "ran-the-tests" in res["output_tail"]
    # Full transcript is logged.
    assert (tmp_path / "workspace" / "logs" / "build_test.log").exists()


def test_build_failing_command_reports_not_passed(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T")
    _write_config(tmp_path, commands={"test": "exit 3"})
    (tmp_path / "project").mkdir(exist_ok=True)
    res = build_op(tmp_path, "test")
    assert res["status"] == "error"
    assert res["passed"] is False
    assert res["exit_code"] == 3


def test_build_unconfigured_command_gives_clear_message(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T")
    _write_config(tmp_path, commands={})
    (tmp_path / "project").mkdir(exist_ok=True)
    res = build_op(tmp_path, "build")
    assert res["status"] == "error"
    assert res["configured"] is False
    assert "workspace.commands.build" in res["message"]


def test_build_unknown_operation_errors(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T")
    _write_config(tmp_path)
    res = build_op(tmp_path, "deploy")
    assert res["status"] == "error"
    assert "unknown operation" in res["message"].lower()


# ---------------------------------------------------------------------------
# scope='tool' audits — mode-awareness
# ---------------------------------------------------------------------------


def test_audits_noop_outside_tool_build(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T")
    _write_config(tmp_path, mode="analysis")
    assert is_tool_build_mode(tmp_path) is False
    for fn in (audit_tool_tests, audit_tool_git_hygiene, audit_tool_build):
        res = fn(tmp_path)
        assert res["status"] == "success"
        assert res["applicable"] is False
        assert res["blockers"] == []
        assert "tool_build" in res["message"]


# ---------------------------------------------------------------------------
# scope='tool' audit: tests
# ---------------------------------------------------------------------------


@requires_git
def test_audit_tests_blocks_on_failing_suite(tmp_path):
    _tool_build_project(tmp_path, commands={"test": "exit 1"})
    res = audit_tool_tests(tmp_path)
    assert res["applicable"] is True
    assert res["status"] == "error"
    assert res["blockers"]
    assert "failed" in res["blockers"][0].lower()


@requires_git
def test_audit_tests_blocks_on_zero_tests(tmp_path):
    _tool_build_project(
        tmp_path, commands={"test": "echo 'collected 0 items'"}
    )
    res = audit_tool_tests(tmp_path)
    assert res["status"] == "error"
    assert any("zero tests" in b.lower() for b in res["blockers"])


@requires_git
def test_audit_tests_passes_on_real_green_run(tmp_path):
    _tool_build_project(
        tmp_path, commands={"test": "echo '3 passed in 0.01s'"}
    )
    res = audit_tool_tests(tmp_path)
    assert res["status"] == "success"
    assert res["blockers"] == []


@requires_git
def test_audit_tests_blocks_when_unconfigured(tmp_path):
    _tool_build_project(tmp_path, commands={})
    res = audit_tool_tests(tmp_path)
    assert res["status"] == "error"
    assert any("no test command" in b.lower() for b in res["blockers"])


# ---------------------------------------------------------------------------
# scope='tool' audit: git_hygiene
# ---------------------------------------------------------------------------


@requires_git
def test_audit_git_hygiene_blocks_no_commit(tmp_path):
    _tool_build_project(tmp_path)
    res = audit_tool_git_hygiene(tmp_path)
    assert res["status"] == "error"
    assert any("no commit at head" in b.lower() for b in res["blockers"])


@requires_git
def test_audit_git_hygiene_blocks_uncommitted(tmp_path):
    repo = _tool_build_project(tmp_path)
    (repo / "a.txt").write_text("a\n")
    git_op(tmp_path, "commit", message="first")
    (repo / "b.txt").write_text("b\n")  # uncommitted
    res = audit_tool_git_hygiene(tmp_path)
    assert res["status"] == "error"
    assert any("uncommitted" in b.lower() for b in res["blockers"])


@requires_git
def test_audit_git_hygiene_clean_passes(tmp_path):
    repo = _tool_build_project(tmp_path)
    (repo / "a.txt").write_text("a\n")
    git_op(tmp_path, "commit", message="add a clean implementation")
    res = audit_tool_git_hygiene(tmp_path)
    assert res["status"] == "success"
    assert res["blockers"] == []


@requires_git
def test_audit_git_hygiene_warns_on_wip_commit(tmp_path):
    repo = _tool_build_project(tmp_path)
    (repo / "a.txt").write_text("a\n")
    git_op(tmp_path, "commit", message="wip: half-done thing")
    res = audit_tool_git_hygiene(tmp_path)
    # Clean tree (committed) but WIP subject → warning, not block.
    assert res["status"] == "warning"
    assert res["warnings"]
    assert res["wip_commits"]


# ---------------------------------------------------------------------------
# scope='tool' audit: build
# ---------------------------------------------------------------------------


@requires_git
def test_audit_build_passes_on_green_build(tmp_path):
    _tool_build_project(tmp_path, commands={"build": "echo built"})
    res = audit_tool_build(tmp_path)
    assert res["status"] == "success"
    assert res["blockers"] == []


@requires_git
def test_audit_build_blocks_on_failure(tmp_path):
    _tool_build_project(tmp_path, commands={"build": "exit 2"})
    res = audit_tool_build(tmp_path)
    assert res["status"] == "error"
    assert any("build failed" in b.lower() for b in res["blockers"])


@requires_git
def test_audit_build_blocks_when_unconfigured(tmp_path):
    _tool_build_project(tmp_path, commands={})
    res = audit_tool_build(tmp_path)
    assert res["status"] == "error"
    assert any("no build command" in b.lower() for b in res["blockers"])


@requires_git
def test_git_restore_rolls_back_to_tagged_version(tmp_path):
    """restore returns the tree to a blessed tag without losing history."""
    repo = _tool_build_project(tmp_path)
    # v1: good version, tagged.
    (repo / "main.py").write_text("VERSION = 1\n")
    git_op(tmp_path, "commit", message="v1")
    git_op(tmp_path, "tag", name="good-v1")
    # v2: a regression.
    (repo / "main.py").write_text("VERSION = 2  # broke it\n")
    git_op(tmp_path, "commit", message="v2 regression")

    res = git_op(tmp_path, "restore", name="good-v1")
    assert res["status"] == "success"
    assert res["restored_to"] == "good-v1"
    assert res["rolled_back_from"]  # the v2 sha is recorded
    # the file is back to v1 content
    assert "VERSION = 1" in (repo / "main.py").read_text()
    # history is NOT lost — v2 commit still in the log
    log = git_op(tmp_path, "log")
    subjects = [c["subject"] for c in log["commits"]]
    assert "v2 regression" in subjects


@requires_git
def test_git_restore_rejects_unknown_ref(tmp_path):
    _tool_build_project(tmp_path)
    res = git_op(tmp_path, "restore", name="no-such-tag")
    assert res["status"] == "error"
    assert "unknown" in res["message"].lower()


@requires_git
def test_git_restore_needs_a_ref(tmp_path):
    _tool_build_project(tmp_path)
    res = git_op(tmp_path, "restore")
    assert res["status"] == "error"
    assert "name=" in res["message"]

