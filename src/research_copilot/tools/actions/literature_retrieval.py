import logging
from typing import Dict, Any, List

logger = logging.getLogger("research.tools.literature_retrieval")

def search_crossref(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        from habanero import Crossref
        cr = Crossref()
        result = cr.works(query=query, limit=limit)
        items = result.get("message", {}).get("items", [])
        return [{
            "title": item.get("title", [""])[0],
            "authors": [a.get("family", "") for a in item.get("author", [])],
            "year": item.get("issued", {}).get("date-parts", [[None]])[0][0],
            "url": item.get("URL", ""),
            "doi": item.get("DOI", "")
        } for item in items]
    except Exception as e:
        logger.error(f"Crossref search failed: {e}")
        return []

def search_pubmed(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        from metapub import PubMedFetcher
        fetch = PubMedFetcher()
        pmids = fetch.pmids_for_query(query, retmax=limit)
        results = []
        for pmid in pmids:
            try:
                article = fetch.article_by_pmid(pmid)
                results.append({
                    "title": article.title,
                    "authors": article.authors,
                    "year": article.year,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "doi": article.doi
                })
            except Exception:
                continue
        return results
    except Exception as e:
        logger.error(f"PubMed search failed: {e}")
        return []

def search_arxiv(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    # Simple arxiv search via urllib
    import urllib.request
    import xml.etree.ElementTree as ET
    try:
        url = f"http://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query)}&max_results={limit}"
        response = urllib.request.urlopen(url).read()
        root = ET.fromstring(response)
        ns = {"arxiv": "http://www.w3.org/2005/Atom"}
        results = []
        for entry in root.findall("arxiv:entry", ns):
            results.append({
                "title": entry.find("arxiv:title", ns).text.strip(),
                "authors": [a.find("arxiv:name", ns).text for a in entry.findall("arxiv:author", ns)],
                "year": entry.find("arxiv:published", ns).text[:4],
                "url": entry.find("arxiv:id", ns).text,
                "doi": ""
            })
        return results
    except Exception as e:
        logger.error(f"Arxiv search failed: {e}")
        return []

def retrieve_literature(query: str, source: str = "crossref", limit: int = 5) -> Dict[str, Any]:
    """Retrieve literature from live sources."""
    results = []
    if source == "crossref":
        results = search_crossref(query, limit)
    elif source == "pubmed":
        results = search_pubmed(query, limit)
    elif source == "arxiv":
        results = search_arxiv(query, limit)
    else:
        results = search_crossref(query, limit)
        
    return {
        "status": "success",
        "source": source,
        "query": query,
        "results": results
    }
