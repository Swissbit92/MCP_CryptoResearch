# mcp-farm/packages/mcp_kg/mcp_kg/kg_store.py
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from rdflib import Dataset, Graph, Namespace
from dotenv import load_dotenv

try:
    from terminusdb_client import WOQLClient
except Exception:
    WOQLClient = None  # optional in CI

load_dotenv()

EX = Namespace("https://example.org/crypto-kg#")
SCHEMA = Namespace("https://schema.org/")

@dataclass
class KGConfig:
    backend: str = os.getenv("KG_STORE_BACKEND", "memory")  # "terminus" or "memory"
    terminus_url: str = os.getenv("TERMINUSDB_URL", "http://localhost:6363")
    terminus_db: str = os.getenv("TERMINUSDB_DB", "stratkg")
    terminus_user: str = os.getenv("TERMINUSDB_USER", "admin")
    terminus_token: str = os.getenv("TERMINUSDB_TOKEN", "changeme")
    context_path: str = os.getenv("KG_CONTEXT_PATH", "packages/mcp_kg/mcp_kg/resources/context.jsonld")
    ontology_path: str = os.getenv("KG_ONTOLOGY_PATH", "packages/mcp_kg/mcp_kg/resources/ontology.ttl")
    shapes_path: str = os.getenv("KG_SHAPES_PATH", "packages/mcp_kg/mcp_kg/resources/shapes.ttl")

class KGStore:
    def __init__(self, cfg: Optional[KGConfig]=None):
        self.cfg = cfg or KGConfig()
        self._memory_graph: Optional[Dataset] = None  # <-- Dataset now
        self._client: Optional[WOQLClient] = None

    # ---------------- Backends ----------------
    def _ensure_backend(self):
        if self.cfg.backend == "memory":
            if self._memory_graph is None:
                self._memory_graph = Dataset()
                # Load ontology into the default graph so classes/properties exist
                if os.path.exists(self.cfg.ontology_path):
                    self._memory_graph.parse(self.cfg.ontology_path, format="turtle")
            return
        if self.cfg.backend == "terminus":
            if WOQLClient is None:
                raise RuntimeError("terminusdb-client not installed")
            if self._client is None:
                self._client = WOQLClient(self.cfg.terminus_url)
                self._client.connect(db=self.cfg.terminus_db, user=self.cfg.terminus_user, key=self.cfg.terminus_token)
            return
        raise RuntimeError(f"Unknown backend: {self.cfg.backend}")

    # --------------- Schema ensure ---------------
    def ensure_schema(self, ontology_ttl: str):
        self._ensure_backend()
        if self.cfg.backend == "memory":
            self._memory_graph.parse(data=ontology_ttl, format="turtle")
        else:
            # Manage schema in TerminusDB via console/import for PR1.
            pass

    # --------------- Insert / Upsert ---------------
    def validate_jsonld_with_shacl(self, jsonld_str: str, shapes_ttl: str) -> Tuple[bool, str]:
        from .validators.shacl import run_shacl_jsonld
        return run_shacl_jsonld(jsonld_str, shapes_ttl)

    def insert_jsonld(self, jsonld_str: str) -> None:
        self._ensure_backend()
        if self.cfg.backend == "memory":
            # Parse JSON-LD into Dataset (fixes ConjunctiveGraph deprecation)
            self._memory_graph.parse(data=jsonld_str, format="json-ld")
        else:
            assert self._client is not None
            import json
            docs = json.loads(jsonld_str)
            if isinstance(docs, dict):
                docs = [docs]
            self._client.insert_document(docs)

    # --------------- Queries ---------------
    def get_strategy_by_signature(self, signature: str) -> Optional[str]:
        self._ensure_backend()
        if self.cfg.backend == "memory":
            g = self._memory_graph
            q = f"""
            PREFIX ex: <{EX}>
            PREFIX schema: <{SCHEMA}>
            CONSTRUCT {{
              ?s ?p ?o .
              ?iu ?pi ?oi .
              ?r ?pr ?or .
              ?d ?pd ?od .
            }} WHERE {{
              ?s ex:signature "{signature}" .
              ?s ?p ?o .
              OPTIONAL {{ ?s ex:usesIndicator ?iu . ?iu ?pi ?oi . }}
              OPTIONAL {{ ?s ex:hasRule ?r . ?r ?pr ?or . }}
              OPTIONAL {{ ?s ex:hasSource ?d . ?d ?pd ?od . }}
            }}
            """
            res = g.query(q)
            out = Graph()
            for t in res.graph.triples((None, None, None)):
                out.add(t)
            return out.serialize(format="json-ld")
        else:
            return None

    def search_strategies(self, indicators: List[str], timeframe: Optional[str], universe: Optional[List[str]], limit: int=50) -> List[Dict[str, Any]]:
        self._ensure_backend()
        if self.cfg.backend != "memory":
            return []

        g = self._memory_graph

        def _lit_list(vals: List[str]) -> str:
            escaped = [f"\"{v}\"" for v in vals]
            return " ".join(escaped)

        where_lines: List[str] = [
            "?s a ex:Strategy ;",
            "   schema:name ?name ;",
            "   ex:signature ?sig ;",
            "   ex:timeframe ?tf .",
        ]

        if universe:
            where_lines.append("?s ex:universe ?u .")
            where_lines.append(f"VALUES ?u {{ {_lit_list(universe)} }}")
        else:
            where_lines.append("OPTIONAL { ?s ex:universe ?u . }")

        if timeframe:
            where_lines.append(f'FILTER(?tf = "{timeframe}")')

        if indicators:
            where_lines.append("?s ex:usesIndicator ?iu . ?iu schema:name ?indName .")
            where_lines.append(f"VALUES ?indName {{ {_lit_list(indicators)} }}")

        q = f"""
        PREFIX ex: <{EX}>
        PREFIX schema: <{SCHEMA}>
        SELECT DISTINCT ?s ?name ?tf ?sig WHERE {{
          {' '.join(where_lines)}
        }} LIMIT {int(limit)}
        """

        rows = g.query(q)
        out = []
        for (s, name, tf, sig) in rows:
            out.append({
                "uri": str(s),
                "name": str(name),
                "timeframe": str(tf),
                "signature": str(sig),
            })
        return out

    def export_graph_jsonld(self) -> str:
        self._ensure_backend()
        if self.cfg.backend == "memory":
            # Serialize the dataset (default graph content) to JSON-LD
            return self._memory_graph.serialize(format="json-ld")
        return "[]"
