# 🧪 MCP Farm (Monorepo) — Indicators MCP ✅ • Strategy Research MCP ✅

Welcome! This repo hosts a **farm of MCP servers** for quantitative research and trading.
- **Indicators MCP** — compute + validate TA indicators over your OHLCV data.
- **Strategy Research MCP** — LLM-powered researcher that finds papers (arXiv fast‑path + Brave), extracts TA rules, and normalizes results into a JSON schema.

---

## 🗺️ Repository Layout

```
mcp-farm/
├─ mcp.json                      # Inspector config (stdio) → launches both servers
├─ .env                          # runtime knobs (Brave key, Ollama model, etc.)
├─ libs/
│  └─ mcp_common/                # shared helpers (URIs, schemas, etc.)
│     ├─ pyproject.toml
│     └─ mcp_common/
│        └─ uri.py               # (example shared util)
└─ packages/
   ├─ mcp_indicators/
   │  ├─ pyproject.toml
   │  └─ mcp_indicators/
   │     ├─ server.py            # FastMCP server entrypoint
   │     └─ indicators/
   │        ├─ registry.py       # metadata + validation + compute()
   │        └─ backends/
   │           └─ pandas_ta_backend.py
   └─ mcp_strategy_research/
      ├─ pyproject.toml
      └─ mcp_strategy_research/
         ├─ server.py            # FastMCP server entrypoint
         ├─ brave.py             # Brave + arXiv search helpers
         ├─ fetcher.py           # robots-aware fetch (HTML/PDF → text)
         ├─ extractor.py         # LangChain + Ollama extractor (LLM-first with fallback)
         ├─ normalizer.py        # JSON schema v1 validation + storage
         ├─ prompts.py           # query planning & extraction prompts
         ├─ host_helpers/
         │  └─ indicator_synonyms.py  # build llm_hint from Indicators MCP metadata
         ├─ schemas/
         │  └─ strategy_v1.json  # normalized strategy schema (packaged)
         ├─ storage/             # research:// raw/normalized/results artifacts
         └─ tests/
            └─ test_smoke_pipeline.py
```

---

## 🧰 Requirements

- 🐍 **Python 3.11** (virtual environment recommended)
- 🪟 **Windows + PowerShell** (tested on Win 11)
- 📦 **pip**
- ⚙️ **Node.js LTS** (for the MCP Inspector UI) — `winget install OpenJS.NodeJS.LTS`
- 🧠 **Ollama** (for the Strategy Research MCP extractor)
  - Recommended default in `.env`: `qwen2.5:14b-instruct` (fallback `llama3.1:8b`)
  - Ensure `ollama serve` is running and the models are pulled:  
    `ollama pull qwen2.5:14b-instruct` and `ollama pull llama3.1:8b`
- 🔎 **Brave Search API key** (optional but recommended; arXiv fast‑path works without it)

---

## ⚙️ Configuration Files

### 📄 `mcp.json` (Inspector config)

The repo’s `mcp.json` defines two stdio servers:

```jsonc
{
  "mcpServers": {
    "indicators": {
      "type": "stdio",
      "command": "indicators-mcp",
      "args": [],
      "env": { "PYTHONUNBUFFERED": "1", "INDICATORS_MCP_PREVIEW_ROWS": "8" }
    },
    "strategy-research": {
      "type": "stdio",
      "command": "strategy-research-mcp",
      "args": [],
      "env": { "PYTHONUNBUFFERED": "1", "RESEARCH_USER_AGENT": "StrategyResearchMCP/0.1 (+contact)" }
    }
  }
}
```

> If Inspector says “Multiple servers found in config file. Please specify one with --server.”, start with e.g.:
> ```powershell
> npx @modelcontextprotocol/inspector --config .\mcp.json --server indicators
> npx @modelcontextprotocol/inspector --config .\mcp.json --server strategy-research
> ```

### 🌿 `.env` (runtime knobs)

> Read at startup via `python-dotenv`.

```env
# Indicators MCP
INDICATORS_MCP_PREVIEW_ROWS=8
INDICATORS_MCP_LOG_LEVEL=INFO
INDICATORS_MCP_BACKEND=pandas_ta
INDICATORS_MCP_MAX_ROWS=200000
INDICATORS_MCP_TIMEOUT_MS=10000

# Strategy Research MCP
BRAVE_API_KEY= <your_brave_key>       # optional; arXiv API fast-path works without it
RESEARCH_MAX_CONCURRENCY=4
RESEARCH_USER_AGENT=StrategyResearchMCP/0.1 (+contact)

# Ollama (LLM extractor)
OLLAMA_MODEL=qwen2.5:14b-instruct
OLLAMA_MODEL_FALLBACK=llama3.1:8b-instruct
```

> Tip: If you change `.env`, restart the server process that loaded it.

---

## 🚀 Quick Start (Windows / PowerShell)

Run from repo root: `...\mcp-farm>`

