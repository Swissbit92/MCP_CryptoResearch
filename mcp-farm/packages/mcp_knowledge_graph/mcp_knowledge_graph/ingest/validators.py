import json
from typing import Dict, Any

def validate_normalized_strategy(doc: Dict[str, Any]) -> None:
    required = ["id", "name", "family", "signals", "indicators"]
    for k in required:
        if k not in doc:
            raise ValueError(f"Missing required field: {k}")
    if doc["family"] not in ("indicator", "ml", "hybrid"):
        raise ValueError("family must be indicator|ml|hybrid")
    if not doc["signals"].get("entry"):
        raise ValueError("At least one entry signal required")
