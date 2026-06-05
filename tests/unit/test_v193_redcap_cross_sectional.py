"""v1.9.3 — REDCap adapter detects cross-sectional exports
(AUDIT-v1.9.2-012).

describe() advertised ``cross_sectional_export_csv`` as a supported shape,
but the original ``_classify_csv`` required a row-stamping
``redcap_event_name`` / ``redcap_repeat_*`` column — which cross-sectional
exports never carry. This test confirms detection now accepts:
  * a CSV with ``record_id`` + a sibling data dictionary
  * a CSV with ``record_id`` + a ``*_complete`` sentinel column
  * the longitudinal shape still detects unchanged
"""

from __future__ import annotations


def _write_csv(path, header, rows=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)]
    for row in rows or []:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n")


def test_cross_sectional_with_complete_sentinel(tmp_path):
    """Single-instrument export with consent_complete column → detected."""
    from research_os_adapter_redcap import _classify_csv

    csv = tmp_path / "inputs" / "participants.csv"
    _write_csv(csv, ["record_id", "age", "consent_complete"], [["1", "42", "2"]])
    assert _classify_csv(csv) == "export"


def test_cross_sectional_with_sibling_dictionary(tmp_path):
    """Cross-sectional export + sibling dictionary CSV → detected."""
    from research_os_adapter_redcap import _classify_csv

    export = tmp_path / "data" / "people.csv"
    _write_csv(export, ["record_id", "age", "score"], [["1", "42", "8"]])
    dictionary = tmp_path / "data" / "people_dictionary.csv"
    _write_csv(dictionary, ["Variable / Field Name", "Form Name"], [["age", "demo"]])
    assert _classify_csv(export) == "export"
    assert _classify_csv(dictionary) == "dictionary"


def test_longitudinal_still_detects(tmp_path):
    """Long-shape exports keep working — no regression."""
    from research_os_adapter_redcap import _classify_csv

    csv = tmp_path / "long.csv"
    _write_csv(csv, ["record_id", "redcap_event_name", "age"], [["1", "baseline", "42"]])
    assert _classify_csv(csv) == "export"


def test_random_csv_with_record_id_alone_is_not_redcap(tmp_path):
    """A CSV that happens to have ``record_id`` but no REDCap signals
    must NOT misclassify as a REDCap export."""
    from research_os_adapter_redcap import _classify_csv

    csv = tmp_path / "random.csv"
    _write_csv(csv, ["record_id", "color", "weight"], [["1", "red", "12"]])
    assert _classify_csv(csv) is None
