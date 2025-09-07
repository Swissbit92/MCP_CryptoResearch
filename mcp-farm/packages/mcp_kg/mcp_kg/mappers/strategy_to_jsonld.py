# mcp-farm/packages/mcp_kg/mcp_kg/mappers/strategy_to_jsonld.py
from __future__ import annotations
import orjson
from typing import Dict, Any, List, Any as AnyType  # rename to avoid shadowing

def _strategy_iri(signature: str) -> str:
    return f"kg://strategy/{signature}"

def _doc_iri(i: int, signature: str) -> str:
    return f"kg://doc/{signature}/{i}"

def _induse_iri(i: int, signature: str) -> str:
    return f"kg://induse/{signature}/{i}"

def _rule_iri(i: int, signature: str, direction: str) -> str:
    return f"kg://rule/{signature}/{direction}/{i}"

def _token_iri(symbol: str) -> str:
    sym = symbol.upper().strip().replace(":", "_").replace("/", "_")
    return f"kg://token/{sym}"

def load_context(context_path: str) -> Dict[str, Any]:
    with open(context_path, "r", encoding="utf-8") as f:
        return orjson.loads(f.read())

def map_strategy_v1_to_jsonld(normalized: Dict[str, Any], context_path: str) -> List[Dict[str, Any]]:
    """
    Map normalized strategy.v1 JSON to JSON-LD instances, including BOTH:
      - ex:universe literals (so SPARQL search works),
      - ex:targetsToken links (token nodes).
    """
    ctx = load_context(context_path)["@context"]

    sig = normalized.get("signature") or normalized.get("id") or "unknown"
    base: Dict[str, AnyType] = {
        "@context": ctx,
        "@id": _strategy_iri(sig),
        "@type": "Strategy",
        "signature": sig,
        "name": normalized.get("name", f"Strategy {sig}"),
        "description": normalized.get("description", ""),
        "timeframe": normalized.get("timeframe", "1d"),
    }

    # universe → keep literal values (for search) AND mint Tokens for links
    universe_vals = list(normalized.get("universe", []) or [])
    if universe_vals:
        # 1) keep the original literals
        base["universe"] = universe_vals

    # sources → Documents
    docs = []
    for i, s in enumerate(normalized.get("sources", []), start=1):
        d = {"@id": _doc_iri(i, sig), "@type": "Document"}
        if isinstance(s, dict):
            if s.get("url"): d["url"] = s["url"]
            if s.get("doi"): d["doi"] = s["doi"]
        elif isinstance(s, str):
            if "://" in s: d["url"] = s
            else: d["doi"] = s
        docs.append(d)
    if docs:
        base["hasSource"] = [{"@id": d["@id"]} for d in docs]

    # indicators → IndicatorUse with params
    induse_nodes, induse_refs = [], []
    for i, ind in enumerate(normalized.get("indicators", []), start=1):
        name = ind.get("name") if isinstance(ind, dict) else str(ind)
        params = ind.get("params", {}) if isinstance(ind, dict) else {}
        iu_id = _induse_iri(i, sig)
        induse_nodes.append({
            "@context": ctx,
            "@id": iu_id,
            "@type": "IndicatorUse",
            "schema:name": name,
            "params": params
        })
        induse_refs.append({"@id": iu_id})
    if induse_refs:
        base["usesIndicator"] = induse_refs

    # rules
    def rule_obj(idx: int, direction: str, rule: AnyType) -> Dict[str, Any]:
        rid = _rule_iri(idx, sig, direction)
        obj = {"@context": ctx, "@id": rid, "@type": "Rule", "direction": direction}
        if isinstance(rule, dict) and {"operator","left","right"} <= set(rule.keys()):
            obj["operator"] = rule["operator"]
            obj["left"] = str(rule["left"])
            obj["right"] = str(rule["right"])
            if rule.get("text"): obj["text"] = rule["text"]
        else:
            obj["operator"] = "=="
            obj["left"] = "expr"
            obj["right"] = "true"
            obj["text"] = str(rule)
        return obj

    rule_nodes = []
    idx = 1
    for r in normalized.get("entry_rules", []):
        rule_nodes.append(rule_obj(idx, "entry", r)); idx += 1
    for r in normalized.get("exit_rules", []):
        rule_nodes.append(rule_obj(idx, "exit", r)); idx += 1
    if rule_nodes:
        base["hasRule"] = [{"@id": r["@id"]} for r in rule_nodes]

    # optional fields
    if "confidence" in normalized:
        base["confidence"] = normalized["confidence"]
    if "backtest_hints" in normalized:
        base["backtestHint"] = normalized["backtest_hints"]

    # 2) also mint Token nodes + link via targetsToken
    token_nodes, token_refs = [], []
    for sym in universe_vals:
        if not sym: continue
        tid = _token_iri(sym)
        token_nodes.append({
            "@context": ctx,
            "@id": tid,
            "@type": "Token",
            "symbol": sym.upper(),
            "name": sym.upper()
        })
        token_refs.append({"@id": tid})
    if token_refs:
        base["targetsToken"] = token_refs

    # Assemble
    doc = [base] + induse_nodes + rule_nodes + docs + token_nodes
    return doc
