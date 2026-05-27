"""Backward-compatible shim — moved into ``search.py``."""

from research_os.tools.actions.search import (  # noqa: F401
    retrieve_literature,
    search_arxiv,
    search_crossref,
    search_pubmed,
    search_semantic_scholar,
)
