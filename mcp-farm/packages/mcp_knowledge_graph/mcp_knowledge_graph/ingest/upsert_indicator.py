from ..db.graphdb_client import sparql_update
from ..utils.ids import sha1

def upsert_indicator(canonical_name: str) -> None:
    iri = f"<http://example.org/indicator#{canonical_name}>"
    update = f"""
PREFIX kg:   <http://example.org/kg#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
DELETE {{ {iri} ?p ?o }}
INSERT {{
  {iri} a kg:Indicator ;
       rdfs:label "{canonical_name}" .
}}
WHERE {{ OPTIONAL {{ {iri} ?p ?o }} }}
"""
    sparql_update(update)
