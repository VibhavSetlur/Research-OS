"""Unit tests for ISBN-based monograph citation verifiers.

Covers the three new verifiers (WorldCat, OpenLibrary, LOC) plus the
auto-select dispatcher.  All network calls are mocked via
``urllib.request.urlopen``; no test should hit the wire.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from research_os.tools.actions.research.citations_isbn import (
    _clean_isbn,
    _extract_isbn,
    verify_citation_auto,
    verify_loc,
    verify_openlibrary,
    verify_worldcat,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeResp(io.BytesIO):
    """urllib-compatible context-manager response."""

    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _mock_urlopen(payload, *, status: int = 200):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return lambda req, timeout=None: _FakeResp(body, status=status)


def _mock_urlopen_raises(exc):
    def _raiser(req, timeout=None):
        raise exc
    return _raiser


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------


def test_clean_isbn_strips_hyphens_and_spaces():
    assert _clean_isbn("978-0-19-953685-2") == "9780199536852"
    assert _clean_isbn(" 0-19-953685-X ") == "019953685X"
    assert _clean_isbn("") == ""
    assert _clean_isbn(None) == ""  # type: ignore[arg-type]


def test_extract_isbn_checks_multiple_fields():
    assert _extract_isbn({"isbn": "978-0-19-953685-2"}) == "9780199536852"
    assert _extract_isbn({"ISBN": "0199536856"}) == "0199536856"
    assert _extract_isbn({"isbn13": "978-0199536852"}) == "9780199536852"
    assert _extract_isbn({"title": "no isbn"}) == ""


# ---------------------------------------------------------------------------
# OpenLibrary
# ---------------------------------------------------------------------------


def test_verify_openlibrary_happy_path():
    payload = {
        "ISBN:9780199536852": {
            "title": "Paradise Lost",
            "authors": [{"name": "John Milton"}],
            "publishers": [{"name": "Oxford UP"}],
            "publish_date": "2008",
            "url": "https://openlibrary.org/works/OL123W/Paradise_Lost",
        }
    }
    with patch(
        "research_os.tools.actions.research.citations_isbn.urllib.request.urlopen",
        side_effect=_mock_urlopen(payload),
    ):
        ok, evidence, url = verify_openlibrary({"isbn": "978-0-19-953685-2"})
    assert ok is True
    assert evidence["title"] == "Paradise Lost"
    assert "John Milton" in evidence["authors"]
    assert "openlibrary.org" in url


def test_verify_openlibrary_offline_returns_unreachable():
    with patch(
        "research_os.tools.actions.research.citations_isbn.urllib.request.urlopen",
        side_effect=_mock_urlopen_raises(urllib.error.URLError("offline")),
    ):
        ok, evidence, url = verify_openlibrary({"isbn": "9780199536852"})
    assert ok is False
    assert "unreachable" in evidence["reason"]
    assert "openlibrary.org" in url


def test_verify_openlibrary_no_isbn_returns_no_isbn_reason():
    ok, evidence, url = verify_openlibrary({"title": "no identifier"})
    assert ok is False
    assert evidence["reason"] == "no_isbn"
    assert url == ""


# ---------------------------------------------------------------------------
# WorldCat
# ---------------------------------------------------------------------------


_WORLDCAT_HIT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<classify xmlns="http://classify.oclc.org">'
    '<response code="2"/>'
    '<work owi="123456789" title="Paradise Lost" author="Milton, John" '
    'editions="42"/>'
    '</classify>'
).encode()


def test_verify_worldcat_happy_path():
    with patch(
        "research_os.tools.actions.research.citations_isbn.urllib.request.urlopen",
        side_effect=_mock_urlopen(_WORLDCAT_HIT),
    ):
        ok, evidence, url = verify_worldcat({"isbn": "9780199536852"})
    assert ok is True
    assert evidence["title"] == "Paradise Lost"
    assert "Milton" in evidence["author"]
    assert evidence["owi"] == "123456789"
    assert "classify.oclc.org" in url


def test_verify_worldcat_offline_returns_unreachable():
    with patch(
        "research_os.tools.actions.research.citations_isbn.urllib.request.urlopen",
        side_effect=_mock_urlopen_raises(urllib.error.URLError("dns")),
    ):
        ok, evidence, _ = verify_worldcat({"isbn": "9780199536852"})
    assert ok is False
    assert "unreachable" in evidence["reason"]


def test_verify_worldcat_code_102_means_not_found():
    not_found = (
        '<?xml version="1.0"?><classify><response code="102"/></classify>'
    ).encode()
    with patch(
        "research_os.tools.actions.research.citations_isbn.urllib.request.urlopen",
        side_effect=_mock_urlopen(not_found),
    ):
        ok, evidence, _ = verify_worldcat({"isbn": "9780199536852"})
    assert ok is False
    assert "worldcat_code_102" in evidence["reason"]


# ---------------------------------------------------------------------------
# LOC
# ---------------------------------------------------------------------------


def test_verify_loc_happy_path():
    payload = {
        "results": [
            {
                "title": "Paradise Lost",
                "contributor": ["Milton, John"],
                "date": "1674",
                "id": "https://www.loc.gov/item/abc/",
            }
        ]
    }
    with patch(
        "research_os.tools.actions.research.citations_isbn.urllib.request.urlopen",
        side_effect=_mock_urlopen(payload),
    ):
        ok, evidence, url = verify_loc({"isbn": "9780199536852"})
    assert ok is True
    assert evidence["title"] == "Paradise Lost"
    assert evidence["hit_count"] == 1
    assert "loc.gov" in url


def test_verify_loc_offline_returns_unreachable():
    with patch(
        "research_os.tools.actions.research.citations_isbn.urllib.request.urlopen",
        side_effect=_mock_urlopen_raises(urllib.error.URLError("timeout")),
    ):
        ok, evidence, _ = verify_loc({"isbn": "9780199536852"})
    assert ok is False
    assert "unreachable" in evidence["reason"]


def test_verify_loc_empty_results_means_not_found():
    with patch(
        "research_os.tools.actions.research.citations_isbn.urllib.request.urlopen",
        side_effect=_mock_urlopen({"results": []}),
    ):
        ok, evidence, _ = verify_loc({"isbn": "9780199536852"})
    assert ok is False
    assert evidence["reason"] == "not_found"


# ---------------------------------------------------------------------------
# Auto-select dispatcher
# ---------------------------------------------------------------------------


def test_auto_select_routes_isbn_to_isbn_chain():
    with patch(
        "research_os.tools.actions.research.citations_isbn.verify_worldcat",
        return_value=(True, {"title": "PL"}, "http://classify"),
    ) as wc, patch(
        "research_os.tools.actions.research.citations_isbn.verify_openlibrary"
    ) as ol, patch(
        "research_os.tools.actions.research.citations_isbn.verify_loc"
    ) as loc:
        ok, evidence, url = verify_citation_auto({"isbn": "9780199536852"})
    assert ok is True
    assert evidence["verified_via"] == "worldcat"
    assert "worldcat:hit" in evidence["tried"]
    wc.assert_called_once()
    ol.assert_not_called()
    loc.assert_not_called()


def test_auto_select_falls_through_to_loc_when_others_miss():
    with patch(
        "research_os.tools.actions.research.citations_isbn.verify_worldcat",
        return_value=(False, {"reason": "not_found"}, "http://classify"),
    ), patch(
        "research_os.tools.actions.research.citations_isbn.verify_openlibrary",
        return_value=(False, {"reason": "not_found"}, "http://ol"),
    ), patch(
        "research_os.tools.actions.research.citations_isbn.verify_loc",
        return_value=(True, {"title": "Found at LOC"}, "http://loc"),
    ):
        ok, evidence, url = verify_citation_auto({"isbn": "9780199536852"})
    assert ok is True
    assert evidence["verified_via"] == "loc"
    assert "worldcat:not_found" in evidence["tried"]
    assert "openlibrary:not_found" in evidence["tried"]
    assert "loc:hit" in evidence["tried"]


def test_auto_select_doi_only_returns_doi_path_skip():
    ok, evidence, url = verify_citation_auto({"doi": "10.1/abc"})
    assert ok is False
    assert evidence["reason"] == "doi_path"
    assert url == ""


def test_auto_select_no_identifier_returns_no_identifier():
    ok, evidence, url = verify_citation_auto({"title": "Untitled"})
    assert ok is False
    assert evidence["reason"] == "no_identifier"


def test_auto_select_swallows_verifier_exceptions():
    def _boom(_entry):
        raise RuntimeError("network exploded")

    with patch(
        "research_os.tools.actions.research.citations_isbn.verify_worldcat",
        side_effect=_boom,
    ), patch(
        "research_os.tools.actions.research.citations_isbn.verify_openlibrary",
        return_value=(True, {"title": "saved"}, "http://ol"),
    ), patch(
        "research_os.tools.actions.research.citations_isbn.verify_loc"
    ):
        ok, evidence, _ = verify_citation_auto({"isbn": "9780199536852"})
    assert ok is True
    assert evidence["verified_via"] == "openlibrary"
    assert "worldcat:exception" in evidence["tried"]


# ---------------------------------------------------------------------------
# citations.py integration helper
# ---------------------------------------------------------------------------


def test_verify_citation_entry_dispatches_to_isbn_when_present():
    from research_os.tools.actions.synthesis import citations as cit

    with patch(
        "research_os.tools.actions.research.citations_isbn.verify_citation_auto",
        return_value=(True, {"title": "Hit", "verified_via": "openlibrary"},
                      "http://ol"),
    ):
        out = cit.verify_citation_entry({"isbn": "9780199536852",
                                         "citation_key": "milton1674paradise"})
    assert out is not None
    assert out["title"] == "Hit"
    assert out["verified_via"] == "openlibrary"
    assert out["source_url"] == "http://ol"


def test_verify_citation_entry_falls_back_to_crossref_for_doi_only():
    from research_os.tools.actions.synthesis import citations as cit

    with patch(
        "research_os.tools.actions.synthesis.citations.verify_citation_key",
        return_value={"title": "from crossref", "doi": "10.1/x"},
    ) as fallback:
        out = cit.verify_citation_entry({"doi": "10.1/x",
                                         "citation_key": "smith2024foo"})
    assert out is not None
    assert out["title"] == "from crossref"
    fallback.assert_called_once_with("smith2024foo")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
