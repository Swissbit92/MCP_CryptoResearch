{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Strategy v1",
  "type": "object",
  "required": [
    "schema_version",
    "name",
    "description",
    "universe",
    "timeframe",
    "indicators",
    "entry_rules",
    "exit_rules",
    "sources",
    "confidence"
  ],
  "properties": {
    "schema_version": { "const": "strategy.v1" },
    "name": { "type": "string" },
    "description": { "type": "string" },
    "universe": { "type": "array", "items": { "type": "string" } },
    "timeframe": { "type": "string" },
    "indicators": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name","params"],
        "properties": {
          "name": { "type": "string" },
          "params": { "type": "object" }
        }
      }
    },
    "entry_rules": { "type": "array", "items": { "type": "string" } },
    "exit_rules":  { "type": "array", "items": { "type": "string" } },
    "position_sizing": { "type": ["object","null"] },
    "defaults": { "type": ["object","null"] },
    "backtest_hints": { "type": ["object","null"] },
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["url"],
        "properties": {
          "url": { "type": "string" },
          "doi": { "type": ["string","null"] }
        }
      }
    },
    "confidence": { "type": "object" }
  },
  "additionalProperties": true
}
