import hashlib
from slugify import slugify

def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()

def strategy_iri(name: str, family: str, signals_canon: str) -> str:
    """
    Stable, URL-safe IRI for strategies.
    Uses a short sha1 token from (name|family|signals_canon) to avoid spaces/() etc.
    """
    token = sha1(f"{name}|{family}|{signals_canon}")[:10]
    return f"http://example.org/strategy#{slugify(name)}-{token}"

def rule_iri(dsl: str) -> str:
    return f"http://example.org/rule#{sha1(dsl)[:16]}"

def indicator_usage_iri(strategy_iri: str, indicator_name: str, role: str) -> str:
    base = sha1(f"{strategy_iri}|{indicator_name}|{role}")[:16]
    return f"http://example.org/indicatorUsage#{base}"
