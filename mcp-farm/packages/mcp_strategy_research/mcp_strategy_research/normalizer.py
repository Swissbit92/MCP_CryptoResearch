from typing import Any, Dict, List
import json
from jsonschema import validate, Draft202012Validator
from importlib.resources import files, as_file

from .storage import write_normalized

# ---------- Robust schema load with an in-code fallback ----------

_DEFAULT_SCHEMA: Dict[str, Any] = {
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Strategy v1",
  "type": "object",
  "required": [
    "schema_version", "name", "description", "universe", "timeframe",
    "indicators", "entry_rules", "exit_rules", "sources", "confidence"
  ],
  "properties": {
    "schema_version": { "const": "strategy.v1" },
    "name": { "type": "string" },
    "description": { "type": "string" },
    "universe": { "type": "array", "items": { "type": "string" } },
    "timeframe": { "type": "string" },
    "indicators": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name","params"],
        "properties": {
          "name": { "type": "string" },
          "params": { "type": "object" }
        }
      }
    },
    "entry_rules": { "type": "array", "items": { "type": "string" } },
    "exit_rules":  { "type": "array", "items": { "type": "string" } },
    "position_sizing": { "type": ["object","null"] },
    "defaults": { "type": ["object","null"] },
    "backtest_hints": { "type": ["object","null"] },
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["url"],
        "properties": {
          "url": { "type": "string" },
          "doi": { "type": ["string","null"] }
        }
      }
    },
    "confidence": { "type": "object" }
  },
  "additionalProperties": True
}

def _load_schema() -> Dict[str, Any]:
    """
    Try to load strategy_v1.json from package data.
    If not present (editable install not packaging data yet), fall back to _DEFAULT_SCHEMA.
    """
    try:
        with as_file(files("mcp_strategy_research.schemas") / "strategy_v1.json") as p:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return _DEFAULT_SCHEMA

SCHEMA: Dict[str, Any] = _load_schema()
Draft202012Validator.check_schema(SCHEMA)

# ----------------------------------------------------------------

def _fill_defaults(c: Dict[str, Any], source_url: str) -> Dict[str, Any]:
    """Fill required fields and reasonable defaults for missing bits."""
    return {
        "schema_version": "strategy.v1",
        "name": c.get("name") or "Unnamed Strategy",
        "description": c.get("description") or "",
        "universe": c.get("universe") or ["BTCUSDT"],
        "timeframe": c.get("timeframe") or "1h",
        "indicators": c.get("indicators") or [],
        "entry_rules": c.get("entry_rules") or [],
        "exit_rules": c.get("exit_rules") or [],
        "position_sizing": c.get("position_sizing") or {"type": "fixed_risk", "risk_pct": 1.0},
        "defaults": c.get("defaults") or {"stop": {"atr_mult": 2.0}, "take_profit": None},
        "backtest_hints": c.get("backtest_hints") or {"warmup_bars": 200, "min_data": None},
        "sources": c.get("sources") or [{"url": source_url, "doi": None}],
        "confidence": c.get("confidence") or {"evidence": ["text-derived"], "notes": "LLM-normalized"},
    }

def normalize_strategy(doc: Dict[str, Any], source_url: str, indicators: List[str]) -> Dict[str, Any]:
    """
    Validate and persist a single normalized strategy.
    Returns:
      { "uri": research://normalized/<id>.json, "json": <strategy_obj> }
    """
    obj = _fill_defaults(doc, source_url)

    # Minimal sanity: ensure non-empty rule arrays
    if not obj["entry_rules"]:
        obj["entry_rules"] = ["RSI(window=14) crosses below 30 then crosses back above 30"]
    if not obj["exit_rules"]:
        obj["exit_rules"] = ["RSI crosses below 70"]

    validate(instance=obj, schema=SCHEMA)

    uri = write_normalized(obj)
    return {"uri": uri, "json": obj}
