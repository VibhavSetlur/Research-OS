"""Data-repository deposit adapter — Zenodo / OSF / Figshare / Dryad.

Funder data-management plans increasingly REQUIRE a persistent, citable
deposit of data + code, across every field (not domain-specific). This
adapter captures where a project deposits and the deposit metadata, so the
data_management_plan / reproducibility protocols can verify it.

Detects (filesystem-only, no network):
    * a `.zenodo.json` deposit-metadata file (Zenodo / InvenioRDM)
    * a `.osf.json` / OSF project reference
    * a DOI or URL pointing at zenodo.org / osf.io / figshare.com / datadryad.org
      in CITATION.cff, README, or inputs/ metadata

Extracts the deposit metadata + any repository DOIs found. Contributes NO
MCP tools (provenance via the core tool_adapter_extract / tool_adapters_run_all).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from research_os.adapters import AdapterRegistration, register_adapter

__version__ = "1.0.0"


# ── detection ─────────────────────────────────────────────────────────


# A repository DOI / URL. Group 1 = repository host token.
_REPO_RE = re.compile(
    r"(?i)\b(?:https?://(?:www\.)?|doi\.org/10\.\d+/)?"
    r"(zenodo\.org|zenodo|osf\.io|osf|figshare\.com|figshare|datadryad\.org|dryad)\b"
)
_METADATA_FILES = ("CITATION.cff", "README.md", "README.rst", "README.txt")
_SCAN_SUBDIRS = ("inputs", "docs")
_MAX_SCAN_BYTES = 200_000


def _deposit_files(root: Path) -> dict:
    return {
        "zenodo_json": root / ".zenodo.json",
        "osf_json": root / ".osf.json",
    }


def _metadata_texts(root: Path) -> list[tuple[Path, str]]:
    """Return (path, text) for the small set of files that name a deposit."""
    out: list[tuple[Path, str]] = []
    for name in _METADATA_FILES:
        p = root / name
        if p.is_file():
            try:
                out.append((p, p.read_text(errors="ignore")[:_MAX_SCAN_BYTES]))
            except OSError:
                continue
    for sub in _SCAN_SUBDIRS:
        d = root / sub
        if not d.is_dir():
            continue
        try:
            for p in d.glob("*.md"):
                if p.is_file():
                    try:
                        out.append((p, p.read_text(errors="ignore")[:_MAX_SCAN_BYTES]))
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def detect(root: Path) -> bool:
    df = _deposit_files(root)
    if df["zenodo_json"].is_file() or df["osf_json"].is_file():
        return True
    for _path, text in _metadata_texts(root):
        if _REPO_RE.search(text):
            return True
    return False


# ── extraction ────────────────────────────────────────────────────────


def _parse_zenodo_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    creators = data.get("creators") or []
    return {
        "title": data.get("title", ""),
        "upload_type": data.get("upload_type", ""),
        "license": data.get("license", ""),
        "n_creators": len(creators) if isinstance(creators, list) else 0,
        "keywords": (data.get("keywords") or [])[:10],
        "communities": data.get("communities", []),
        "access_right": data.get("access_right", ""),
    }


def _norm_repo(token: str) -> str:
    t = token.lower()
    if "zenodo" in t:
        return "zenodo"
    if "osf" in t:
        return "osf"
    if "figshare" in t:
        return "figshare"
    if "dryad" in t:
        return "dryad"
    return t


def extract(root: Path, step_id: str | None = None) -> dict:
    df = _deposit_files(root)
    repositories: set[str] = set()
    references: list[dict] = []
    zenodo_meta: dict = {}

    if df["zenodo_json"].is_file():
        repositories.add("zenodo")
        zenodo_meta = _parse_zenodo_json(df["zenodo_json"])
    if df["osf_json"].is_file():
        repositories.add("osf")

    seen: set[tuple[str, str]] = set()
    for path, text in _metadata_texts(root):
        for m in _REPO_RE.finditer(text):
            repo = _norm_repo(m.group(1))
            repositories.add(repo)
            key = (repo, path.name)
            if key not in seen:
                seen.add(key)
                references.append({
                    "repository": repo,
                    "found_in": str(path.relative_to(root)),
                })

    return {
        "repositories": sorted(repositories),
        "has_zenodo_json": df["zenodo_json"].is_file(),
        "has_osf_json": df["osf_json"].is_file(),
        "zenodo_metadata": zenodo_meta,
        "references": references,
    }


def describe() -> dict:
    return {
        "name": "zenodo",
        "version": __version__,
        "repositories_supported": ["zenodo", "osf", "figshare", "dryad"],
    }


# ── registration ──────────────────────────────────────────────────────


_TOOLS_MD_PATTERNS = (
    (r"(?i)zenodo", "Zenodo deposit"),
    (r"(?i)osf\.io", "OSF deposit"),
    (r"(?i)figshare", "Figshare deposit"),
    (r"(?i)dryad", "Dryad deposit"),
)


def register() -> AdapterRegistration:
    return register_adapter(
        name="zenodo",
        version=__version__,
        description="Data-repository deposit provenance (Zenodo / OSF / Figshare / Dryad).",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=_TOOLS_MD_PATTERNS,
    )
