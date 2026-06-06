"""v1.11.1 known issue — citation retrieval handles empty / malformed
upstream responses without raising.

Previously a Crossref or Semantic Scholar response that came back empty,
``None``, or with a malformed per-hit shape (empty author list, author
string with no whitespace-splittable name, ``title`` as a string instead
of a list, etc.) would surface as a silent ``list index out of range``
during synthesis. ``tool_synthesize`` returned ``citations_used: 0`` with
no signal that the network path even ran — the AI then assumed the
literature was simply quiet.

These tests pin the contract:

1. ``collect_for_section`` returns an empty list (never raises) on every
   pathological response shape we've seen.
2. ``collect_for_section_with_failures`` reports the per-provider failure
   count + a sample so the caller knows *why* nothing came back.
3. ``_make_key`` is defensive against every empty-author / weird-title
   shape that previously crashed it.
4. Failures get appended to ``workspace/logs/citation_failures.jsonl``
   as one JSON line per failure, not lost.
5. ``synthesize_workspace`` (single-section mode) bubbles the failure
   count up in its structured return.

All mocking is at the HTTP / search-function layer — no real network.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from research_os.tools.actions.synthesis.citations import (
    _make_key,
    collect_for_section,
    collect_for_section_with_failures,
)


# ---------------------------------------------------------------------------
# _make_key — every shape that previously crashed
# ---------------------------------------------------------------------------


class TestMakeKeyDefensive:
    """The bare ``authors[0].split()[-1]`` raised IndexError on any author
    string that whitespace-split into ``[]`` — i.e. ``""`` or all-whitespace.
    """

    def test_empty_authors_list(self):
        key = _make_key({"authors": [], "title": "Foo Bar"})
        assert key.startswith("anon")

    def test_authors_is_none(self):
        key = _make_key({"authors": None, "title": "Foo Bar"})
        assert key.startswith("anon")

    def test_authors_field_missing(self):
        key = _make_key({"title": "Foo Bar"})
        assert key.startswith("anon")

    def test_first_author_empty_string(self):
        """The v1.11.1 IndexError reproducer."""
        key = _make_key({"authors": [""], "year": 2024, "title": "Foo Bar"})
        assert key == "anon2024foo" or key.startswith("anon")

    def test_first_author_whitespace_only(self):
        key = _make_key({"authors": ["   "], "title": "Foo Bar"})
        assert key.startswith("anon")

    def test_first_author_is_dict_with_name(self):
        # Some upstreams (S2-raw) hand back author dicts, not strings.
        key = _make_key({"authors": [{"name": "Jane Doe"}], "title": "Foo Bar"})
        assert "doe" in key

    def test_first_author_is_dict_with_family(self):
        key = _make_key({"authors": [{"family": "Doe"}], "title": "Foo Bar"})
        assert "doe" in key

    def test_first_author_dict_with_no_name_field(self):
        key = _make_key({"authors": [{"orcid": "0000"}], "title": "Foo Bar"})
        assert key.startswith("anon")

    def test_title_is_none(self):
        key = _make_key({"authors": ["Jane Doe"], "title": None})
        assert "paper" in key  # falls back to "paper" stem

    def test_title_is_list_of_strings(self):
        # Crossref hands back title as a list — defensive code unwraps it.
        key = _make_key(
            {"authors": ["Jane Doe"], "title": ["Foo Bar Baz"], "year": 2024}
        )
        assert "2024" in key

    def test_title_is_empty_list(self):
        key = _make_key({"authors": ["Jane Doe"], "title": []})
        assert "paper" in key


# ---------------------------------------------------------------------------
# collect_for_section — every empty / malformed response shape
# ---------------------------------------------------------------------------


def _patch_search(s2=None, cr=None):
    """Patch both provider entry points to return the supplied lists."""
    return patch.multiple(
        "research_os.tools.actions.search.search",
        search_semantic_scholar=lambda q, limit=5: s2 or [],
        search_crossref=lambda q, limit=5: cr or [],
    )


class TestCollectForSectionEmptyResponse:
    def test_both_providers_empty_returns_empty_list(self):
        with _patch_search(s2=[], cr=[]):
            out = collect_for_section("any query", k=5)
        assert out == []

    def test_provider_returns_none(self):
        # search_* legitimately returns [] on HTTP failure; if a future
        # refactor ever returns None we must NOT crash.
        with patch(
            "research_os.tools.actions.search.search.search_semantic_scholar",
            return_value=None,
        ), patch(
            "research_os.tools.actions.search.search.search_crossref",
            return_value=None,
        ):
            out = collect_for_section("q", k=5)
        assert out == []

    def test_provider_raises_does_not_propagate(self):
        def boom(q, limit=5):
            raise RuntimeError("upstream 503")

        with patch(
            "research_os.tools.actions.search.search.search_semantic_scholar",
            side_effect=boom,
        ), patch(
            "research_os.tools.actions.search.search.search_crossref",
            return_value=[],
        ):
            out = collect_for_section("q", k=5)
        assert out == []

    def test_malformed_hit_with_empty_author_does_not_index_error(self):
        """The v1.11.1 reproducer wired end-to-end."""
        bad = [
            {"title": "P", "authors": [""], "year": 2024,
             "doi": "10.1/p", "url": "http://p"},
        ]
        with _patch_search(s2=bad, cr=[]):
            out = collect_for_section("q", k=5)
        # The entry is salvageable — defensive _make_key produces "anon2024p".
        assert len(out) == 1
        assert out[0]["citation_key"].startswith("anon")

    def test_hit_with_no_doi_or_url_is_dropped(self):
        bad = [{"title": "P", "authors": ["A B"]}]
        with _patch_search(s2=bad, cr=[]):
            out = collect_for_section("q", k=5)
        assert out == []

    def test_hit_with_non_dict_payload_is_skipped(self):
        bad = ["not a dict", None, 42]
        with _patch_search(s2=bad, cr=[]):
            out = collect_for_section("q", k=5)
        assert out == []


# ---------------------------------------------------------------------------
# Failure metadata + structured logging
# ---------------------------------------------------------------------------


class TestFailureReporting:
    def test_with_failures_reports_provider_exception(self, tmp_path):
        def boom(q, limit=5):
            raise RuntimeError("upstream 503")

        with patch(
            "research_os.tools.actions.search.search.search_semantic_scholar",
            side_effect=boom,
        ), patch(
            "research_os.tools.actions.search.search.search_crossref",
            return_value=[],
        ):
            entries, failures = collect_for_section_with_failures(
                "q", k=5, root=tmp_path,
            )
        assert entries == []
        assert failures["total"] >= 1
        assert failures["by_provider"].get("semantic_scholar") == 1
        assert failures["samples"]
        assert failures["samples"][0]["exception_type"] == "RuntimeError"

    def test_with_failures_writes_jsonl_log(self, tmp_path):
        def boom(q, limit=5):
            raise RuntimeError("upstream 503")

        with patch(
            "research_os.tools.actions.search.search.search_semantic_scholar",
            side_effect=boom,
        ), patch(
            "research_os.tools.actions.search.search.search_crossref",
            return_value=[],
        ):
            collect_for_section_with_failures("q", k=5, root=tmp_path)
        log = tmp_path / "workspace" / "logs" / "citation_failures.jsonl"
        assert log.exists(), "citation_failures.jsonl must be created"
        records = [json.loads(ln) for ln in log.read_text().splitlines() if ln]
        assert records
        assert records[0]["provider"] == "semantic_scholar"
        assert records[0]["exception_type"] == "RuntimeError"
        assert records[0]["query"] == "q"
        assert "ts" in records[0]

    def test_with_failures_clean_run_has_zero_failures(self, tmp_path):
        good = [
            {"title": "Real Paper", "authors": ["A B"], "year": 2024,
             "url": "http://x", "doi": "10.1/x"},
        ]
        with _patch_search(s2=good, cr=[]):
            entries, failures = collect_for_section_with_failures(
                "q", k=5, root=tmp_path,
            )
        assert len(entries) == 1
        assert failures["total"] == 0
        assert failures["by_provider"] == {}
        assert failures["samples"] == []


# ---------------------------------------------------------------------------
# synthesize_workspace — failure metadata bubbles up to the tool surface
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_project(tmp_path):
    """A bare-bones project root just sufficient to run synthesize_workspace
    against. No real database touched; no inputs that would force a different
    code path.
    """
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "methods.md").write_text(
        "## Methods\n\nUsed defensive parsing.\n" * 10
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "research_overview.md").write_text(
        "# Overview\n\nDoes empty-response handling work end-to-end?\n"
    )
    (tmp_path / ".os_state").mkdir()
    return tmp_path


class TestSynthesizeSurfacesFailures:
    def test_synthesize_section_includes_failure_count(self, minimal_project):
        from research_os.tools.actions.synthesis.synthesize import (
            synthesize_workspace,
        )

        def boom(q, limit=5):
            raise RuntimeError("upstream went down")

        with patch(
            "research_os.tools.actions.search.search.search_semantic_scholar",
            side_effect=boom,
        ), patch(
            "research_os.tools.actions.search.search.search_crossref",
            side_effect=boom,
        ):
            result = synthesize_workspace(
                minimal_project,
                output_format="markdown",
                section="methods",
                output_type="paper",
            )
        # Must not have raised; structured fields must be present.
        assert result.get("status") == "success"
        assert "citation_retrieval_failures" in result
        assert result["citation_retrieval_failures"] >= 2
        assert "citation_failure_detail" in result
        detail = result["citation_failure_detail"]
        assert detail["live_retrieval_attempted"] is True
        assert detail["log_path"] == "workspace/logs/citation_failures.jsonl"
        assert detail["by_provider"].get("semantic_scholar", 0) >= 1
        assert detail["by_provider"].get("crossref", 0) >= 1

    def test_synthesize_clean_run_reports_zero_failures(self, minimal_project):
        from research_os.tools.actions.synthesis.synthesize import (
            synthesize_workspace,
        )

        good = [
            {"title": "Real Paper", "authors": ["A B"], "year": 2024,
             "url": "http://x", "doi": "10.1/x"},
        ]
        with patch(
            "research_os.tools.actions.search.search.search_semantic_scholar",
            return_value=good,
        ), patch(
            "research_os.tools.actions.search.search.search_crossref",
            return_value=[],
        ):
            result = synthesize_workspace(
                minimal_project,
                output_format="markdown",
                section="methods",
                output_type="paper",
            )
        assert result["status"] == "success"
        assert result["citation_retrieval_failures"] == 0
        assert result["citation_failure_detail"]["log_path"] is None
