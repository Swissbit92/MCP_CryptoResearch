# packages/mcp_strategy_research/mcp_strategy_research/extractor.py
from typing import Any, Dict, List, Optional, Tuple
import json, os, re, hashlib

from langchain_ollama import OllamaLLM

from .prompts import build_extraction_prompt


# ---------------- Env knobs (safe defaults) ----------------
def _ollama_model() -> str:
    # keep compatibility with older env names
    return os.getenv("OLLAMA_MODEL", os.getenv("Ollama_MODEL", "qwen2.5:14b-instruct"))

def _ollama_fallback() -> str:
    return os.getenv("OLLAMA_MODEL_FALLBACK", os.getenv("Ollama_MODEL_FALLBACK", "llama3.1:8b-instruct"))

CHUNK_SIZE = int(os.getenv("RESEARCH_CHUNK_SIZE_CHARS", "6000"))
CHUNK_OVERLAP = int(os.getenv("RESEARCH_CHUNK_OVERLAP_CHARS", "600"))
MAX_CHUNKS = int(os.getenv("RESEARCH_MAX_CHUNKS", "6"))
MAX_RETURN = int(os.getenv("RESEARCH_MAX_CANDIDATES", "8"))


# ---------------- LLM helpers ----------------
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


# ---------------- Chunking + dedup ----------------
def _chunk_text(text: str, chunk_size: int, overlap: int, max_chunks: int) -> List[str]:
    if not text or len(text) <= chunk_size:
        return [text]
    step = max(1, chunk_size - max(0, overlap))
    chunks: List[str] = []
    i = 0
    while i < len(text) and len(chunks) < max_chunks:
        chunks.append(text[i:i + chunk_size])
        i += step
    return chunks

def _norm_str(s: str) -> str:
    s = (s or "").lower()
    return re.sub(r"[^a-z0-9\s]", " ", s).strip()

def _sig_for_candidate(c: Dict[str, Any]) -> str:
    """
    Build a stable signature to deduplicate similar candidates across chunks.
    Combines name, timeframe, indicator list, and rules (normalized).
    """
    name = _norm_str(c.get("name", ""))
    timeframe = _norm_str(c.get("timeframe", ""))
    inds = ",".join(sorted(_norm_str(i.get("name", "")) for i in (c.get("indicators") or [])))
    rules = " ".join((_norm_str(" ".join(c.get("entry_rules", []) + c.get("exit_rules", [])))))
    blob = f"{name}|{timeframe}|{inds}|{rules}"
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()

def _dedup_candidates(cands: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in cands:
        sig = _sig_for_candidate(c)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(c)
        if len(out) >= limit:
            break
    return out


# ---------------- Public API ----------------
def extract_strategies(text: str, indicators: List[str], llm_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    LLM-based extractor (Ollama by default) with optional synonyms bias via llm_hint (JSON).
    Adds:
      - automatic chunking for long texts
      - cross-chunk candidate deduplication
      - same deterministic fallback if LLM is unavailable
    """
    chunks = _chunk_text(text or "", CHUNK_SIZE, CHUNK_OVERLAP, MAX_CHUNKS)
    all_candidates: List[Dict[str, Any]] = []

    def _run_llm_once(chunk_text: str) -> List[Dict[str, Any]]:
        final_prompt = _compose_prompt(chunk_text, indicators, llm_hint)

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

        return []

    # Try chunked extraction first
    try:
        for ck in chunks:
            out = _run_llm_once(ck)
            if out:
                all_candidates.extend(out)
        if all_candidates:
            return _dedup_candidates(all_candidates, MAX_RETURN)
    except Exception:
        # swallow & proceed to deterministic fallback
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
