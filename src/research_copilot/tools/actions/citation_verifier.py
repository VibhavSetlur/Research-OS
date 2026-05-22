#!/usr/bin/env python3
"""Citation Verification Pipeline — three-pass anti-hallucination system.

Pass 1: Existence check (CrossRef, arXiv, PubMed)
Pass 2: Content verification (Semantic Scholar abstract vs claim)
Pass 3: Retraction check (CrossRef retraction notices)

Usage:
    python .research/scripts/utils/citation_verifier.py --bibliography 00_inputs/literature/bibliography.bib
    python .research/scripts/utils/citation_verifier.py --corpus 00_inputs/literature/literature_corpus.json
    python .research/scripts/utils/citation_verifier.py --manuscript 03_synthesis/manuscript/research_findings.md
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_exponential


logger = logging.getLogger("research.citation_verifier")


class APITimeoutError(Exception):
    pass


def _is_retryable_api_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    if isinstance(exc, urllib.error.URLError):
        return True
    return isinstance(exc, TimeoutError)


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=False,
)
def _url_get_with_backoff(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchCopilot/1.0 (mailto:research@copilot.local)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _timeout_tagged_citation(citation: dict) -> str:
    author = citation.get("author", "Unknown")
    year = citation.get("year", "N/A")
    return f"{author}, {year} [UNVERIFIED - API TIMEOUT]"


def _api_timeout_result(source: str) -> dict:
    return {"status": "api_timeout", "error": f"{source} API timed out after 3 retries"}

class CitationNotFoundError(Exception):
    def __init__(self, message, identifier):
        super().__init__(message)
        self.identifier = identifier

class CitationRetractedError(Exception):
    def __init__(self, message, identifier):
        super().__init__(message)
        self.identifier = identifier


from research_copilot.utils.common import find_project_root, save_json_atomic, now_iso


def add_core_path():
    core = find_project_root() / ".research" / "core"
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))


def url_get(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch URL content with error handling."""
    try:
        return _url_get_with_backoff(url, timeout)
    except RetryError as exc:
        last_exc = None
        if getattr(exc, "last_attempt", None) is not None:
            last_exc = exc.last_attempt.exception()
        if last_exc is not None and _is_retryable_api_error(last_exc):
            raise APITimeoutError(f"API request failed after 3 retries: {url}") from last_exc
        return None
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise APITimeoutError(f"API rate limited after 3 retries: {url}") from exc
        return None
    except Exception:
        return None


def url_get_json(url: str, timeout: int = 15) -> Optional[dict]:
    """Fetch URL and parse as JSON."""
    raw = url_get(url, timeout)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


# ── Pass 1: Existence Check ──────────────────────────────────────────────

def verify_crossref(doi: str) -> dict:
    """Verify a DOI via CrossRef API."""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        data = url_get_json(url)
    except APITimeoutError as exc:
        return {**_api_timeout_result("CrossRef"), "citation_tag": "[UNVERIFIED - API TIMEOUT]", "error": str(exc)}
    if data is None:
        return {"status": "not_found", "error": "CrossRef API returned no data"}

    message = data.get("message", {})
    title = message.get("title", [""])[0]
    authors = [a.get("given", "") + " " + a.get("family", "") for a in message.get("author", [])]
    year = None
    date_parts = message.get("published-print", message.get("published-online", {}))
    if "date-parts" in date_parts and date_parts["date-parts"]:
        year = date_parts["date-parts"][0][0]

    return {
        "status": "verified",
        "title": title,
        "authors": authors[:5],
        "year": year,
        "error": None,
    }


