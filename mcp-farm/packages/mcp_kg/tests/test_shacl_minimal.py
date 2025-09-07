# mcp-farm/packages/mcp_kg/tests/test_shacl_minimal.py
import json, os
from mcp_kg.validators.shacl import run_shacl_jsonld

def _read(p): return open(p, "r", encoding="utf-8").read()

SHAPES = _read("packages/mcp_kg/mcp_kg/resources/shapes.ttl")
CTX = json.loads(_read("packages/mcp_kg/mcp_kg/resources/context.jsonld"))["@context"]

def test_shacl_valid_minimal():
    doc = [{
      "@context": CTX,
      "@id": "kg://strategy/testsig",
      "@type": "Strategy",
      "signature": "testsig",
      "name": "Test Strategy",
      "timeframe": "1h",
      "usesIndicator": [{"@id": "kg://induse/testsig/1"}],
      "hasRule": [{"@id": "kg://rule/testsig/entry/1"}, {"@id": "kg://rule/testsig/exit/2"}],
      "hasSource": [{"@id": "kg://doc/testsig/1"}]
    },{
      "@context": CTX,
      "@id": "kg://induse/testsig/1",
      "@type": "IndicatorUse",
      "schema:name": "RSI",
      "params": {"length": 14}
    },{
      "@context": CTX,
      "@id": "kg://rule/testsig/entry/1",
      "@type": "Rule",
      "direction": "entry",
      "operator": "crosses_above",
      "left": "RSI_14",
      "right": "30"
    },{
      "@context": CTX,
      "@id": "kg://rule/testsig/exit/2",
      "@type": "Rule",
      "direction": "exit",
      "operator": "<",
      "left": "RSI_14",
      "right": "70"
    },{
      "@context": CTX,
      "@id": "kg://doc/testsig/1",
      "@type": "Document",
      "schema:url": "https://arxiv.org/abs/1234.5678"
    }]
    from orjson import dumps
    conforms, report = run_shacl_jsonld(dumps(doc).decode(), SHAPES)
    assert conforms, report

def test_shacl_invalid_missing_indicator():
    doc = [{
      "@context": CTX,
      "@id": "kg://strategy/bad",
      "@type": "Strategy",
      "signature": "bad",
      "name": "Bad",
      "timeframe": "1h",
      "hasRule": [{"@id": "kg://rule/bad/entry/1"}, {"@id": "kg://rule/bad/exit/2"}],
      "hasSource": [{"@id": "kg://doc/bad/1"}]
    }]
    from orjson import dumps
    conforms, report = run_shacl_jsonld(dumps(doc).decode(), SHAPES)
    assert not conforms
