"""Unified literature + web search.

Public functions
----------------
* ``search_semantic_scholar(query, limit)``  → list[dict]
* ``search_crossref(query, limit)``          → list[dict]
* ``search_pubmed(query, limit)``            → list[dict]
* ``search_arxiv(query, limit)``             → list[dict]
* ``search_web(query, limit)``               → dict with results[] + warning
* ``scrape_web(url)``                        → dict with content + warning
* ``retrieve_literature(query, source, limit)`` → unified envelope

Everything is cached under ``.os_state/cache/`` so repeated calls are free.
Public endpoints are used by default; setting the matching API key just
raises the rate limit.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.search")


# ---------------------------------------------------------------------------
# Credentials & cache
# ---------------------------------------------------------------------------


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    if val:
        return val
    try:
        from research_os.config import settings  # noqa: F401

        return getattr(settings, name, None)
    except Exception:
        return None


def _cache_path(query: str, source: str) -> Path | None:
    try:
        from research_os.utils.common import find_project_root

        root = find_project_root()
    except Exception:
        return None
    if not root:
        return None
    h = hashlib.md5(f"{source}::{query}".encode()).hexdigest()
    return root / ".os_state" / "cache" / f"{source}_{h}.json"


def _read_cache(query: str, source: str) -> list[dict[str, Any]] | None:
    p = _cache_path(query, source)
    if p and p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def _write_cache(query: str, source: str, data: list[dict[str, Any]]) -> None:
    p = _cache_path(query, source)
    if not p:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(data))
    except Exception:
        pass


def _log_error(message: str) -> None:
    try:
        from research_os.project_ops import now_iso
        from research_os.utils.common import find_project_root

        root = find_project_root()
        if not root or not (root / ".os_state").exists():
            return
        log_path = root / "workspace" / "logs" / "errors.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{now_iso()}] search: {message}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Literature providers
# ---------------------------------------------------------------------------


_S2_LAST_CALL = 0.0


def search_semantic_scholar(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search Semantic Scholar Graph API. Optional key raises rate limits."""
    global _S2_LAST_CALL
    cached = _read_cache(query, "semantic_scholar")
    if cached is not None:
        return cached[:limit]

    api_key = _env("SEMANTIC_SCHOLAR_API_KEY") or _env("S2_API_KEY")
    min_interval = 0.11 if api_key else 1.1
    elapsed = time.time() - _S2_LAST_CALL
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _S2_LAST_CALL = time.time()

    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={urllib.parse.quote(query)}&limit={limit}"
        "&fields=title,authors,year,url,externalIds,abstract"
    )
    headers = {"User-Agent": "Research-OS/1.0"}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        _log_error(f"semantic_scholar failed: {e}")
        return []

    results = []
    for item in data.get("data", []) or []:
        results.append(
            {
                "title": item.get("title", ""),
                "authors": [a.get("name", "") for a in item.get("authors", []) or []],
                "year": item.get("year"),
                "url": item.get("url", ""),
                "doi": (item.get("externalIds") or {}).get("DOI", ""),
                "abstract": item.get("abstract", ""),
            }
        )
    _write_cache(query, "semantic_scholar", results)
    return results


def search_crossref(query: str, limit: int = 5) -> list[dict[str, Any]]:
    cached = _read_cache(query, "crossref")
    if cached is not None:
        return cached[:limit]

    url = (
        "https://api.crossref.org/works"
        f"?query={urllib.parse.quote(query)}&rows={limit}"
    )
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Research-OS/1.0"}),
            timeout=15,
        ) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        _log_error(f"crossref failed: {e}")
        return []

    items = (data.get("message") or {}).get("items", []) or []
    results = []
    for item in items:
        title_list = item.get("title") or [""]
        title = title_list[0] if title_list else ""
        date = (item.get("issued") or {}).get("date-parts") or [[None]]
        year = date[0][0] if date and date[0] else None
        results.append(
            {
                "title": title,
                "authors": [
                    f"{a.get('given', '').strip()} {a.get('family', '').strip()}".strip()
                    for a in item.get("author", []) or []
                ],
                "year": year,
                "url": item.get("URL", ""),
                "doi": item.get("DOI", ""),
                "abstract": (item.get("abstract") or "")[:1000],
            }
        )
    _write_cache(query, "crossref", results)
    return results


def search_pubmed(query: str, limit: int = 5) -> list[dict[str, Any]]:
    cached = _read_cache(query, "pubmed")
    if cached is not None:
        return cached[:limit]

    api_key = _env("NCBI_API_KEY")
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    esearch = (
        f"{base}/esearch.fcgi?db=pubmed&retmode=json"
        f"&retmax={limit}&term={urllib.parse.quote(query)}"
    )
    if api_key:
        esearch += f"&api_key={api_key}"
    try:
        with urllib.request.urlopen(esearch, timeout=15) as resp:
            ids = (json.loads(resp.read()).get("esearchresult") or {}).get("idlist", []) or []
    except Exception as e:
        _log_error(f"pubmed esearch failed: {e}")
        return []
    if not ids:
        return []

    esummary = f"{base}/esummary.fcgi?db=pubmed&retmode=json&id={','.join(ids)}"
    if api_key:
        esummary += f"&api_key={api_key}"
    try:
        with urllib.request.urlopen(esummary, timeout=15) as resp:
            summary = (json.loads(resp.read()).get("result") or {})
    except Exception as e:
        _log_error(f"pubmed esummary failed: {e}")
        return []

    results = []
    for pmid in ids:
        item = summary.get(pmid)
        if not item:
            continue
        results.append(
            {
                "title": item.get("title", ""),
                "authors": [a.get("name", "") for a in item.get("authors", []) or []],
                "year": (item.get("pubdate") or "")[:4],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "doi": next(
                    (
                        a.get("value")
                        for a in item.get("articleids", []) or []
                        if a.get("idtype") == "doi"
                    ),
                    "",
                ),
            }
        )
    _write_cache(query, "pubmed", results)
    return results