def verify_arxiv(arxiv_id: str) -> dict:
    """Verify an arXiv ID via arXiv API."""
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        raw = url_get(url)
    except APITimeoutError as exc:
        return {**_api_timeout_result("arXiv"), "citation_tag": "[UNVERIFIED - API TIMEOUT]", "error": str(exc)}
    if raw is None:
        return {"status": "not_found", "error": "arXiv API returned no data"}

    title_match = re.search(r"<title>(.+?)</title>", raw, re.DOTALL)
    author_matches = re.findall(r"<name>(.+?)</name>", raw)
    date_match = re.search(r"<published>(\d{4})", raw)

    if not title_match:
        return {"status": "not_found", "error": "No title found in arXiv response"}

    title = title_match.group(1).strip()
    if title == "Error":
        return {"status": "not_found", "error": "arXiv returned error"}

    return {
        "status": "verified",
        "title": title,
        "authors": author_matches[:5],
        "year": int(date_match.group(1)) if date_match else None,
        "error": None,
    }


def verify_pubmed(pmid: str) -> dict:
    """Verify a PubMed ID via NCBI E-utilities."""
    fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=text&rettype=abstract"
    try:
        raw = url_get(fetch_url)
    except APITimeoutError as exc:
        return {**_api_timeout_result("PubMed"), "citation_tag": "[UNVERIFIED - API TIMEOUT]", "error": str(exc)}
    if raw is None:
        return {"status": "not_found", "error": "PubMed API returned no data"}

    title_match = re.search(r"^\s*(.+)$", raw, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""

    if "error" in raw.lower() and "uid" in raw.lower():
        return {"status": "not_found", "error": "PubMed ID not found"}

    return {
        "status": "verified",
        "title": title,
        "authors": [],
        "year": None,
        "error": None,
    }


def pass1_existence(identifier: str, identifier_type: str) -> dict:
    """Run Pass 1: existence check based on identifier type."""
    if identifier_type == "doi":
        return verify_crossref(identifier)
    elif identifier_type == "arxiv":
        return verify_arxiv(identifier)
    elif identifier_type == "pubmed":
        return verify_pubmed(identifier)
    else:
        return {"status": "skipped", "error": f"Unknown identifier type: {identifier_type}"}


# ── Pass 2: Content Verification ─────────────────────────────────────────

def fetch_semantic_scholar_abstract(identifier: str, identifier_type: str) -> Optional[str]:
    """Fetch abstract from Semantic Scholar API."""
    if identifier_type == "doi":
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{identifier}?fields=title,abstract,authors,year"
    elif identifier_type == "arxiv":
        url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{identifier}?fields=title,abstract,authors,year"
    elif identifier_type == "pubmed":
        url = f"https://api.semanticscholar.org/graph/v1/paper/PMID:{identifier}?fields=title,abstract,authors,year"
    else:
        return None

    data = url_get_json(url)
    if data:
        return data.get("abstract")
    return None


def pass2_content(abstract: Optional[str], claim: str) -> dict:
    """Run Pass 2: content verification.

    Since we cannot call an LLM from this script, we perform a keyword-based
    heuristic check. The agent should re-run this with LLM verification.
    """
    if abstract is None:
        return {"status": "no_abstract", "justification": "No abstract available for content verification"}

    abstract_lower = abstract.lower()
    claim_lower = claim.lower()

    claim_words = set(re.findall(r"\b\w{4,}\b", claim_lower))
    abstract_words = set(re.findall(r"\b\w{4,}\b", abstract_lower))
    overlap = claim_words & abstract_words

    overlap_ratio = len(overlap) / len(claim_words) if claim_words else 0

    if overlap_ratio >= 0.3:
        status = "supported"
        justification = f"Abstract shares {len(overlap)} key terms with claim ({overlap_ratio:.0%} overlap)"
    elif overlap_ratio >= 0.1:
        status = "partial"
        justification = f"Abstract shares some terms with claim ({overlap_ratio:.0%} overlap) — needs LLM review"
    else:
        status = "unsupported"
        justification = f"Abstract shares minimal terms with claim ({overlap_ratio:.0%} overlap) — likely does not support"

    return {
        "status": status,
        "justification": justification,
        "abstract_snippet": abstract[:200],
        "overlap_ratio": round(overlap_ratio, 3),
        "shared_terms": list(overlap)[:10],
    }


# ── Pass 3: Retraction Check ─────────────────────────────────────────────

def check_crossref_retraction(doi: str) -> dict:
    """Check if a DOI has been retracted via CrossRef."""
    url = f"https://api.crossref.org/works/{doi}"
    data = url_get_json(url)
    if data is None:
        return {"status": "unknown", "source": "crossref", "retraction_date": None, "retraction_reason": None}

    message = data.get("message", {})
    update_types = message.get("update-type", [])
    update_labels = message.get("update-label", [])

    for ut, ul in zip(update_types, update_labels):
        if "retraction" in ut.lower() or "retraction" in ul.lower():
            date = message.get("update-to", [{}])[0].get("update-date", {}).get("date-parts", [[None]])
            return {
                "status": "retracted",
                "source": "crossref",
                "retraction_date": str(date[0][0]) if date and date[0][0] else None,
                "retraction_reason": ul,
            }

    is_retracted = message.get("is-retracted", False)
    if is_retracted:
        return {
            "status": "retracted",
            "source": "crossref",
            "retraction_date": None,
            "retraction_reason": "CrossRef is-retracted flag",
        }

    return {"status": "clear", "source": "crossref", "retraction_date": None, "retraction_reason": None}


def pass3_retraction(doi: str) -> dict:
    """Run Pass 3: retraction check."""
    return check_crossref_retraction(doi)


# ── Bibliography Parsing ─────────────────────────────────────────────────

def parse_bibtex(path: Path) -> list[dict]:
    """Parse a BibTeX file and extract citations."""
    citations = []
    try:
        content = path.read_text()
    except FileNotFoundError:
        return citations

    entries = re.split(r"@(?:article|inproceedings|book|misc|techreport|conference)\{", content)
    for entry in entries[1:]:
        lines = entry.strip().split("\n")
        citation_key = lines[0].strip().rstrip(",") if lines else ""
        doi = ""
        title = ""
        year = ""
        author = ""
        arxiv_id = ""
        pubmed_id = ""

        for line in lines[1:]:
            line = line.strip().rstrip(",")
            if line.lower().startswith("doi"):
                doi = line.split("=", 1)[-1].strip().strip("{}\"'")
            elif line.lower().startswith("title"):
                title = line.split("=", 1)[-1].strip().strip("{}\"'")
            elif line.lower().startswith("year"):
                year = line.split("=", 1)[-1].strip().strip("{}\"'")
            elif line.lower().startswith("author"):
                author = line.split("=", 1)[-1].strip().strip("{}\"'")
            elif line.lower().startswith("eprint"):
                arxiv_id = line.split("=", 1)[-1].strip().strip("{}\"'")
            elif line.lower().startswith("pmid"):
                pubmed_id = line.split("=", 1)[-1].strip().strip("{}\"'")

        identifier = doi or arxiv_id or pubmed_id
        identifier_type = "doi" if doi else ("arxiv" if arxiv_id else ("pubmed" if pubmed_id else "unknown"))

        citations.append({
            "key": citation_key,
            "identifier": identifier,
            "identifier_type": identifier_type,
            "title": title,
            "author": author,
            "year": year,
        })

    return citations


def parse_literature_corpus(path: Path) -> list[dict]:
    """Parse a literature corpus JSON file."""
    try:
        with open(path) as f:
            corpus = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    citations = []
    papers = corpus.get("papers", corpus) if isinstance(corpus, dict) else corpus
    if isinstance(papers, list):
        for paper in papers:
            doi = paper.get("doi", "")
            arxiv_id = paper.get("arxiv_id", paper.get("arxiv", ""))
            pubmed_id = paper.get("pmid", paper.get("pubmed_id", ""))
            identifier = doi or arxiv_id or pubmed_id
            identifier_type = "doi" if doi else ("arxiv" if arxiv_id else ("pubmed" if pubmed_id else "unknown"))
            citations.append({
                "key": paper.get("id", paper.get("citation_key", "")),
                "identifier": identifier,
                "identifier_type": identifier_type,
                "title": paper.get("title", ""),
                "author": ", ".join(paper.get("authors", [])),
                "year": paper.get("year", ""),
                "abstract": paper.get("abstract", ""),
                "claims": paper.get("claims", []),
            })
    return citations


def extract_dois_from_manuscript(path: Path) -> list[dict]:
    """Extract DOIs and citations from a manuscript markdown file."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return []

    citations = []
    doi_pattern = r"10\.\d{4,}[^\s\"'\]]+"
    dois = re.findall(doi_pattern, content)

    for doi in set(dois):
        citations.append({
            "key": f"manuscript_doi_{hashlib.md5(doi.encode()).hexdigest()[:8]}",
            "identifier": doi,
            "identifier_type": "doi",
            "title": "",
            "author": "",
            "year": "",
        })

    arxiv_pattern = r"(?:arXiv[:\s]+)?(\d{4}\.\d{4,5}(?:v\d+)?)\b"
    arxiv_ids = re.findall(arxiv_pattern, content)
    for aid in set(arxiv_ids):
        citations.append({
            "key": f"manuscript_arxiv_{hashlib.md5(aid.encode()).hexdigest()[:8]}",
            "identifier": aid,
            "identifier_type": "arxiv",
            "title": "",
            "author": "",
            "year": "",
        })

    return citations


# ── Main Verification Pipeline ───────────────────────────────────────────

def verify_citation(citation: dict, delay: float = 0.5) -> dict:
    """Run all three passes on a single citation."""
    identifier = citation.get("identifier", "")
    identifier_type = citation.get("identifier_type", "unknown")
    citation_label = f"{citation.get('author', 'Unknown')}, {citation.get('year', 'N/A')}"
    timeout_seen = False

    if not identifier or identifier_type == "unknown":
        return {
            "citation": citation_label,
            "identifier": identifier,
            "identifier_type": identifier_type,
            "pass_1": {"status": "skipped", "error": "No valid identifier"},
            "pass_2": {"status": "skipped", "justification": "No identifier for content check"},
            "pass_3": {"status": "unknown", "source": "none", "retraction_date": None, "retraction_reason": None},
            "overall_status": "unverified",
        }

    time.sleep(delay)

    # Pass 1
    try:
        pass1_result = pass1_existence(identifier, identifier_type)
    except APITimeoutError as exc:
        timeout_seen = True
        pass1_result = {**_api_timeout_result(identifier_type.title()), "error": str(exc)}
    pass1_result["claimed_title"] = citation.get("title", "")
    pass1_result["claimed_year"] = citation.get("year", "")

    if pass1_result.get("title") and citation.get("title"):
        pass1_result["title_match"] = _fuzzy_match(pass1_result["title"], citation["title"])
    else:
        pass1_result["title_match"] = None

    if pass1_result.get("year") and citation.get("year"):
        try:
            pass1_result["year_match"] = str(pass1_result["year"]) == str(citation["year"])
        except (ValueError, TypeError):
            pass1_result["year_match"] = None
    else:
        pass1_result["year_match"] = None

    # Pass 2
    abstract = None
    if pass1_result["status"] == "verified":
        try:
            abstract = fetch_semantic_scholar_abstract(identifier, identifier_type)
            claims = citation.get("claims", [])
            claim_text = " ".join(claims) if claims else citation.get("title", "")
            pass2_result = pass2_content(abstract, claim_text)
        except APITimeoutError as exc:
            timeout_seen = True
            pass2_result = {**_api_timeout_result("Semantic Scholar"), "justification": str(exc)}
    else:
        pass2_result = {"status": "skipped", "justification": "Pass 1 failed, skipping content check"}

    # Pass 3
    if identifier_type == "doi":
        try:
            pass3_result = pass3_retraction(identifier)
        except APITimeoutError as exc:
            timeout_seen = True
            pass3_result = {**_api_timeout_result("CrossRef retraction"), "retraction_reason": str(exc)}
    else:
        pass3_result = {"status": "unknown", "source": "none", "retraction_date": None, "retraction_reason": None}

    # Overall status
    if pass3_result["status"] == "retracted":
        overall = "retracted"
    elif pass1_result["status"] == "verified" and pass2_result.get("status") in ("supported",) and pass3_result["status"] == "clear":
        overall = "verified"
    elif pass1_result["status"] == "verified" and pass2_result.get("status") == "partial":
        overall = "partial"
    elif pass1_result["status"] == "verified":
        overall = "verified"
    else:
        overall = "unverified"

    if timeout_seen:
        citation_label = _timeout_tagged_citation(citation)

    return {
        "citation": citation_label,
        "identifier": identifier,
        "identifier_type": identifier_type,
        "pass_1": pass1_result,
        "pass_2": pass2_result,
        "pass_3": pass3_result,
        "overall_status": overall,
    }


def _fuzzy_match(title1: str, title2: str, threshold: float = 0.7) -> bool:
    """Simple fuzzy match between two titles."""
    t1 = set(re.findall(r"\w+", title1.lower()))
    t2 = set(re.findall(r"\w+", title2.lower()))
    if not t1 or not t2:
        return False
    return len(t1 & t2) / len(t1 | t2) >= threshold


def run_verification(citations: list[dict], output_path: Path, delay: float = 0.5) -> dict:
    """Run full three-pass verification on a list of citations."""
    results = []
    for i, citation in enumerate(citations):
        print(f"  [{i+1}/{len(citations)}] Verifying: {citation.get('key', citation.get('identifier', 'unknown'))}")
        result = verify_citation(citation, delay=delay)
        results.append(result)

    summary = {
        "fully_verified": sum(1 for r in results if r["overall_status"] == "verified"),
        "unverified": sum(1 for r in results if r["overall_status"] == "unverified"),
        "retracted": sum(1 for r in results if r["overall_status"] == "retracted"),
        "partial_match": sum(1 for r in results if r["overall_status"] == "partial"),
        "not_found": sum(1 for r in results if r["overall_status"] == "unverified" and r["pass_1"].get("status") == "not_found"),
    }

    total = len(results)
    if summary["retracted"] > 0:
        verdict = "FAIL"
    elif summary["unverified"] > total * 0.1:
        verdict = "FAIL"
    elif summary["partial_match"] > 0 or summary["unverified"] > 0:
        verdict = "CONDITIONAL"
    else:
        verdict = "PASS"

    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_citations": total,
        "summary": summary,
        "verdict": verdict,
        "citations": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    return report


def print_report_summary(report: dict) -> None:
    """Print a human-readable summary of the verification report."""
    print()
    print("=" * 60)
    print("CITATION VERIFICATION REPORT")
    print("=" * 60)
    print()
    print(f"  Total citations: {report['total_citations']}")
    print(f"  Verdict: {report['verdict']}")
    print()
    summary = report["summary"]
    print(f"  Fully verified: {summary['fully_verified']}")
    print(f"  Partial match:  {summary['partial_match']}")
    print(f"  Unverified:     {summary['unverified']}")
    print(f"  Retracted:      {summary['retracted']}")
    print(f"  Not found:      {summary['not_found']}")
    print()

    for citation in report["citations"]:
        status_icon = {
            "verified": "✓",
            "unverified": "✗",
            "retracted": "⚠ RETRACTED",
            "partial": "?",
        }.get(citation["overall_status"], "?")
        print(f"  {status_icon} {citation['citation']}")
        print(f"    ID: {citation['identifier']} ({citation['identifier_type']})")
        p1 = citation["pass_1"]
        print(f"    Pass 1 (existence): {p1['status']}")
        p2 = citation["pass_2"]
        print(f"    Pass 2 (content):   {p2['status']}")
        p3 = citation["pass_3"]
        print(f"    Pass 3 (retraction):{p3['status']}")
        print()


def replace_with_verified(citation: dict) -> dict:
    """Run verification and fetch canonical BibTeX."""
    res = verify_citation(citation)
    status = res["overall_status"]
    identifier = citation.get("identifier")
    
    if status == "retracted":
        raise CitationRetractedError(f"Citation retracted: {res['pass_3'].get('retraction_reason')}", identifier)
    
    id_type = citation.get("identifier_type")
    bibtex = ""
    if id_type == "doi" and status not in ("unverified", "not_found"):
        bibtex = url_get(f"https://api.crossref.org/works/{identifier}/transform/application/x-bibtex")
    
    if not bibtex:
        title = res["pass_1"].get("title", citation.get("title", "Unknown Title"))
        if status in ("unverified", "not_found"):
            title = f"[UNVERIFIED] {title}"
        year = res["pass_1"].get("year", citation.get("year", "Unknown Year"))
        authors = " and ".join(res["pass_1"].get("authors", [citation.get("author", "Unknown Author")]))
        key = f"ref_{str(identifier).replace('/', '_').replace('.', '_')}" if identifier else "ref_unknown"
        bibtex = f"@article{{{key},\n  title={{{title}}},\n  author={{{authors}}},\n  year={{{year}}},\n  url={{{identifier}}}\n}}"

    return {
        "status": "replaced" if status not in ("unverified", "not_found") else "fallback",
        "bibtex": bibtex,
        "doi": identifier if id_type == "doi" else None,
        "verified_title": res["pass_1"].get("title"),
        "verified_year": res["pass_1"].get("year"),
    }

def build_verified_bibliography(citations: list[dict], output_bib: Path, delay: float = 0.5) -> dict:
    replaced = 0
    failed = 0
    retracted = 0
    bib_entries = []

    for cit in citations:
        try:
            res = replace_with_verified(cit)
            bib_entries.append(res["bibtex"])
            replaced += 1
        except CitationRetractedError:
            retracted += 1
            failed += 1
        except CitationNotFoundError:
            failed += 1
        except Exception:
            failed += 1
        time.sleep(delay)

    output_bib.parent.mkdir(parents=True, exist_ok=True)
    with open(output_bib, "w") as f:
        f.write("\n\n".join(filter(None, bib_entries)))
    
    return {
        "total": len(citations),
        "replaced": replaced,
        "failed": failed,
        "retracted": retracted,
        "bib_path": str(output_bib)
    }

# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Citation Verification Pipeline")
    parser.add_argument("--bibliography", type=str, help="Path to BibTeX bibliography file")
    parser.add_argument("--corpus", type=str, help="Path to literature corpus JSON")
    parser.add_argument("--manuscript", type=str, help="Path to manuscript markdown file")
    parser.add_argument("--output", type=str, help="Output report path (default: 00_inputs/literature/citation_verification_report.json)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls in seconds")
    args = parser.parse_args()

    root = find_project_root()
    citations = []

    if args.bibliography:
        path = Path(args.bibliography) if Path(args.bibliography).is_absolute() else root / args.bibliography
        citations.extend(parse_bibtex(path))
        print(f"Parsed {len(citations)} citations from BibTeX")

    if args.corpus:
        path = Path(args.corpus) if Path(args.corpus).is_absolute() else root / args.corpus
        corpus_citations = parse_literature_corpus(path)
        citations.extend(corpus_citations)
        print(f"Parsed {len(corpus_citations)} citations from corpus (total: {len(citations)})")

    if args.manuscript:
        path = Path(args.manuscript) if Path(args.manuscript).is_absolute() else root / args.manuscript
        manuscript_citations = extract_dois_from_manuscript(path)
        citations.extend(manuscript_citations)
        print(f"Extracted {len(manuscript_citations)} citations from manuscript (total: {len(citations)})")

    if not citations:
        print("ERROR: No citations found. Provide --bibliography, --corpus, or --manuscript")
        sys.exit(1)

    output_path = Path(args.output) if args.output else root / "00_inputs" / "literature" / "citation_verification_report.json"
    if not output_path.is_absolute():
        output_path = root / output_path

    print(f"\nVerifying {len(citations)} citations...")
    report = run_verification(citations, output_path, delay=args.delay)
    print_report_summary(report)
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
