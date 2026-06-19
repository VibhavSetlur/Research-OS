"""Handler-layer contract tests for mode-conditional params + the
semantic-route unavailable envelope.

Covers:

* mem_log / tool_ground / tool_verify return a directed, mode-aware
  ``_error`` (not a bare KeyError) when a mode-required param is
  missing. (F9)
* tool_semantic_route / sys_semantic_tool_search return a ``warning``
  envelope (the op did not run) with the payload intact and no
  redundant inner ``status`` key, when the semantic extra is absent.
  (env-06)
"""
from __future__ import annotations

import json
from pathlib import Path

from research_os.server.handlers.grounding import (
    _handle_mem_log,
    _handle_tool_ground,
    _handle_tool_verify,
)


def _payload(resp):
    return json.loads(resp[0].text)


# ── F9: mode-aware errors instead of KeyError ────────────────────────


def test_mem_log_methods_missing_method(tmp_path: Path):
    r = _payload(_handle_mem_log("mem_log", {"kind": "methods"}, tmp_path))
    assert r["status"] == "error"
    assert "method=" in r["error"]


def test_mem_log_decision_missing_fields(tmp_path: Path):
    r = _payload(_handle_mem_log("mem_log", {"kind": "decision"}, tmp_path))
    assert r["status"] == "error"
    assert "context=" in r["error"] and "rationale=" in r["error"]


def test_mem_log_analysis_missing_entry(tmp_path: Path):
    r = _payload(_handle_mem_log("mem_log", {"kind": "analysis"}, tmp_path))
    assert r["status"] == "error"
    assert "entry=" in r["error"]


def test_mem_log_hypothesis_missing_id(tmp_path: Path):
    r = _payload(_handle_mem_log("mem_log", {"kind": "hypothesis"}, tmp_path))
    assert r["status"] == "error"
    assert "hypothesis_id=" in r["error"]


def test_tool_ground_explicit_missing_sources(tmp_path: Path):
    r = _payload(_handle_tool_ground(
        "tool_ground", {"mode": "explicit", "claim": "c"}, tmp_path,
    ))
    assert r["status"] == "error"
    assert "sources=" in r["error"]


def test_tool_ground_from_context_missing_paths(tmp_path: Path):
    r = _payload(_handle_tool_ground(
        "tool_ground", {"mode": "from_context", "claim": "c"}, tmp_path,
    ))
    assert r["status"] == "error"
    assert "context_paths=" in r["error"]


def test_tool_verify_claim_missing_verifications(tmp_path: Path):
    r = _payload(_handle_tool_verify(
        "tool_verify", {"scope": "claim", "claim": "c"}, tmp_path,
    ))
    assert r["status"] == "error"
    assert "verifications=" in r["error"]


# ── env-06: warning envelope when semantic routing unavailable ───────


def test_semantic_route_unavailable_returns_warning(tmp_path: Path, monkeypatch):
    from research_os.server.handlers import meta_routing
    from research_os.tools.actions import semantic

    monkeypatch.setattr(semantic, "semantic_available", lambda: False)
    r = _payload(meta_routing._handle_tool_semantic_route(
        "tool_semantic_route", {"prompt": "x"}, tmp_path,
    ))
    assert r["status"] == "warning"
    # Payload preserved, no redundant inner status.
    assert "status" not in r["payload"]
    assert "reason" in r["payload"]


def test_semantic_tool_search_unavailable_returns_warning(tmp_path: Path, monkeypatch):
    from research_os.server.handlers import meta_routing
    from research_os.tools.actions import semantic

    monkeypatch.setattr(semantic, "semantic_available", lambda: False)
    r = _payload(meta_routing._handle_sys_semantic_tool_search(
        "sys_semantic_tool_search", {"query": "x"}, tmp_path,
    ))
    assert r["status"] == "warning"
    assert "status" not in r["payload"]
    assert "reason" in r["payload"]
