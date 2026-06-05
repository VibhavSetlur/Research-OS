"""Reviewer persona YAML asset tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from research_os.tools.actions.synthesis.reviewer import (
    DEFAULT_PERSONAS,
    PERSONAS_DIR,
    load_all_personas,
    load_persona,
)


REQUIRED_FIELDS = (
    "id",
    "name",
    "lens",
    "what_they_attack",
    "what_they_value",
    "typical_questions",
    "red_flags",
    "signature_phrasings",
)


def test_personas_dir_exists():
    assert PERSONAS_DIR.exists(), f"persona dir missing: {PERSONAS_DIR}"
    assert PERSONAS_DIR.is_dir()


def test_all_seven_personas_ship():
    files = sorted(p.stem for p in PERSONAS_DIR.glob("*.yaml"))
    assert set(DEFAULT_PERSONAS).issubset(files), (
        f"missing personas — expected {DEFAULT_PERSONAS}, found {files}"
    )
    assert len(DEFAULT_PERSONAS) == 7


@pytest.mark.parametrize("persona_id", list(DEFAULT_PERSONAS))
def test_persona_yaml_parses(persona_id):
    payload = load_persona(persona_id)
    assert isinstance(payload, dict)
    assert payload.get("id") == persona_id


@pytest.mark.parametrize("persona_id", list(DEFAULT_PERSONAS))
def test_persona_has_required_fields(persona_id):
    payload = load_persona(persona_id)
    missing = [f for f in REQUIRED_FIELDS if not payload.get(f)]
    assert not missing, f"{persona_id} missing fields: {missing}"


@pytest.mark.parametrize("persona_id", list(DEFAULT_PERSONAS))
def test_persona_has_at_least_ten_typical_questions(persona_id):
    payload = load_persona(persona_id)
    qs = payload.get("typical_questions") or []
    assert isinstance(qs, list)
    assert len(qs) >= 10, (
        f"{persona_id} only has {len(qs)} typical_questions; spec requires 10+"
    )


@pytest.mark.parametrize("persona_id", list(DEFAULT_PERSONAS))
def test_persona_has_red_flags_and_signatures(persona_id):
    payload = load_persona(persona_id)
    rfs = payload.get("red_flags") or []
    sigs = payload.get("signature_phrasings") or []
    assert len(rfs) >= 3, f"{persona_id} needs >=3 red_flags"
    assert len(sigs) >= 3, f"{persona_id} needs >=3 signature_phrasings"


def test_load_all_personas_returns_seven():
    loaded = load_all_personas()
    assert len(loaded) == 7
    ids = {p["id"] for p in loaded}
    assert ids == set(DEFAULT_PERSONAS)


def test_load_all_personas_filters_unknown():
    loaded = load_all_personas(["statistician", "this_persona_does_not_exist"])
    assert len(loaded) == 1
    assert loaded[0]["id"] == "statistician"


def test_load_unknown_persona_raises():
    with pytest.raises(FileNotFoundError):
        load_persona("zzz_not_a_real_persona")


def test_every_persona_file_is_valid_yaml():
    for path in PERSONAS_DIR.glob("*.yaml"):
        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        assert isinstance(data, dict), f"{path.name} is not a YAML mapping"
