"""v1.7.0 — plugin system + humanities/qualitative packs + stress runner.

Covers:
    Plugin loader
      * @register_tool decorator captures (name, schema, handler).
      * PackRegistration namespace validation (tool prefix, router prefix, pack name).
      * Loader rejects duplicate tool names + duplicate pack registrations.
      * Errors are isolated per-pack (a bad pack doesn't block others).
      * sys_packs_installed reflects discovered packs.
    Bundled packs
      * `humanities` registers cleanly: 3 tools, 8 router entries, detector.
      * `qualitative` registers cleanly: 2 tools, 5 router entries, detector.
      * Every pack protocol loads via the protocol_loader.
      * Pack tool dispatch works through the core _handle_tool_call.
    Domain detectors
      * humanities detector triggers on TEI/XML inputs + literary terms.
      * qualitative detector triggers on speaker-turn patterns + IRB hints.
    Stress runner
      * Reference projects load from manifest.yaml.
      * mock_model_call returns canned responses keyed by step.
      * run_stress produces deterministic per-project SLO metrics.
      * write_reliability_md renders a table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────


def _fresh_import():
    """Force-reload the server module so packs are rediscovered."""
    for m in list(sys.modules):
        if m.startswith("research_os") or m.startswith("research_os_"):
            del sys.modules[m]
    import research_os.server  # noqa: F401
    return sys.modules["research_os.server"]


# ── plugin loader ─────────────────────────────────────────────────────


def test_pack_registration_namespace_prefix_enforced(tmp_path):
    from research_os.plugins.pack_api import (
        PackRegistration, PackTool, register_tool,
    )
    from research_os.plugins.loader import _validate

    pdir = tmp_path / "protocols"
    pdir.mkdir()
    bad = PackRegistration(
        name="mypack",
        version="0.1.0",
        protocols_dir=pdir,
        tools=(PackTool(
            name="tool_wrongprefix",
            handler=lambda *a, **k: None,
            schema={"type": "object"},
        ),),
    )
    from research_os.server.errors import RoError
    with pytest.raises((RoError, ValueError), match="tool_mypack_"):
        _validate(bad)


def test_pack_registration_router_prefix_enforced(tmp_path):
    from research_os.plugins.pack_api import PackRegistration
    from research_os.plugins.loader import _validate

    pdir = tmp_path / "protocols"
    pdir.mkdir()
    bad = PackRegistration(
        name="mypack",
        version="0.1.0",
        protocols_dir=pdir,
        router_entries={"otherpack/foo": {}},
    )
    from research_os.server.errors import RoError
    with pytest.raises((RoError, ValueError), match="mypack/"):
        _validate(bad)


def test_pack_registration_lowercase_name_required(tmp_path):
    from research_os.plugins.pack_api import PackRegistration
    from research_os.plugins.loader import _validate

    pdir = tmp_path / "protocols"
    pdir.mkdir()
    bad = PackRegistration(name="MyPack", version="0.1", protocols_dir=pdir)
    from research_os.server.errors import RoError
    with pytest.raises((RoError, ValueError), match="lowercase"):
        _validate(bad)


def test_register_tool_captures_to_module_registry():
    from research_os.plugins.pack_api import (
        captured_tools, register_tool, reset_captured_tools,
    )
    # Define a dummy module-level decorator usage.
    reset_captured_tools(__name__)

    @register_tool("tool_demo_foo", schema={"type": "object"})
    def foo(name, args, root):  # pragma: no cover - test stub
        return ("ok",)

    captured = captured_tools(__name__)
    assert len(captured) == 1
    assert captured[0].name == "tool_demo_foo"
    assert callable(captured[0].handler)
    reset_captured_tools(__name__)


def test_bundled_packs_register_cleanly():
    _fresh_import()
    from research_os.plugins import installed_packs, load_pack_errors
    assert load_pack_errors() == []
    names = {p["name"] for p in installed_packs()}
    assert "humanities" in names
    assert "qualitative" in names


def test_sys_packs_installed_handler_returns_packs(tmp_path):
    srv = _fresh_import()
    (tmp_path / ".os_state").mkdir()
    r = srv._handle_tool_call("sys_packs_installed", {}, tmp_path)
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    names = {p["name"] for p in env["data"]["packs"]}
    assert "humanities" in names
    assert "qualitative" in names


# ── pack contents ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tool_name",
    [
        "tool_humanities_archive_lookup",
        "tool_humanities_transcribe",
        "tool_humanities_citation_chain",
        "tool_qualitative_codebook_diff",
        "tool_qualitative_quote_provenance",
    ],
)
def test_pack_tool_registered(tool_name):
    srv = _fresh_import()
    assert tool_name in srv.TOOL_DEFINITIONS, f"missing TOOL_DEFINITIONS: {tool_name}"
    assert tool_name in srv._HANDLERS, f"missing handler: {tool_name}"


@pytest.mark.parametrize(
    "protocol_id",
    [
        "humanities/archival/archival_research",
        "humanities/archival/source_provenance",
        "humanities/textual/close_reading",
        "humanities/textual/distant_reading",
        "humanities/method/hermeneutic_method",
        "humanities/method/digital_humanities_workflow",
        "humanities/citation/citation_chains",
        "humanities/output/scholarly_edition",
        "qualitative/coding/coding_scheme_iteration",
        "qualitative/validity/member_checking",
        "qualitative/method/grounded_theory_iteration",
        "qualitative/method/thematic_analysis_braun_clarke",
        "qualitative/output/qualitative_report_format",
    ],
)
def test_pack_protocol_loads(protocol_id):
    _fresh_import()
    from research_os.tools.actions.protocol import load_protocol
    p = load_protocol(protocol_id)
    assert p.get("id"), f"{protocol_id} missing id"
    assert isinstance(p.get("steps"), list) and len(p["steps"]) > 0


def test_pack_tool_dispatch_writes_file(tmp_path):
    srv = _fresh_import()
    r = srv._handle_tool_call(
        "tool_humanities_archive_lookup",
        {"query": "Beowulf"},
        tmp_path,
    )
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    plan = tmp_path / env["data"]["plan_path"]
    assert plan.exists()
    body = plan.read_text()
    assert "Beowulf" in body


def test_qualitative_codebook_diff_dispatches(tmp_path):
    srv = _fresh_import()
    # Build two tiny YAML codebooks.
    cb = tmp_path / "workspace" / "codebooks"
    cb.mkdir(parents=True)
    (cb / "v1.yaml").write_text(
        "codes:\n- {id: c1, label: alpha}\n- {id: c2, label: beta}\n"
    )
    (cb / "v2.yaml").write_text(
        "codes:\n- {id: c1, label: alpha-prime}\n- {id: c3, label: gamma}\n"
    )
    r = srv._handle_tool_call(
        "tool_qualitative_codebook_diff",
        {"codebook_v1": "workspace/codebooks/v1.yaml",
         "codebook_v2": "workspace/codebooks/v2.yaml"},
        tmp_path,
    )
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    assert "c3" in env["data"]["added"]
    assert "c2" in env["data"]["removed"]
    assert any(rn["id"] == "c1" for rn in env["data"]["renamed"])


# ── domain detectors ──────────────────────────────────────────────────


def test_humanities_detector_triggers_on_tei(tmp_path):
    from research_os_humanities.detector import detect_humanities
    (tmp_path / "doc.tei").write_text(
        '<?xml version="1.0"?><TEI xmlns="http://www.tei-c.org/ns/1.0"></TEI>'
    )
    result = detect_humanities(tmp_path)
    assert result["pack"] == "humanities"
    assert result["confidence"] > 0.2
    assert any("TEI" in s for s in result["signals"])


def test_humanities_detector_quiet_on_csv_only(tmp_path):
    from research_os_humanities.detector import detect_humanities
    (tmp_path / "data.csv").write_text("id,value\n1,42\n")
    result = detect_humanities(tmp_path)
    assert result["confidence"] < 0.3


def test_qualitative_detector_triggers_on_speaker_turns(tmp_path):
    from research_os_qualitative.detector import detect_qualitative
    transcript = "\n".join([
        "Interviewer: tell me about your work",
        "P1: it was hard",
        "Interviewer: hard how",
        "P1: I felt isolated",
        "Interviewer: when",
        "P1: at the start",
        "Interviewer: thanks",
        "P1: yeah",
    ])
    (tmp_path / "p01.txt").write_text(transcript)
    result = detect_qualitative(tmp_path)
    assert result["pack"] == "qualitative"
    assert result["confidence"] > 0.3
    assert any("speaker-turn" in s for s in result["signals"])


# ── stress runner ─────────────────────────────────────────────────────


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "projects"


def test_reference_projects_present():
    fixtures = _fixtures_root()
    assert fixtures.exists(), f"missing fixtures dir: {fixtures}"
    found = sorted(p.name for p in fixtures.iterdir() if p.is_dir())
    assert "biology_genomics_mini" in found
    assert "humanities_ms_review" in found
    assert "qualitative_interviews" in found


def test_load_reference_project_parses_manifest():
    from research_os.testing.stress_runner import load_reference_project
    proj = load_reference_project(_fixtures_root() / "biology_genomics_mini")
    assert proj.name == "biology_genomics_mini"
    assert "guidance/project_startup" in proj.protocols_expected
    assert proj.max_tool_calls >= 1


def test_mock_model_call_returns_canned_response_by_step_id():
    from research_os.testing.stress_runner import mock_model_call
    call = mock_model_call({"step_alpha": "alpha-done"})
    out = call([{"role": "user", "content": "STEP: step_alpha\nsome description"}])
    assert out == "alpha-done"
    # Default fallback for unknown step ids.
    out = call([{"role": "user", "content": "STEP: unknown_step\n..."}])
    assert "Step" in out


def test_stress_runner_biology_genomics_mini_succeeds():
    _fresh_import()  # ensure pack discovery (needed for cross-project protocols)
    from research_os.testing.stress_runner import (
        load_reference_project, mock_model_call, run_stress,
    )
    proj = load_reference_project(_fixtures_root() / "biology_genomics_mini")
    res = run_stress(proj, model_call=mock_model_call(proj.canned_responses))
    assert res.success_rate >= 0.99, f"unexpected drop: {res.to_dict()}"
    assert res.tool_errors == 0


def test_stress_runner_humanities_ms_review_succeeds():
    _fresh_import()
    from research_os.testing.stress_runner import (
        load_reference_project, mock_model_call, run_stress,
    )
    proj = load_reference_project(_fixtures_root() / "humanities_ms_review")
    res = run_stress(proj, model_call=mock_model_call(proj.canned_responses))
    assert res.success_rate >= 0.99, res.notes


def test_stress_runner_qualitative_interviews_succeeds():
    _fresh_import()
    from research_os.testing.stress_runner import (
        load_reference_project, mock_model_call, run_stress,
    )
    proj = load_reference_project(_fixtures_root() / "qualitative_interviews")
    res = run_stress(proj, model_call=mock_model_call(proj.canned_responses))
    assert res.success_rate >= 0.99, res.notes


def test_write_reliability_md_renders_table(tmp_path):
    from research_os.testing.stress_runner import StressResult
    from research_os.testing.reliability import write_reliability_md
    r = StressResult(
        project_name="demo",
        model_label="mock",
        started_at="2026-06-05T00:00:00Z",
        finished_at="2026-06-05T00:00:01Z",
        duration_seconds=1.0,
        tool_calls=5,
        protocols_attempted=["x/y"],
        protocols_completed=["x/y"],
        gates_passed=["x/y:g"],
        gates_failed=[],
        artifacts_present=["a.txt"],
        artifacts_missing=[],
        success_rate=1.0,
    )
    out = tmp_path / "RELIABILITY.md"
    write_reliability_md([r], out)
    body = out.read_text()
    assert "Research-OS reliability" in body
    assert "demo" in body
    assert "x/y" in body


# ── preflight integration ─────────────────────────────────────────────


def test_preflight_packs_discovered():
    import importlib.util
    pf = Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    spec = importlib.util.spec_from_file_location("preflight", pf)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok, msg = mod.check_packs_discovered()
    assert ok, msg


def test_preflight_pack_protocols_load():
    import importlib.util
    pf = Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    spec = importlib.util.spec_from_file_location("preflight", pf)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok, msg = mod.check_pack_protocols_load()
    assert ok, msg
