import os
import json
import requests
from typing import Any, Dict, Optional

# Load .env (CWD first, then repo root fallback)
try:
    from dotenv import load_dotenv
    loaded = load_dotenv()
    if not loaded:
        here = os.path.dirname(__file__)
        repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
        load_dotenv(os.path.join(repo_root, ".env"))
except Exception:
    pass

GRAPHDB_BASE = os.getenv("GRAPHDB_BASE", "http://localhost:7200").rstrip("/")
REPO         = os.getenv("GRAPHDB_REPOSITORY", "eeva_kg")

# Optional HTTP Basic Auth
AUTH = None
if os.getenv("GRAPHDB_USER") and os.getenv("GRAPHDB_PASSWORD"):
    AUTH = (os.getenv("GRAPHDB_USER"), os.getenv("GRAPHDB_PASSWORD"))

SPARQL_UPDATE_URL = f"{GRAPHDB_BASE}/repositories/{REPO}/statements"
SPARQL_QUERY_URL  = f"{GRAPHDB_BASE}/repositories/{REPO}"

# REST GraphQL endpoints (preferred)
GQL_REST_DEFAULT  = f"{GRAPHDB_BASE}/rest/repositories/{REPO}/graphql"
def _gql_rest_named(schema_id: str) -> str:
    return f"{GRAPHDB_BASE}/rest/repositories/{REPO}/graphql/{schema_id}"

# Legacy UI paths (fallback only)
GQL_LEGACY_ROOT   = f"{GRAPHDB_BASE}/graphql"
def _gql_legacy_named(schema_id: str) -> str:
    return f"{GRAPHDB_BASE}/graphql/{schema_id}"


def sparql_update(update: str) -> None:
    r = requests.post(
        SPARQL_UPDATE_URL,
        data=update.encode("utf-8"),
        headers={
            "Content-Type": "application/sparql-update",
            "Accept": "application/sparql-results+json,application/json,text/plain,*/*"
        },
        auth=AUTH,
    )
    if not r.ok:
        msg = f"SPARQL UPDATE failed [{r.status_code}] at {r.url}\n--- RESPONSE ---\n{r.text[:2000]}"
        raise requests.HTTPError(msg, response=r)


def sparql_query(query: str, accept: str = "application/sparql-results+json") -> Dict[str, Any]:
    r = requests.get(SPARQL_QUERY_URL, params={"query": query}, headers={"Accept": accept}, auth=AUTH)
    r.raise_for_status()
    return r.json()


def list_graphql_endpoints() -> Dict[str, Any]:
    url = f"{GRAPHDB_BASE}/rest/repositories/{REPO}/graphql/endpoints"
    r = requests.get(url, headers={"Accept": "application/json"}, auth=AUTH)
    r.raise_for_status()
    return r.json()


def graphql(query: str,
            variables: Optional[Dict[str, Any]] = None,
            endpoint: Optional[str] = None,
            operation_name: Optional[str] = None) -> Dict[str, Any]:
    """
    REST-first GraphQL for GraphDB 11:
      - GET /rest/repositories/{repo}/graphql                 (default schema)
      - GET /rest/repositories/{repo}/graphql/{schemaId}      (named schema)
    Falls back to legacy UI endpoints if REST fails.
    """
    vars_obj = variables or {}
    params = {"query": query}
    if vars_obj:
        params["variables"] = json.dumps(vars_obj)
    if operation_name:
        params["operationName"] = operation_name

    # --- Try REST (preferred) ---
    url = _gql_rest_named(endpoint) if endpoint else GQL_REST_DEFAULT

    # Prefer GET (per REST API docs)
    r = requests.get(url, params=params, headers={"Accept": "application/json"}, auth=AUTH)
    if r.ok:
        data = r.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])
        return data.get("data", data)

    # Try POST JSON (still REST)
    r = requests.post(
        url,
        json={"query": query, "variables": vars_obj, "operationName": operation_name},
        headers={"Accept": "application/json"},
        auth=AUTH,
    )
    if r.ok:
        data = r.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])
        return data.get("data", data)

    # --- Fallback to legacy UI endpoints (/graphql) ---
    # 1) POST to named path or root
    if endpoint:
        url = _gql_legacy_named(endpoint)
        r = requests.post(url, params={"repository": REPO}, json={"query": query, "variables": vars_obj},
                          headers={"Accept": "application/json"}, auth=AUTH)
    else:
        url = GQL_LEGACY_ROOT
        r = requests.post(url, params={"repository": REPO}, json={"query": query, "variables": vars_obj},
                          headers={"Accept": "application/json"}, auth=AUTH)
    if r.ok:
        data = r.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])
        return data.get("data", data)

    # 2) GET legacy with params
    if endpoint:
        url = _gql_legacy_named(endpoint)
        r = requests.get(url, params={"repository": REPO, **params}, headers={"Accept": "application/json"}, auth=AUTH)
    else:
        url = GQL_LEGACY_ROOT
        r = requests.get(url, params={"repository": REPO, **params}, headers={"Accept": "application/json"}, auth=AUTH)
    if r.ok:
        data = r.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])
        return data.get("data", data)

    raise RuntimeError(f"GraphQL failed. Status={r.status_code}, url={r.url}, body={r.text[:500]}")
