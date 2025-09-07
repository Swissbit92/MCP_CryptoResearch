# packages/mcp_strategy_research/mcp_strategy_research/storage.py
import os, json, hashlib, time, re
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage"))
DIRS = {
    "raw": os.path.join(ROOT, "raw"),
    "normalized": os.path.join(ROOT, "normalized"),
    "results": os.path.join(ROOT, "results"),
}

def init_storage():
    os.makedirs(ROOT, exist_ok=True)
    for d in DIRS.values():
        os.makedirs(d, exist_ok=True)

def _sha1(s: bytes) -> str:
    return hashlib.sha1(s).hexdigest()

def write_raw_text(text: str) -> str:
    h = _sha1(text.encode("utf-8"))
    path = os.path.join(DIRS["raw"], f"{h}.txt")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return f"research://raw/{h}.txt"

def write_normalized(obj: Dict[str, Any]) -> str:
    # id = sha1 of name + url + timestamp for uniqueness
    base = (obj.get("name","") + "|" + (obj.get("sources",[{}])[0].get("url",""))).encode("utf-8")
    h = _sha1(base + str(time.time()).encode("ascii"))
    path = os.path.join(DIRS["normalized"], f"{h}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return f"research://normalized/{h}.json"

def _norm_str(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _sig_for_strategy_obj(obj: Dict[str, Any]) -> str:
    """
    Build a stable signature from key content:
    - name
    - timeframe
    - indicator names (sorted; params are usually reflected in rules)
    - entry/exit rules text (joined, normalized)
    """
    name = _norm_str(obj.get("name", ""))
    timeframe = _norm_str(obj.get("timeframe", ""))
    inds = obj.get("indicators") or []
    ind_names = ",".join(sorted(_norm_str(i.get("name","")) for i in inds))
    entry_rules = obj.get("entry_rules") or []
    exit_rules = obj.get("exit_rules") or []
    rules_text = _norm_str(" ".join([*(r or "" for r in entry_rules), *(r or "" for r in exit_rules)]))
    blob = f"{name}|{timeframe}|{ind_names}|{rules_text}"
    return _sha1(blob.encode("utf-8"))

def _parse_normalized_uri(uri: str) -> Optional[str]:
    """
    Accepts 'research://normalized/<key>.json' and returns '<key>.json' (filename).
    """
    if not isinstance(uri, str):
        return None
    prefix = "research://normalized/"
    if not uri.startswith(prefix) or not uri.endswith(".json"):
        return None
    key = uri[len(prefix):]
    # key should be '<id>.json'
    return key

def _load_normalized_json_by_uri(uri: str) -> Optional[Dict[str, Any]]:
    key = _parse_normalized_uri(uri)
    if not key:
        return None
    path = os.path.join(DIRS["normalized"], key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def bundle_results(strategy_uris: List[str]) -> Dict[str, Any]:
    """
    Write a results bundle while dropping near-duplicates:
    - For each normalized strategy URI, load and compute a signature.
    - Keep only the first URI per signature.
    - Return same shape as before.
    """
    deduped: List[str] = []
    seen_sigs = set()

    for uri in strategy_uris or []:
        obj = _load_normalized_json_by_uri(uri)
        if obj is None:
            # If we can't load it, keep the URI (fail-open)
            deduped.append(uri)
            continue
        sig = _sig_for_strategy_obj(obj)
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)
        deduped.append(uri)

    payload = {"strategies": deduped, "created_ts": int(time.time())}
    h = _sha1(json.dumps(payload, sort_keys=True).encode("utf-8"))
    path = os.path.join(DIRS["results"], f"{h}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"uri": f"research://results/{h}.json", **payload}

def read_resource(kind: str, key: str) -> Dict[str, Any]:
    path = os.path.join(DIRS[kind], key)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{kind} missing: {key}")
    if path.endswith(".txt"):
        with open(path, "r", encoding="utf-8") as f:
            return {"uri": f"research://{kind}/{key}", "text": f.read()}
    with open(path, "r", encoding="utf-8") as f:
        return {"uri": f"research://{kind}/{key}", "json": json.load(f)}
