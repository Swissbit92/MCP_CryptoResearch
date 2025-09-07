# packages/mcp_strategy_research/tests/test_smoke_pipeline.py
"""
End-to-end smoke test for Strategy Research MCP (local/offline).

It exercises:
  - extractor.extract_strategies (LLM default; falls back deterministically if Ollama unavailable)
  - normalizer.normalize_strategy (schema fill + validation + persist)
  - storage.bundle_results (manifest write)

This test uses a self-contained sample text with RSI/MACD/ATR TA logic.
No network calls; Brave/arXiv not used here.
"""

from __future__ import annotations
from typing import List

from mcp_strategy_research import extractor, normalizer, storage
from mcp_strategy_research.host_helpers.indicator_synonyms import build_llm_hint_from_registry


def test_smoke_pipeline_end_to_end(tmp_path):
    # Ensure storage directories exist (writes under package storage/ by design)
    storage.init_storage()

    # --- Sample TA-style text (pretend excerpt from a paper/notes) ---
    sample_text = """
We evaluate a momentum-reversal strategy for BTC on the 1-hour timeframe.
The entry requires Relative Strength Index (RSI, period 14) to dip below 30 and subsequently cross back above 30.
To reduce false positives, the MACD line (12,26,9) must be above its signal line at entry.
Risk management uses Average True Range (ATR) with a trailing stop equal to 2.0× ATR.
Exits occur if RSI exceeds 70 and later crosses back below 70, or the trailing stop is hit.
"""

    # Canonical indicators (host/orchestrator typically fetches from Indicators MCP)
    indicators = ["RSI", "MACD", "ATR"]

    # Build an llm_hint with synonyms as you’d get from the Indicators MCP registry (or a static map)
    reg_synonyms = {
        "RSI":  ["Relative Strength Index"],
        "MACD": ["Moving Average Convergence Divergence"],
        "ATR":  ["Average True Range"],
    }
    llm_hint = build_llm_hint_from_registry(indicators, reg_synonyms)

    # --- Extract multiple candidate strategies from the text ---
    candidates = extractor.extract_strategies(sample_text, indicators, llm_hint=llm_hint)

    assert isinstance(candidates, list), "Extractor must return a list"
    assert len(candidates) >= 1, "Should produce at least one candidate (LLM or fallback)"

    # Pick the first candidate and normalize it
    source_url = "https://example.org/mock-source"  # attach any representative URL
    norm = normalizer.normalize_strategy(candidates[0], source_url, indicators)

    assert isinstance(norm, dict) and "uri" in norm and "json" in norm
    uri = norm["uri"]
    obj = norm["json"]
    assert uri.startswith("research://normalized/"), "Normalization must persist to normalized URI"

    # Check minimal required keys exist post-normalization
    for key in ["schema_version", "name", "description", "universe", "timeframe",
                "indicators", "entry_rules", "exit_rules", "sources", "confidence"]:
        assert key in obj, f"Missing required field: {key}"

    # Bundle results (manifest)
    bundle = storage.bundle_results([uri])
    assert isinstance(bundle, dict) and "uri" in bundle and "strategies" in bundle
    assert bundle["uri"].startswith("research://results/")
    assert [uri] == bundle["strategies"]
