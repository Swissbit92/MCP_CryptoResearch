# packages/mcp_strategy_research/mcp_strategy_research/server.py
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv, find_dotenv
from mcp.server.fastmcp import FastMCP

from . import brave as brave_mod
from . import fetcher as fetch_mod
from . import extractor as extractor_mod
from . import normalizer as norm_mod
from . import storage as store_mod
from . import prompts as prompts_mod

# Load .env from repo root (or nearest)
load_dotenv(find_dotenv())

APP = {"inited": False}

@asynccontextmanager
async def lifespan(server: FastMCP):
    store_mod.init_storage()  # ensure storage dirs exist
    APP["inited"] = True
    try:
        yield APP
    finally:
        APP["inited"] = False

mcp = FastMCP("Strategy Research MCP", lifespan=lifespan)

# ----------------------- TOOLS -----------------------

@mcp.tool()
def plan_queries(topic: str, indicators: List[str], max_per_indicator: int = 3, source: str = "arxiv") -> List[str]:
    return prompts_mod.plan_queries(topic, indicators, max_per_indicator, source=source)

@mcp.tool()
def brave_search(query: str, max_results: int = 10, site: str = "arxiv.org") -> List[Dict[str, str]]:
    return brave_mod.search(query=query, max_results=max_results, site=site)

# NEW: clean arXiv-only tool
@mcp.tool()
def arxiv_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    return brave_mod.arxiv_search(query=query, max_results=max_results)

# NEW: SSRN allowlisted search (Brave-backed)
@mcp.tool()
def ssrn_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    return brave_mod.ssrn_search(query=query, max_results=max_results)

# NEW: IDEAS/RePEc allowlisted search (Brave-backed)
@mcp.tool()
def ideas_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    return brave_mod.ideas_search(query=query, max_results=max_results)

@mcp.tool()
def fetch_url(url: str, render_js: bool = False) -> Dict[str, Any]:
    return fetch_mod.fetch_url(url, render_js=render_js)

@mcp.tool()
def extract_strategies(text: str, indicators: Optional[List[str]] = None, llm_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    return extractor_mod.extract_strategies(text=text, indicators=indicators or [], llm_hint=llm_hint)

@mcp.tool()
def normalize_strategy(doc: Dict[str, Any], source_url: str, indicators: Optional[List[str]] = None) -> Dict[str, Any]:
    return norm_mod.normalize_strategy(doc, source_url, indicators or [])

@mcp.tool()
def bundle_results(strategy_resource_uris: List[str]) -> Dict[str, Any]:
    return store_mod.bundle_results(strategy_resource_uris)

# --------------------- RESOURCES ---------------------

@mcp.resource("research://raw/{sha1}.txt")
def raw_resource(sha1: str) -> Dict[str, Any]:
    return store_mod.read_resource(kind="raw", key=f"{sha1}.txt")

@mcp.resource("research://normalized/{key}.json")
def normalized_resource(key: str) -> Dict[str, Any]:
    return store_mod.read_resource(kind="normalized", key=f"{key}.json")

@mcp.resource("research://results/{key}.json")
def results_resource(key: str) -> Dict[str, Any]:
    return store_mod.read_resource(kind="results", key=f"{key}.json")

# ---------------------- PROMPTS ----------------------

@mcp.prompt()
def strategy_extraction_guidelines() -> str:
    return prompts_mod.strategy_extraction_guidelines_placeholder()

# ----------------------- ENTRY -----------------------

def main():
    mcp.run()

if __name__ == "__main__":
    main()
