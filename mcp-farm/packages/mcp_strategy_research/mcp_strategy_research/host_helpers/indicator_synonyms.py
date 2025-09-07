# mcp-farm/packages/mcp_strategy_research/mcp_strategy_research/host_helpers/indicator_synonyms.py
"""
Host-side helper to build an `llm_hint` JSON string for the Strategy Research MCP.

You can feed this directly to the MCP tool:
  extract_strategies(text: str, indicators: list[str], llm_hint: Optional[str])

The host/orchestrator should gather canonical indicators and any synonyms
(e.g., from the Indicators MCP or a static mapping), then call
`build_llm_hint_from_registry(...)` to produce a compact JSON string:

    {"synonyms": {"RSI": ["Relative Strength Index"], ...}}

This keeps the Strategy Research MCP API stable while improving extraction quality.
"""
from __future__ import annotations
from typing import Dict, List, Optional
import json


def build_llm_hint_from_registry(
    canonical: List[str],
    registry_synonyms: Optional[Dict[str, List[str]]] = None,
) -> str:
    """
    Build a compact JSON string suitable for the Strategy Research MCP `llm_hint` param.

    Args:
      canonical: list of canonical indicator names (e.g., ["RSI","MACD","ATR"])
      registry_synonyms: optional dict {canonical_name: [synonym1, synonym2, ...]}

    Returns:
      JSON string like: {"synonyms": {"RSI":["Relative Strength Index"], ...}}
    """
    synonyms: Dict[str, List[str]] = {}
    registry_synonyms = registry_synonyms or {}

    canon_set = {c for c in (canonical or []) if isinstance(c, str) and c.strip()}
    for name in sorted(canon_set):
        vals = registry_synonyms.get(name) or []
        # Deduplicate (case-insensitive) and drop self-name echoes
        seen = set()
        clean = []
        for v in vals:
            v = (v or "").strip()
            if v and v.lower() not in seen and v.lower() != name.lower():
                seen.add(v.lower())
                clean.append(v)
        if clean:
            synonyms[name] = clean

    return json.dumps({"synonyms": synonyms}, ensure_ascii=False)
