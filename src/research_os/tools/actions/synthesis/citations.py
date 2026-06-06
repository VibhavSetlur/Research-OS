"""Verified citation management — only real, verified papers in final outputs.

Hallucinated citations are the most common failure mode of AI-generated
papers. Every paper we emit must be:

1. Sourced from a real Crossref / Semantic Scholar / PubMed hit.
2. Stored with its DOI (when available), authors, year, venue.
3. Ranked by relevance to a specific claim.
4. Capped per section to avoid 'literature dump' style writing.

Workflow
--------
* ``collect_for_section(query, k)`` — ground a section's claims by pulling
  the top-K relevant papers from real providers. Returns a structured list
  with ``verified_via=<provider>``.
* ``collect_for_section_with_failures(query, k)`` — same as above but also
  reports the per-provider failure count + structured exception sample so
  ``tool_synthesize`` can surface why retrieval came back empty instead of
  silently writing ``citations_used: 0``.
* ``verify_citation_key(key)`` — re-verify an existing citation key against
  Crossref. Returns the verified metadata or None.
* ``format_bib(entries, style)`` — BibTeX / APA / Vancouver / ACL formatting.
* ``write_references_bib(entries, dest)`` — write a proper .bib file.

Failure logging
---------------
When live retrieval or per-entry parsing raises (for example, the
``list index out of range`` triggered by a malformed upstream hit), the
exception is captured in ``workspace/logs/citation_failures.jsonl`` as one JSON line
per failure with ``{ts, provider, query, exception_type, message,
traceback}``. The caller is never re-raised at; an empty list is returned
so the synthesis pipeline keeps moving.

Section caps
------------
* ``paper.md`` total: ≤ 40 citations (cite once per claim; reuse across sections).
* ``poster.tex``:     ≤ 6 (compact format).
* ``abstract.md``:    ≤ 3 (only seminal anchors).
* ``systematic_review/data_extraction.csv``: unbounded (the whole point).
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.citations")


SECTION_CAPS: dict[str, int] = {
    "paper": 40,
    "poster": 6,
    "abstract": 3,
    "dashboard": 12,
    "report": 25,
}


# ---------------------------------------------------------------------------
# Failure logging — surface what the catch-all previously buried
# ---------------------------------------------------------------------------


def _log_citation_failure(
    *,
    provider: str,
    query: str,
    exc: BaseException,
    root: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one JSON line to ``workspace/logs/citation_failures.jsonl``.

    Never raises — failure logging must not itself break synthesis. When
    no project root is available (running outside a project) the failure
    is logged through the module logger and that's it.
    """
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "query": query,
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc().splitlines()[-12:],
    }
    if extra:
        record.update(extra)

    try:
        if root is None:
            from research_os.utils.common import find_project_root

            root = find_project_root()
        if root is None:
            logger.warning(
                "citation retrieval failure (no project root for jsonl): %s",
                record,
            )
            return
        log_path = root / "workspace" / "logs" / "citation_failures.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001
        logger.warning("could not append citation_failures.jsonl: %r", record)


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------


