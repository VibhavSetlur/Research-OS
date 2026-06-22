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


def test_data_sample_rejects_negative_n_rows(tmp_path: Path):
    """C8: a negative n_rows is valid pandas for head/tail (mis-selects rows)
    and would silently return the wrong rows with status=success. Reject it
    so head/tail/random share the same contract."""
    (tmp_path / "inputs").mkdir()
    pd.DataFrame({"x": [1, 2, 3, 4, 5]}).to_csv(
        tmp_path / "inputs" / "d.csv", index=False
    )
    for strat in ("head", "tail", "random"):
        res = data_sample("inputs/d.csv", -2, strategy=strat, root=tmp_path)
        assert res["status"] == "error", strat
        assert ">= 0" in res["message"]


def test_data_sample_rejects_zero_n_rows(tmp_path: Path):
    """C8: n_rows=0 produces an empty (useless) sample; reject it."""
    (tmp_path / "inputs").mkdir()
    pd.DataFrame({"x": [1, 2, 3]}).to_csv(tmp_path / "inputs" / "d.csv", index=False)
    res = data_sample("inputs/d.csv", 0, root=tmp_path)
    assert res["status"] == "error"
    assert ">= 1" in res["message"]


def test_data_sample_absolute_path_outside_root_rejected(tmp_path: Path):
    """C5/A6/E5: an absolute filepath outside root must be rejected up front,
    mirroring data_convert's containment guard."""
    external = tmp_path / "external"
    external.mkdir()
    root = tmp_path / "project"
    (root / "inputs").mkdir(parents=True)
    src = external / "secret.csv"
    pd.DataFrame({"x": [1, 2]}).to_csv(src, index=False)

    res = data_sample(str(src), 5, root=root)
    assert res["status"] == "error"
    assert "escapes project root" in res["message"]


def test_data_sample_dotdot_escape_rejected(tmp_path: Path):
    """C5/A6/E5: a ../-escaping relative filepath must be rejected."""
    external = tmp_path / "external"
    external.mkdir()
    root = tmp_path / "project"
    (root / "inputs").mkdir(parents=True)
    pd.DataFrame({"x": [1]}).to_csv(external / "out.csv", index=False)

    res = data_sample("../external/out.csv", 5, root=root)
    assert res["status"] == "error"
    assert "escapes project root" in res["message"]


def test_data_sample_latin1_csv_reads_with_fallback(tmp_path: Path):
    """C3: a latin-1 CSV head-sample must read via the encoding fallback
    (with a surfaced note) rather than raise UnicodeDecodeError."""
    (tmp_path / "inputs").mkdir()
    p = tmp_path / "inputs" / "latin.csv"
    p.write_bytes("name,city\nJos\xe9,M\xe1laga\nAnn,Paris\n".encode("latin-1"))

    res = data_sample("inputs/latin.csv", 5, strategy="head", root=tmp_path)
    assert res["status"] == "success"
    assert res["rows"] == 2
    assert "encoding_note" in res
