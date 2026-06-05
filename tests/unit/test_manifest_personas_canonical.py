"""Assert every persona referenced in fixture manifests is canonical.

Drift like `skeptical_methodologist` → `methodology_skeptic` (the v1.11.x
bug) silently broke reviewer_simulation in the E2E smoke harness because
the loader fell through to defaults. This test walks every
`tests/fixtures/**/manifest.yaml` and confirms each persona ID under
`reviewer_simulation.personas` corresponds to a real YAML asset in
`src/research_os/assets/reviewer_personas/`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures"
PERSONAS_DIR = REPO_ROOT / "src" / "research_os" / "assets" / "reviewer_personas"


def _canonical_persona_ids() -> set[str]:
    return {p.stem for p in PERSONAS_DIR.glob("*.yaml")}


def _iter_manifests() -> list[Path]:
    return sorted(FIXTURES_ROOT.rglob("manifest.yaml"))


def test_personas_dir_exists():
    assert PERSONAS_DIR.is_dir(), f"missing persona dir: {PERSONAS_DIR}"
    assert _canonical_persona_ids(), "no canonical personas shipped"


def test_at_least_one_fixture_manifest_walked():
    # Guard: if the fixture tree is reorganized, surface that loud
    # instead of silently passing zero assertions.
    assert _iter_manifests(), f"no manifest.yaml under {FIXTURES_ROOT}"


@pytest.mark.parametrize("manifest_path", _iter_manifests(), ids=lambda p: p.parent.name)
def test_manifest_personas_are_canonical(manifest_path: Path) -> None:
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    rev = data.get("reviewer_simulation") or {}
    personas = rev.get("personas") or []
    if not personas:
        pytest.skip(f"{manifest_path.relative_to(REPO_ROOT)} declares no personas")

    canonical = _canonical_persona_ids()
    unknown = [p for p in personas if p not in canonical]
    assert not unknown, (
        f"{manifest_path.relative_to(REPO_ROOT)} references non-canonical "
        f"persona IDs {unknown}; canonical set is {sorted(canonical)}"
    )
