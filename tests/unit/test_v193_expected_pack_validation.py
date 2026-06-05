"""v1.9.3 — stress runner asserts expected_pack from manifest
(AUDIT-v1.9.2-035).

``ReferenceProject.expected_pack`` was defined but never read by any
caller. This test confirms ``run_stress`` now surfaces a note when the
detected pack does not match the manifest's declared ``expected_pack``.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _make_project(tmp_path: Path, expected_pack: str | None) -> Path:
    """Build a minimal reference-project directory the runner accepts."""
    root = tmp_path / "ref_proj"
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "ref_proj",
        "protocols_expected": [],
        "gates_expected_pass": [],
        "artifacts_required": [],
        "max_tool_calls": 10,
        "max_seconds": 5,
    }
    if expected_pack is not None:
        manifest["expected_pack"] = expected_pack
    (root / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    return root


def test_run_stress_notes_when_pack_mismatches(tmp_path: Path):
    """A manifest claiming ``expected_pack: humanities`` over a fixture
    with no humanities signals should produce a mismatch note."""
    from research_os.testing.stress_runner import (
        load_reference_project,
        mock_model_call,
        run_stress,
    )

    root = _make_project(tmp_path, expected_pack="humanities")
    # Empty inputs → no humanities signals → detector confidence 0.
    project = load_reference_project(root)
    result = run_stress(project, model_call=mock_model_call({}))
    pack_notes = [n for n in result.notes if "expected_pack" in n]
    assert pack_notes, f"expected a pack mismatch / low-confidence note: {result.notes}"


def test_run_stress_silent_when_no_expected_pack(tmp_path: Path):
    """When the manifest declares no expected_pack, the runner does not
    emit a pack-related note."""
    from research_os.testing.stress_runner import (
        load_reference_project,
        mock_model_call,
        run_stress,
    )

    root = _make_project(tmp_path, expected_pack=None)
    project = load_reference_project(root)
    result = run_stress(project, model_call=mock_model_call({}))
    pack_notes = [n for n in result.notes if "expected_pack" in n]
    assert not pack_notes, f"unexpected pack notes: {pack_notes}"


def test_expected_pack_unknown_returns_detector_unavailable_note(tmp_path: Path):
    """An expected_pack name with no registered detector logs the
    detector-unavailable note (not a hard failure)."""
    from research_os.testing.stress_runner import (
        load_reference_project,
        mock_model_call,
        run_stress,
    )

    root = _make_project(tmp_path, expected_pack="nonexistent_pack")
    project = load_reference_project(root)
    result = run_stress(project, model_call=mock_model_call({}))
    assert any("detector unavailable" in n for n in result.notes), result.notes
