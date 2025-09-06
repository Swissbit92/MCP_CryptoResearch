# packages/mcp_strategy_research/mcp_strategy_research/extractor.py
from typing import Any, Dict, List
import json, os, re
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from .prompts import build_extraction_prompt

def _ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", os.getenv("Ollama_MODEL", "qwen2.5:14b-instruct"))

def _ollama_fallback() -> str:
    return os.getenv("OLLAMA_MODEL_FALLBACK", os.getenv("Ollama_MODEL_FALLBACK", "llama3.1:8b-instruct"))

def _make_llm(model: str) -> OllamaLLM:
    return OllamaLLM(
        model=model,
        temperature=0.15,
        top_p=0.9,
        num_ctx=8192,
        repeat_penalty=1.05,
    )

def _json_from_text(s: str) -> List[Dict[str, Any]]:
    # Try to extract the first JSON array
    m = re.search(r"\[[\s\S]*\]", s)
    js = s if m is None else m.group(0)
    try:
        data = json.loads(js)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []

def extract_strategies(text: str, indicators: List[str], llm_hint: str | None = None) -> List[Dict[str, Any]]:
    system = build_extraction_prompt(indicators)
    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("user", "{text}"),
    ])
    # primary
    try:
        llm = _make_llm(_ollama_model())
        res = (prompt | llm).invoke({"text": text})
        out = _json_from_text(res.content)
        if out:
            return out
    except Exception:
        pass
    # fallback
    try:
        llm = _make_llm(_ollama_fallback())
        res = (prompt | llm).invoke({"text": text})
        out = _json_from_text(res.content)
        if out:
            return out
    except Exception:
        pass
    # deterministic minimal fallback
    return [{
        "name": "RSI 14 / MACD Confirmed Pullback (fallback)",
        "description": "Heuristic fallback when LLM is unavailable.",
        "timeframe": "1h",
        "indicators": [
            {"name":"RSI","params":{"window":14}},
            {"name":"MACD","params":{"fast":12,"slow":26,"signal":9}}
        ],
        "entry_rules": [
            "RSI(window=14) crosses below 30 then crosses back above 30",
            "MACD line > signal line"
        ],
        "exit_rules": [
            "RSI crosses below 70",
            "or trailing_stop(ATR, multiple=2.0)"
        ],
        "position_sizing": {"type":"fixed_risk","risk_pct":1.0},
        "defaults": {"stop":{"atr_mult":2.0}, "take_profit": None},
        "backtest_hints": {"warmup_bars":200}
    }]
