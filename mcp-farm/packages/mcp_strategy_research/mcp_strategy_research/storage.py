# packages/mcp_strategy_research/mcp_strategy_research/storage.py
import os, json, hashlib, time
from typing import Any, Dict, List

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

def bundle_results(strategy_uris: List[str]) -> Dict[str, Any]:
    payload = {"strategies": strategy_uris, "created_ts": int(time.time())}
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
