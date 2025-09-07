# packages/mcp_strategy_research/mcp_strategy_research/normalizer.py
from typing import Any, Dict, List, Optional
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

# ----------- Light canonicalization / validation helpers -----------

# Common aliases → canonical names (best-effort; non-exhaustive).
_ALIAS_MAP = {
    "relative strength index": "RSI",
    "rsi": "RSI",

    "moving average convergence divergence": "MACD",
    "macd": "MACD",

    "simple moving average": "SMA",
    "moving average": "SMA",
    "sma": "SMA",

    "exponential moving average": "EMA",
    "ema": "EMA",

    "average true range": "ATR",
    "atr": "ATR",

    "bollinger bands": "BBANDS",
    "bb": "BBANDS",
    "bbands": "BBANDS",

    "percentage price oscillator": "PPO",
    "ppo": "PPO",

    "money flow index": "MFI",
    "mfi": "MFI",

    "commodity channel index": "CCI",
    "cci": "CCI",
}

def _canon_indicator(name: str, allowed: Optional[set] = None) -> str:
    """
    Map common aliases → canonical. If allowed set is provided and the mapped
    name is not allowed, keep the original (allow unknown-but-valid names).
    """
    if not name:
        return name
    candidate = _ALIAS_MAP.get(name.strip().lower(), name)
    if allowed and candidate not in allowed:
        return name
    return candidate

def _canon_all_indicators(ind_list: List[Dict[str, Any]], allowed_names: List[str]) -> List[Dict[str, Any]]:
    allowed = set(allowed_names or [])
    out: List[Dict[str, Any]] = []
    for itm in ind_list or []:
        nm = _canon_indicator(str(itm.get("name","")), allowed)
        params = itm.get("params", {}) or {}
        out.append({"name": nm, "params": params})
    return out

# ----------- Rule coercion (objects → readable strings) -----------

def _stringify_rule(rule: Any) -> str:
    """
    Convert non-string rules into string form acceptable by the schema.
    - Special-cases ATR trailing stop dicts (common from LLMs).
    - Falls back to compact JSON if we can’t infer a nicer phrasing.
    """
    if rule is None:
        return ""
    if isinstance(rule, str):
        return rule.strip()

    # Heuristic: {"ATR": {"trailing_stop": true, "multiple": 2.0}} → "trailing_stop(ATR, multiple=2.0)"
    try:
        if isinstance(rule, dict):
            # Flatten single-key wrappers like {"ATR": {...}}
            if len(rule) == 1:
                k = next(iter(rule))
                v = rule[k]
                if str(k).strip().upper() == "ATR" and isinstance(v, dict):
                    if v.get("trailing_stop") is True:
                        mult = v.get("multiple", v.get("multiplier", v.get("atr_mult")))
                        if mult is not None:
                            try:
                                mult_val = float(mult)
                            except Exception:
                                mult_val = mult
                            return f"trailing_stop(ATR, multiple={mult_val})"
                        return "trailing_stop(ATR)"
            # If we can't map nicely, stringify as compact JSON
            return json.dumps(rule, ensure_ascii=False, separators=(",", ":"))
        # Lists / tuples → compact JSON
        if isinstance(rule, (list, tuple)):
            return json.dumps(rule, ensure_ascii=False, separators=(",", ":"))
        # Numbers / bools
        if isinstance(rule, (int, float, bool)):
            return str(rule)
        # Anything else
        return str(rule)
    except Exception:
        # Last-resort stringify
        try:
            return json.dumps(rule, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return str(rule)

def _coerce_rules(rules: Any) -> List[str]:
    if not rules:
        return []
    out: List[str] = []
    for r in rules:
        s = _stringify_rule(r)
        if s:
            out.append(s)
    return out

# ----------- Sources coercion (strings/objects → objects) -----------

_PLACEHOLDERS = {"URL_TO_BE_ATTACHED", "TBD", "N/A", "NA", "NONE", ""}

def _coerce_sources(raw: Any, source_url: str) -> List[Dict[str, Any]]:
    """
    Accepts:
      - None → fallback to source_url
      - list[str|dict] → normalize each into {"url": str, "doi": None}
      - dict → normalize if it has a url-like field
    Ensures at least one valid object with a 'url' string.
    """
    out: List[Dict[str, Any]] = []

    def _add(url_val: Optional[str], doi_val: Optional[str] = None):
        uv = (url_val or "").strip()
        if not uv or uv.strip().upper() in _PLACEHOLDERS:
            return
        out.append({"url": uv, "doi": doi_val})

    if raw is None:
        _add(source_url)
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, str):
                s = it.strip()
                if s.upper() in _PLACEHOLDERS:
                    continue
                _add(s)
            elif isinstance(it, dict):
                url = it.get("url") or it.get("href") or it.get("link")
                doi = it.get("doi")
                if url:
                    _add(str(url), str(doi) if doi is not None else None)
            # ignore other types silently
        if not out:
            _add(source_url)
    elif isinstance(raw, dict):
        url = raw.get("url") or raw.get("href") or raw.get("link")
        doi = raw.get("doi")
        if url:
            _add(str(url), str(doi) if doi is not None else None)
        else:
            _add(source_url)
    else:
        # unexpected primitive → treat as missing
        _add(source_url)

    if not out:
        _add(source_url)

    return out

# -------------------------------------------------------------------

def _fill_defaults(c: Dict[str, Any], source_url: str, allowed_names: List[str]) -> Dict[str, Any]:
    """
    Fill required fields and reasonable defaults for missing bits, with indicator canonicalization,
    rule coercion, and sources coercion.
    """
    return {
        "schema_version": "strategy.v1",
        "name": c.get("name") or "Unnamed Strategy",
        "description": c.get("description") or "",
        "universe": c.get("universe") or ["BTCUSDT"],
        "timeframe": c.get("timeframe") or "1h",
        "indicators": _canon_all_indicators(c.get("indicators") or [], allowed_names),
        "entry_rules": _coerce_rules(c.get("entry_rules") or []),
        "exit_rules": _coerce_rules(c.get("exit_rules") or []),
        "position_sizing": c.get("position_sizing") or {"type": "fixed_risk", "risk_pct": 1.0},
        "defaults": c.get("defaults") or {"stop": {"atr_mult": 2.0}, "take_profit": None},
        "backtest_hints": c.get("backtest_hints") or {"warmup_bars": 200, "min_data": None},
        "sources": _coerce_sources(c.get("sources"), source_url),
        "confidence": c.get("confidence") or {"evidence": ["text-derived"], "notes": "LLM-normalized"},
    }

def normalize_strategy(doc: Dict[str, Any], source_url: str, indicators: List[str]) -> Dict[str, Any]:
    """
    Validate and persist a single normalized strategy.
    Returns:
      { "uri": research://normalized/<id>.json, "json": <strategy_obj> }
    (Retains existing behavior + light canonicalization + rule & sources coercion.)
    """
    obj = _fill_defaults(doc, source_url, allowed_names=indicators or [])

    # Minimal sanity guards (keep behavior)
    if not obj["entry_rules"]:
        obj["entry_rules"] = ["RSI(window=14) crosses below 30 then crosses back above 30"]
    if not obj["exit_rules"]:
        obj["exit_rules"] = ["RSI crosses below 70"]

    validate(instance=obj, schema=SCHEMA)

    uri = write_normalized(obj)
    return {"uri": uri, "json": obj}
