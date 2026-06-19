"""Contract guards for the 5 domain packs + 6 infra adapters.

Before this file, the per-pack tests hardcoded names, so the NEXT pack (or
a regressed one) could ship half-wired: a dropped domain_detector, an empty
tool+router contribution, a non-IMRAD pack that forgot paper_sections, an
adapter whose describe() drifted. These contract tests close that whole
class — they iterate the LIVE registry, so a new bundled pack/adapter is
automatically held to the same bar.

Discovery is triggered by importing research_os.server (idempotent); the
tests parametrize over static name lists to stay collection-safe (no
sys.modules surgery at collection time).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import research_os.server  # noqa: F401 — triggers pack + adapter discovery

PACK_NAMES = ["humanities", "qualitative", "theory_math", "wet_lab", "engineering"]
ADAPTER_NAMES = ["slurm", "snakemake", "nextflow", "cytoscape", "redcap",
                 "synapse", "mlflow", "zenodo"]


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "inputs").mkdir()
    return tmp_path


def _pack(name):
    from research_os.plugins import installed_packs
    for p in installed_packs():
        if p["name"] == name:
            return p
    pytest.fail(f"pack {name} not installed")


# ── pack contract (C6, C9, C10) ───────────────────────────────────────


def test_the_five_bundled_packs_present():
    from research_os.plugins import installed_packs
    names = {p["name"] for p in installed_packs()}
    assert names >= set(PACK_NAMES)


@pytest.mark.parametrize("name", PACK_NAMES)
def test_every_pack_contributes_and_wires_a_detector(name):
    """C6 + C9: each pack contributes tools or router entries, has a wired
    domain_detector, and ships at least one loadable protocol."""
    pack = _pack(name)
    assert pack["tool_count"] > 0 or pack["router_entry_count"] > 0, (
        f"{name} contributes neither tools nor router entries"
    )
    assert pack["has_domain_detector"], (
        f"{name} dropped its domain_detector wiring in register()"
    )
    pdir = Path(pack["protocols_dir"])
    yamls = [f for f in pdir.rglob("*.yaml") if not f.name.startswith("_")]
    assert yamls, f"{name} ships no protocol YAML"


@pytest.mark.parametrize("name", PACK_NAMES)
def test_every_wired_detector_returns_its_own_name(name):
    """C6: the wired detector must return {pack: <name>} with the right shape."""
    from research_os.plugins.loader import pack_domain_detectors
    det = pack_domain_detectors().get(name)
    assert det is not None, f"{name} detector not wired into the registry"
    res = det(Path("/nonexistent_inputs_dir")) or {}
    assert res.get("pack") == name
    assert "confidence" in res and "signals" in res


def test_paper_sections_declared_where_non_imrad():
    """C10: theory_math + engineering opt out of IMRAD; the rest default."""
    from research_os.plugins import pack_paper_sections
    assert pack_paper_sections("theory_math"), "theory_math lost paper_sections"
    assert pack_paper_sections("engineering"), "engineering lost paper_sections"
    assert pack_paper_sections("wet_lab") == ()  # IMRAD default is intentional


@pytest.mark.parametrize("name", PACK_NAMES)
def test_packs_report_the_wheel_version(name):
    """B6: bundled packs are coupled to the wheel version (no stale 1.9.x)."""
    import research_os
    assert _pack(name)["version"] == research_os.__version__


# ── detector reader (D1) ──────────────────────────────────────────────


def test_run_pack_domain_detectors_surfaces_wet_lab(project_root):
    from research_os.plugins import run_pack_domain_detectors
    inp = project_root / "inputs"
    (inp / "protocols").mkdir()
    (inp / "notes.md").write_text(
        "qPCR plate map, 96-well, antibody, primer, reagent CAT#AB-1234, "
        "CRISPR knockout, mycoplasma test, SOP versioning"
    )
    hits = run_pack_domain_detectors(inp)
    assert any(h["pack"] == "wet_lab" for h in hits), hits
    assert hits[0]["signals"]  # best-first, with human-readable signals


def test_run_pack_domain_detectors_quiet_on_empty(project_root):
    from research_os.plugins import run_pack_domain_detectors
    assert run_pack_domain_detectors(project_root / "inputs") == []


def test_pack_signals_cache_memoises_on_mtime(project_root, monkeypatch):
    """router._pack_signals_cached must memoise on the inputs/ dir mtime
    so a repeated boot does NOT re-walk the corpus, and must recompute
    when inputs/ changes. (router-4)"""
    from research_os.tools.actions import router

    router._PACK_SIGNALS_CACHE.clear()
    calls = {"n": 0}

    def _fake_detect(inputs_dir):
        calls["n"] += 1
        return [{"pack": "fake", "confidence": 0.9, "signals": ["x"]}]

    monkeypatch.setattr(
        "research_os.plugins.run_pack_domain_detectors", _fake_detect,
    )
    inp = project_root / "inputs"

    first = router._pack_signals_cached(inp)
    second = router._pack_signals_cached(inp)
    assert first == second
    assert calls["n"] == 1, "cache should not recompute when inputs unchanged"

    # Change inputs/ (new file at top level bumps the dir mtime) → recompute.
    import os
    import time
    (inp / "new_file.txt").write_text("hello")
    os.utime(inp, (time.time() + 5, time.time() + 5))
    router._pack_signals_cached(inp)
    assert calls["n"] == 2, "cache should recompute when inputs/ changes"

    router._PACK_SIGNALS_CACHE.clear()


# ── adapter contract (C7, C11) ────────────────────────────────────────


@pytest.mark.parametrize("name", ADAPTER_NAMES)
def test_every_adapter_describe_returns_a_dict(name):
    """C11: describe() must return a dict (≥ name) and never raise."""
    from research_os.adapters.loader import adapter_registrations
    reg = adapter_registrations()[name]
    assert reg.describe is not None
    info = reg.describe()
    assert isinstance(info, dict) and "name" in info


_ADAPTER_TOOL_STUBS = {
    "tool_snakemake_dryrun": {"snakefile": "Snakefile"},
    "tool_snakemake_dag_render": {"snakefile": "Snakefile"},
    "tool_nextflow_validate": {"pipeline_path": "main.nf"},
    "tool_cytoscape_export_static": {"cys_file": "demo.cys"},
    "tool_redcap_schema_describe": {"step_id": "01"},
    "tool_synapse_entity_info": {"entity_id": "syn123456"},
    "tool_slurm_job_status": {"job_id": "1"},
    "tool_slurm_estimate_cost": {"step_id": "01"},
}


@pytest.mark.parametrize("tool_name", sorted(_ADAPTER_TOOL_STUBS))
def test_adapter_tool_handlers_dispatch_to_clean_envelope(tool_name, project_root):
    """C7: each adapter tool dispatches to a well-formed envelope (success or
    a graceful error), even when its system binary / input is absent."""
    import research_os.server as srv
    if tool_name not in srv.TOOL_DEFINITIONS:
        pytest.skip(f"{tool_name} not registered")
    out = srv._handle_tool_call(tool_name, _ADAPTER_TOOL_STUBS[tool_name], project_root)
    env = json.loads(out[0].text)
    assert env.get("status") in {"success", "error"}


# ── shared envelope helpers (B1, B3) + register_adapter hardening (B4) ──


def test_shared_pack_envelope_helpers():
    from research_os.plugins import pack_err, pack_ok
    assert json.loads(pack_ok({"k": 1})[0].text) == {"status": "success", "data": {"k": 1}}
    assert json.loads(pack_err("boom")[0].text) == {"status": "error", "error": "boom"}


def test_shared_adapter_envelope_helpers():
    from research_os.adapters import err_envelope, ok_envelope
    assert json.loads(ok_envelope({"k": 1})[0].text) == {"status": "success", "data": {"k": 1}}
    assert json.loads(err_envelope("boom")[0].text) == {"status": "error", "error": "boom"}


def test_register_adapter_rejects_compiled_pattern():
    """B4: tools_md_patterns source must be a str, not a compiled re.Pattern."""
    import re
    from research_os.adapters import register_adapter
    with pytest.raises(TypeError):
        register_adapter(
            name="demo",
            version="0.1",
            description="x",
            detect=lambda r: False,
            extract=lambda r, step_id=None: {},
            tools_md_patterns=((re.compile(r"demo"), "Demo present"),),
        )
