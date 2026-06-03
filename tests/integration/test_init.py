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


def test_scaffold_creates_eager_directories():
    """Scaffold creates EAGER dirs (always populated). LAZY dirs
    (synthesis/, environment/, inputs/{raw_data,literature,context}/)
    are created at first write, not at init — keeps the project
    surface uncluttered for the researcher."""
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        for directory in (
            "inputs",
            "workspace",
            "workspace/logs",
            "workspace/scratch",
            "docs",
            ".os_state",
        ):
            assert (root / directory).is_dir(), f"missing {directory}"


def test_scaffold_omits_lazy_directories():
    """Lazy dirs (currently just ``synthesis/``) must NOT exist after a
    cold init — they materialise on first write via ``ensure_lazy_dir``.

    Note: as of v1.3.0, inputs/{raw_data,literature,context}/ moved from
    LAZY_DIRS to EAGER_DIRS so a researcher's `cp foo.csv inputs/raw_data/`
    works without `mkdir -p`. See ``test_scaffold_creates_key_files``."""
    from research_os.project_ops import LAZY_DIRS

    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        for rel in LAZY_DIRS:
            assert not (root / rel).exists(), (
                f"scaffold created lazy dir '{rel}' — should defer to first write"
            )


def test_scaffold_creates_key_files():
    """Scaffold creates the minimum needed for boot — NOT pre-baked outputs."""
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        # Required for session_boot + project_startup.
        for rel in (
            "AGENTS.md",
            "GETTING_STARTED.md",
            "inputs/intake.md",
            "inputs/researcher_config.yaml",
            # v1.3.0 round-3: inputs/{raw_data,literature,context}/ are
            # now eagerly scaffolded so a researcher running
            # `cp foo.csv inputs/raw_data/` doesn't need mkdir -p first.
            # Each ships with a one-paragraph README explaining what
            # belongs there.
            "inputs/raw_data/README.md",
            "inputs/literature/README.md",
            "inputs/context/README.md",
            # v1.3.0 round-3: project-root README.md — the GitHub /
            # repo-browser-cold-open front page. Distinct from
            # GETTING_STARTED.md (researcher-driving-this-project).
            "README.md",
            "docs/glossary.md",
            "workspace/methods.md",
            "workspace/analysis.md",
            "workspace/citations.md",
            "workspace/workflow.mermaid",
            "workspace/scratch/README.md",
            "workspace/scratch/.gitignore",
            ".os_state/state_ledger.json",
            ".os_state/manifest.json",
            # v1.3.0 round-2: human-readable status is now at PROJECT
            # ROOT (was `.os_state/os_state.md`) so a fresh AI session
            # finds it without inside knowledge.
            "STATE.md",
            ".gitignore",
        ):
            assert (root / rel).exists(), f"missing {rel}"
        # v1.3.0 round-2: the old buried os_state.md must NOT exist.
        assert not (root / ".os_state" / "os_state.md").exists(), (
            "old `.os_state/os_state.md` should be gone in v1.3.0"
        )
        # These must NOT be pre-created — protocols own them.
        # docs/research_overview.md is also deferred — created lazily
        # by tool_intake_autofill once the researcher has real context.
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


def test_cold_init_keeps_short_intake_pointer():
    """Bug: scaffold wrote the short pointer, then regenerate_intake
    immediately overwrote it with the legacy long-form table on every
    cold init. The pointer must survive when no inputs/overrides are
    present so the AI knows to call tool_intake_autofill later."""
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        intake = (root / "inputs" / "intake.md").read_text()
        assert "fill out the intake" in intake.lower(), (
            f"cold init should keep the short pointer; got:\n{intake[:300]}"
        )
        # And NOT regenerate the long-form table on a cold init.
        assert "Auto-generated:" not in intake


