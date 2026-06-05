"""AUDIT-026 closure — COREQ + SRQR checklist YAMLs ship and the
``tool_qualitative_select_standard`` handler copies the right file into
the workspace.

These tests intentionally stay tight on shape (item count + required
per-item fields + standard name) so a future edit that adds guidance
prose or domain labels doesn't break them, but dropping an item or
mis-naming a domain does.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


# Locate the source-checkout templates/checklists/. The test runs from
# the repo root in CI, so the relative path under the repo is stable.
REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKLISTS_DIR = REPO_ROOT / "templates" / "checklists"

COREQ_FILE = CHECKLISTS_DIR / "coreq_32items.yaml"
SRQR_FILE = CHECKLISTS_DIR / "srqr_21items.yaml"


# ----- parse + shape -----

def test_coreq_file_exists_and_parses():
    assert COREQ_FILE.exists(), f"missing: {COREQ_FILE}"
    data = yaml.safe_load(COREQ_FILE.read_text())
    assert isinstance(data, dict)
    assert data["standard"] == "COREQ"
    assert data["total_items"] == 32
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 32


def test_srqr_file_exists_and_parses():
    assert SRQR_FILE.exists(), f"missing: {SRQR_FILE}"
    data = yaml.safe_load(SRQR_FILE.read_text())
    assert isinstance(data, dict)
    assert data["standard"] == "SRQR"
    assert data["total_items"] == 21
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 21


def test_coreq_items_have_required_fields():
    data = yaml.safe_load(COREQ_FILE.read_text())
    for item in data["items"]:
        assert set(item).issuperset({"id", "domain", "item_text", "guidance_short"}), item
        assert item["id"].startswith("Q"), item
        assert item["domain"] in set(data["domains"]), item


def test_srqr_items_have_required_fields():
    data = yaml.safe_load(SRQR_FILE.read_text())
    for item in data["items"]:
        assert set(item).issuperset({"id", "domain", "item_text", "guidance_short"}), item
        assert item["id"].startswith("S"), item
        assert item["domain"] in set(data["domains"]), item


def test_coreq_ids_are_q1_through_q32():
    data = yaml.safe_load(COREQ_FILE.read_text())
    ids = [it["id"] for it in data["items"]]
    assert ids == [f"Q{i}" for i in range(1, 33)]


def test_srqr_ids_are_s1_through_s21():
    data = yaml.safe_load(SRQR_FILE.read_text())
    ids = [it["id"] for it in data["items"]]
    assert ids == [f"S{i}" for i in range(1, 22)]


def test_coreq_domains_cover_three_canonical_categories():
    data = yaml.safe_load(COREQ_FILE.read_text())
    domains = set(data["domains"])
    # Tong et al. 2007 organises the 32 items into three domains.
    assert domains == {
        "Research team and reflexivity",
        "Study design",
        "Analysis and findings",
    }


def test_srqr_domains_cover_canonical_categories():
    data = yaml.safe_load(SRQR_FILE.read_text())
    domains = set(data["domains"])
    # O'Brien et al. 2014 organises 21 items across these six domains.
    assert domains == {
        "Title and abstract",
        "Introduction",
        "Methods",
        "Results / findings",
        "Discussion",
        "Other",
    }


# ----- tool handler: select_standard copies the right file -----

def _import_select_standard():
    """Import the new tool. Skipped if the integration agent hasn't
    wired it in yet — keeps this test file useful both before and
    after wiring."""
    mod = pytest.importorskip(
        "research_os_qualitative.tools",
        reason="tool_qualitative_select_standard not yet wired",
    )
    return mod.select_standard


def _result_payload(result):
    """Pull the {status, data|message} dict out of the MCP TextContent
    list that handlers return."""
    import json
    assert isinstance(result, list) and result, result
    return json.loads(result[0].text)


def test_select_standard_explicit_coreq_copies_32_items(tmp_path):
    select_standard = _import_select_standard()
    result = select_standard(
        "tool_qualitative_select_standard",
        {"standard": "coreq"},
        tmp_path,
    )
    payload = _result_payload(result)
    assert payload["status"] == "success", payload
    data = payload["data"]
    assert data["standard"] == "COREQ"
    assert data["item_count"] == 32

    dest = tmp_path / data["coverage_path"]
    assert dest.exists(), f"copy did not land at {dest}"
    parsed = yaml.safe_load(dest.read_text())
    assert parsed["standard"] == "COREQ"
    assert len(parsed["items"]) == 32


def test_select_standard_explicit_srqr_copies_21_items(tmp_path):
    select_standard = _import_select_standard()
    result = select_standard(
        "tool_qualitative_select_standard",
        {"standard": "srqr"},
        tmp_path,
    )
    payload = _result_payload(result)
    assert payload["status"] == "success", payload
    data = payload["data"]
    assert data["standard"] == "SRQR"
    assert data["item_count"] == 21

    dest = tmp_path / data["coverage_path"]
    assert dest.exists()
    parsed = yaml.safe_load(dest.read_text())
    assert parsed["standard"] == "SRQR"
    assert len(parsed["items"]) == 21


def test_select_standard_auto_picks_coreq_for_interview_design(tmp_path):
    select_standard = _import_select_standard()
    design_dir = tmp_path / "workspace"
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "study_design.yaml").write_text("method: interviews\n")

    result = select_standard(
        "tool_qualitative_select_standard",
        {"standard": "auto"},
        tmp_path,
    )
    payload = _result_payload(result)
    assert payload["status"] == "success", payload
    assert payload["data"]["standard"] == "COREQ"


def test_select_standard_auto_defaults_to_srqr_for_ethnography(tmp_path):
    select_standard = _import_select_standard()
    design_dir = tmp_path / "workspace"
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "study_design.yaml").write_text("method: ethnography\n")

    result = select_standard(
        "tool_qualitative_select_standard",
        {"standard": "auto"},
        tmp_path,
    )
    payload = _result_payload(result)
    assert payload["status"] == "success", payload
    assert payload["data"]["standard"] == "SRQR"


def test_select_standard_auto_defaults_to_srqr_when_design_missing(tmp_path):
    select_standard = _import_select_standard()
    # No workspace/study_design.yaml exists.
    result = select_standard(
        "tool_qualitative_select_standard",
        {"standard": "auto"},
        tmp_path,
    )
    payload = _result_payload(result)
    assert payload["status"] == "success", payload
    assert payload["data"]["standard"] == "SRQR"


def test_select_standard_increments_version_on_second_call(tmp_path):
    select_standard = _import_select_standard()
    r1 = _result_payload(select_standard(
        "tool_qualitative_select_standard",
        {"standard": "coreq"},
        tmp_path,
    ))
    r2 = _result_payload(select_standard(
        "tool_qualitative_select_standard",
        {"standard": "coreq"},
        tmp_path,
    ))
    assert r1["data"]["version"] == 1
    assert r2["data"]["version"] == 2
    assert r1["data"]["coverage_path"] != r2["data"]["coverage_path"]


def test_select_standard_rejects_unknown_standard(tmp_path):
    select_standard = _import_select_standard()
    result = select_standard(
        "tool_qualitative_select_standard",
        {"standard": "casp"},
        tmp_path,
    )
    payload = _result_payload(result)
    assert payload["status"] == "error"
    assert "casp" in payload["message"].lower()