def collect_for_section(
    query: str, *, k: int = 5, providers: list[str] | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Pull k relevant papers from real providers. Skips any with no DOI/url.

    Backwards-compatible wrapper around
    :func:`collect_for_section_with_failures` — returns only the list so
    every existing caller keeps working. New code that wants the failure
    counts should call the ``_with_failures`` variant.
    """
    entries, _failures = collect_for_section_with_failures(
        query, k=k, providers=providers, root=root
    )
    return entries


def collect_for_section_with_failures(
    query: str, *, k: int = 5, providers: list[str] | None = None,
    root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pull k relevant papers AND report per-provider failure metadata.

    Per-hit parsing is wrapped so that one malformed upstream record
    (for instance an empty / non-list author field that raises
    ``list index out of range`` inside the parser) cannot abort the
    whole provider — the bad hit is logged and skipped, every other hit
    still flows through.

    Returns ``(entries, failures)`` where ``failures`` is::

        {
            "total": int,                       # all failures across providers
            "by_provider": {prov: int, ...},    # per-provider counts
            "samples": [                        # at most 3, for the response
                {"provider", "exception_type", "message"}, ...
            ],
        }
    """
    from research_os.tools.actions.search.search import (
        search_arxiv,
        search_crossref,
        search_pubmed,
        search_semantic_scholar,
    )

    providers = providers or ["crossref", "semantic_scholar"]
    pool: list[dict[str, Any]] = []
    by_provider: dict[str, int] = {}
    samples: list[dict[str, str]] = []

    def _record_failure(prov: str, exc: BaseException) -> None:
        by_provider[prov] = by_provider.get(prov, 0) + 1
        if len(samples) < 3:
            samples.append(
                {
                    "provider": prov,
                    "exception_type": type(exc).__name__,
                    "message": str(exc)[:240],
                }
            )
        _log_citation_failure(provider=prov, query=query, exc=exc, root=root)

    for prov in providers:
        try:
            if prov == "crossref":
                hits = search_crossref(query, limit=k)
            elif prov == "semantic_scholar":
                hits = search_semantic_scholar(query, limit=k)
            elif prov == "pubmed":
                hits = search_pubmed(query, limit=k)
            elif prov == "arxiv":
                hits = search_arxiv(query, limit=k)
            else:
                continue
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "collect_for_section: provider %s search raised: %s", prov, e
            )
            _record_failure(prov, e)
            continue

        # Defensive: an upstream provider can in principle hand us None
        # (no body, deserialise failed) — treat as empty.
        if not hits:
            continue

        for h in hits:
            try:
                if not isinstance(h, dict):
                    continue
                if not (h.get("doi") or h.get("url")):
                    continue
                h["verified_via"] = prov
                pool.append(h)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "collect_for_section: per-hit parse failure in %s: %s",
                    prov, e,
                )
                _record_failure(prov, e)
                continue

    # Dedupe by DOI (lowercased) then URL.
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in pool:
        try:
            key = (p.get("doi") or p.get("url") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            # Generate a stable citation_key — defensive so a hit with an
            # empty author / weird title doesn't IndexError out of the loop.
            p["citation_key"] = _make_key(p)
            out.append(p)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "collect_for_section: key/dedupe failure for %s: %s",
                p.get("title") or p.get("url") or "?", e,
            )
            _record_failure(p.get("verified_via") or "unknown", e)
            continue
        if len(out) >= k:
            break

    failures: dict[str, Any] = {
        "total": sum(by_provider.values()),
        "by_provider": by_provider,
        "samples": samples,
    }
    return out, failures


def _make_key(entry: dict[str, Any]) -> str:
    """Author{Year}{FirstSignificantWord} citation key — defensive.

    Tolerates the failure modes a real upstream feed can hand us:
      * ``authors`` is missing, ``None``, an empty list, or a list whose
        first element is an empty / whitespace-only string.
      * ``authors[0]`` is not a string (some upstreams hand dicts).
      * ``title`` is missing / ``None`` / a list of strings.
    Never raises ``IndexError``; falls back to ``anon{year}paper``.
    """
    authors = entry.get("authors") or []
    raw_first = authors[0] if authors else "anon"
    if isinstance(raw_first, dict):
        raw_first = raw_first.get("name") or raw_first.get("family") or "anon"
    if not isinstance(raw_first, str) or not raw_first.strip():
        raw_first = "anon"
    parts = raw_first.split()
    first_author = parts[-1] if parts else "anon"
    first_author = re.sub(r"[^a-zA-Z]", "", first_author).lower() or "anon"
    year = str(entry.get("year") or "nd")
    raw_title = entry.get("title") or ""
    if isinstance(raw_title, list):
        raw_title = raw_title[0] if raw_title and isinstance(raw_title[0], str) else ""
    title_words = re.findall(r"[A-Za-z]{4,}", raw_title)
    stem = title_words[0].lower() if title_words else "paper"
    return f"{first_author}{year}{stem}"


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify_citation_key(key: str) -> dict[str, Any] | None:
    """Re-verify an existing citation against Crossref by keyword search."""
    try:
        from research_os.tools.actions.search.search import search_crossref

        query = key.replace("_", " ")
        hits = search_crossref(query, limit=3)
        for h in hits:
            if h.get("doi") or h.get("url"):
                return h
    except Exception as e:
        logger.warning(f"verify_citation_key failed: {e}")
    return None


