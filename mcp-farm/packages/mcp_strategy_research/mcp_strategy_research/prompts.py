# packages/mcp_strategy_research/mcp_strategy_research/prompts.py
from typing import Dict, List, Optional


def plan_queries(topic: str, indicators: List[str], max_per_indicator: int, source: str = "arxiv") -> List[str]:
    """
    Generate targeted web queries for research.
    (Unchanged tool behavior/signature.)
    """
    site = "site:arxiv.org" if source.lower() == "arxiv" else ""
    patterns = [
        "{ind} strategy {topic}",
        "{ind} crossover {topic}",
        "{ind} backtest {topic}",
        "{ind} trading rules {topic}",
    ]
    out: List[str] = []
    for ind in indicators:
        for p in patterns[:max_per_indicator]:
            q = p.format(ind=ind, topic=topic)
            if site:
                q = f"{q} {site}"
            out.append(q)
    return out


def strategy_extraction_guidelines_placeholder() -> str:
    """
    Displayed in MCP 'Prompts' list (informational only).
    """
    return (
        "Extract TA-style strategies with explicit ENTRY and EXIT rules and parameters. "
        "Prefer indicators (RSI, MACD, SMA, EMA, ATR, BBANDS, etc.), include timeframe, "
        "and produce multiple candidates when possible."
    )


def _format_synonyms_block(synonyms: Optional[Dict[str, List[str]]]) -> str:
    """
    Render a human-readable synonyms section for the system prompt.
    """
    if not synonyms:
        return "- (no extra synonyms provided)"
    lines: List[str] = []
    for name, syns in sorted(synonyms.items(), key=lambda kv: kv[0].lower()):
        if syns:
            # sort + dedupe, display nicely
            seen = set()
            clean = []
            for s in syns:
                s = (s or "").strip()
                if s and s.lower() not in seen:
                    seen.add(s.lower())
                    clean.append(s)
            if clean:
                lines.append(f"- {name}: {', '.join(clean)}")
                continue
        lines.append(f"- {name}: (none)")
    return "\n".join(lines)


def build_extraction_prompt(indicators: List[str], synonyms: Optional[Dict[str, List[str]]] = None) -> str:
    """
    Build the instruction text for the LLM extractor.
    This is returned as a single string; the extractor will append the source text.
    """
    inds = ", ".join(indicators) if indicators else "RSI, MACD, SMA, EMA, ATR, BBANDS"
    syn_text = _format_synonyms_block(synonyms)

    return f"""
You are a strategy extraction assistant.

GOAL
- From the provided text, extract 2–5 distinct **technical analysis** trading strategies.

CONSTRAINTS
- Prefer these indicators (canonical names): {inds}.
- Indicator synonyms (map to canonical names when found):
{syn_text}

- Each candidate MUST include:
  • timeframe (e.g., 1h, 4h, 1d)
  • indicators[] with params
  • entry_rules[] and exit_rules[] phrased explicitly (crosses above/below, thresholds, windows)
  • defaults (stop/take-profit) if present or reasonable
  • sources[] including the original URL (to be attached by caller)
- Return a STRICT JSON array of objects with fields:
  name, description, timeframe, indicators, entry_rules, exit_rules, position_sizing?, defaults?, backtest_hints?

QUALITY
- Avoid vague “buy the dip” advice or pure ML descriptions without TA rules.
- Prefer clear numeric params and cross semantics (from-below vs from-above).
- Respond with **ONLY** the JSON array. No prose, no markdown.
"""
