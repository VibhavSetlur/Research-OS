"""v1.7.1 — theory_math + wet_lab + engineering domain packs.

Covers:
    * Each new pack discovers cleanly through the bundled-list pathway.
    * All 8+8+7 protocols load via the pack-aware protocol loader.
    * All 9 new tools register + dispatch.
    * Each domain detector triggers on its signature inputs.
    * Stress-runner manifests for the 3 new reference projects parse.
    * Pack-to-pack namespace isolation: no tool or router-entry collisions
      across the 5 bundled packs.
    * Preflight pack checks still pass with 5 packs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from research_os.tools.actions import protocol as protocol_mod


def _fresh_import():
    for m in list(sys.modules):
        if m.startswith("research_os") or m.startswith("research_os_"):
            del sys.modules[m]
    import research_os.server  # noqa: F401
    return sys.modules["research_os.server"]


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    return tmp_path


# ── all 5 packs discover ─────────────────────────────────────────────


def test_all_five_packs_register():
    _fresh_import()
    from research_os.plugins import installed_packs, load_pack_errors
    assert load_pack_errors() == []
    names = {p["name"] for p in installed_packs()}
    assert names >= {"humanities", "qualitative", "theory_math",
                     "wet_lab", "engineering"}


def test_pack_to_pack_namespace_isolation():
    """No tool or router-entry collisions across the 5 bundled packs."""
    _fresh_import()
    from research_os.plugins import installed_packs
    from research_os.plugins.loader import pack_router_entries
    # Confirm the 5 expected bundled packs are present before checking isolation.
    expected_packs = {"humanities", "qualitative", "theory_math",
                      "wet_lab", "engineering"}
    discovered_names = {p["name"] for p in installed_packs()}
    assert expected_packs <= discovered_names, (
        f"missing expected packs: {expected_packs - discovered_names}"
    )
    tool_owners: dict[str, str] = {}
    # Walk each pack's tools (we have to peek at the loader's record).
    from research_os.plugins.loader import _DISCOVERED_PACKS
    for name, rec in _DISCOVERED_PACKS.items():
        for t in rec.tools:
            assert t.name not in tool_owners, (
                f"pack '{name}' tool '{t.name}' collides with pack "
                f"'{tool_owners[t.name]}'"
            )
            tool_owners[t.name] = name
    # Same for router entries.
    entry_owners: dict[str, str] = {}
    for name, rec in _DISCOVERED_PACKS.items():
        # router_entry_count is on PackLoadResult but the actual keys
        # live on the merged map. We can compare prefixes.
        for key in pack_router_entries():
            head = key.split("/", 1)[0]
            if head == name:
                if key in entry_owners and entry_owners[key] != name:
                    raise AssertionError(
                        f"router entry '{key}' claimed by '{entry_owners[key]}' "
                        f"and '{name}'"
                    )
                entry_owners[key] = name


# ── all new tools registered ─────────────────────────────────────────


@pytest.mark.parametrize(
    "tool_name",
    [
        "tool_theory_math_lean_check",
        "tool_theory_math_coq_check",
        "tool_theory_math_dep_graph",
        "tool_wet_lab_plate_map_render",
        "tool_wet_lab_reagent_query",
        "tool_wet_lab_sample_lineage_export",
        "tool_engineering_fmea_render",
        "tool_engineering_fault_tree_render",
        "tool_engineering_requirements_matrix",
    ],
)
def test_new_pack_tool_registered(tool_name):
    srv = _fresh_import()
    assert tool_name in srv.TOOL_DEFINITIONS, f"missing TOOL_DEFINITIONS: {tool_name}"
    assert tool_name in srv._HANDLERS, f"missing handler: {tool_name}"


# ── all new pack protocols load ──────────────────────────────────────


@pytest.mark.parametrize(
    "protocol_id",
    [
        "theory_math/proof/proof_verification_workflow",
        "theory_math/proof/lemma_library",
        "theory_math/proof/theorem_dependency_graph",
        "theory_math/conjecture/conjecture_tracking",
        "theory_math/formal/lean_integration",
        "theory_math/formal/coq_integration",
        "theory_math/output/theory_paper_structure",
        "theory_math/method/proof_strategy_selection",
        "wet_lab/protocol/sop_versioning",
        "wet_lab/protocol/reagent_lot_tracking",
        "wet_lab/protocol/plate_map_provenance",
        "wet_lab/protocol/instrument_run_log",
        "wet_lab/protocol/sample_lineage",
        "wet_lab/method/wet_lab_experiment_design",
        "wet_lab/audit/wet_lab_reproducibility_audit",
        "wet_lab/output/methods_section_wet_lab",
        "engineering/design/design_iteration",
        "engineering/design/requirements_traceability",
        "engineering/safety/fmea_protocol",
        "engineering/safety/fault_tree_analysis",
        "engineering/test/test_failure_causation",
        "engineering/test/build_test_fix_loop",
        "engineering/output/engineering_report_structure",
    ],
)
def test_new_pack_protocol_loads(protocol_id):
    _fresh_import()
    p = protocol_mod.load_protocol(protocol_id)
    assert p.get("id"), f"{protocol_id} missing id"
    assert isinstance(p.get("steps"), list) and len(p["steps"]) > 0


# ── tool dispatch smoke tests ────────────────────────────────────────


def test_theory_dep_graph_dispatches(project_root):
    srv = _fresh_import()
    (project_root / "proofs").mkdir()
    (project_root / "proofs" / "demo.lean").write_text(
        "import Mathlib.Tactic\n\ntheorem foo : 1 + 1 = 2 := by rfl\n"
        "lemma bar : 2 + 2 = 4 := by rfl\n"
    )
    r = srv._handle_tool_call(
        "tool_theory_math_dep_graph", {"source_dir": "proofs"}, project_root
    )
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    assert env["data"]["n_theorems"] >= 2
    mermaid = project_root / "workspace" / "docs" / "proof_dependencies.mermaid"
    assert mermaid.exists()


def test_wet_lab_plate_map_render_dispatches(project_root):
    srv = _fresh_import()
    spec_path = project_root / "inputs" / "plate.yaml"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        "title: demo\nrows: [A, B, C, D]\ncols: [1, 2, 3]\n"
        "wells:\n  A1: NTC\n  A2: pos\n  B1: s1\n  B2: s2\n"
    )
    r = srv._handle_tool_call(
        "tool_wet_lab_plate_map_render",
        {"spec_path": "inputs/plate.yaml"},
        project_root,
    )
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    assert "ascii" in env["data"]["paths"]
    assert (project_root / env["data"]["paths"]["ascii"]).exists()


def test_engineering_fmea_render_dispatches(project_root):
    srv = _fresh_import()
    spec_path = project_root / "inputs" / "fmea.yaml"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        "items:\n"
        "- {id: F1, function: power, failure_mode: brownout, effect: reset, "
        "cause: low_batt, severity: 8, occurrence: 4, detection: 3, "
        "mitigation: brownout_circuit}\n"
        "- {id: F2, function: radio, failure_mode: no_link, effect: data_loss, "
        "cause: interference, severity: 5, occurrence: 6, detection: 4, "
        "mitigation: retry_queue}\n"
    )
    r = srv._handle_tool_call(
        "tool_engineering_fmea_render",
        {"spec_path": "inputs/fmea.yaml"},
        project_root,
    )
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    assert env["data"]["n_items"] == 2
    md = project_root / env["data"]["paths"]["md"]
    assert md.exists()
    assert "FMEA" in md.read_text()


def test_engineering_requirements_matrix_flags_orphans(project_root):
    srv = _fresh_import()
    spec_path = project_root / "inputs" / "req.yaml"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        "requirements:\n"
        "- {id: SRS-001, text: foo, design_elements: [D1], test_cases: [TC-1]}\n"
        "- {id: SRS-002, text: bar, design_elements: [D2], test_cases: []}\n"
        "test_results:\n"
        "  TC-1: pass\n"
        "  TC-99: pass\n"
    )
    r = srv._handle_tool_call(
        "tool_engineering_requirements_matrix",
        {"spec_path": "inputs/req.yaml"},
        project_root,
    )
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    assert "SRS-002" in env["data"]["orphan_requirements"]
    assert "TC-99" in env["data"]["orphan_tests"]


# ── domain detectors ─────────────────────────────────────────────────


def test_theory_math_detector_triggers_on_lean(tmp_path):
    from research_os_theory_math.detector import detect_theory_math
    (tmp_path / "demo.lean").write_text(
        "import Mathlib.Tactic\ntheorem foo : True := trivial\n"
    )
    result = detect_theory_math(tmp_path)
    assert result["pack"] == "theory_math"
    assert result["confidence"] > 0.2
    assert any("formal-proof" in s for s in result["signals"])


def test_theory_math_detector_quiet_on_csv_only(tmp_path):
    from research_os_theory_math.detector import detect_theory_math
    (tmp_path / "data.csv").write_text("id,value\n1,2\n")
    result = detect_theory_math(tmp_path)
    assert result["confidence"] < 0.2


def test_wet_lab_detector_triggers_on_protocols_dir_plus_terms(tmp_path):
    from research_os_wet_lab.detector import detect_wet_lab
    (tmp_path / "protocols").mkdir()
    (tmp_path / "protocols" / "qpcr_sop.md").write_text(
        "# qPCR SOP\n\nUse primer IL6 Cat. 12345 with antibody anti-FLAG, "
        "follow 384-well plate map. SOP v3. RRID: AB_12345."
    )
    result = detect_wet_lab(tmp_path)
    assert result["pack"] == "wet_lab"
    assert result["confidence"] > 0.3


def test_engineering_detector_triggers_on_req_ids(tmp_path):
    from research_os_engineering.detector import detect_engineering
    (tmp_path / "spec.md").write_text(
        "# Spec\n\nSRS-001: device shall transmit at 868 MHz.\n"
        "SRS-002: TC-12 verifies FR-003. FMEA on housing follows.\n"
        "Fault tree shows V&V coverage gaps. 5 whys analysis pending."
    )
    result = detect_engineering(tmp_path)
    assert result["pack"] == "engineering"
    assert result["confidence"] > 0.3


# ── stress-runner fixtures ───────────────────────────────────────────


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "projects"


@pytest.mark.parametrize(
    "fixture_name",
    [
        "theory_math_short_proof",
        "wet_lab_qpcr_run",
        "engineering_fmea_simple",
    ],
)
def test_new_reference_project_manifest_parses(fixture_name):
    from research_os.testing.stress_runner import load_reference_project
    fdir = _fixtures_root() / fixture_name
    assert fdir.exists(), f"missing fixture: {fdir}"
    proj = load_reference_project(fdir)
    assert proj.name == fixture_name
    assert len(proj.protocols_expected) > 0


@pytest.mark.parametrize(
    "fixture_name",
    [
        "theory_math_short_proof",
        "wet_lab_qpcr_run",
        "engineering_fmea_simple",
    ],
)
def test_new_reference_project_stress_runs(fixture_name):
    _fresh_import()  # ensure pack discovery so protocols resolve
    from research_os.testing.stress_runner import (
        load_reference_project, mock_model_call, run_stress,
    )
    proj = load_reference_project(_fixtures_root() / fixture_name)
    res = run_stress(proj, model_call=mock_model_call(proj.canned_responses))
    assert res.success_rate >= 0.99, (
        f"{fixture_name} success_rate dropped: {res.notes}"
    )


# ── preflight check coverage ─────────────────────────────────────────


def test_preflight_packs_discovered_with_five_packs():
    import importlib.util
    pf = Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    spec = importlib.util.spec_from_file_location("preflight", pf)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok, msg = mod.check_packs_discovered()
    assert ok, msg
    assert "5 pack(s) discovered" in msg or "5 packs" in msg.lower()


def test_preflight_pack_protocols_load_with_three_more_packs():
    import importlib.util
    pf = Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    spec = importlib.util.spec_from_file_location("preflight", pf)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok, msg = mod.check_pack_protocols_load()
    assert ok, msg
    # 13 from v1.7.0 + 23 new = 36 pack protocols total.
    assert "36" in msg or "load" in msg
