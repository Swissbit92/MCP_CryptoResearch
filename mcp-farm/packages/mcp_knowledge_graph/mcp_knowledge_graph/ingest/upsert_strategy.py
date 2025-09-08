import json
from typing import Dict, Any, List
from ..db.graphdb_client import sparql_update
from ..utils.ids import strategy_iri, rule_iri, indicator_usage_iri, sha1
from ..utils.dsl import normalize_dsl

def _triple(s: str, p: str, o: str) -> str:
    return f"{s} {p} {o} .\n"

def upsert_strategy(doc: Dict[str, Any]) -> None:
    name = doc["name"]
    family = doc["family"]
    entry_rules: List[str] = doc["signals"].get("entry", [])
    exit_rules:  List[str] = doc["signals"].get("exit", [])
    indicators:  List[Dict[str, Any]] = doc.get("indicators", [])

    # Build a canonical signals string then hash it for a safe IRI token
    sig_canon_list = [normalize_dsl(r) for r in entry_rules + exit_rules]
    sig_canon = "__".join(sorted(sig_canon_list))
    s_iri = f"<{strategy_iri(name, family, sig_canon)}>"

    triples = []
    triples.append(_triple(s_iri, "a", "kg:Strategy"))
    triples.append(_triple(s_iri, "kg:name", f"\"{name}\""))
    triples.append(_triple(s_iri, "kg:family", f"\"{family}\""))

    # Rules
    for dsl in entry_rules:
        r_iri = f"<{rule_iri(dsl)}>"
        triples.append(_triple(r_iri, "a", "kg:EntryRule"))
        triples.append(_triple(r_iri, "kg:dsl", f"\"\"\"{dsl}\"\"\""))
        triples.append(_triple(s_iri, "kg:hasEntryRule", r_iri))

    for dsl in exit_rules:
        r_iri = f"<{rule_iri(dsl)}>"
        triples.append(_triple(r_iri, "a", "kg:ExitRule"))
        triples.append(_triple(r_iri, "kg:dsl", f"\"\"\"{dsl}\"\"\""))
        triples.append(_triple(s_iri, "kg:hasExitRule", r_iri))

    # IndicatorUsage
    for iu in indicators:
        canonical = iu.get("canonical_name")
        role = iu.get("role", "filter")
        params = json.dumps(iu.get("params", {})).replace('"', '\\"')
        iu_iri = f"<{indicator_usage_iri(s_iri, canonical, role)}>"
        ind_iri = f"<http://example.org/indicator#{canonical}>"
        triples.append(_triple(iu_iri, "a", "kg:IndicatorUsage"))
        triples.append(_triple(iu_iri, "kg:ofIndicator", ind_iri))
        triples.append(_triple(iu_iri, "kg:role", f"\"{role}\""))
        triples.append(_triple(iu_iri, "kg:params", f"\"{params}\""))
        triples.append(_triple(s_iri, "kg:usesIndicator", iu_iri))

    insert = "PREFIX kg: <http://example.org/kg#>\nINSERT DATA {\n" + "".join(triples) + "}"
    sparql_update(insert)
