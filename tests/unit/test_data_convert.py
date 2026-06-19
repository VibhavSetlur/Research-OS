"""Tests for data_convert path-containment safety (E7)."""
from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from research_os.tools.actions.data.data import data_convert  # noqa: E402


def test_data_convert_relative_input_succeeds(tmp_path: Path):
    """A normal relative input inside the project converts cleanly and
    returns a project-relative output path."""
    (tmp_path / "inputs").mkdir()
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    df.to_csv(tmp_path / "inputs" / "d.csv", index=False)

    res = data_convert("inputs/d.csv", "parquet", tmp_path)
    assert res["status"] == "success"
    assert res["filepath"] == "inputs/d.parquet"
    assert (tmp_path / "inputs" / "d.parquet").exists()


def test_data_convert_absolute_input_outside_root_is_rejected(tmp_path: Path):
    """E7: an absolute filepath outside root must be rejected up front —
    not written outside the project and then reported as a false error.

    Previously `root / abspath` discarded root, the conversion file was
    written next to the source (outside the project), and relative_to(root)
    raised ValueError, so the caller saw a generic failure even though the
    file physically existed outside the tree."""
    src_dir = tmp_path / "external"
    src_dir.mkdir()
    root = tmp_path / "project"
    root.mkdir()
    df = pd.DataFrame({"x": [1, 2]})
    src = src_dir / "shared.csv"
    df.to_csv(src, index=False)

    res = data_convert(str(src), "parquet", root)
    assert res["status"] == "error"
    assert "escapes project root" in res["message"]
    # The conversion must NOT have been written outside the project tree.
    assert not (src_dir / "shared.parquet").exists()
