# 🧪 MCP Farm (Monorepo) — Indicators MCP + Strategy Research MCP

Welcome! This repo hosts a **farm of MCP servers** for quantitative research and trading.

**Status**
- ✅ `mcp_indicators` — compute/validate TA indicators (pandas_ta backend).
- ✅ `mcp_strategy_research` — LLM-based strategy researcher (arXiv fast‑path + Brave Search + Ollama).
- ✅ Inspector config and smoke tests.

---

## 🗺️ Repository Layout

```
mcp-farm/
├─ mcp.json                      # Inspector config (stdio) → launches both servers
├─ .env                          # runtime knobs (BRAVE_API_KEY, OLLAMA_MODEL, etc.)
├─ libs/
│  └─ mcp_common/
│     ├─ pyproject.toml
│     └─ mcp_common/
│        └─ uri.py
└─ packages/
   ├─ mcp_indicators/
   │  ├─ pyproject.toml
   │  └─ mcp_indicators/
   │     ├─ server.py
   │     └─ indicators/
   │        ├─ registry.py
   │        └─ backends/
   │           └─ pandas_ta_backend.py
   └─ mcp_strategy_research/
      ├─ pyproject.toml
      └─ mcp_strategy_research/
         ├─ server.py
         ├─ brave.py               # Brave & arXiv search (arXiv API fast-path)
         ├─ fetcher.py             # robots-aware fetcher (HTML/PDF → text)
         ├─ extractor.py           # LLM extractor (LangChain + OllamaLLM)
         ├─ normalizer.py          # JSON schema (strategy.v1) coercion + save
         ├─ prompts.py             # query planner + extraction prompt builder
         ├─ storage.py             # resource URIs (research://...)
         ├─ host_helpers/
         │  └─ indicator_synonyms.py  # build llm_hint from Indicators MCP metadata
         └─ schemas/
            └─ strategy_v1.json
      └─ tests/
         └─ test_smoke_pipeline.py
```

---

## 🧰 Requirements

- 🐍 **Python 3.11** (virtual environment recommended)
- 🪟 **Windows + PowerShell** (tested on Win 11)
- ⚙️ **Node.js LTS** for the MCP Inspector UI (`npx`)
- 🧠 **Ollama** running locally (default at `http://localhost:11434`)
  - Recommended model (reasoning‑friendly): `qwen2.5:14b-instruct`
  - Fallback: `llama3.1:8b-instruct`
- 🔎 **(Optional) Brave Search API key** for broader web search
  - arXiv queries use the **arXiv API** fast‑path and do not require Brave.

---

## 🚀 Setup (Windows / PowerShell)

> All commands from repo root: `...\\mcp-farm>`

### 1) Create & activate venv, update pip

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

### 3) (Optional) Test dependencies

```powershell
python -m pip install -U pytest
```

### 4) Install Node (if needed)

```powershell
# Ensure Node is on PATH for npx
node -v; npm -v; npx -v
```

### 5) Run Ollama & pull models

```powershell
# In a separate shell or before running tests
ollama --version
ollama pull qwen2.5:14b-instruct
ollama pull llama3.1:8b-instruct
```

---

## ⚙️ Configuration

### `.env`

Put at repo root. Loaded automatically (via `python-dotenv`).

```env
# Strategy Research MCP
RESEARCH_USER_AGENT=StrategyResearchMCP/0.1 (+contact)
RESEARCH_MAX_CONCURRENCY=4
BRAVE_API_KEY=your_key_if_you_have_one

# Ollama (LangChain OllamaLLM)
OLLAMA_MODEL=qwen2.5:14b-instruct
OLLAMA_MODEL_FALLBACK=llama3.1:8b-instruct
# OLLAMA_HOST=http://localhost:11434  # default; set if non-standard
```

### `mcp.json` (Inspector config)

Already included in repo. It launches both servers with stdio:

```json
{
  "mcpServers": {
    "indicators": {
      "type": "stdio",
      "command": "indicators-mcp",
      "args": [],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "INDICATORS_MCP_PREVIEW_ROWS": "8"
      }
    },
    "strategy-research": {
      "type": "stdio",
      "command": "strategy-research-mcp",
      "args": [],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "RESEARCH_USER_AGENT": "StrategyResearchMCP/0.1 (+contact)"
      }
    }
  }
}
```

> **Tip (Windows JSON encoding):** Ensure the file is UTF‑8 **without BOM**.

---

## ▶️ Running (Inspector UI)

Launch Inspector and choose a server:

```powershell
npx @modelcontextprotocol/inspector --config .\mcp.json --server indicators
npx @modelcontextprotocol/inspector --config .\mcp.json --server strategy-research
```

