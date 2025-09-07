# 📦 MCP_KG — Knowledge Graph MCP (TerminusDB + SHACL)

**Milestone A** for the Strategy Research MCP adds a Knowledge Graph MCP using **TerminusDB** (JSON‑LD + optional GraphQL) with **pySHACL** validation **before writes**.  
It indexes **normalized strategies**, **indicators (with SKOS synonyms)**, **rules**, **evidence spans**, **provenance (PROV‑O)**, and **optional whitepapers/tokens** so research results can be tied to first‑party docs (e.g., Bitcoin whitepaper).

---

## ✨ What you get

- **MCP server** `mcp_kg` with tools:
  - `kg_upsert_strategy(normalized_uri)` — ingest a normalized `strategy.v1` JSON (from `research://normalized/*.json`), SHACL‑validate, upsert to KG.
  - `kg_upsert_whitepaper(whitepaper_uri)` — ingest a whitepaper JSON (title/url/doi/date/authors/token), SHACL‑validate, upsert to KG.
  - `kg_search(indicators[], timeframe?, universe?, limit)` — find strategies by indicators/timeframe/universe.
  - `kg_get_strategy_by_signature(signature)` — fetch JSON‑LD for a strategy.
  - `kg_validate(resource_uri)` — SHACL validation only (no insert).
  - `kg_query_graphql(query)` — passthrough (stub in A; wire real GraphQL in PR2).
- **JSON‑LD @context** mapping `strategy.v1 → ontology`.
- **Ontology (Turtle)** with: `Strategy`, `Indicator`, `IndicatorUse` (reified params), `Rule` (entry/exit ops), `EvidenceSpan`, `Document`, `ExtractionRun`, **`Token`**, **`Whitepaper`**, `Agent`.
- **SHACL shapes** for `Strategy`, `IndicatorUse`, `Rule`, `Whitepaper`, `Token`.
- **Store layer** with **TerminusDB** backend or **in‑memory rdflib** fallback (great for tests/CI).
- **Mapper**: strategy → JSON‑LD (now links `targetsToken` from strategy `universe` symbols).
- **Mapper**: whitepaper → JSON‑LD (mints `Whitepaper`, `Token`, `Agent` nodes).
- **Streamlit MVP** UI (search + details).

Repo layout (new):
```
mcp-farm/
  packages/
    mcp_kg/
      pyproject.toml
      mcp_kg/
        __init__.py
        server.py                # MCP surface & tool wiring
        kg_store.py              # TerminusDB client + memory fallback
        validators/
          shacl.py               # pySHACL runner
        mappers/
          strategy_to_jsonld.py  # strategy.v1 → JSON-LD
          whitepaper_to_jsonld.py# whitepaper → JSON-LD
        resources/
          context.jsonld         # JSON-LD context
          ontology.ttl           # Ontology (incl. Token, Whitepaper)
          shapes.ttl             # SHACL shapes
      tests/
        test_shacl_minimal.py
        test_upsert_and_fetch.py
        # (optional) test_upsert_whitepaper.py
      README.md  # (this file content)
  apps/
    kg_streamlit/
      requirements.txt
      streamlit_app.py
```

---

## 🚀 Install (dev)

```bash
# from repo root
pip install -e packages/mcp_kg
```

Python ≥ 3.10 recommended.

---

## 🔧 Environment

Add to your **.env** (document only; do not commit secrets):

```
TERMINUSDB_URL=http://localhost:6363
TERMINUSDB_DB=stratkg
TERMINUSDB_USER=admin
TERMINUSDB_TOKEN=changeme
KG_STORE_BACKEND=memory  # or "terminus" to use TerminusDB
KG_CONTEXT_PATH=packages/mcp_kg/mcp_kg/resources/context.jsonld
KG_ONTOLOGY_PATH=packages/mcp_kg/mcp_kg/resources/ontology.ttl
KG_SHAPES_PATH=packages/mcp_kg/mcp_kg/resources/shapes.ttl
```

Update **mcp.json** to register the server (stdio):
```json
{
  "servers": {
    "kg": {
      "command": "kg-mcp",
      "transport": { "type": "stdio" },
      "env": {}
    }
  }
}
```

---

## 🗄️ Backend options

### Memory (default for tests/CI)
Set `KG_STORE_BACKEND=memory`. No external services needed.

### TerminusDB (recommended for real use)
- Run TerminusDB locally (example using Docker):
  ```bash
  docker run -it --rm -p 6363:6363 \
    -e TERMINUSDB_SERVER_DB_PATH='/data' \
    -v $PWD/.terminusdb:/data \
    terminusdb/terminusdb-server:latest
  ```
