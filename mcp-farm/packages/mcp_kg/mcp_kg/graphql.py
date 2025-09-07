# mcp-farm/packages/mcp_kg/mcp_kg/graphql.py
from __future__ import annotations
from typing import Optional
from .kg_store import KGStore, KGConfig

def graphql_query(query: str, store: Optional[KGStore]=None):
    store = store or KGStore(KGConfig())
    if store.cfg.backend != "terminus":
        return {"error": "GraphQL only available with backend=terminus"}
    client = store._client  # type: ignore
    if client is None:
        store._ensure_backend()
        client = store._client
    # TerminusDB python client exposes WOQL; GraphQL is typically via HTTP endpoint.
    # For PR1, return a stub and recommend switching to GraphQL endpoint call in PR2.
    return {"warning": "GraphQL passthrough not fully wired in PR1"}