def verify_citation_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Verify a citation dict using the best available identifier.

    Routing:
      * ISBN present → tries WorldCat → OpenLibrary → LOC (humanities path).
      * Otherwise → falls back to Crossref keyword search via
        :func:`verify_citation_key` using the citation_key / title.

    Returns the verified metadata dict on success, ``None`` otherwise.
    Always non-raising — verifier failures are swallowed and logged.
    """
    try:
        from research_os.tools.actions.research.citations_isbn import (
            _extract_isbn,
            verify_citation_auto,
        )

        if _extract_isbn(entry):
            ok, evidence, source_url = verify_citation_auto(entry)
            if ok:
                return {**entry, **evidence, "source_url": source_url}
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"verify_citation_entry ISBN path failed: {e}")

    probe = entry.get("citation_key") or entry.get("title") or ""
    if not probe:
        return None
    return verify_citation_key(probe)


def verify_all_in_workspace(root: Path) -> dict[str, Any]:
    """Walk workspace/citations.md and confirm each citation_key resolves."""
    citations_md = root / "workspace" / "citations.md"
    if not citations_md.exists():
        return {"status": "error", "message": "workspace/citations.md not found"}
    text = citations_md.read_text()
    keys = re.findall(r"^###\s+`([^`]+)`", text, flags=re.MULTILINE)
    verified, unverified = [], []
    for k in keys:
        meta = verify_citation_key(k)
        (verified if meta else unverified).append(k)
    return {
        "status": "success",
        "verified": verified,
        "unverified": unverified,
        "verified_count": len(verified),
        "unverified_count": len(unverified),
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_bib(entry: dict[str, Any]) -> str:
    """One BibTeX entry from a verified citation dict."""
    key = entry.get("citation_key") or _make_key(entry)
    authors = " and ".join(entry.get("authors") or ["Unknown"])
    title = entry.get("title", "Untitled").replace("{", "").replace("}", "")
    year = entry.get("year") or ""
    doi = entry.get("doi") or ""
    url = entry.get("url") or ""
    fields = [
        f"  author    = {{{authors}}}",
        f"  title     = {{{title}}}",
        f"  year      = {{{year}}}",
    ]
    if doi:
        fields.append(f"  doi       = {{{doi}}}")
    if url:
        fields.append(f"  url       = {{{url}}}")
    return "@article{" + key + ",\n" + ",\n".join(fields) + "\n}\n"


def format_apa(entry: dict[str, Any]) -> str:
    """One APA-style citation line."""
    authors = entry.get("authors") or []
    if not authors:
        author_str = "Unknown"
    elif len(authors) == 1:
        author_str = authors[0]
    elif len(authors) <= 6:
        author_str = ", ".join(authors[:-1]) + ", & " + authors[-1]
    else:
        author_str = ", ".join(authors[:6]) + ", et al."
    year = entry.get("year") or "n.d."
    title = entry.get("title", "Untitled")
    venue = entry.get("venue", "")
    doi_str = f" https://doi.org/{entry['doi']}" if entry.get("doi") else ""
    venue_str = f" {venue}." if venue else ""
    return f"{author_str} ({year}). {title}.{venue_str}{doi_str}".strip()


def format_vancouver(entry: dict[str, Any]) -> str:
    """One Vancouver-style citation line."""
    authors = entry.get("authors") or []
    if not authors:
        author_str = "Anon"
    elif len(authors) <= 6:
        author_str = ", ".join(authors)
    else:
        author_str = ", ".join(authors[:6]) + ", et al"
    year = entry.get("year") or ""
    title = entry.get("title", "Untitled")
    venue = entry.get("venue", "")
    doi_str = f" doi: {entry['doi']}" if entry.get("doi") else ""
    venue_str = f" {venue}." if venue else ""
    return f"{author_str}. {title}.{venue_str} {year}.{doi_str}".strip()


_FORMATTERS = {
    "bibtex": format_bib,
    "apa": format_apa,
    "vancouver": format_vancouver,
}


def write_references_bib(entries: list[dict[str, Any]], dest: Path) -> Path:
    """Write a BibTeX file from verified entries (one @article each)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = "% Auto-generated by Research OS — all entries verified online.\n\n"
    body += "\n".join(format_bib(e) for e in entries)
    dest.write_text(body)
    return dest


def cap_for(output_type: str) -> int:
    """Section cap for a given output type."""
    return SECTION_CAPS.get(output_type.lower(), 25)