- Set `KG_STORE_BACKEND=terminus` and fill `TERMINUSDB_*` envs.
- Create/connect DB `stratkg` (via TerminusDB console).  
  > In Milestone A, ontology is also kept as TTL files. You can import/migrate to TerminusDB’s schema graph in PR2.

---

## ▶️ Run the MCP server

```bash
npx @modelcontextprotocol/inspector --config mcp.json --server kg
```

Try tools:

- **Upsert a strategy** (normalized JSON from the Strategy Research MCP):
  ```json
  {
    "tool": "kg_upsert_strategy",
    "args": { "normalized_uri": "research://normalized/<id>.json" }
  }
  ```

- **Upsert a whitepaper** (simple JSON with token & authors):
  ```json
  {
    "tool": "kg_upsert_whitepaper",
    "args": { "whitepaper_uri": "whitepapers/bitcoin.json" }
  }
  ```

- **Search**:
  ```json
  {
    "tool": "kg_search",
    "args": { "indicators": ["RSI","MACD"], "timeframe": "1h", "universe": ["BTCUSDT"], "limit": 20 }
  }
  ```

- **Get strategy by signature**:
  ```json
  {
    "tool": "kg_get_strategy_by_signature",
    "args": { "signature": "sig123" }
  }
  ```

- **Validate only (no insert)**:
  ```json
  {
    "tool": "kg_validate",
    "args": { "resource_uri": "research://normalized/<id>.json" }
  }
  ```

---

## 🧬 Data model highlights

- **Strategy** links:
  - `usesIndicator` → **IndicatorUse** (reified params)
  - `hasRule` → **Rule** (direction/operator/left/right, text)
  - `hasSource` → **Document** (url/doi) with PROV support
  - `targetsToken` → **Token** (from `universe` symbols like `BTCUSDT` → `BTC` token node)
- **Whitepaper** links:
  - `describesToken` → **Token**
  - `authoredBy` → **Agent**
  - `cites` → **Document**

All inserts are **SHACL‑validated** before commit.

---

## 🧪 Tests

```bash
pytest -q packages/mcp_kg/tests
```

What they cover:
- `test_shacl_minimal.py` — valid/invalid JSON‑LD against shapes.
- `test_upsert_and_fetch.py` — memory backend: upsert a strategy, fetch by signature, search.
- *(Optional)* `test_upsert_whitepaper.py` — memory backend: upsert a whitepaper and assert token exists.

---

## 🖥️ Streamlit MVP

Install and run:
```bash
pip install -r apps/kg_streamlit/requirements.txt
streamlit run apps/kg_streamlit/streamlit_app.py
```
- Sidebar filters: indicators/timeframe/universe.
- Results: click a card to view its JSON‑LD.

---

## 📚 Files to look at

- `mcp_kg/resources/ontology.ttl` — merged ontology (Strategy, IndicatorUse, Rule, EvidenceSpan, Token, Whitepaper, Agent).
- `mcp_kg/resources/shapes.ttl` — SHACL constraints (Strategy, IndicatorUse, Rule, Whitepaper, Token).
- `mappers/strategy_to_jsonld.py` — generates JSON‑LD, mints Token nodes and links via `targetsToken`.
- `mappers/whitepaper_to_jsonld.py` — maps lightweight whitepaper JSON to Whitepaper/Token/Agent nodes.

---

## 🛣️ Roadmap (PR2 ideas)

- Evidence span nodes & UI highlights.
- Backtest nodes (`BacktestRun`, metrics, datasets).
- Real TerminusDB GraphQL passthrough + query builder helpers.
- Auto‑upsert from Strategy Research MCP after normalization.
- Indicator SKOS synonyms bootstrap from Indicators MCP.

---

## 📄 Whitepaper JSON example

```jsonc
{
  "key": "bitcoin-whitepaper",
  "title": "Bitcoin: A Peer-to-Peer Electronic Cash System",
  "url": "https://bitcoin.org/bitcoin.pdf",
  "published_on": "2008-10-31",
  "token": { "symbol": "BTC", "name": "Bitcoin" },
  "authors": ["Satoshi Nakamoto"],
  "citations": []
}
```

Ingest via:
```json
{
  "tool": "kg_upsert_whitepaper",
  "args": { "whitepaper_uri": "whitepapers/bitcoin.json" }
}
```

---

## ✅ Definition of Done (Milestone A)
- MCP server starts and lists tools.
- `kg_upsert_strategy` and `kg_upsert_whitepaper` accept real JSON, pass SHACL, and persist.
- `kg_search` returns inserted strategy using indicators/timeframe/universe filters.
- `kg_get_strategy_by_signature` returns JSON‑LD graph (Strategy + nodes).
- All tests green.
- Streamlit shows search + details.

---

**Have fun connecting strategies ↔ tokens ↔ whitepapers with clean provenance!** 🔗
