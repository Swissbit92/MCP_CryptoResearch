# mcp-farm/packages/mcp_kg/mcp_kg/mappers/whitepaper_to_jsonld.py
from __future__ import annotations
import re, orjson
from typing import Dict, Any, List

def _whitepaper_iri(key: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", key.strip()).strip("-").lower()
    return f"kg://whitepaper/{slug}"

def _token_iri(symbol: str) -> str:
    sym = symbol.upper().strip().replace(":", "_").replace("/", "_")
    return f"kg://token/{sym}"

def _agent_iri(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()
    return f"kg://agent/{slug}"

def load_context(context_path: str) -> Dict[str, Any]:
    with open(context_path, "r", encoding="utf-8") as f:
        return orjson.loads(f.read())

def map_whitepaper_to_jsonld(wp: Dict[str, Any], context_path: str) -> List[Dict[str, Any]]:
    """
    Expected input (flexible):
      {
        "key": "bitcoin-whitepaper",    # for @id (fallback: title/url/doi)
        "title": "Bitcoin: A Peer-to-Peer Electronic Cash System",
        "url": "https://bitcoin.org/bitcoin.pdf",
        "doi": null,
        "published_on": "2008-10-31",
        "token": {"symbol":"BTC","name":"Bitcoin"},
        "authors": ["Satoshi Nakamoto"],
        "citations": ["https://link/to/ref1", "10.1234/xyz"],
        "conformsTo": ["bibo", "schema"]
      }
    """
    ctx = load_context(context_path)["@context"]
    key = wp.get("key") or wp.get("title") or wp.get("url") or wp.get("doi") or "whitepaper"
    wid = _whitepaper_iri(str(key))
    title = wp.get("title") or key

    # Whitepaper node
    wnode = {
        "@context": ctx,
        "@id": wid,
        "@type": "Whitepaper",
        "name": title
    }
    if wp.get("url"): wnode["url"] = wp["url"]
    if wp.get("doi"): wnode["doi"] = wp["doi"]
    if wp.get("published_on"): wnode["publishedOn"] = wp["published_on"]

    # Token node + link
    nodes: List[Dict[str, Any]] = [wnode]
    token = wp.get("token") or {}
    if token.get("symbol"):
        t_sym = token["symbol"].upper()
        t_id = _token_iri(t_sym)
        tnode = {
            "@context": ctx,
            "@id": t_id,
            "@type": "Token",
            "symbol": t_sym,
            "name": token.get("name", t_sym)
        }
        nodes.append(tnode)
        wnode["describesToken"] = {"@id": t_id}

    # Authors → Agent nodes + authoredBy
    agents = []
    for a in wp.get("authors", []) or []:
        a = str(a).strip()
        if not a: continue
        aid = _agent_iri(a)
        anode = {"@context": ctx, "@id": aid, "@type": "Agent", "name": a}
        nodes.append(anode)
        agents.append({"@id": aid})
    if agents:
        wnode["authoredBy"] = agents

    # Citations
    cites = []
    for c in wp.get("citations", []) or []:
        c = str(c).strip()
        if not c: continue
        if "://" in c:
            cites.append({"@id": f"kg://doc/{re.sub(r'[^a-zA-Z0-9]+', '-', c)}", "@type":"Document", "url": c, "@context": ctx})
        else:
            cites.append({"@id": f"kg://doc/{re.sub(r'[^a-zA-Z0-9]+', '-', c)}", "@type":"Document", "doi": c, "@context": ctx})
    for d in cites:
        nodes.append(d)
    if cites:
        wnode["cites"] = [{"@id": d["@id"]} for d in cites]

    return nodes
