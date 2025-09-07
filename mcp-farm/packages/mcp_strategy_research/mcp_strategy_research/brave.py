# packages/mcp_strategy_research/mcp_strategy_research/brave.py
from typing import Dict, List
import os, requests, xml.etree.ElementTree as ET

BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
ARXIV_API = "http://export.arxiv.org/api/query"


def _arxiv_api_search(q: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Direct arXiv Atom API search. Returns [{title, url, snippet}]
    """
    params = {
        "search_query": f"all:{q}",
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    resp = requests.get(ARXIV_API, params=params, timeout=20)
    resp.raise_for_status()
    out: List[Dict[str, str]] = []
    root = ET.fromstring(resp.text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip().replace("\n", " ")
        url = ""
        for link in entry.findall("a:link", ns):
            href = link.attrib.get("href", "")
            if href and "arxiv.org/abs/" in href:
                url = href
                break
        if not url:
            # fallback to <id>
            url = entry.findtext("a:id", default="", namespaces=ns) or ""
        if title and url:
            out.append({"title": title, "url": url, "snippet": summary})
    return out


def _brave_search(q: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Brave Web Search (JSON). Returns [{title, url, snippet}]
    """
    key = os.getenv("BRAVE_API_KEY", "").strip()
    if not key:
        # graceful no-key fallback
        return []
    headers = {"X-Subscription-Token": key, "Accept": "application/json"}
    params = {"q": q, "count": max_results}
    r = requests.get(BRAVE_API, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    js = r.json()
    out: List[Dict[str, str]] = []
    for it in js.get("web", {}).get("results", []):
        out.append(
            {
                "title": it.get("title", ""),
                "url": it.get("url", ""),
                "snippet": it.get("description", ""),
            }
        )
    return out


def search(query: str, max_results: int = 10, site: str = "arxiv.org") -> List[Dict[str, str]]:
    """
    Existing tool impl: keeps arXiv fast-path, otherwise uses Brave.
    """
    q = query
    if site:
        q = f"{query} site:{site}"
    if site and "arxiv" in site.lower():
        res = _arxiv_api_search(query, max_results=max_results)
        if res:
            return res
        return _brave_search(q, max_results=max_results)
    return _brave_search(q, max_results=max_results)


# ---- New clean arXiv-only tool wrapper ----
def arxiv_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Exposed as its own MCP tool for clarity:
    - Always uses the arXiv API directly
    - No Brave dependency
    """
    return _arxiv_api_search(query, max_results=max_results)


# ---- NEW: Domain-allowlisted helpers for SSRN & IDEAS ----
def _domain_search(query: str, domains: List[str], max_results: int = 10) -> List[Dict[str, str]]:
    """
    Brave-backed domain-allowlisted search. Returns [{title, url, snippet}].
    Gracefully returns [] if no BRAVE_API_KEY is present.
    """
    if not domains:
        return []
    site_clause = " OR ".join(f"site:{d}" for d in domains)
    q = f"{query} ({site_clause})"
    return _brave_search(q, max_results=max_results)


def ssrn_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    SSRN allowlisted search via Brave. Same shape as arxiv_search().
    Typical hosts: ssrn.com, papers.ssrn.com
    """
    return _domain_search(query, ["ssrn.com", "papers.ssrn.com"], max_results=max_results)


def ideas_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    IDEAS/RePEc allowlisted search via Brave. Same shape as arxiv_search().
    Canonical host: ideas.repec.org
    """
    return _domain_search(query, ["ideas.repec.org"], max_results=max_results)
