# mcp-farm/packages/mcp_kg/tests/test_upsert_whitepaper.py
import json
from mcp_kg.kg_store import KGStore, KGConfig
from mcp_kg.mappers.whitepaper_to_jsonld import map_whitepaper_to_jsonld
from mcp_kg.validators.shacl import run_shacl_jsonld

def test_upsert_whitepaper_memory(monkeypatch):
    monkeypatch.setenv("KG_STORE_BACKEND", "memory")
    cfg = KGConfig()
    store = KGStore(cfg)
    shapes = open(cfg.shapes_path, "r", encoding="utf-8").read()

    wp = {
        "key": "bitcoin-whitepaper",
        "title": "Bitcoin: A Peer-to-Peer Electronic Cash System",
        "url": "https://bitcoin.org/bitcoin.pdf",
        "published_on": "2008-10-31",
        "token": {"symbol": "BTC", "name": "Bitcoin"},
        "authors": ["Satoshi Nakamoto"]
    }
    jd = map_whitepaper_to_jsonld(wp, cfg.context_path)
    from orjson import dumps
    jd_str = dumps(jd).decode()
    conforms, report = run_shacl_jsonld(jd_str, shapes)
    assert conforms, report

    store.insert_jsonld(jd_str)
    # Confirm Token exists
    gjson = store.export_graph_jsonld()
    data = json.loads(gjson)
    ids = [n.get("@id") for n in data]
    assert any(i for i in ids if "kg://token/BTC" in (i or ""))
