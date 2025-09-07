# packages/mcp_strategy_research/tests/test_chunking_dedup.py
import json
from mcp_strategy_research.extractor import _chunk_text, _dedup_candidates

def test_chunking_produces_multiple_chunks_for_long_text():
    # Force a small chunk size / overlap to ensure multiple chunks
    long_text = ("RSI crosses below 30 then above 30. " * 40).strip()
    chunks = _chunk_text(long_text, chunk_size=120, overlap=20, max_chunks=10)
    # Expect >1 chunk and overlaps (adjacent chunks should share content)
    assert len(chunks) >= 2
    assert any(chunks[i][-20:] == chunks[i+1][:20] for i in range(len(chunks)-1))


def test_dedup_collapses_duplicate_candidates_across_chunks():
    # Simulate the same candidate emitted from two different chunks
    base = {
        "name": "RSI 14 / MACD Confirmed Pullback",
        "timeframe": "1h",
        "indicators": [
            {"name": "RSI", "params": {"window": 14}},
            {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}},
        ],
        "entry_rules": [
            "RSI(window=14) crosses below 30 then crosses back above 30",
            "MACD line > signal line",
        ],
        "exit_rules": ["RSI crosses below 70"],
    }
    dup1 = json.loads(json.dumps(base))  # identical copy
    # Slightly different (distinct) candidate
    alt = json.loads(json.dumps(base))
    alt["timeframe"] = "4h"
    alt["name"] = "RSI 14 / MACD Confirmed Pullback (4h)"

    merged = _dedup_candidates([base, dup1, alt], limit=10)
    # Expect duplicates to be collapsed: only 2 unique candidates
    assert len(merged) == 2
    # And order preserved for the first occurrence
    assert merged[0]["timeframe"] == "1h"
    assert merged[1]["timeframe"] == "4h"
