"""Tests for workflow-engine awareness (/v1/workflows, JUDGE-7)."""
from __future__ import annotations

import json

from research_os.daemon import workflows as wf


def test_detect_finds_snakefile_and_nextflow(tmp_path):
    (tmp_path / "Snakefile").write_text("rule all:\n    input: 'out.txt'\n")
    (tmp_path / "main.nf").write_text("workflow { foo() }\n")
    found = wf.detect_workflows(tmp_path)
    engines = {d["engine"] for d in found}
    assert engines == {"snakemake", "nextflow"}
    paths = {d["path"] for d in found}
    assert "Snakefile" in paths and "main.nf" in paths


def test_detect_smk_glob(tmp_path):
    (tmp_path / "rules.smk").write_text("rule x:\n    shell: 'echo'\n")
    found = wf.detect_workflows(tmp_path)
    assert any(d["path"] == "rules.smk" and d["engine"] == "snakemake" for d in found)


def test_detect_dedups_resolved_paths(tmp_path):
    # A single main.nf matches both 'main.nf' and '*.nf' signals -> one entry.
    (tmp_path / "main.nf").write_text("workflow {}\n")
    found = wf.detect_workflows(tmp_path)
    assert sum(1 for d in found if d["name"] == "main.nf") == 1


def test_detect_no_root_or_missing_returns_empty():
    assert wf.detect_workflows(None) == []
    assert wf.detect_workflows("/nonexistent/path/xyz") == []


def test_snakemake_step_parser():
    sample = [
        "Building DAG of jobs...",
        "rule bwa_map:",
        "    input: data/genome.fa",
        "rule samtools_sort:",
        "    input: mapped/a.bam",
        "rule bwa_map:",  # dup, ignored
        "checkpoint split:",
    ]
    steps = wf._snakemake_steps(sample)
    assert steps == ["bwa_map", "samtools_sort", "split"]


def test_nextflow_step_parser():
    sample = [
        "[skipping] Stored process > FOO",
        "[a1/b2c3d4] process > ALIGN",
        "[e5/f6g7h8] process > CALL_VARIANTS",
        "[a1/b2c3d4] process > ALIGN",  # dup
    ]
    steps = wf._nextflow_steps(sample)
    assert steps == ["FOO", "ALIGN", "CALL_VARIANTS"]


def test_introspect_degrades_when_engine_absent(tmp_path, monkeypatch):
    (tmp_path / "Snakefile").write_text("rule all:\n    input: 'x'\n")
    monkeypatch.setattr(wf.shutil, "which", lambda _b: None)
    rep = wf.introspect_workflow(tmp_path, "snakemake", "Snakefile")
    assert rep["available"] is False
    assert rep["steps"] == []
    assert "not installed" in rep["note"]


def test_survey_detection_only_is_cheap(tmp_path, monkeypatch):
    (tmp_path / "Snakefile").write_text("rule all:\n    input: 'x'\n")
    # introspect=False must never shell out.
    def _boom(*a, **k):  # pragma: no cover - asserts it is NOT called
        raise AssertionError("survey(introspect=False) must not run a subprocess")
    monkeypatch.setattr(wf.subprocess, "run", _boom)
    out = wf.survey_workflows(tmp_path, introspect=False)
    assert out["detected"] == 1
    assert out["workflows"][0]["engine"] == "snakemake"


def test_survey_is_json_serializable_and_degrades(tmp_path, monkeypatch):
    (tmp_path / "main.nf").write_text("workflow {}\n")
    monkeypatch.setattr(wf.shutil, "which", lambda _b: None)
    out = wf.survey_workflows(tmp_path)
    json.dumps(out)  # must round-trip (HTTP payload)
    assert out["detected"] == 1
    assert out["engines_present"] == {"nextflow": False}
    assert out["workflows"][0]["available"] is False


def test_survey_empty_root_never_raises():
    out = wf.survey_workflows(None)
    assert out["detected"] == 0
    assert out["workflows"] == []
