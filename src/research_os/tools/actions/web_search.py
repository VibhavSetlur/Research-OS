import logging
import json
from typing import Dict, Any, List
from research_os.config import settings

logger = logging.getLogger("research.tools.web_search")

def search_web(query: str, limit: int = 5) -> Dict[str, Any]:
    try:
        from firecrawl import FirecrawlApp
        if not settings.FIRECRAWL_API_KEY:
            logger.warning("Firecrawl API key not set, falling back to stub.")
            return {"query": query, "source": "web (stub)", "count": 0, "results": [], "warning": "Firecrawl API key not set"}

        app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
        response = app.search(query)
        results = response.get("data", [])[:limit]
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", "")
            })
        return {"query": query, "source": "web", "count": len(formatted), "results": formatted}
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return {"query": query, "source": "web", "count": 0, "results": [], "warning": str(e)}

def scrape_web(url: str) -> Dict[str, Any]:
    try:
        from firecrawl import FirecrawlApp
        if not settings.FIRECRAWL_API_KEY:
            return {"url": url, "content": "", "warning": "Firecrawl API key not set"}

        app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
        scrape_result = app.scrape_url(url, params={'formats': ['markdown']})
        return {"url": url, "content": scrape_result.get("markdown", "")}
    except Exception as e:
        logger.error(f"Web scrape failed: {e}")
        return {"url": url, "content": "", "warning": str(e)}
