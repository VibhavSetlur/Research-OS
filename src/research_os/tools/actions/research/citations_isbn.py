"""ISBN-based monograph citation verifiers (WorldCat / OpenLibrary / LOC).

Humanities work (literary criticism, history, philosophy) cites books, not
journal articles. Crossref + Semantic Scholar resolve DOIs well but rarely
cover monographs. This module adds three ISBN-aware verifiers that wrap free
public bibliographic APIs:

* WorldCat (xISBN / OCLC search)
* OpenLibrary (`/api/books?bibkeys=ISBN:<isbn>`)
* Library of Congress (SRU search on loc.gov)

Interface — every verifier takes a citation dict and returns the tuple
``(verified: bool, evidence: dict, source_url: str)``.  Failures (network
unreachable, rate-limit, malformed response) are caught: the verifier
returns ``verified=False`` with an ``evidence={"reason": ...}`` envelope
and NEVER raises.  This keeps the synthesis pipeline tolerant of offline
or partial environments.

The module also exposes ``verify_citation_auto(entry)`` which picks the
right verifier based on what the citation carries:

* DOI present (no ISBN) → caller should use the existing Crossref / S2
  flow in ``synthesis.citations``; this module returns ``("skipped",
  {"reason": "doi_path"}, "")``.
* ISBN present (with or without DOI) → tries WorldCat → OpenLibrary →
  LOC, returns the first success.

Only stdlib (``urllib`` + ``json``).  All network calls use a 5 s timeout.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("research_os.tools.research.citations_isbn")

_TIMEOUT = 5.0
_UA = "Research-OS/1.0 (+https://github.com/vsetlur/Research-OS)"


# ---------------------------------------------------------------------------
# ISBN helpers
# ---------------------------------------------------------------------------


def _clean_isbn(raw: str) -> str:
    """Strip hyphens / whitespace; return digits (+ trailing 'X' allowed)."""
    if not raw:
        return ""
    s = re.sub(r"[^0-9Xx]", "", str(raw))
    return s.upper()


def _extract_isbn(entry: dict[str, Any]) -> str:
    """Pull an ISBN out of common citation-dict fields."""
    for key in ("isbn", "ISBN", "isbn13", "isbn10"):
        val = entry.get(key)
        if val:
            cleaned = _clean_isbn(val)
            if cleaned:
                return cleaned
    return ""


def _has_doi(entry: dict[str, Any]) -> bool:
    return bool((entry.get("doi") or entry.get("DOI") or "").strip())


# ---------------------------------------------------------------------------
# Network primitive
# ---------------------------------------------------------------------------


def _fetch(url: str, *, accept: str = "application/json") -> tuple[int, bytes, str]:
    """GET ``url`` with a short timeout.  Returns ``(status, body, reason)``.

    Never raises.  On failure, ``status=0`` and ``reason`` describes why.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": accept})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read()
            return (getattr(resp, "status", 200) or 200, body, "")
    except urllib.error.HTTPError as e:
        return (e.code, b"", f"http_{e.code}")
    except urllib.error.URLError as e:
        return (0, b"", f"unreachable:{e.reason!s}")
    except Exception as e:  # noqa: BLE001 — must never raise
        return (0, b"", f"error:{e!s}")


# ---------------------------------------------------------------------------
# Verifiers
# ---------------------------------------------------------------------------


def verify_openlibrary(citation: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
    """Verify an ISBN against the OpenLibrary Books API.

    Endpoint: ``/api/books?bibkeys=ISBN:<isbn>&format=json&jscmd=data``.
    Returns the canonical OpenLibrary record (title, authors, publisher) on
    success.
    """
    isbn = _extract_isbn(citation)
    if not isbn:
        return (False, {"reason": "no_isbn"}, "")

    source_url = (
        f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}"
        "&format=json&jscmd=data"
    )
    status, body, reason = _fetch(source_url)
    if status == 0 or not body:
        return (False, {"reason": reason or "unreachable"}, source_url)
    if status != 200:
        return (False, {"reason": f"http_{status}"}, source_url)

    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return (False, {"reason": "bad_json"}, source_url)

    key = f"ISBN:{isbn}"
    record = (payload or {}).get(key)
    if not record:
        return (False, {"reason": "not_found", "isbn": isbn}, source_url)

    evidence = {
        "title": record.get("title", ""),
        "authors": [a.get("name", "") for a in record.get("authors", []) or []],
        "publishers": [p.get("name", "") for p in record.get("publishers", []) or []],
        "publish_date": record.get("publish_date", ""),
        "openlibrary_url": record.get("url", ""),
        "isbn": isbn,
    }
    return (True, evidence, source_url)


