# mcp-farm/packages/mcp_kg/mcp_kg/validators/shacl.py
from __future__ import annotations
from typing import Tuple
from rdflib import Graph, Dataset
from pyshacl import validate

def run_shacl_ttl(data_graph_ttl: str, shapes_ttl: str) -> Tuple[bool, str]:
    # TTL parsing does not trigger the JSON-LD deprecation, Graph is fine here
    data_g = Graph()
    data_g.parse(data=data_graph_ttl, format="turtle")
    shapes_g = Graph()
    shapes_g.parse(data=shapes_ttl, format="turtle")
    conforms, _, report_text = validate(
        data_graph=data_g,
        shacl_graph=shapes_g,
        inference="rdfs",
        debug=False
    )
    return bool(conforms), str(report_text)

def run_shacl_jsonld(jsonld_str: str, shapes_ttl: str) -> Tuple[bool, str]:
    # Parse JSON-LD into a Dataset to avoid ConjunctiveGraph deprecation
    data_ds = Dataset()
    data_ds.parse(data=jsonld_str, format="json-ld")
    data_g = data_ds.default_context  # use default graph for SHACL
    shapes_g = Graph()
    shapes_g.parse(data=shapes_ttl, format="turtle")
    conforms, _, report_text = validate(
        data_graph=data_g,
        shacl_graph=shapes_g,
        inference="rdfs",
        debug=False
    )
    return bool(conforms), str(report_text)
