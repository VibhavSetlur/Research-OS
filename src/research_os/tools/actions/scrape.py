import logging
from typing import Dict, Any

logger = logging.getLogger("research.tools.scrape")

def scrape_web(url: str) -> Dict[str, Any]:
    try:
        from bs4 import BeautifulSoup
        import requests
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text()
        
        # Break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return {"url": url, "content": text[:15000]} # Limit output length
    except Exception as e:
        logger.error(f"Web scrape failed: {e}")
        return {"url": url, "content": "", "warning": str(e)}
