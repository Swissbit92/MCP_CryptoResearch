# packages/mcp_strategy_research/mcp_strategy_research/fetcher.py
from typing import Any, Dict
import time, urllib.parse, urllib.robotparser, requests, fitz
from bs4 import BeautifulSoup
import os

UA = os.getenv("RESEARCH_USER_AGENT", "StrategyResearchMCP/0.1 (+contact)")
_MIN_INTERVAL = 0.6  # ~1–2 req/s global

_last_ts = 0.0
_rp_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

def _throttle():
    global _last_ts
    now = time.monotonic()
    elapsed = now - _last_ts
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_ts = time.monotonic()

def _robots_ok(url: str) -> bool:
    u = urllib.parse.urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    rp = _rp_cache.get(base)
    if rp is None:
        robots_url = urllib.parse.urljoin(base, "/robots.txt")
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.set_url(robots_url)
            rp.read()
        except Exception:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse("")  # treat as unknown → allow
        _rp_cache[base] = rp
    return rp.can_fetch(UA, url) if hasattr(rp, "can_fetch") else True

def fetch_url(url: str, render_js: bool = False) -> Dict[str, Any]:
    if not _robots_ok(url):
        raise PermissionError(f"robots.txt disallows: {url}")
    headers = {"User-Agent": UA}
    _throttle()
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type","").lower()
    text = ""
    meta: Dict[str, Any] = {"status": r.status_code, "content_type": ctype}
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            text = "\n\n".join(page.get_text("text") for page in doc)
    else:
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script","style","noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
    from .storage import write_raw_text
    uri = write_raw_text(text)
    return {"url": url, "content_type": ctype, "text": text, "meta": meta, "resource_uri": uri}