def verify_worldcat(citation: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
    """Verify an ISBN against WorldCat (OCLC ClassifyAPI).

    The classic ``xisbn`` service was retired; we use ``classify.oclc.org``
    which still answers ISBN lookups and returns an OCLC work number plus a
    canonical title / author block.  Response is XML — we extract the bits
    we need with regex (no extra deps).
    """
    isbn = _extract_isbn(citation)
    if not isbn:
        return (False, {"reason": "no_isbn"}, "")

    source_url = (
        f"http://classify.oclc.org/classify2/Classify?isbn={isbn}&summary=true"
    )
    status, body, reason = _fetch(source_url, accept="application/xml")
    if status == 0 or not body:
        return (False, {"reason": reason or "unreachable"}, source_url)
    if status != 200:
        return (False, {"reason": f"http_{status}"}, source_url)

    text = body.decode("utf-8", errors="replace")
    # Response carries a <response code="N"/> header — 0/2/4 mean a hit.
    code_match = re.search(r'<response\s+code="(\d+)"', text)
    code = code_match.group(1) if code_match else ""
    if code not in {"0", "2", "4"}:
        return (False, {"reason": f"worldcat_code_{code or 'missing'}",
                        "isbn": isbn}, source_url)

    work_match = re.search(r'<work[^>]*\stitle="([^"]+)"', text)
    author_match = re.search(r'\sauthor="([^"]+)"', text)
    owi_match = re.search(r'\sowi="(\d+)"', text)
    evidence = {
        "title": work_match.group(1) if work_match else "",
        "author": author_match.group(1) if author_match else "",
        "owi": owi_match.group(1) if owi_match else "",
        "isbn": isbn,
    }
    if not evidence["title"]:
        return (False, {"reason": "no_work_element", "isbn": isbn}, source_url)
    return (True, evidence, source_url)


def verify_loc(citation: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
    """Verify an ISBN against the Library of Congress SRU endpoint.

    Endpoint: ``https://www.loc.gov/books/?q=<isbn>&fo=json`` — LOC's
    public JSON-over-HTTP search.  Counts a hit as verified when at least
    one ``results`` entry mentions the queried ISBN.
    """
    isbn = _extract_isbn(citation)
    if not isbn:
        return (False, {"reason": "no_isbn"}, "")

    query = urllib.parse.quote(isbn)
    source_url = f"https://www.loc.gov/books/?q={query}&fo=json&c=5"
    status, body, reason = _fetch(source_url)
    if status == 0 or not body:
        return (False, {"reason": reason or "unreachable"}, source_url)
    if status != 200:
        return (False, {"reason": f"http_{status}"}, source_url)

    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return (False, {"reason": "bad_json"}, source_url)

    results = (payload or {}).get("results") or []
    if not results:
        return (False, {"reason": "not_found", "isbn": isbn}, source_url)

    first = results[0] or {}
    evidence = {
        "title": first.get("title", ""),
        "contributor": first.get("contributor", []),
        "date": first.get("date", ""),
        "loc_url": first.get("id", "") or first.get("url", ""),
        "isbn": isbn,
        "hit_count": len(results),
    }
    return (True, evidence, source_url)


# ---------------------------------------------------------------------------
# Auto-select dispatcher
# ---------------------------------------------------------------------------


def _isbn_verifiers() -> list[tuple[str, Any]]:
    """Resolve verifier callables at call time so test-suite ``patch``
    decorators on the module-level names propagate into the chain."""
    mod = sys.modules[__name__]
    return [
        ("worldcat", mod.verify_worldcat),
        ("openlibrary", mod.verify_openlibrary),
        ("loc", mod.verify_loc),
    ]


def verify_citation_auto(
    citation: dict[str, Any],
) -> tuple[bool, dict[str, Any], str]:
    """Pick the right verifier for a citation dict.

    Routing rules:
      * Has DOI, no ISBN → returns ``(False, {"reason":"doi_path"}, "")``.
        Caller delegates to the existing Crossref/S2 verifier.
      * Has ISBN (with or without DOI) → tries WorldCat → OpenLibrary →
        LOC in order.  First success wins.  If all three fail, returns the
        last verifier's negative result with the chain recorded under
        ``evidence['tried']``.
      * Has neither → ``(False, {"reason":"no_identifier"}, "")``.
    """
    isbn = _extract_isbn(citation)
    if not isbn:
        if _has_doi(citation):
            return (False, {"reason": "doi_path"}, "")
        return (False, {"reason": "no_identifier"}, "")

    tried: list[str] = []
    last_neg: tuple[bool, dict[str, Any], str] = (
        False,
        {"reason": "all_failed", "tried": tried, "isbn": isbn},
        "",
    )
    for name, verifier in _isbn_verifiers():
        try:
            ok, evidence, url = verifier(citation)
        except Exception as e:  # noqa: BLE001 — verifiers must not raise
            logger.warning("ISBN verifier %s raised %s", name, e)
            tried.append(f"{name}:exception")
            continue
        tried.append(f"{name}:{'hit' if ok else evidence.get('reason', 'miss')}")
        if ok:
            evidence["verified_via"] = name
            evidence["tried"] = list(tried)
            return (True, evidence, url)
        last_neg = (False, {**evidence, "tried": list(tried),
                            "last_via": name}, url)
    return last_neg
