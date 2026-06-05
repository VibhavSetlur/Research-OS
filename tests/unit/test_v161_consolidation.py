"""v1.6.1 Theme 6: surface consolidation tests.

Coverage:
  * Every deprecated alias resolves to a registered handler.
  * Param-injection map covers every deprecated alias.
  * Each old tool name still works end-to-end (back-compat).
  * New consolidated tools work with explicit operation/kind/source.
  * Old + new produce identical outputs for equivalent invocations.
  * Deprecation log entries are written for alias hits.
  * tool_deprecations_summary aggregates correctly.
  * Protocol loader honours redirect_to: + redirect_params.
  * Synthesis/printable redirect stubs load the consolidated body.
  * Preflight catches stub-with-steps + missing alias targets.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.server import (
    TOOL_DEFINITIONS,
    _ALIAS_PARAM_INJECTION,
    _DEPRECATED_ALIASES,
    _HANDLERS,
    _handle_tool_call,
    _resolve_tool_name,
)


# ── fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "logs").mkdir()
    return tmp_path


def _result_text(result):
    return result[0].text


def _parse_envelope(result):
    return json.loads(_result_text(result))


# ── alias completeness ────────────────────────────────────────────


def test_every_deprecated_alias_resolves_to_a_handler():
    for old in _DEPRECATED_ALIASES:
        new = _resolve_tool_name(old)
        assert new in _HANDLERS, f"{old} → {new} (handler missing)"


def test_every_deprecated_alias_has_param_injection():
    missing = sorted(_DEPRECATED_ALIASES - set(_ALIAS_PARAM_INJECTION))
    assert not missing, f"missing injection for: {missing}"


def test_alias_param_injection_targets_are_valid_keys():
    # Sanity: the injected key must be one of the consolidation params we
    # expect (operation / kind / source / mode / scope).
    valid_keys = {"operation", "kind", "source", "mode", "scope"}
    for old, (key, _) in _ALIAS_PARAM_INJECTION.items():
        assert key in valid_keys, f"{old} injects unknown key '{key}'"


# ── new consolidated tools registered ─────────────────────────────


@pytest.mark.parametrize(
    "tool_name",
    [
        "tool_search",
        "tool_plan",
        "sys_path",
        "tool_ground",
        "tool_verify",
        "tool_lessons",
        "mem_log",
        "tool_deprecations_summary",
    ],
)
def test_new_consolidated_tools_registered(tool_name):
    assert tool_name in _HANDLERS, f"handler missing: {tool_name}"
    assert tool_name in TOOL_DEFINITIONS, f"TOOL_DEFINITIONS missing: {tool_name}"


# ── end-to-end: legacy aliases ────────────────────────────────────


def test_legacy_mem_methods_append_writes_methods_md(project_root):
    r = _handle_tool_call(
        "mem_methods_append", {"method": "OLS regression"}, project_root
    )
    env = _parse_envelope(r)
    assert env["status"] == "success"
    methods_md = project_root / "workspace" / "methods.md"
    assert methods_md.exists()
    assert "OLS regression" in methods_md.read_text()


def test_new_mem_log_methods_writes_methods_md(project_root):
    r = _handle_tool_call(
        "mem_log", {"kind": "methods", "method": "GLM"}, project_root
    )
    env = _parse_envelope(r)
    assert env["status"] == "success"
    assert "GLM" in (project_root / "workspace" / "methods.md").read_text()


def test_legacy_mem_decision_log_routes_through_consolidation(project_root):
    r = _handle_tool_call(
        "mem_decision_log",
        {"context": "pick X", "selected": "X", "rationale": "cheaper"},
        project_root,
    )
    env = _parse_envelope(r)
    assert env["status"] == "success"
    # mem_decision_log writes to analysis.md (pre-existing log_decision behaviour).
    assert (project_root / "workspace" / "analysis.md").exists()


def test_legacy_sys_path_list_works(project_root):
    r = _handle_tool_call("sys_path_list", {}, project_root)
    env = _parse_envelope(r)
    assert env["status"] == "success"
    assert "paths" in env["data"]


def test_new_sys_path_list_works(project_root):
    r = _handle_tool_call("sys_path", {"operation": "list"}, project_root)
    env = _parse_envelope(r)
    assert env["status"] == "success"
    assert "paths" in env["data"]


def test_legacy_tool_plan_clear_works(project_root):
    r = _handle_tool_call("tool_plan_clear", {}, project_root)
    env = _parse_envelope(r)
    assert env["status"] == "success"


def test_new_tool_plan_clear_works(project_root):
    r = _handle_tool_call(
        "tool_plan", {"operation": "clear"}, project_root
    )
    env = _parse_envelope(r)
    assert env["status"] == "success"


def test_legacy_tool_lessons_record_then_consult(project_root):
    rec = _handle_tool_call(
        "tool_lessons_record",
        {"outcome": "success", "reflection": "use X", "tags": ["x"]},
        project_root,
    )
    assert _parse_envelope(rec)["status"] == "success"
    con = _handle_tool_call(
        "tool_lessons_consult", {"task": "plan an x"}, project_root
    )
    assert _parse_envelope(con)["status"] == "success"


def test_new_tool_lessons_unified(project_root):
    rec = _handle_tool_call(
        "tool_lessons",
        {"operation": "record", "outcome": "success", "reflection": "use Y"},
        project_root,
    )
    assert _parse_envelope(rec)["status"] == "success"
    con = _handle_tool_call(
        "tool_lessons",
        {"operation": "consult", "task": "plan a y"},
        project_root,
    )
    assert _parse_envelope(con)["status"] == "success"


def test_legacy_mem_hypothesis_update_routes(project_root):
    add = _handle_tool_call(
        "mem_hypothesis_add", {"statement": "X causes Y"}, project_root
    )
    assert _parse_envelope(add)["status"] == "success"
    upd = _handle_tool_call(
        "mem_hypothesis_update",
        {"hypothesis_id": "H1", "status": "supported"},
        project_root,
    )
    assert _parse_envelope(upd)["status"] == "success"


def test_new_mem_log_hypothesis_routes(project_root):
    add = _handle_tool_call(
        "mem_hypothesis_add", {"statement": "X causes Y"}, project_root
    )
    assert _parse_envelope(add)["status"] == "success"
    upd = _handle_tool_call(
        "mem_log",
        {"kind": "hypothesis", "hypothesis_id": "H1", "status": "rejected"},
        project_root,
    )
    assert _parse_envelope(upd)["status"] == "success"


def test_new_mem_log_analysis_writes_entry(project_root):
    r = _handle_tool_call(
        "mem_log", {"kind": "analysis", "entry": "ran EDA pass"}, project_root
    )
    assert _parse_envelope(r)["status"] == "success"
    txt = (project_root / "workspace" / "analysis.md").read_text()
    assert "ran EDA pass" in txt


def test_new_mem_log_rejects_unknown_kind(project_root):
    r = _handle_tool_call(
        "mem_log", {"kind": "telepathy", "entry": "x"}, project_root
    )
    assert _parse_envelope(r)["status"] == "error"


def test_new_sys_path_rejects_unknown_operation(project_root):
    r = _handle_tool_call("sys_path", {"operation": "obliterate"}, project_root)
    assert _parse_envelope(r)["status"] == "error"


def test_new_tool_plan_rejects_unknown_operation(project_root):
    r = _handle_tool_call("tool_plan", {"operation": "wiggle"}, project_root)
    assert _parse_envelope(r)["status"] == "error"


# ── deprecation logging ───────────────────────────────────────────


def test_deprecation_log_written_for_alias_invocation(project_root):
    _handle_tool_call("mem_methods_append", {"method": "X"}, project_root)
    _handle_tool_call("sys_path_list", {}, project_root)
    log = project_root / ".os_state" / "deprecations.log"
    assert log.exists()
    lines = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    sources = {e["source"] for e in lines}
    assert "mem_methods_append" in sources
    assert "sys_path_list" in sources


def test_non_deprecated_alias_does_not_log(project_root):
    # `tool_audit_statistical_power` is a nickname, not a v1.6.1 consolidation.
    _handle_tool_call(
        "sys_state_summary", {}, project_root
    )  # resolves to sys_state_get
    log = project_root / ".os_state" / "deprecations.log"
    if log.exists():
        entries = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        assert all(e["source"] != "sys_state_summary" for e in entries)


def test_new_canonical_name_does_not_log(project_root):
    _handle_tool_call("mem_log", {"kind": "analysis", "entry": "x"}, project_root)
    log = project_root / ".os_state" / "deprecations.log"
    if log.exists():
        entries = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        assert all(e["source"] != "mem_log" for e in entries)


def test_tool_deprecations_summary_empty_when_no_log(project_root):
    r = _handle_tool_call("tool_deprecations_summary", {}, project_root)
    env = _parse_envelope(r)
    assert env["status"] == "success"
    assert env["data"]["total"] == 0


def test_tool_deprecations_summary_aggregates(project_root):
    _handle_tool_call("mem_methods_append", {"method": "X"}, project_root)
    _handle_tool_call("mem_methods_append", {"method": "Y"}, project_root)
    _handle_tool_call("sys_path_list", {}, project_root)
    r = _handle_tool_call("tool_deprecations_summary", {}, project_root)
    env = _parse_envelope(r)
    assert env["data"]["total"] == 3
    assert env["data"]["by_source"]["mem_methods_append"] == 2
    assert env["data"]["by_source"]["sys_path_list"] == 1
    assert env["data"]["by_target"]["mem_log"] == 2
    assert env["data"]["by_target"]["sys_path"] == 1


# ── tool_search consolidation ─────────────────────────────────────


def test_tool_search_unknown_source_returns_error(project_root):
    r = _handle_tool_call(
        "tool_search", {"query": "q", "source": "scihub"}, project_root
    )
    env = _parse_envelope(r)
    assert env["status"] == "error"


def test_tool_search_auto_picks_biomedical_providers_for_rna(
    project_root, monkeypatch
):
    """`source='auto'` with an RNA-flavoured query should call S2 + PubMed."""
    called = []

    def fake_s2(q, limit):
        called.append(("s2", q, limit))
        return [{"title": "rna paper", "_source": "semantic_scholar"}]

    def fake_pm(q, limit):
        called.append(("pm", q, limit))
        return [{"title": "rna paper pm", "_source": "pubmed"}]

    monkeypatch.setattr(
        "research_os.server.search_semantic_scholar", fake_s2
    )
    monkeypatch.setattr("research_os.server.search_pubmed", fake_pm)
    r = _handle_tool_call(
        "tool_search",
        {"query": "snRNA-seq dorsal raphe", "source": "auto", "limit": 4},
        project_root,
    )
    env = _parse_envelope(r)
    assert env["status"] == "success"
    assert env["data"]["mode"] == "auto"
    assert "semantic_scholar" in env["data"]["sources"]
    assert "pubmed" in env["data"]["sources"]
    called_providers = {c[0] for c in called}
    assert called_providers == {"s2", "pm"}


def test_legacy_tool_search_pubmed_routes_to_pubmed(project_root, monkeypatch):
    called = []

    def fake_pm(q, limit):
        called.append((q, limit))
        return [{"title": "hit"}]

    monkeypatch.setattr("research_os.server.search_pubmed", fake_pm)
    _handle_tool_call(
        "tool_search_pubmed", {"query": "foo", "limit": 3}, project_root
    )
    assert called == [("foo", 3)]


# ── protocol redirect_to: ─────────────────────────────────────────


def test_protocol_loader_follows_redirect_to(monkeypatch, tmp_path):
    """Custom redirect stub points at a custom target; loader follows it."""
    import yaml
    import research_os.tools.actions.protocol as P

    dest = tmp_path / "cat"
    dest.mkdir()
    target = dest / "real.yaml"
    target.write_text(
        yaml.safe_dump(
            {
                "id": "real",
                "version": "1.6.1",
                "steps": [{"id": "s1", "name": "S1", "description": "do it"}],
            }
        )
    )
    stub = dest / "old.yaml"
    stub.write_text(
        yaml.safe_dump(
            {
                "id": "old",
                "redirect_to": "cat/real",
                "redirect_params": {"variant": "x"},
            }
        )
    )
    monkeypatch.setattr(P, "PROTOCOLS_DIR", tmp_path)
    result = P.load_protocol("cat/old")
    assert result.get("id") == "real"
    assert result.get("_redirected_from") == "cat/old"
    assert result.get("_redirect_params") == {"variant": "x"}


def test_redirect_cycle_raises(monkeypatch, tmp_path):
    import yaml
    import research_os.tools.actions.protocol as P

    dest = tmp_path / "cat"
    dest.mkdir()
    # a → a (self-cycle)
    (dest / "a.yaml").write_text(
        yaml.safe_dump({"id": "a", "redirect_to": "cat/a"})
    )
    monkeypatch.setattr(P, "PROTOCOLS_DIR", tmp_path)
    with pytest.raises(ValueError, match="Redirect cycle"):
        P.load_protocol("cat/a")


def test_synthesis_handout_redirect_resolves(monkeypatch, tmp_path):
    """The real synthesis_handout stub loads the consolidated printable body."""
    from research_os.tools.actions.protocol import load_protocol

    # Set a fake workspace so the redirect-log doesn't pollute the live project.
    import os

    (tmp_path / ".os_state").mkdir()
    monkeypatch.setenv("RESEARCH_OS_WORKSPACE", str(tmp_path))
    r = load_protocol("synthesis/synthesis_handout")
    assert r.get("id") == "printable"
    assert r.get("_redirected_from") == "synthesis/synthesis_handout"
    assert r.get("_redirect_params") == {"format": "handout"}
    assert len(r.get("steps", [])) > 0


def test_synthesis_poster_redirect_resolves(monkeypatch, tmp_path):
    from research_os.tools.actions.protocol import load_protocol

    (tmp_path / ".os_state").mkdir()
    monkeypatch.setenv("RESEARCH_OS_WORKSPACE", str(tmp_path))
    r = load_protocol("synthesis/synthesis_poster")
    assert r.get("id") == "printable"
    assert r.get("_redirect_params") == {"format": "poster"}


def test_redirect_log_written_to_deprecations_log(monkeypatch, tmp_path):
    from research_os.tools.actions.protocol import load_protocol

    (tmp_path / ".os_state").mkdir()
    monkeypatch.setenv("RESEARCH_OS_WORKSPACE", str(tmp_path))
    load_protocol("synthesis/synthesis_handout")
    log = tmp_path / ".os_state" / "deprecations.log"
    assert log.exists()
    entries = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    redirect_entries = [e for e in entries if e["kind"] == "protocol_redirect"]
    assert any(
        e["source"] == "synthesis/synthesis_handout" for e in redirect_entries
    )


# ── preflight check coverage ──────────────────────────────────────


def test_preflight_alias_completeness_passes():
    """Live preflight check should report ok for the live alias table."""
    import importlib.util

    pf_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    )
    spec = importlib.util.spec_from_file_location("preflight", pf_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok, msg = mod.check_alias_table_complete()
    assert ok, msg


def test_preflight_redirect_targets_passes():
    import importlib.util

    pf_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    )
    spec = importlib.util.spec_from_file_location("preflight", pf_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok, msg = mod.check_redirect_targets()
    assert ok, msg


def test_preflight_catches_stub_with_steps(tmp_path, monkeypatch):
    """Preflight rejects a YAML that has BOTH redirect_to: and steps:."""
    import importlib.util
    import yaml

    pf_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    )
    spec = importlib.util.spec_from_file_location("preflight", pf_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Point PROTOCOLS_DIR at a temp dir with a violating stub.
    cat = tmp_path / "cat"
    cat.mkdir()
    (cat / "target.yaml").write_text(yaml.safe_dump({"id": "t", "steps": [{"id": "s"}]}))
    (cat / "bad.yaml").write_text(
        yaml.safe_dump(
            {"id": "bad", "redirect_to": "cat/target", "steps": [{"id": "x"}]}
        )
    )
    monkeypatch.setattr(mod, "PROTOCOLS_DIR", tmp_path)
    ok, msg = mod.check_redirect_targets()
    assert not ok
    assert "mutually exclusive" in msg


def test_preflight_catches_unresolved_redirect(tmp_path, monkeypatch):
    import importlib.util
    import yaml

    pf_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    )
    spec = importlib.util.spec_from_file_location("preflight", pf_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cat = tmp_path / "cat"
    cat.mkdir()
    (cat / "stub.yaml").write_text(
        yaml.safe_dump({"id": "s", "redirect_to": "cat/nowhere"})
    )
    monkeypatch.setattr(mod, "PROTOCOLS_DIR", tmp_path)
    ok, msg = mod.check_redirect_targets()
    assert not ok
    assert "nowhere" in msg
