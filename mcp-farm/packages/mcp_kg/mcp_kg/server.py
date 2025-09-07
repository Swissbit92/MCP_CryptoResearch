# mcp-farm/packages/mcp_kg/mcp_kg/server.py
from __future__ import annotations
import os, json, orjson
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from mcp import FastMCP
from .kg_store import KGStore, KGConfig
from .mappers.strategy_to_jsonld import map_strategy_v1_to_jsonld
from .mappers.whitepaper_to_jsonld import map_whitepaper_to_jsonld
from .validators.shacl import run_shacl_jsonld

load_dotenv()
app = FastMCP("kg")

def _read_text(p: str) -> str:
    with open(p, "r", encoding="utf-8") as f:
        return f.read()

def _load_json(p: str) -> Dict[str, Any]:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def _resolve_uri_to_path(uri: str) -> str:
    # Strategy pipeline uses research://normalized/*.json
    # Whitepapers can be anywhere; we allow direct file path URIs.
    if uri.startswith("research://"):
        rel = uri.replace("research://", "")
        candidates = [
            rel,
            os.path.join("packages", "mcp_strategy_research", rel),
            os.path.join(rel),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        raise FileNotFoundError(f"Cannot resolve {uri} to a local path: tried {candidates}")
    if os.path.exists(uri):
        return uri
    raise FileNotFoundError(uri)

@app.tool()
def kg_upsert_strategy(normalized_uri: str) -> Dict[str, Any]:
    cfg = KGConfig(); store = KGStore(cfg)
    shapes_ttl = _read_text(cfg.shapes_path)
    path = _resolve_uri_to_path(normalized_uri)
    normalized = _load_json(path)
    jd = map_strategy_v1_to_jsonld(normalized, cfg.context_path)
    jd_str = orjson.dumps(jd).decode("utf-8")
    conforms, report = run_shacl_jsonld(jd_str, shapes_ttl)
    if not conforms:
        return {"ok": False, "error": "SHACL validation failed", "report": report}
    store.insert_jsonld(jd_str)
    sig = normalized.get("signature") or normalized.get("id") or "unknown"
    return {"ok": True, "uri": f"kg://strategy/{sig}"}

@app.tool()
def kg_upsert_whitepaper(whitepaper_uri: str) -> Dict[str, Any]:
    """
    Upsert a whitepaper JSON describing fields like:
    {
      "key": "...", "title": "...", "url": "...", "doi": "...",
      "published_on": "YYYY-MM-DD",
      "token": {"symbol":"BTC","name":"Bitcoin"},
      "authors": ["Satoshi Nakamoto"],
      "citations": ["https://...", "10.1234/xyz"]
    }
    """
    cfg = KGConfig(); store = KGStore(cfg)
    shapes_ttl = _read_text(cfg.shapes_path)
    path = _resolve_uri_to_path(whitepaper_uri)
    wj = _load_json(path)
    jd = map_whitepaper_to_jsonld(wj, cfg.context_path)
    jd_str = orjson.dumps(jd).decode("utf-8")
    conforms, report = run_shacl_jsonld(jd_str, shapes_ttl)
    if not conforms:
        return {"ok": False, "error": "SHACL validation failed", "report": report}
    store.insert_jsonld(jd_str)
    # Return the Whitepaper @id
    wid = [n["@id"] for n in jd if n.get("@type") == "Whitepaper"]
    return {"ok": True, "uri": wid[0] if wid else None}

@app.tool()
def kg_search(indicators: List[str], timeframe: Optional[str]=None, universe: Optional[List[str]]=None, limit: int=50) -> Dict[str, Any]:
    cfg = KGConfig(); store = KGStore(cfg)
    res = store.search_strategies(indicators, timeframe, universe, limit)
    return {"ok": True, "results": res}

@app.tool()
def kg_get_strategy_by_signature(signature: str) -> Dict[str, Any]:
    cfg = KGConfig(); store = KGStore(cfg)
    data = store.get_strategy_by_signature(signature)
    if not data:
        return {"ok": False, "error": "Not found or backend unsupported"}
    return {"ok": True, "data": json.loads(data)}

@app.tool()
def kg_validate(resource_uri: str) -> Dict[str, Any]:
    cfg = KGConfig()
    path = _resolve_uri_to_path(resource_uri)
    data = _load_json(path)
    # Heuristic: if it has 'indicators' treat as strategy; if it has 'token' treat as whitepaper
    if "indicators" in data or "entry_rules" in data or "exit_rules" in data:
        jd = map_strategy_v1_to_jsonld(data, cfg.context_path)
    else:
        jd = map_whitepaper_to_jsonld(data, cfg.context_path)
    jd_str = orjson.dumps(jd).decode("utf-8")
    shapes_ttl = _read_text(cfg.shapes_path)
    conforms, report = run_shacl_jsonld(jd_str, shapes_ttl)
    return {"ok": True, "conforms": conforms, "report": report}

@app.tool()
def kg_query_graphql(query: str) -> Dict[str, Any]:
    from .graphql import graphql_query
    return graphql_query(query)

def main():
    app.run()

if __name__ == "__main__":
    main()
