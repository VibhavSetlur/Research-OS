from typing import Dict, Any
from research_os.tools.actions.literature_retrieval import retrieve_literature

def search_semantic_scholar(query: str, limit: int = 5) -> Dict[str, Any]:
    # Placeholder using the same literature retrieval
    return retrieve_literature(query, source="pubmed", limit=limit) # Fallback to crossref/pubmed logic

def search_crossref(query: str, limit: int = 5) -> Dict[str, Any]:
    return retrieve_literature(query, source="crossref", limit=limit)

def search_pubmed(query: str, limit: int = 5) -> Dict[str, Any]:
    return retrieve_literature(query, source="pubmed", limit=limit)
