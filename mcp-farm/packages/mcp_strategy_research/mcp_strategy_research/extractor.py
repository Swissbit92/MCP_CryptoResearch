# packages/mcp_strategy_research/mcp_strategy_research/extractor.py
from typing import Any, Dict, List, Optional
import json, os, re

from langchain_ollama import OllamaLLM

from .prompts import build_extraction_prompt


def _ollama_model() -> str:
    # keep compatibility with older env names
    return os.getenv("OLLAMA_MODEL", os.getenv("Ollama_MODEL", "qwen2.5:14b-instruct"))


def _ollama_fallback() -> str:
    return os.getenv("OLLAMA_MODEL_FALLBACK", os.getenv("Ollama_MODEL_FALLBACK", "llama3.1:8b-instruct"))


def _make_llm(model: str) -> OllamaLLM:
    # Using OllamaLLM (ChatOllama is deprecated)
    return OllamaLLM(
        model=model,
        temperature=0.15,
        top_p=0.9,
        num_ctx=8192,
        repeat_penalty=1.05,
    )


def _json_from_text(s: str) -> List[Dict[str, Any]]:
    """
    Try to extract the first JSON array from a raw LLM response string.
    """
    # tolerant first-pass extraction in case the model adds pre/post text (shouldn't)
    m = re.search(r"\[[\s\S]*\]", s)
    js = s if m is None else m.group(0)
    try:
        data = json.loads(js)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _parse_hint(llm_hint: Optional[str]) -> Dict[str, Any]:
    """
    Accept an optional JSON string in llm_hint with shape:
      { "synonyms": { "RSI": ["Relative Strength Index", ...], ... } }
    Silently ignore if not valid JSON.
    """
    if not llm_hint:
        return {}
    try:
        return json.loads(llm_hint)
    except Exception:
        return {}


def _compose_prompt(text: str, indicators: List[str], llm_hint: Optional[str]) -> str:
    """
    Create a single-string prompt for OllamaLLM:
    [INSTRUCTIONS]\n\n[TEXT]\n\n(ask for JSON array only)
    """
    hint = _parse_hint(llm_hint)
    synonyms = hint.get("synonyms") if isinstance(hint.get("synonyms"), dict) else None
    instructions = build_extraction_prompt(indicators, synonyms=synonyms)
    return f"{instructions}\n\nTEXT:\n{text}\n\nReturn ONLY the JSON array."


def extract_strategies(text: str, indicators: List[str], llm_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    LLM-based extractor (Ollama by default) with optional synonyms bias via llm_hint (JSON).
    Keeps the existing MCP signature and fallback behavior.
    """
    final_prompt = _compose_prompt(text, indicators, llm_hint)

    # Primary model
    try:
        llm = _make_llm(_ollama_model())
        res = llm.invoke(final_prompt)
        out = _json_from_text(res if isinstance(res, str) else getattr(res, "content", ""))
        if out:
            return out
    except Exception:
        pass

    # Fallback model
    try:
        llm = _make_llm(_ollama_fallback())
        res = llm.invoke(final_prompt)
        out = _json_from_text(res if isinstance(res, str) else getattr(res, "content", ""))
        if out:
            return out
    except Exception:
        pass

    # Deterministic minimal fallback (unchanged)
    return [{
        "name": "RSI 14 / MACD Confirmed Pullback (fallback)",
        "description": "Heuristic fallback when LLM is unavailable.",
        "timeframe": "1h",
        "indicators": [
            {"name": "RSI", "params": {"window": 14}},
            {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
        ],
        "entry_rules": [
            "RSI(window=14) crosses below 30 then crosses back above 30",
            "MACD line > signal line"
        ],
        "exit_rules": [
            "RSI crosses below 70",
            "or trailing_stop(ATR, multiple=2.0)"
        ],
        "position_sizing": {"type": "fixed_risk", "risk_pct": 1.0},
        "defaults": {"stop": {"atr_mult": 2.0}, "take_profit": None},
        "backtest_hints": {"warmup_bars": 200}
    }]
