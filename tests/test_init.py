"""Tests: workspace init creates the expected directory/file structure."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from research_os.project_ops import scaffold_minimal_workspace, load_state


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _scaffold(tmp: Path, name: str = "Test Project", **kwargs) -> Path:
    """Call scaffold and return the root."""
    scaffold_minimal_workspace(tmp, name, **kwargs)
    return tmp


# ─────────────────────────────────────────────────────────────────────────────
# Directory structure
# ─────────────────────────────────────────────────────────────────────────────

def test_scaffold_creates_required_directories():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        for directory in ("inputs", "workspace", "synthesis", "docs", "environment", ".os_state"):
            assert (root / directory).is_dir(), f"Missing directory: {directory}"


def test_scaffold_creates_key_markdown_files():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        expected = [
            "synthesis/paper.md",
            "inputs/intake.md",
            "docs/research_question.md",
            "docs/research_overview.md",
            "workspace/methods.md",
            "workspace/analysis.md",
            "workspace/citations.md",
        ]
        for rel in expected:
            assert (root / rel).exists(), f"Missing file: {rel}"


def test_scaffold_creates_state_files():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        assert (root / ".os_state" / "state.json").exists() or \
               (root / ".os_state" / "manifest.json").exists(), \
               ".os_state should contain state or manifest JSON"


def test_scaffold_creates_researcher_config():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        cfg = root / "inputs" / "researcher_config.yaml"
        assert cfg.exists(), "researcher_config.yaml must be created"
        # Should not be world-readable (permissions checked via stat)
        import os, stat
        mode = os.stat(cfg).st_mode
        assert not bool(mode & stat.S_IROTH), "researcher_config.yaml should not be world-readable"


def test_scaffold_creates_gitignore():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        gi = root / ".gitignore"
        assert gi.exists(), ".gitignore must be created"
        content = gi.read_text()
        assert "researcher_config.yaml" in content


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

def test_scaffold_state_has_project_name():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d), name="My Research Project")
        state = load_state(root)
        assert state.get("project_name") == "My Research Project"


def test_scaffold_with_overrides_populates_intake():
    with tempfile.TemporaryDirectory() as d:
        overrides = {
            "research_question": "Does intervention X reduce outcome Y?",
            "domain": "Clinical Research",
            "depth": "deep",
        }
        root = _scaffold(Path(d), config_overrides=overrides)
        intake = (root / "inputs" / "intake.md").read_text()
        assert "Does intervention X reduce outcome Y?" in intake
        assert "Clinical Research" in intake


def test_scaffold_paper_md_has_content():
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        paper = (root / "synthesis" / "paper.md").read_text()
        assert "# " in paper  # Has at least one heading
        assert len(paper) > 50  # More than a stub


# ─────────────────────────────────────────────────────────────────────────────
# CLI integration — runs research-os init in a subprocess
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_cli_init_creates_workspace():
    """End-to-end: 'research-os init' should scaffold correctly."""
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "my_project"
        result = subprocess.run(
            [sys.executable, "-m", "research_os.cli", "init", str(target), "--name", "CLI Test"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"CLI init failed:\n{result.stderr}"
        assert target.is_dir(), "Target directory was not created"
        assert (target / ".os_state").exists(), ".os_state not found after init"
        assert (target / "inputs" / "intake.md").exists(), "intake.md not found"
        assert (target / "synthesis" / "paper.md").exists(), "paper.md not found"


@pytest.mark.integration
def test_cli_init_with_name_flag():
    """--name should be used as project_name in the state."""
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "proj"
        subprocess.run(
            [sys.executable, "-m", "research_os.cli", "init", str(target), "--name", "Named Project"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        state = load_state(target)
        assert state.get("project_name") == "Named Project"
