"""Global test fixtures — ensures tests never touch the real filesystem."""
import pytest
from pathlib import Path
from unittest import mock

@pytest.fixture(autouse=True)
def _isolate_find_project_root(monkeypatch, tmp_path):
    """Force find_project_root to return a temp directory, never the real cwd."""
    from research_os.utils import asset_manager

    def _fake_find_project_root(start=None):
        # Always return the test's temporary directory
        return tmp_path

    monkeypatch.setattr(
        asset_manager.AssetManager, "find_project_root",
        staticmethod(_fake_find_project_root),
    )
    # Also patch the convenience import in common.py
    monkeypatch.setattr(
        "research_os.utils.common.find_project_root",
        _fake_find_project_root,
    )
    # And the direct import in state_ledger.py
    monkeypatch.setattr(
        "research_os.state.state_ledger.find_project_root",
        _fake_find_project_root,
    )
    # And in checkpoint_manager.py
    monkeypatch.setattr(
        "research_os.state.checkpoint_manager.find_project_root",
        _fake_find_project_root,
    )
