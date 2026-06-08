"""Pre-registration freeze/diff tests.

The dashboard test scaffolding (generate_dashboard_test_suite /
run_dashboard_tests) was removed when the auto-dashboard generator
was dropped. AI-authored dashboards write their own tests if needed.
"""

from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.audit.preregistration import (
    diff_preregistration,
    freeze_preregistration,
)


def _scaffold(tmp_path: Path):
    scaffold_minimal_workspace(tmp_path, project_name="P", git_init=False, ide_flags=[])


def test_freeze_preregistration_writes_files(tmp_path: Path):
    _scaffold(tmp_path)
    r = freeze_preregistration(
        tmp_path, primary_outcomes="MoCA score change", target_n=200,
    )
    assert r["status"] == "success"
    prereg_dir = tmp_path / "workspace" / ".preregistration"
    files = list(prereg_dir.glob("prereg_*.md"))
    assert len(files) == 1
    # YAML companion present.
    assert list(prereg_dir.glob("prereg_*.yaml"))


def test_diff_preregistration_clean_with_no_changes(tmp_path: Path):
    _scaffold(tmp_path)
    freeze_preregistration(tmp_path)
    r = diff_preregistration(tmp_path)
    # No changes since freeze → success (or warning, but not error).
    assert r["status"] in {"success", "warning"}


def test_diff_returns_warning_when_no_prereg(tmp_path: Path):
    _scaffold(tmp_path)
    r = diff_preregistration(tmp_path)
    assert r["status"] == "warning"
    assert "pre-registration" in r["message"].lower()