### 1) Create & activate a venv + upgrade pip
```powershell
py -3.11 -m venv ..\MCP_CryptoResearch
..\MCP_CryptoResearch\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2) Install local packages (editable)
```powershell
pip install -e libs\mcp_common
pip install -e packages\mcp_indicators
pip install -e packages\mcp_strategy_research
```

### 3) (Optional) Pull Ollama models
```powershell
ollama pull qwen2.5:14b-instruct
ollama pull llama3.1:8b-instruct
```

### 4) Launch Inspector for each server (separately)
```powershell
# Indicators MCP
npx @modelcontextprotocol/inspector --config .\mcp.json --server indicators

# Strategy Research MCP
npx @modelcontextprotocol/inspector --config .\mcp.json --server strategy-research
```

The Inspector UI opens at `http://localhost:6274` and will spawn the selected server via stdio.

---

## 🧠 Indicators MCP — What It Exposes

### 🛠️ Tools
- `list_indicators()` → `["RSI","SMA","EMA", ...]`
- `describe_indicator(name)` → metadata (params, outputs, etc.)
- `validate_params(name, params?)` → fill defaults + check types/ranges
- `load_csv_dataset(dataset_id, path, date_col?, tz?)` → load into memory
- `compute_indicator(dataset_id, name, params?, backend="pandas_ta")` → mutates DF, returns `{new_columns, spec, row_count}`
- `preview_ohlcv(dataset_id, limit=5)` → first N rows

### 📚 Resources
- `indicators://index` → list of indicator names
- `indicators://{name}` → descriptor JSON
- `ohlcv://{dataset_id}` → table preview (rows controlled by `INDICATORS_MCP_PREVIEW_ROWS`)

> Entry point: `python -m mcp_indicators.server` (used by the `indicators-mcp` script).

---

## 🔎 Strategy Research MCP — What It Exposes (v0.1)

### 🧩 Tools
- `plan_queries(topic, indicators[], max_per_indicator=3, source="arxiv")` → heuristic query strings
- `brave_search(query, max_results=10, site="arxiv.org")` → arXiv API fast‑path, Brave fallback
- `fetch_url(url, render_js=false)` → respects robots.txt + throttles (~1–2 req/s), extracts text (HTML/PDF)
- `extract_strategies(text, indicators[]?, llm_hint?)` → LLM extractor (LangChain `OllamaLLM`), synonyms bias via `llm_hint`
- `normalize_strategy(doc, source_url, indicators[])` → schema‑v1 validation + canonicalization + persistence
- `bundle_results(strategies[])` → write `research://results/<id>.json` (list of normalized URIs)

### 📚 Resources
- `research://raw/<sha1>.txt`           — raw text of fetched page/PDF
- `research://normalized/<id>.json`     — one normalized strategy
- `research://results/<id>.json`        — bundle of strategy URIs + timestamp

### 🧠 LLM Hint (synonyms) — Host‑side helper
Use the included helper to build a JSON `llm_hint` from your canonical indicators + synonyms (often from Indicators MCP metadata):

```python
from mcp_strategy_research.host_helpers.indicator_synonyms import build_llm_hint_from_registry

canonical = ["RSI","MACD","ATR"]
registry_synonyms = {
  "RSI":  ["Relative Strength Index"],
  "MACD": ["Moving Average Convergence Divergence"],
  "ATR":  ["Average True Range"],
}
llm_hint = build_llm_hint_from_registry(canonical, registry_synonyms)
# -> '{"synonyms":{"ATR":["Average True Range"],"MACD":["Moving Average Convergence Divergence"],"RSI":["Relative Strength Index"]}}'
```

Pass that `llm_hint` string into `extract_strategies(...)` to bias the LLM toward mapping synonyms to canonical names.

### 🔒 Politeness & Limits
- `fetcher.py` enforces robots.txt checks and a global throttle (≈ 0.6s between requests).
- PDF text extraction uses PyMuPDF (`fitz`).
- JS rendering is **off** by default; leave it off unless you truly need it.

---

## ✅ Smoke Test

A tiny end‑to‑end smoke test is included for the Strategy Research MCP.

```powershell
python -m pytest packages\mcp_strategy_research\tests\test_smoke_pipeline.py -q
# Expected: 1 passed
```

The test:
1. Builds an `llm_hint` using the helper above.
2. Runs the extractor (LLM if available; falls back to a deterministic template).
3. Normalizes into schema‑v1 and writes artifacts under `packages/mcp_strategy_research/mcp_strategy_research/storage/`.
4. Asserts schema validity and presence of required fields.

> Note: Running the test does **not** hit the network and will pass even if Ollama is unavailable (fallback path).

---

## 🛠️ Dev Tips

- Re‑run `pip install -e` after adding new packages or entry points.
- Keep shared contracts/JSON Schemas in `libs/mcp_common` or package `schemas/`.
- For Windows JSON files (like `mcp.json`), ensure **UTF‑8 without BOM** to avoid Inspector parse issues.
- If Inspector reports multiple servers, select one with `--server`.
- Ollama: keep `ollama serve` running; confirm models are available with `ollama list`.

---

## 🧭 Roadmap

- **Strategy Research MCP**: extend sources (SSRN, selected blogs & forums), dedupe/merge, retry fan‑out.
- **Backtester MCP**: wrap a backtest runner; return metrics + equity curve as resources.
- **Orchestrator (LangGraph)**: optional coordinator to chain Research → Generator → Backtester.

---

## ⚖️ License

TBD.
