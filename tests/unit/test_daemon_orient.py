"""Tests for the /v1/orient "standup" synthesis (v4 improvement pass)."""
from __future__ import annotations

import json

from research_os.daemon import orient
from research_os.daemon.core import Daemon


def test_orient_no_root_still_orients():
    """No workspace -> available=False but field + recommendation present."""
    daemon = Daemon.for_root(None)
    out = orient.build_orientation(daemon)
    assert out["service"] == "research-os"
    assert out["available"] is False
    assert "field" in out
    assert out["recommended_next_action"]["action"] == "record_first_result"
    assert isinstance(out["narrative"], str) and out["narrative"]


def test_orient_recommends_record_when_journal_empty(tmp_path):
    daemon = Daemon.for_root(str(tmp_path))
    out = orient.build_orientation(daemon)
    # Fresh workspace, journal exists but empty -> record the first result.
    assert out["work"]["total"] == 0
    assert out["recommended_next_action"]["action"] == "record_first_result"
    assert out["recommended_next_action"]["priority"] == "normal"


def test_orient_reports_budget_not_configured(tmp_path):
    daemon = Daemon.for_root(str(tmp_path))
    out = orient.build_orientation(daemon)
    assert out["budget"]["configured"] is False


def test_orient_reports_declared_budget(tmp_path):
    import yaml

    (tmp_path / "inputs").mkdir(parents=True)
    (tmp_path / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump({"resource_budget": {"memory_mb": 8192, "cpu_seconds": 3600}})
    )
    daemon = Daemon.for_root(str(tmp_path))
    out = orient.build_orientation(daemon)
    assert out["budget"]["configured"] is True
    assert out["budget"]["limits"]["address_space_mb"] == 8192
    assert out["budget"]["limits"]["cpu_seconds"] == 3600


def test_recommend_rebuild_when_stale():
    """Stale results dominate the recommendation, with the plan attached."""
    field = {"label": "chemistry"}
    runs = {"total": 3, "by_status": {"succeeded": 3}}
    freshness = {"stale": ["r2", "r3"], "rebuild_plan": ["r2", "r3"],
                 "counts": {"stale": 2, "fresh": 1}}
    rec = orient._recommend(field, runs, freshness)
    assert rec["action"] == "rebuild_stale"
    assert rec["priority"] == "high"
    assert rec["targets"] == ["r2", "r3"]


def test_recommend_investigate_when_failure():
    field = {"label": "ml"}
    runs = {"total": 2, "by_status": {"failed": 1, "succeeded": 1}}
    freshness = {"stale": [], "rebuild_plan": [], "counts": {}}
    rec = orient._recommend(field, runs, freshness)
    assert rec["action"] == "investigate_failure"
    assert rec["priority"] == "high"


def test_recommend_proceed_when_all_fresh():
    field = {"label": "history"}
    runs = {"total": 4, "by_status": {"succeeded": 4}}
    freshness = {"stale": [], "rebuild_plan": [], "counts": {"fresh": 4, "stale": 0}}
    rec = orient._recommend(field, runs, freshness)
    assert rec["action"] == "proceed"


def test_orient_never_leaks_and_is_json_serializable(tmp_path):
    daemon = Daemon.for_root(str(tmp_path))
    out = orient.build_orientation(daemon)
    # Must round-trip through JSON (it's an HTTP payload).
    json.dumps(out)
    assert set(out) >= {
        "service", "available", "field", "work", "freshness",
        "narrative", "recommended_next_action",
    }
