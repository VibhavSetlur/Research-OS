"""Tests for data_sample preview JSON-safety (data-3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from research_os.tools.actions.data.data import data_sample  # noqa: E402


def test_data_sample_preview_is_json_safe(tmp_path: Path):
    """Timestamp + NaN values in the sampled preview must serialise to
    valid JSON (ISO strings + null), not raw Timestamp objects / NaN."""
    (tmp_path / "inputs").mkdir()
    df = pd.DataFrame({
        "t": pd.to_datetime(["2024-01-01", "2024-02-01"]),
        "x": [1.0, np.nan],
    })
    csvp = tmp_path / "inputs" / "d.csv"
    df.to_csv(csvp, index=False)

    res = data_sample("inputs/d.csv", 5, root=tmp_path)
    assert res["status"] == "success"
    # The preview must round-trip through json.dumps without error.
    dumped = json.dumps(res["preview"])
    assert "NaN" not in dumped
    # NaN became null; Timestamp became an ISO string.
    assert res["preview"][1]["x"] is None
    assert res["preview"][0]["t"].startswith("2024-01-01")