def test_init_writes_full_intake_when_overrides_present():
    """When the wizard captures a research question / domain, the
    intake should reflect it immediately (so the AI doesn't have to
    re-derive what the researcher already said)."""
    with tempfile.TemporaryDirectory() as d:
        overrides = {
            "research_question": "Does X reduce Y?",
            "domain": "clinical",
        }
        root = _scaffold(Path(d), config_overrides=overrides)
        intake = (root / "inputs" / "intake.md").read_text()
        assert "Does X reduce Y?" in intake
        assert "clinical" in intake


def test_ensure_lazy_dir_rejects_unknown_paths(tmp_path):
    """Bug: ensure_lazy_dir was dead code that quietly mkdir'd any
    path. It now refuses paths not in LAZY_DIRS so writers can't
    silently grow the lazy surface."""
    from research_os.project_ops import ensure_lazy_dir, scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    # Registered lazy dir — OK.
    p = ensure_lazy_dir(tmp_path, "synthesis")
    assert p.is_dir()
    # Random path — refused.
    with pytest.raises(ValueError):
        ensure_lazy_dir(tmp_path, "not_a_lazy_dir")


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
        # synthesis/ is LAZY — created on first synthesis, NOT at init.
        assert not (target / "synthesis").exists()
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


# ---------------------------------------------------------------------------
# v1.3.0 round-3 — new init invariants
# ---------------------------------------------------------------------------


def test_project_root_readme_is_researcher_facing():
    """The project-root README.md must read as a GitHub/repo front page —
    NOT a Research-OS-internal doc. Smoke check: doesn't lead with MCP
    tool names, includes the project name + a 'Reproducing' section."""
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d), name="Test Project Name")
        readme = (root / "README.md").read_text()
        assert "Test Project Name" in readme, "project name should be in README"
        # No leakage of MCP / system jargon at the top of the file.
        first_500 = readme[:500]
        for forbidden in ("sys_boot", "tool_route", "mem_analysis_log", "_handle_"):
            assert forbidden not in first_500, (
                f"{forbidden!r} leaked into the researcher-facing README "
                f"opening — should NEVER appear in the project front page."
            )
        # The "Reproducing" + "What's in this folder" sections matter.
        assert "Reproducing" in readme
        assert "What's in this folder" in readme


def test_inputs_subdirs_eagerly_scaffolded_with_readmes():
    """v1.3.0: inputs/{raw_data,literature,context}/ are eager so
    `cp foo.csv inputs/raw_data/` works at init without mkdir -p."""
    with tempfile.TemporaryDirectory() as d:
        root = _scaffold(Path(d))
        for sub in ("raw_data", "literature", "context"):
            sub_dir = root / "inputs" / sub
            assert sub_dir.is_dir(), f"inputs/{sub}/ must be eager"
            readme = sub_dir / "README.md"
            assert readme.exists(), f"inputs/{sub}/README.md should be seeded"
            body = readme.read_text()
            assert sub in body or "Drop" in body or "AI" in body, (
                f"inputs/{sub}/README.md should briefly explain what belongs"
            )


def test_cross_project_profile_seeds_researcher_block(tmp_path, monkeypatch):
    """When ~/.config/research-os/profile.yaml exists, init_config should
    seed researcher.name / email / institution / orcid from it."""
    fake_xdg = tmp_path / "xdg_config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_xdg))
    from research_os.tools.actions.state.config import save_profile, init_config

    save_profile({
        "researcher": {
            "name": "Test Researcher",
            "email": "test@example.org",
            "institution": "Test University",
            "orcid": "0000-0001-2345-6789",
        },
        "model_profile": "large",
    })
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "inputs").mkdir()
    init_config(proj, overrides={})
    import yaml as _y
    cfg = _y.safe_load((proj / "inputs" / "researcher_config.yaml").read_text())
    assert cfg["researcher"]["name"] == "Test Researcher"
    assert cfg["researcher"]["email"] == "test@example.org"
    assert cfg["researcher"]["institution"] == "Test University"
    assert cfg["model_profile"] == "large"
