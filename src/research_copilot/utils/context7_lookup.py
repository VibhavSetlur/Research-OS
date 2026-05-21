#!/usr/bin/env python3
"""Skill Documentation Lookup — BM25-powered local search.

When an agent requests documentation for a topic (e.g. "how to do a t-test"),
this module:
  1. Builds (or loads from cache) a BM25 index over every .md file under
     src/research_copilot/assets/skills/.
  2. Scores all skill files against the query.
  3. Returns the single best-matching file's content, capped at 2 000 characters,
     keeping token usage well under budget.

The cache is stored as a JSON sidecar next to the skill index so the BM25
corpus is only rebuilt when skill files change.
"""

import sys
import json
import re
import argparse
import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("research.context7_lookup")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _skills_dir() -> Path:
    """Return the canonical skills directory from the installed package."""
    here = Path(__file__).parent
    # Installed layout: src/research_copilot/utils/ → assets/skills/
    candidate = here.parent / "assets" / "skills"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Skills directory not found: {candidate}")


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()


def _corpus_fingerprint(skills_dir: Path) -> str:
    """MD5 of all skill file mtimes — cheap staleness check."""
    md5 = hashlib.md5()
    for md_file in sorted(skills_dir.rglob("*.md")):
        md5.update(str(md_file.stat().st_mtime).encode())
    return md5.hexdigest()


def _build_bm25_index(skills_dir: Path) -> tuple[list[dict], object]:
    """Parse all skill .md files and return (corpus_meta, BM25Okapi)."""
    try:
        from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "rank-bm25 is required: pip install rank-bm25"
        ) from exc

    corpus_meta: list[dict] = []
    tokenized_corpus: list[list[str]] = []

    for md_file in sorted(skills_dir.rglob("*.md")):
        if md_file.name in ("SKILL_TEMPLATE.md",):
            continue
        text = md_file.read_text(errors="replace")
        tokens = _tokenize(text)
        corpus_meta.append({"path": str(md_file), "title": md_file.stem})
        tokenized_corpus.append(tokens)

    if not tokenized_corpus:
        raise RuntimeError(f"No skill files found under {skills_dir}")

    return corpus_meta, BM25Okapi(tokenized_corpus)


# Module-level lazy singletons so the index is only built once per process.
_INDEX_META: Optional[list[dict]] = None
_BM25: Optional[object] = None
_INDEX_FINGERPRINT: Optional[str] = None


def _get_index(skills_dir: Path):
    """Return (corpus_meta, BM25Okapi), rebuilding only when files change."""
    global _INDEX_META, _BM25, _INDEX_FINGERPRINT

    fp = _corpus_fingerprint(skills_dir)
    if _BM25 is None or fp != _INDEX_FINGERPRINT:
        logger.debug("Building BM25 skill index from %s", skills_dir)
        _INDEX_META, _BM25 = _build_bm25_index(skills_dir)
        _INDEX_FINGERPRINT = fp

    return _INDEX_META, _BM25


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

MAX_DOC_CHARS = 2_000  # keep token usage under ~500 tokens


def search_skills(query: str, top_k: int = 1) -> list[dict]:
    """Return the top-k most relevant skill files for *query*.

    Each result is a dict with keys:
        path  — absolute path to the .md file
        title — file stem
        score — BM25 relevance score
        content — file text, truncated to MAX_DOC_CHARS
    """
    skills_dir = _skills_dir()
    corpus_meta, bm25 = _get_index(skills_dir)

    tokens = _tokenize(query)
    scores = bm25.get_scores(tokens)

    # Pair scores with metadata and sort descending.
    ranked = sorted(
        zip(scores, corpus_meta), key=lambda t: t[0], reverse=True
    )

    results = []
    for score, meta in ranked[:top_k]:
        path = Path(meta["path"])
        try:
            content = path.read_text(errors="replace")[:MAX_DOC_CHARS]
        except OSError:
            content = ""
        results.append({
            "path": str(path),
            "title": meta["title"],
            "score": float(score),
            "content": content,
        })
    return results


def resolve_library_id(library_name: str, cache=None) -> str:  # noqa: ANN001
    """Resolve a library name to a pseudo-ID using BM25 skill lookup.

    Falls back gracefully if no relevant skill is found.
    """
    results = search_skills(library_name, top_k=1)
    if results and results[0]["score"] > 0:
        return f"skill:{results[0]['title']}"
    return f"lib_{library_name.strip().lower()}_generic"


def get_library_docs(library_id: str, topic: str, cache=None) -> str:  # noqa: ANN001
    """Retrieve skill documentation for a resolved library/topic query.

    Performs a combined BM25 search on "library_id topic" and returns the
    best matching skill content, capped at MAX_DOC_CHARS characters.
    """
    query = f"{library_id} {topic}"
    results = search_skills(query, top_k=1)
    if results and results[0]["score"] > 0:
        return results[0]["content"]
    return (
        f"No local skill documentation found for '{topic}' in '{library_id}'.\n"
        "Refer to the official library documentation online."
    )


# ---------------------------------------------------------------------------
# CLI entry point (unchanged interface)
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local BM25 Skill Documentation Lookup"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_p = subparsers.add_parser("resolve", help="Resolve library name to skill ID")
    resolve_p.add_argument("library", help="Library/topic name (e.g. pandas, t-test)")

    docs_p = subparsers.add_parser("docs", help="Retrieve documentation for a skill ID")
    docs_p.add_argument("library_id", help="Resolved skill ID")
    docs_p.add_argument("topic", help="Topic or function to look up")

    args = parser.parse_args()

    if args.command == "resolve":
        print(resolve_library_id(args.library))
        sys.exit(0)
    elif args.command == "docs":
        print(get_library_docs(args.library_id, args.topic))
        sys.exit(0)


if __name__ == "__main__":
    main()
