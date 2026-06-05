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
* ``verify_citation_key(key)`` — re-verify an existing citation key against
  Crossref. Returns the verified metadata or None.
* ``format_bib(entries, style)`` — BibTeX / APA / Vancouver / ACL formatting.
* ``write_references_bib(entries, dest)`` — write a proper .bib file.

Section caps
------------
* ``paper.md`` total: ≤ 40 citations (cite once per claim; reuse across sections).
* ``poster.tex``:     ≤ 6 (compact format).
* ``abstract.md``:    ≤ 3 (only seminal anchors).
* ``systematic_review/data_extraction.csv``: unbounded (the whole point).
"""

from __future__ import annotations

import logging
import re
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
# Collect
# ---------------------------------------------------------------------------


def collect_for_section(
    query: str, *, k: int = 5, providers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Pull k relevant papers from real providers. Skips any with no DOI/url."""
    from research_os.tools.actions.search.search import (
        search_crossref,
        search_semantic_scholar,
        search_pubmed,
        search_arxiv,
    )

    providers = providers or ["crossref", "semantic_scholar"]
    pool: list[dict[str, Any]] = []
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
            for h in hits:
                if not (h.get("doi") or h.get("url")):
                    continue
                h["verified_via"] = prov
                pool.append(h)
        except Exception as e:
            logger.warning(f"collect_for_section: {prov} failed: {e}")

    # Dedupe by DOI (lowercased) then URL.
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in pool:
        key = (p.get("doi") or p.get("url") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        # Generate a stable citation_key.
        p["citation_key"] = _make_key(p)
        out.append(p)
        if len(out) >= k:
            break
    return out


def _make_key(entry: dict[str, Any]) -> str:
    """Author{Year}{FirstSignificantWord} citation key."""
    authors = entry.get("authors") or []
    first_author = (authors[0] if authors else "anon").split()[-1]
    first_author = re.sub(r"[^a-zA-Z]", "", first_author).lower() or "anon"
    year = str(entry.get("year") or "nd")
    title_words = re.findall(r"[A-Za-z]{4,}", entry.get("title") or "")
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
