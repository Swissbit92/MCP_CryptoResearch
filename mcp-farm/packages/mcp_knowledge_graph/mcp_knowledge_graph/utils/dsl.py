def normalize_dsl(dsl: str) -> str:
    return " ".join(dsl.strip().lower().replace("crosses above","crosses_above").replace("crosses below","crosses_below").split())
