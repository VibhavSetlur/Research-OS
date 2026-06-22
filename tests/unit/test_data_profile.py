"""Tests for data_profile correctness (C1, C2, C3, C4) and containment.

Covers the 3.2.10 data-IO hardening wave:
  C1 — non-finite stats (NaN/Inf) serialise to valid JSON (null), not the
       JS-only NaN/Infinity tokens.
  C2 — a .jsonl with list/dict-valued cells degrades per-column instead of
       crashing the whole profile with a bare 'unhashable type'.
  C3 — a latin-1 CSV reads via the encoding fallback (with a note) instead
       of raising UnicodeDecodeError.
  C4 — pandas nullable Int64/Float64 columns get descriptive stats.
  C5/A6/E5 — an absolute/escaping filepath is rejected ('escapes project root').
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from research_os.tools.actions.data.data import data_profile  # noqa: E402


def _mkproj(tmp_path: Path) -> Path:
    (tmp_path / "inputs").mkdir(exist_ok=True)
    return tmp_path


def test_profile_single_row_numeric_is_json_safe(tmp_path: Path):
    """C1: std of a single value is NaN. The profile result must serialise
    to valid JSON (NaN → null), not emit the JS-only NaN token."""
    root = _mkproj(tmp_path)
    (root / "inputs" / "one.csv").write_text("x\n5\n")

    res = data_profile("inputs/one.csv", root)
    assert res["status"] == "success"
    # Strict serialisation must not raise on a non-finite float.
    dumped = json.dumps(res, allow_nan=False)
    assert "NaN" not in dumped and "Infinity" not in dumped
    xcol = next(c for c in res["columns"] if c["name"] == "x")
    assert xcol["std"] is None  # NaN coerced to None
    assert xcol["min"] == 5.0


def test_profile_all_nan_column_is_json_safe(tmp_path: Path):
    """C1: an all-missing numeric column makes every stat NaN."""
    root = _mkproj(tmp_path)
    df = pd.DataFrame({"a": [1, 2, 3], "b": [np.nan, np.nan, np.nan]})
    df.to_csv(root / "inputs" / "miss.csv", index=False)

    res = data_profile("inputs/miss.csv", root)
    assert res["status"] == "success"
    json.dumps(res, allow_nan=False)  # must not raise
    bcol = next(c for c in res["columns"] if c["name"] == "b")
    assert bcol["mean"] is None and bcol["std"] is None


def test_profile_jsonl_with_list_cells_does_not_crash(tmp_path: Path):
    """C2: list-valued columns (normal in .jsonl) must degrade per-column,
    not kill the whole profile with 'unhashable type: list'."""
    root = _mkproj(tmp_path)
    lines = [
        json.dumps({"id": 1, "tags": ["a", "b"]}),
        json.dumps({"id": 2, "tags": ["c"]}),
    ]
    (root / "inputs" / "nested.jsonl").write_text("\n".join(lines) + "\n")

    res = data_profile("inputs/nested.jsonl", root)
    assert res["status"] == "success"
    by_name = {c["name"]: c for c in res["columns"]}
    # The well-behaved id column still profiles.
    assert by_name["id"]["n_unique"] == 2
    # The unhashable tags column appears with n_unique=None + a note.
    assert by_name["tags"]["n_unique"] is None
    assert "note" in by_name["tags"]


def test_profile_latin1_csv_reads_with_fallback(tmp_path: Path):
    """C3: a latin-1 CSV must read (with an encoding note) rather than raise
    UnicodeDecodeError."""
    root = _mkproj(tmp_path)
    p = root / "inputs" / "latin.csv"
    p.write_bytes("name,city\nJos\xe9,M\xe1laga\n".encode("latin-1"))

    res = data_profile("inputs/latin.csv", root)
    assert res["status"] == "success"
    assert res["rows"] == 1
    assert "encoding_note" in res


def _has_parquet_engine() -> bool:
    for mod in ("pyarrow", "fastparquet"):
        try:
            __import__(mod)
            return True
        except ImportError:
            continue
    return False


@pytest.mark.skipif(
    not _has_parquet_engine(), reason="no parquet engine (pyarrow/fastparquet)"
)
def test_profile_nullable_int64_gets_stats(tmp_path: Path):
    """C4: a pandas nullable Int64/Float64 column (which stringifies
    capitalised) must get descriptive stats, not be silently skipped by the
    old lowercase string-prefix dtype check. Persist via parquet so the
    nullable dtype survives the round-trip the tool reads from disk."""
    root = _mkproj(tmp_path)
    p = root / "inputs" / "nul.parquet"
    df = pd.DataFrame(
        {
            "k": pd.array([1, 2, None, 4], dtype="Int64"),
            "f": pd.array([1.5, None, 3.5, 4.5], dtype="Float64"),
        }
    )
    df.to_parquet(p, index=False)

    res = data_profile("inputs/nul.parquet", root)
    assert res["status"] == "success"
    by_name = {c["name"]: c for c in res["columns"]}
    # Both capitalised nullable dtypes must hit the numeric branch.
    assert by_name["k"]["dtype"] == "Int64"
    assert by_name["k"]["mean"] is not None
    assert by_name["f"]["dtype"] == "Float64"
    assert by_name["f"]["max"] == 4.5


def test_profile_absolute_path_outside_root_rejected(tmp_path: Path):
    """C5/A6/E5: an absolute filepath outside root must be rejected up front."""
    external = tmp_path / "external"
    external.mkdir()
    root = tmp_path / "project"
    (root / "inputs").mkdir(parents=True)
    src = external / "secret.csv"
    pd.DataFrame({"x": [1, 2]}).to_csv(src, index=False)

    res = data_profile(str(src), root)
    assert res["status"] == "error"
    assert "escapes project root" in res["message"]


def test_profile_dotdot_escape_rejected(tmp_path: Path):
    """C5/A6/E5: a ../-escaping relative filepath must be rejected."""
    external = tmp_path / "external"
    external.mkdir()
    root = tmp_path / "project"
    (root / "inputs").mkdir(parents=True)
    pd.DataFrame({"x": [1]}).to_csv(external / "out.csv", index=False)

    res = data_profile("../external/out.csv", root)
    assert res["status"] == "error"
    assert "escapes project root" in res["message"]