def search_arxiv(query: str, limit: int = 5) -> list[dict[str, Any]]:
    cached = _read_cache(query, "arxiv")
    if cached is not None:
        return cached[:limit]

    url = (
        "http://export.arxiv.org/api/query"
        f"?search_query=all:{urllib.parse.quote(query)}&max_results={limit}"
        "&sortBy=relevance&sortOrder=descending"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read()
    except Exception as e:
        _log_error(f"arxiv failed: {e}")
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        _log_error(f"arxiv parse failed: {e}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        link = entry.findtext("atom:id", default="", namespaces=ns) or ""
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        authors = [
            (a.findtext("atom:name", default="", namespaces=ns) or "")
            for a in entry.findall("atom:author", ns)
        ]
        results.append(
            {
                "title": title,
                "authors": authors,
                "year": published[:4],
                "url": link,
                "doi": "",
                "abstract": summary[:1000],
            }
        )
    _write_cache(query, "arxiv", results)
    return results


def retrieve_literature(
    query: str, source: str = "crossref", limit: int = 5
) -> dict[str, Any]:
    """Unified envelope returning status + count + results[]."""
    limit = max(1, min(limit, 10))
    source = (source or "crossref").lower()
    try:
        if source == "semantic_scholar":
            results = search_semantic_scholar(query, limit)
        elif source == "pubmed":
            results = search_pubmed(query, limit)
            if not results:
                results = search_crossref(query, limit)
                source = "crossref (pubmed fallback)"
        elif source == "arxiv":
            results = search_arxiv(query, limit)
        else:
            results = search_crossref(query, limit)

        payload: dict[str, Any] = {
            "status": "success",
            "source": source,
            "query": query,
            "count": len(results),
            "results": results,
        }
        if len(json.dumps(payload)) > 15000:
            payload["results"] = payload["results"][:3]
            payload["warning"] = "truncated; narrow the query"
        return payload
    except Exception as e:
        logger.exception("retrieve_literature failed")
        return {
            "status": "error",
            "source": source,
            "query": query,
            "details": str(e),
        }


# ---------------------------------------------------------------------------
# Web search + scrape (Firecrawl preferred, SerpAPI fallback)
# ---------------------------------------------------------------------------


def search_web(query: str, limit: int = 5) -> dict[str, Any]:
    """Search the web. Firecrawl first; SerpAPI fallback."""
    fc = _env("FIRECRAWL_API_KEY") or _env("FIRECRAWL")
    serpapi = _env("SERPAPI_API_KEY") or _env("SERPAPI")

    if fc:
        try:
            from firecrawl import FirecrawlApp  # type: ignore

            app = FirecrawlApp(api_key=fc)
            response = app.search(query)
            raw = response.get("data", []) if isinstance(response, dict) else []
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", "") or r.get("snippet", ""),
                }
                for r in raw[:limit]
            ]
            return {
                "query": query,
                "source": "firecrawl",
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            _log_error(f"firecrawl failed: {e}")

    if serpapi:
        try:
            url = (
                "https://serpapi.com/search?engine=google"
                f"&q={urllib.parse.quote(query)}&api_key={serpapi}"
            )
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
            organic = data.get("organic_results", [])[:limit]
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "description": r.get("snippet", ""),
                }
                for r in organic
            ]
            return {
                "query": query,
                "source": "serpapi",
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            _log_error(f"serpapi failed: {e}")

    return {
        "query": query,
        "source": "web",
        "count": 0,
        "results": [],
        "warning": (
            "No web-search provider configured. Add `firecrawl` or `serpapi` "
            "to inputs/researcher_config.yaml api_keys."
        ),
    }


def scrape_web(url: str) -> dict[str, Any]:
    """Scrape a webpage to markdown. Firecrawl preferred, trafilatura fallback."""
    fc = _env("FIRECRAWL_API_KEY") or _env("FIRECRAWL")
    if fc:
        try:
            from firecrawl import FirecrawlApp  # type: ignore

            app = FirecrawlApp(api_key=fc)
            r = app.scrape_url(url, params={"formats": ["markdown"]})
            content = r.get("markdown") if isinstance(r, dict) else None
            if content:
                return {"url": url, "source": "firecrawl", "content": content}
        except Exception as e:
            _log_error(f"firecrawl scrape failed: {e}")

    try:
        import trafilatura  # type: ignore

        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            content = trafilatura.extract(downloaded) or ""
            return {"url": url, "source": "trafilatura", "content": content}
    except Exception as e:
        _log_error(f"trafilatura scrape failed: {e}")

    return {
        "url": url,
        "content": "",
        "warning": "No scraper available — install trafilatura or set firecrawl key.",
    }
