"""Workspace scaffolding tests."""

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from research_os.project_ops import load_state, scaffold_minimal_workspace


def _scaffold(tmp: Path, name: str = "Test Project", **kwargs) -> Path:
    scaffold_minimal_workspace(tmp, name, **kwargs)
    return tmp


def test_scaffold_creates_required_directories():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        for directory in (
            "inputs",
            "inputs/raw_data",
            "inputs/literature",
            "inputs/context",
            "workspace",
            "workspace/logs",
            "synthesis",
            "docs",
            "environment",
            ".os_state",
        ):
            assert (root / directory).is_dir(), f"missing {directory}"


def test_scaffold_creates_key_files():
    """Scaffold creates the minimum needed for boot — NOT pre-baked outputs."""
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        # Required for session_boot + project_startup.
        for rel in (
            "AGENTS.md",
            "inputs/intake.md",
            "inputs/researcher_config.yaml",
            "docs/research_question.md",
            "docs/glossary.md",
            "workspace/methods.md",
            "workspace/analysis.md",
            "workspace/citations.md",
            "workspace/workflow.mermaid",
            ".os_state/state_ledger.json",
            ".os_state/manifest.json",
            ".os_state/os_state.md",
            ".gitignore",
        ):
            assert (root / rel).exists(), f"missing {rel}"
        # These must NOT be pre-created — protocols own them.
        for forbidden in (
            "synthesis/paper.md",
            "synthesis/abstract.md",
            "synthesis/poster.tex",
            "synthesis/dashboard.html",
            "docs/research_overview.md",
            "docs/domain_summary.md",
            "docs/research_design.md",
        ):
            assert not (root / forbidden).exists(), (
                f"scaffold pre-created {forbidden} — only protocols may write it"
            )


def test_researcher_config_permissions_locked_to_600():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        cfg = root / "inputs" / "researcher_config.yaml"
        mode = os.stat(cfg).st_mode
        if os.name != "nt":
            assert not bool(mode & stat.S_IROTH)
            assert (mode & 0o777) == 0o600


def test_gitignore_excludes_secrets_and_raw_data():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        content = (root / ".gitignore").read_text()
        assert "researcher_config.yaml" in content
        assert "inputs/raw_data/" in content


def test_state_has_project_name():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d), name="My Research Project")
        state = load_state(root)
        assert state.get("project_name") == "My Research Project"


def test_intake_reflects_overrides():
    with tempfile.TemporaryDirectory() as d:
        overrides = {
            "research_question": "Does X reduce Y?",
            "domain": "clinical",
        }
        root = _scaffold(Path(d), config_overrides=overrides)
        intake = (root / "inputs" / "intake.md").read_text()
        assert "Does X reduce Y?" in intake
        assert "clinical" in intake


def test_intake_md_is_minimal_placeholder():
    """intake.md should be a tiny placeholder — autofill replaces it later."""
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        intake = (root / "inputs" / "intake.md").read_text()
        assert "Research Intake" in intake


# ── CLI integration ────────────────────────────────────────────────────


@pytest.mark.integration
def test_cli_init_creates_workspace():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "my_project"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_os.cli",
                "init",
                str(target),
                "--name",
                "CLI Test",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert (target / ".os_state").exists()
        assert (target / "inputs" / "intake.md").exists()
        # synthesis/ should be present as a directory but EMPTY of outputs.
        assert (target / "synthesis").is_dir()
        assert not (target / "synthesis" / "paper.md").exists()


@pytest.mark.integration
def test_cli_init_with_name_flag():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "proj"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "research_os.cli",
                "init",
                str(target),
                "--name",
                "Named Project",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        state = load_state(target)
        assert state.get("project_name") == "Named Project"
