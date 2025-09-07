# mcp-farm/packages/mcp_kg/tests/test_upsert_and_fetch.py
import os, json
from mcp_kg.kg_store import KGStore, KGConfig
from mcp_kg.mappers.strategy_to_jsonld import map_strategy_v1_to_jsonld

def test_upsert_and_fetch_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("KG_STORE_BACKEND", "memory")

    cfg = KGConfig()
    store = KGStore(cfg)

    normalized = {
        "signature": "sig123",
        "name": "RSI+MACD swing",
        "description": "RSI(14) crosses 30, MACD confirm",
        "timeframe": "1h",
        "universe": ["BTCUSDT"],
        "indicators": [
            {"name": "RSI", "params": {"length": 14}},
            {"name": "MACD", "params": {"fast":12,"slow":26,"signal":9}}
        ],
        "entry_rules": [
            {"operator":"crosses_above","left":"RSI_14","right":"30","text":"RSI crosses up 30"},
            {"operator":">","left":"MACD_line","right":"signal_line","text":"MACD > signal"}
        ],
        "exit_rules": [
            {"operator":"<","left":"RSI_14","right":"70","text":"RSI falls below 70"}
        ],
        "sources": [{"url":"https://arxiv.org/abs/2206.12282"}]
    }

    jd = map_strategy_v1_to_jsonld(normalized, cfg.context_path)

    from orjson import dumps
    jd_str = dumps(jd).decode("utf-8")

    # Validate before insert
    shapes = open(cfg.shapes_path, "r", encoding="utf-8").read()
    from mcp_kg.validators.shacl import run_shacl_jsonld
    conforms, report = run_shacl_jsonld(jd_str, shapes)
    assert conforms, report

    store.insert_jsonld(jd_str)

    # Fetch by signature
    got = store.get_strategy_by_signature("sig123")
    assert got is not None
    j = json.loads(got)
    # basic checks
    ids = [n.get("@id") for n in j]
    assert any(i for i in ids if "kg://strategy/sig123" in i or i == "kg://strategy/sig123")

    # Search
    hits = store.search_strategies(["RSI","MACD"], "1h", ["BTCUSDT"], 10)
    assert any(h["signature"] == "sig123" for h in hits)
