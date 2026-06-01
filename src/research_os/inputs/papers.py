"""Auto-download papers from URLs / DOIs / arxiv IDs into ``inputs/literature/``.

Handles the formats researchers actually paste:

* ``2401.12345`` (arxiv ID)
* ``https://arxiv.org/abs/2401.12345``
* ``https://arxiv.org/pdf/2401.12345.pdf``
* ``arxiv:2401.12345``
* ``10.1234/foo.bar`` (DOI)
* ``https://doi.org/10.1234/foo.bar``
* Any other URL pointing at a PDF (we follow redirects + accept on
  ``Content-Type: application/pdf`` or ``.pdf`` suffix)

Returns a structured ``DownloadResult`` per URL — the wizard prints a
table and the researcher gets immediate feedback on what worked, what
didn't, and what they need to download manually.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

_ARXIV_ID_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
_ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?", re.IGNORECASE
)
_DOI_RE = re.compile(r"^(10\.\d{4,9}/[\-._;()/:A-Z0-9]+)$", re.IGNORECASE)
_DOI_URL_RE = re.compile(
    r"(?:doi\.org|dx\.doi\.org)/(10\.\d{4,9}/[\-._;()/:A-Z0-9]+)", re.IGNORECASE
)


def classify(token: str) -> tuple[str, str]:
    """Classify a single paste token. Returns ``(kind, normalised_id)``.

    Kinds: ``arxiv``, ``doi``, ``pdf_url``, ``url``, ``unknown``.
    """
    token = token.strip().rstrip("/")
    if not token:
        return ("unknown", "")
    # Arxiv ID, bare or arxiv:-prefixed.
    if token.lower().startswith("arxiv:"):
        token = token[len("arxiv:"):]
    m = _ARXIV_ID_RE.match(token)
    if m:
        return ("arxiv", m.group(1))
    m = _ARXIV_URL_RE.search(token)
    if m:
        return ("arxiv", m.group(1))
    # DOI, bare or URL.
    if token.lower().startswith("doi:"):
        token = token[len("doi:"):]
    m = _DOI_RE.match(token)
    if m:
        return ("doi", m.group(1))
    m = _DOI_URL_RE.search(token)
    if m:
        return ("doi", m.group(1))
    # Generic URL — guess PDF by suffix.
    if token.startswith(("http://", "https://")):
        path = urlparse(token).path.lower()
        if path.endswith(".pdf"):
            return ("pdf_url", token)
        return ("url", token)
    return ("unknown", token)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class DownloadResult:
    token: str
    kind: str
    ok: bool
    path: Path | None = None
    bytes_written: int = 0
    error: str = ""
    manual_url: str = ""   # Suggested URL when auto-download failed.


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

_UA = "research-os/1.0 (+https://github.com/VibhavSetlur/Research-OS)"
_TIMEOUT = 30


def _safe_filename(stem: str, suffix: str = ".pdf") -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[:80].strip("_") or "paper"
    if not stem.endswith(suffix):
        stem += suffix
    return stem


def _download(url: str, dest_dir: Path, stem: str) -> DownloadResult:
    """Stream a URL into ``dest_dir`` with a safe filename. Returns a
    structured result; never raises."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = _safe_filename(stem)
    target = dest_dir / fname
    if target.exists() and target.stat().st_size > 0:
        return DownloadResult(token=url, kind="reused", ok=True, path=target,
                              bytes_written=target.stat().st_size)
    try:
        with requests.get(url, stream=True, timeout=_TIMEOUT,
                          allow_redirects=True,
                          headers={"User-Agent": _UA, "Accept": "application/pdf,*/*"}) as r:
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "").lower()
            if "application/pdf" not in ctype and not url.lower().endswith(".pdf"):
                # Not a PDF — bail rather than save HTML.
                return DownloadResult(
                    token=url, kind="not_pdf", ok=False,
                    error=f"server returned {ctype or 'unknown content-type'}",
                    manual_url=url,
                )
            total = 0
            with open(target, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            return DownloadResult(token=url, kind="downloaded", ok=True,
                                  path=target, bytes_written=total)
    except requests.RequestException as e:
        return DownloadResult(token=url, kind="error", ok=False,
                              error=f"{type(e).__name__}: {e}", manual_url=url)
    except OSError as e:
        return DownloadResult(token=url, kind="error", ok=False,
                              error=f"write failed: {e}")


# ---------------------------------------------------------------------------
# Per-source resolvers
# ---------------------------------------------------------------------------


def _resolve_arxiv(arxiv_id: str, dest: Path) -> DownloadResult:
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    res = _download(url, dest, stem=f"arxiv_{arxiv_id}")
    res.token = arxiv_id
    res.kind = "arxiv_ok" if res.ok else f"arxiv_{res.kind}"
    if not res.ok and not res.manual_url:
        res.manual_url = f"https://arxiv.org/abs/{arxiv_id}"
    return res


def _resolve_doi(doi: str, dest: Path) -> DownloadResult:
    """Try Unpaywall first (open-access) then fall back to doi.org redirect.

    Unpaywall (https://api.unpaywall.org) returns the best OA PDF for a DOI.
    We hit it with a generic contact email to avoid rate-limit penalties
    (per their docs); failure is silent — we just fall through to telling
    the user to download manually.
    """
    unpaywall = f"https://api.unpaywall.org/v2/{doi}?email=research-os@anthropic.com"
    try:
        r = requests.get(unpaywall, timeout=10, headers={"User-Agent": _UA})
        if r.ok:
            data = r.json()
            best = (data.get("best_oa_location") or {})
            pdf_url = best.get("url_for_pdf")
            if pdf_url:
                stem = f"doi_{doi.replace('/', '_')}"
                res = _download(pdf_url, dest, stem=stem)
                res.token = doi
                res.kind = "doi_oa_ok" if res.ok else f"doi_oa_{res.kind}"
                if not res.ok and not res.manual_url:
                    res.manual_url = f"https://doi.org/{doi}"
                return res
    except (requests.RequestException, ValueError):
        pass
    # No OA copy — tell the user.
    return DownloadResult(
        token=doi, kind="doi_no_oa", ok=False,
        error="no open-access PDF found",
        manual_url=f"https://doi.org/{doi}",
    )


def _resolve_pdf_url(url: str, dest: Path) -> DownloadResult:
    stem = Path(urlparse(url).path).stem or "paper"
    res = _download(url, dest, stem=stem)
    res.token = url
    res.kind = "pdf_ok" if res.ok else f"pdf_{res.kind}"
    return res


def _resolve_url(url: str, dest: Path) -> DownloadResult:
    """Generic URL — try downloading; bail with manual link if not a PDF."""
    res = _resolve_pdf_url(url, dest)
    res.kind = res.kind.replace("pdf_", "url_")
    if not res.ok and not res.manual_url:
        res.manual_url = url
    return res


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def fetch_one(token: str, dest: Path) -> DownloadResult:
    kind, ident = classify(token)
    if kind == "arxiv":
        return _resolve_arxiv(ident, dest)
    if kind == "doi":
        return _resolve_doi(ident, dest)
    if kind == "pdf_url":
        return _resolve_pdf_url(ident, dest)
    if kind == "url":
        return _resolve_url(ident, dest)
    return DownloadResult(token=token, kind="unknown", ok=False,
                          error="couldn't recognise this as an arxiv ID, DOI, or URL")


def fetch_many(tokens: list[str], dest: Path) -> list[DownloadResult]:
    """Fetch many in sequence. We don't parallelise — arxiv has aggressive
    rate-limit policies and the volumes here are tiny (rarely > 10)."""
    return [fetch_one(t, dest) for t in tokens if t.strip()]


def parse_tokens(blob: str) -> list[str]:
    """Split a freeform paste into individual paper tokens.

    Researchers paste in many shapes: a comma list, one-per-line, a
    bullet list, a list with extra commentary. We split on whitespace
    and commas + strip common bullet prefixes.
    """
    if not blob:
        return []
    out: list[str] = []
    for part in re.split(r"[\s,]+", blob.strip()):
        cleaned = part.strip().lstrip("•-*·>").strip()
        # Strip surrounding parens / brackets / quotes.
        cleaned = cleaned.strip("\"'()[]<>")
        if cleaned:
            out.append(cleaned)
    return out
