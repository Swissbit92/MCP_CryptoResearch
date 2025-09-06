# packages/mcp_strategy_research/mcp_strategy_research/brave.py
from typing import Dict, List
import os, urllib.parse, requests, xml.etree.ElementTree as ET

BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
ARXIV_API = "http://export.arxiv.org/api/query"

def _arxiv_api_search(q: str, max_results: int = 10) -> List[Dict[str,str]]:
    params = {
        "search_query": f"all:{q}",
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    resp = requests.get(ARXIV_API, params=params, timeout=20)
    resp.raise_for_status()
    # Parse Atom XML
    out: List[Dict[str,str]] = []
    root = ET.fromstring(resp.text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip().replace("\n"," ")
        url = ""
        for link in entry.findall("a:link", ns):
            href = link.attrib.get("href","")
            if href and "arxiv.org/abs/" in href:
                url = href
        if not url:
            idt = entry.findtext("a:id", default="", namespaces=ns) or ""
            url = idt
        if title and url:
            out.append({"title": title, "url": url, "snippet": summary})
    return out

def _brave_search(q: str, max_results: int = 10) -> List[Dict[str,str]]:
    key = os.getenv("BRAVE_API_KEY", "").strip()
    if not key:
        # graceful no-key fallback
        return []
    headers = {"X-Subscription-Token": key, "Accept": "application/json"}
    params = {"q": q, "count": max_results}
    r = requests.get(BRAVE_API, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    js = r.json()
    out: List[Dict[str,str]] = []
    for it in js.get("web", {}).get("results", []):
        out.append({"title": it.get("title",""), "url": it.get("url",""), "snippet": it.get("description","")})
    return out

def search(query: str, max_results: int = 10, site: str = "arxiv.org") -> List[Dict[str,str]]:
    q = query
    if site:
        q = f"{query} site:{site}"
    # arXiv fast-path if applicable
    if site and "arxiv" in site.lower():
        res = _arxiv_api_search(query, max_results=max_results)
        if res:
            return res
        # fallback to Brave site query
        return _brave_search(q, max_results=max_results)
    # general case
    return _brave_search(q, max_results=max_results)
