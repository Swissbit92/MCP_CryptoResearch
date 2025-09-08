"""
MCP-KG tool surface (skeleton). Wire these functions to your FastMCP server.
"""

from .db.graphdb_client import graphql, sparql_update
from .ingest.upsert_indicator import upsert_indicator
from .ingest.upsert_strategy import upsert_strategy
from .ingest.validators import validate_normalized_strategy

def tool_query_graphql(query: str, variables: dict | None = None, endpoint: str | None = None):
    return graphql(query, variables, endpoint)

def tool_upsert_indicator(payload: dict):
    name = payload["canonical_name"]
    upsert_indicator(name)
    return {"ok": True}

def tool_upsert_strategy(payload: dict):
    validate_normalized_strategy(payload)
    upsert_strategy(payload)
    return {"ok": True}

def tool_validate_shapes(entity_type: str, payload: dict):
    # For MVP, we run client-side schema checks; SHACL runs server-side in GraphDB on insert.
    # Optionally: call a SHACL endpoint if you enable it via GraphDB's Validation API.
    validate_normalized_strategy(payload) if entity_type == "Strategy" else None
    return {"ok": True, "violations": []}

def tool_get_strategy_by_intent(intent: dict):
    # Simple mapper: build vars for the GraphQL query file
    indicators = intent.get("indicators", [])
    asset = intent.get("asset", "BTCUSDT")
    timeframe = intent.get("timeframe", "1h")
    text = intent.get("text", "")
    query = open(__file__.replace("server.py","queries/strategy_by_intent.graphql"), "r", encoding="utf-8").read()
    return graphql(query, {"asset": asset, "timeframe": timeframe, "indicators": indicators, "text": text})
