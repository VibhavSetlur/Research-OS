"""Unit tests for the v4 daemon domain-profile layer
(research_os.daemon.domains).

Covers profile resolution (id / alias / keyword / fallback), file-signal
auto-detection, the declared-domain override precedence, PII-free
serialization, and robustness (never raises on bad input / empty dirs).
"""
from __future__ import annotations

from research_os.daemon.domains import (
    GENERIC,
    DetectionResult,
    DomainProfile,
    all_profiles,
    detect,
    get_profile,
)


# ── profile resolution ───────────────────────────────────────────────
def test_all_profiles_nonempty_and_unique_ids():
    profs = all_profiles()
    assert len(profs) >= 8
    ids = [p.id for p in profs]
    assert len(ids) == len(set(ids))  # no duplicate ids
    assert "generic" not in ids       # fallback is separate


def test_get_profile_exact_id():
    assert get_profile("computational_biology").id == "computational_biology"


def test_get_profile_alias():
    assert get_profile("genomics").id == "computational_biology"
    assert get_profile("ml").id == "data_science_ml"


def test_get_profile_case_insensitive():
    assert get_profile("HUMANITIES").id == "humanities"


def test_get_profile_keyword_substring():
    # "epidemiology study" contains the keyword "epidemiolog".
    assert get_profile("epidemiology study").id == "clinical_health"


def test_get_profile_unknown_falls_back_to_generic():
    assert get_profile("totally-unknown-field-xyz").id == "generic"


def test_get_profile_none_and_empty():
    assert get_profile(None).id == "generic"
    assert get_profile("").id == "generic"
    assert get_profile("   ").id == "generic"


# ── auto-detection from file signals ─────────────────────────────────
def test_detect_compbio_from_files(tmp_path):
    for name in ("seqs.fasta", "reads.fastq", "variants.vcf",
                 "Snakefile", "environment.yml", "run.py"):
        (tmp_path / name).touch()
    result = detect(tmp_path)
    assert result.profile.id == "computational_biology"
    assert result.source == "detected"
    assert 0.0 < result.confidence <= 0.95
    assert result.matched_signals  # non-empty


def test_detect_ml_from_files(tmp_path):
    for name in ("train.ipynb", "model.pt", "data.parquet",
                 "requirements.txt"):
        (tmp_path / name).touch()
    result = detect(tmp_path)
    assert result.profile.id == "data_science_ml"
    assert result.source == "detected"


def test_detect_empty_dir_is_fallback(tmp_path):
    result = detect(tmp_path)
    assert result.profile is GENERIC
    assert result.source == "fallback"
    assert result.confidence == 0.0


# ── declared domain overrides detection ──────────────────────────────
def test_declared_domain_wins_over_files(tmp_path):
    # Files look like humanities, but config declares social_sciences.
    (tmp_path / "paper.tex").touch()
    (tmp_path / "refs.bib").touch()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "researcher_config.yaml").write_text("domain: economics\n")
    result = detect(tmp_path)
    assert result.profile.id == "social_sciences"
    assert result.source == "declared"
    assert result.confidence == 1.0


def test_declared_unknown_domain_falls_through_to_detection(tmp_path):
    # An unrecognized declared domain shouldn't pin to generic if files
    # give a clear signal — detection still runs.
    (tmp_path / "model.pt").touch()
    (tmp_path / "train.ipynb").touch()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "researcher_config.yaml").write_text("domain: underwater_basketweaving\n")
    result = detect(tmp_path)
    assert result.profile.id == "data_science_ml"
    assert result.source == "detected"


# ── robustness + serialization ───────────────────────────────────────
def test_detect_never_raises_on_garbage_config(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "researcher_config.yaml").write_text("{{{ not valid yaml ::::")
    (tmp_path / "model.onnx").touch()
    # Must not raise; bad config is ignored, detection proceeds.
    result = detect(tmp_path)
    assert isinstance(result, DetectionResult)


def test_profile_as_dict_shape():
    d = get_profile("humanities").as_dict()
    assert set(d) == {"id", "label", "aliases", "languages", "artifacts",
                      "reproducibility", "notes"}
    assert isinstance(d["aliases"], list)
    assert isinstance(d["languages"], list)


def test_detection_result_as_dict_shape():
    d = DetectionResult(GENERIC, 0.0, "fallback").as_dict()
    assert set(d) == {"profile", "confidence", "source", "scores",
                      "matched_signals"}
    assert d["source"] == "fallback"


def test_profiles_are_frozen():
    p = get_profile("humanities")
    assert isinstance(p, DomainProfile)
    try:
        p.id = "mutated"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("DomainProfile should be frozen (immutable)")