The UI opens at `http://localhost:6274` and connects via stdio.

---

## 🧠 Indicators MCP — What It Exposes

**Tools**
- `list_indicators()` → `["RSI","SMA","EMA", ...]`
- `describe_indicator(name)` → metadata (params, outputs)
- `validate_params(name, params?)` → fill defaults + validate
- `load_csv_dataset(dataset_id, path, date_col?, tz?)`
- `compute_indicator(dataset_id, name, params?, backend="pandas_ta")`
- `preview_ohlcv(dataset_id, limit=5)`

**Resources**
- `indicators://index` (list of indicator names)
- `indicators://{name}` (descriptor)
- `ohlcv://{dataset_id}` (preview table; row count via `INDICATORS_MCP_PREVIEW_ROWS`)

---

## 🔎 Strategy Research MCP — Flow & Surface

**Goal (v0.1):** Given a topic & indicator list, find arXiv/WWW pages, extract TA strategies via LLM, normalize to a **strategy.v1** JSON schema, and save reproducible artifacts as **resources**.

**Tools**
- `plan_queries(topic, indicators[], max_per_indicator=3, source="arxiv")` → list of search strings.
- `brave_search(query, max_results=10, site="arxiv.org")` → results `[{title,url,snippet}]`.
  - arXiv fast‑path uses the **arXiv API**, then falls back to Brave (`BRAVE_API_KEY` optional).
- `fetch_url(url, render_js=false)` → `{url, content_type, text, meta, resource_uri}`; PDF→text via PyMuPDF; robots + 1–2 req/s throttle.
- `extract_strategies(text, indicators[]?, llm_hint?)` → LLM candidates (LangChain **OllamaLLM**). Falls back to a deterministic template if LLM unavailable.
- `normalize_strategy(doc, source_url, indicators[])` → validates/coerces to **strategy.v1**, writes a resource JSON; returns `{uri, json}`.
- `bundle_results(strategies[])` → writes `research://results/<id>.json` and returns its URI.

**Resources**
- `research://raw/<sha1>.txt` — raw page/PDF text.
- `research://normalized/<id>.json` — one normalized strategy.
- `research://results/<id>.json` — list of normalized strategies with creation ts.

**Prompts**
- `strategy_extraction_guidelines` — informational prompt.
- The extractor composes a system prompt from indicator names + optional synonyms (see below).

**Synonyms (host → llm_hint)**
Use `packages/mcp_strategy_research/mcp_strategy_research/host_helpers/indicator_synonyms.py`:

```python
from mcp_strategy_research.host_helpers.indicator_synonyms import build_llm_hint_from_registry

indicators = ["RSI","MACD","ATR"]
synonyms_map = {
  "RSI":  ["Relative Strength Index"],
  "MACD": ["Moving Average Convergence Divergence"],
  "ATR":  ["Average True Range"],
}
llm_hint = build_llm_hint_from_registry(indicators, synonyms_map)
# -> JSON string: {"synonyms":{"RSI":["Relative Strength Index"], ...}}
```

Pass `llm_hint` to `extract_strategies(...)` to bias canonicalization.

---

## ✅ Smoke Tests

### Pytest (end‑to‑end extractor → normalizer)

```powershell
python -m pytest packages\mcp_strategy_research\tests\test_smoke_pipeline.py -q
```

- If **Ollama** is running with the models pulled, the LLM path is used.
- If not, the extractor falls back to a deterministic template, and the test still passes.

---

## 🛡️ Politeness & Limits

- `fetch_url` respects **robots.txt** and throttles to ~**1–2 req/s** globally.
- JS rendering is **off by default** (set `render_js=true` only when needed).
- arXiv search path uses the **official API** first; Brave is an optional fallback.
- Missing `BRAVE_API_KEY` → `brave_search` will just return an empty list for non‑arXiv sites.

---

## 🔧 Troubleshooting

- **Inspector shows no servers** → ensure `--server indicators` or `--server strategy-research` is passed.
- **Ollama connection issues** → verify `OLLAMA_HOST` and that the models are pulled.
- **Validation errors in `normalize_strategy`** → the normalizer coerces rule objects → strings, canonicalizes indicators, and fixes `sources`. If input is too malformed, it raises a schema error.
- **Windows JSON BOM errors** → make sure JSON files are UTF‑8 without BOM.

---

## 🧭 Roadmap

- Add more sources (SSRN, reputable blogs) behind the same tool surface.
- Fan‑out orchestration (LangGraph), retries & de‑dup across sources.
- Strategy Generator MCP + Backtester MCP chain.
- Richer indicator synonym ingestion by calling the Indicators MCP registry on the host side.

---

## ⚖️ License

TBD.
