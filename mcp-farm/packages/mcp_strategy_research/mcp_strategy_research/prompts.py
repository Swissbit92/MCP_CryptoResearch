# packages/mcp_strategy_research/mcp_strategy_research/prompts.py
from typing import List

def plan_queries(topic: str, indicators: List[str], max_per_indicator: int, source: str = "arxiv") -> List[str]:
    site = "site:arxiv.org" if source.lower()=="arxiv" else ""
    patterns = [
        "{ind} strategy {topic}",
        "{ind} crossover {topic}",
        "{ind} backtest {topic}",
        "{ind} trading rules {topic}",
    ]
    out = []
    for ind in indicators:
        for p in patterns[:max_per_indicator]:
            q = p.format(ind=ind, topic=topic)
            if site:
                q = f"{q} {site}"
            out.append(q)
    return out

def strategy_extraction_guidelines_placeholder() -> str:
    # Shown as an MCP Prompt (help text); extraction prompt is in extractor.py
    return (
        "Extract TA-style strategies with explicit ENTRY and EXIT rules and parameters. "
        "Prefer indicators (RSI, MACD, SMA, EMA, ATR, BBANDS, etc.), include timeframe, "
        "and produce multiple candidates when possible."
    )

def build_extraction_prompt(indicators: List[str]) -> str:
    inds = ", ".join(indicators) if indicators else "RSI, MACD, SMA, EMA, ATR, BBANDS"
    return f"""
You are a strategy extraction assistant.

GOAL
- From the provided text, extract 2–5 distinct **technical analysis** trading strategies.

CONSTRAINTS
- Focus on these indicators when possible: {inds}.
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
- Short, unambiguous JSON. No markdown.
"""
