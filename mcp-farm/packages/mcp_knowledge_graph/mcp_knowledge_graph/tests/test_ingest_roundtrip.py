import os
import time
import pytest

# Ensure .env is picked up even when pytest runs from repo root
try:
    from dotenv import load_dotenv
    loaded = load_dotenv()
    if not loaded:
        import pathlib
        here = pathlib.Path(__file__).resolve()
        repo_root = here.parents[3]
        load_dotenv(repo_root / ".env")
except Exception:
    pass

from mcp_knowledge_graph.db.graphdb_client import (
    sparql_query,
    sparql_update,
    graphql,
    list_graphql_endpoints,
)
from mcp_knowledge_graph.ingest.upsert_indicator import upsert_indicator
from mcp_knowledge_graph.ingest.upsert_strategy import upsert_strategy


def graphdb_alive() -> bool:
    """Health check using a trivial ASK query."""
    try:
        res = sparql_query("ASK { ?s ?p ?o }")
        return isinstance(res, dict) and ("boolean" in res or "results" in res)
    except Exception:
        return False


def gql_alive() -> bool:
    """
    GraphQL health check via REST (/rest/repositories/.../graphql[/schemaId]).
    Requires endpoint id in .env: GRAPHDB_GQL_ENDPOINT (e.g., 'eeva').
    """
    endpoint = os.getenv("GRAPHDB_GQL_ENDPOINT")
    if not endpoint:
        return False
    try:
        data = graphql("query { __typename }", endpoint=endpoint)
        return isinstance(data, dict) and data.get("__typename") == "Query"
    except Exception:
        return False


@pytest.mark.skipif(not graphdb_alive(), reason="GraphDB not reachable—check .env GRAPHDB_BASE/GRAPHDB_REPOSITORY and that Desktop is running.")
def test_ingest_roundtrip_sparql():
    """
    Inserts indicators (RSI/MACD/ATR) then a minimal Strategy via thin upsert.
    Verifies its presence via SPARQL. If SHACL fails, the raised error includes GraphDB's response body.
    """
    ping = """
INSERT DATA {
  <http://example.org/test#ping> <http://example.org/test#ok> "1" .
}
"""
    sparql_update(ping)

    for ind in ("RSI", "MACD", "ATR"):
        upsert_indicator(ind)

    doc = {
        "id": "test_swing_1",
        "name": "Test RSI MACD Swing",
        "family": "indicator",
        "signals": {
            "entry": ["RSI(14) crosses_below 30 THEN crosses_above 30 AND MACD_line > MACD_signal"],
            "exit":  ["RSI(14) crosses_below 70 OR trailing_stop(ATR(14), multiple=2)"]
        },
        "indicators": [
            {"canonical_name": "RSI",  "role": "entry",   "params": {"period": 14, "overSold": 30, "overBought": 70}},
            {"canonical_name": "MACD", "role": "confirm", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"canonical_name": "ATR",  "role": "stop",    "params": {"period": 14, "multiple": 2}}
        ]
    }
    upsert_strategy(doc)
    time.sleep(0.2)

    q = """
PREFIX kg: <http://example.org/kg#>
SELECT ?s WHERE {
  ?s a kg:Strategy ;
     kg:name "Test RSI MACD Swing" .
}
LIMIT 1
"""
    res = sparql_query(q)
    bindings = res.get("results", {}).get("bindings", [])
    assert len(bindings) == 1, f"Expected 1 strategy, got: {bindings}"


@pytest.mark.skipif(not gql_alive(), reason="GraphQL endpoint not reachable—set GRAPHDB_GQL_ENDPOINT in .env and create endpoint in Workbench.")
def test_graphql_lookup_if_endpoint_exists():
    """
    REST-native GraphQL smoke test:
    - Introspects the schema to discover which root field exposes Strategy instances
      (field name varies; may not be 'strategies').
    - Ensures demo Strategy exists (upsert again, idempotent).
    - Queries that field and asserts there is data.
    """
    endpoint = os.getenv("GRAPHDB_GQL_ENDPOINT")

    eps = list_graphql_endpoints()
    ep_ids = [e.get("id") for e in eps] if isinstance(eps, list) else []
    assert endpoint in ep_ids, f"GraphQL endpoint '{endpoint}' not in {ep_ids}"

    doc = {
        "id": "test_swing_1",
        "name": "Test RSI MACD Swing",
        "family": "indicator",
        "signals": {
            "entry": ["RSI(14) crosses_below 30 THEN crosses_above 30 AND MACD_line > MACD_signal"],
            "exit":  ["RSI(14) crosses_below 70 OR trailing_stop(ATR(14), multiple=2)"]
        },
        "indicators": [
            {"canonical_name": "RSI",  "role": "entry",   "params": {"period": 14, "overSold": 30, "overBought": 70}},
            {"canonical_name": "MACD", "role": "confirm", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"canonical_name": "ATR",  "role": "stop",    "params": {"period": 14, "multiple": 2}}
        ]
    }
    upsert_strategy(doc)

    introspect = """
query Introspect {
  __schema {
    queryType {
      fields { name }
    }
  }
}
"""
    schema_data = graphql(introspect, endpoint=endpoint)
    fields = [f["name"] for f in schema_data["__schema"]["queryType"]["fields"]]
    candidates = [f for f in fields if "strategy" in f.lower()]
    if not candidates:
        pytest.skip(f"No Strategy-like root field found. Available fields: {fields}")

    field = candidates[0]

    q_try = f"""
query {{
  {field} {{
    __typename
    id
    name
  }}
}}
"""
    try:
        data = graphql(q_try, endpoint=endpoint)
        value = data.get(field)
        assert value is not None, f"Field '{field}' missing in GraphQL data: {data}"
        if isinstance(value, list):
            assert len(value) >= 1, f"Expected at least one item from '{field}', got empty list."
            assert "__typename" in value[0], f"Missing __typename in first item from '{field}'."
        elif isinstance(value, dict):
            assert "__typename" in value, f"Missing __typename in '{field}' object."
        else:
            pytest.skip(f"Unexpected shape for field '{field}': {type(value)}")
    except Exception:
        q_fallback = f"query {{ {field} {{ __typename }} }}"
        data = graphql(q_fallback, endpoint=endpoint)
        value = data.get(field)
        assert value is not None, f"Field '{field}' missing in GraphQL data: {data}"
        if isinstance(value, list):
            assert len(value) >= 1, f"Expected at least one item from '{field}', got empty list."
            assert "__typename" in value[0], f"Missing __typename in first item from '{field}'."
        elif isinstance(value, dict):
            assert "__typename" in value, f"Missing __typename in '{field}' object."
        else:
            pytest.skip(f"Unexpected shape for field '{field}': {type(value)}")
