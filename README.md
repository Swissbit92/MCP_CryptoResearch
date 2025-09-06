# 🧪 MCP Farm (Monorepo) — Indicators MCP is Live

Welcome! This repo hosts a **farm of MCP servers** for quantitative research and trading.  
Current status: **Indicators MCP** ✅; shared library ✅; Inspector config ✅.  
Next up: **Strategy Research MCP** (LLM + Brave + arXiv).

---

## 🗺️ Repository Layout

```
mcp-farm/
├─ mcp.json                      # Inspector config (stdio) → launches Indicators MCP
├─ .env                          # runtime knobs for servers (optional)
├─ libs/
│  └─ mcp_common/                # shared helpers (URIs, schemas, etc.)
│     ├─ pyproject.toml
│     └─ mcp_common/
│        └─ uri.py
└─ packages/
   └─ mcp_indicators/
      ├─ pyproject.toml
      └─ mcp_indicators/
         ├─ server.py            # FastMCP server entrypoint
         └─ indicators/
            ├─ registry.py       # indicator metadata + validation + compute()
            └─ backends/
               ├─ __init__.py
               └─ pandas_ta_backend.py
```

---

## 🧰 Requirements

- 🐍 **Python 3.11** (virtual environment recommended)
- 📦 **pip**
- 🪟 **Windows + PowerShell** (tested on Win 11)
- ⚙️ **Node.js LTS** (for the MCP Inspector UI)
  - Install: `winget install OpenJS.NodeJS.LTS`

> Indicators MCP is CPU-only and offline; **no API keys** required yet.

---

## 🚀 Quick Start (Windows / PowerShell)

> All commands run **from repo root**: `...\mcp-farm>`.

### 1) Create & activate venv + install deps

```powershell
# venv (example path)
py -3.11 -m venv ..\MCP_CryptoResearch
..\MCP_CryptoResearch\Scripts\Activate.ps1

# pip + core deps (MCP CLI, pandas-ta stack)
python -m pip install --upgrade pip
pip install "mcp[cli]" pandas pyarrow pandas-ta
```

### 2) Install local packages (editable)

```powershell
pip install -e libs\mcp_common
pip install -e packages\mcp_indicators
```

### 3) Ensure Node + npx are on PATH

```powershell
$env:Path = "C:\Program Files\nodejs;$env:Path"
node -v
npm -v
npx -v
```

---

## ⚙️ Configuration Files

### 📄 `mcp.json` (Inspector config, **UTF‑8 w/out BOM**)

> Lives at repo root. Spawns the Indicators MCP via your venv Python.

```json
{
  "mcpServers": {
    "default-server": {
      "type": "stdio",
      "command": "C:\\\\Users\\\\<you>\\\\MCP_CryptoResearch\\\\Scripts\\\\python.exe",
      "args": ["-m", "mcp_indicators.server"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "INDICATORS_MCP_PREVIEW_ROWS": "8"
      }
    }
  }
}
```

**Safe way to write without BOM (PowerShell):**
```powershell
$py = "$env:VIRTUAL_ENV\Scripts\python.exe"
$pyJson = $py -replace '\\','\\'
$json = @"
{
  "mcpServers": {
    "default-server": {
      "type": "stdio",
      "command": "$pyJson",
      "args": ["-m", "mcp_indicators.server"],
      "env": { "PYTHONUNBUFFERED": "1", "INDICATORS_MCP_PREVIEW_ROWS": "8" }
    }
  }
}
"@
[System.IO.File]::WriteAllText(
  (Join-Path (Get-Location) 'mcp.json'),
  $json,
  (New-Object System.Text.UTF8Encoding($false)) # <- no BOM
)
```

### 🌿 `.env` (optional runtime knobs)

> Read by `server.py` via `python-dotenv`.

```env
# Indicators MCP
INDICATORS_MCP_PREVIEW_ROWS=8
INDICATORS_MCP_LOG_LEVEL=INFO
INDICATORS_MCP_BACKEND=pandas_ta
INDICATORS_MCP_MAX_ROWS=200000
INDICATORS_MCP_TIMEOUT_MS=10000
```

In `server.py`, we load it like:

```python
from dotenv import load_dotenv
load_dotenv()

import os
PREVIEW_ROWS = int(os.getenv("INDICATORS_MCP_PREVIEW_ROWS", "5"))
```

---

## ▶️ Run

### 🖥️ Option A — Inspector UI (recommended)

```powershell
npx @modelcontextprotocol/inspector --config .\mcp.json
```
- UI opens at `http://localhost:6274`
- Spawns server with your venv Python via stdio

### 🧩 Option B — Headless server

```powershell
python -m mcp_indicators.server
```

---

## 🧠 What the Indicators MCP Exposes

### 🛠️ Tools
- `list_indicators()` → `["RSI","SMA","EMA", ...]`
- `describe_indicator(name)` → metadata (params, outputs, etc.)
- `validate_params(name, params?)` → fills defaults + checks types/ranges
- `load_csv_dataset(dataset_id, path, date_col?, tz?)` → in-memory dataset
- `compute_indicator(dataset_id, name, params?, backend="pandas_ta")` → mutates DF, returns `{new_columns, spec, row_count}`
- `preview_ohlcv(dataset_id, limit=5)` → preview first N rows

### 📚 Resources
- `indicators://index` → list of indicator names
- `indicators://{name}` → full descriptor JSON
- `ohlcv://{dataset_id}` → table preview (rows controlled by `INDICATORS_MCP_PREVIEW_ROWS`)

---

## ✅ Smoke Test (in Inspector)

1. **Tools →** `list_indicators`  
2. **Tools →** `describe_indicator` with `"RSI"`  
3. **Tools →** `load_csv_dataset`  
   - `dataset_id="btc_1d"`  
   - `path="C:\path\ohlcv.csv"`  
   - `date_col="date"` (if present)  
4. **Tools →** `compute_indicator`  
   - `dataset_id="btc_1d"`, `name="RSI"`, `params={"window":14}`  
5. **Resources →** open `ohlcv://btc_1d` (or **Tools →** `preview_ohlcv` with `limit=10`)

**CSV expectations:** columns like `date,open,high,low,close,volume`. If `date` exists, it becomes a UTC index (optionally converted via `tz`).

---

## 🧯 Troubleshooting (Windows)

- **`npx not found`** → Install Node LTS and refresh current shell PATH:
  ```powershell
  $env:Path = "C:\Program Files\nodejs;$env:Path"
  node -v; npm -v; npx -v
  ```

- **Inspector says “No servers found in config file”** → Ensure top-level key is `mcpServers` and the file is **UTF‑8 w/out BOM**.

- **`spawn uv ENOENT` when using `mcp dev …`** → Either install `uv` or skip `mcp dev` and use `npx … --config mcp.json`.

- **Resource signature error** → For `@mcp.resource("ohlcv://{dataset_id}")`, the function must accept **only** `dataset_id`.

- **Dataclasses / `from __future__ import annotations` issue** → Avoid in `server.py` to prevent Windows import quirks when Inspector loads by file path.

- **BOM error (`Unexpected token '﻿'`)** → Re-write JSON using `UTF8Encoding($false)` as shown above.

- **Import path for backend** → `pandas_ta_backend.py` lives under `mcp_indicators.indicators.backends`. The registry imports it via a **package‑relative** path.

---

## 🧭 Roadmap

- **Strategy Research MCP** (`packages/mcp_strategy_research`)  
  - 🔎 `plan_queries`, `brave_search (site:arxiv.org)`, `fetch_url`,  
    🧠 `extract_strategies`, 🗂️ `normalize_strategy`, 📦 `bundle_results`  
  - Outputs: JSON schema consumable by Strategy Generator MCP.

- **Backtester MCP**  
  - Wrap backtest runner; return metrics + equity curve as resources.

- **Trading MCP**  
  - Paper/live trading tools (guarded by flags & env).

- **Orchestrator (LangGraph)**  
  - Optional later for multi-source fan‑out, retries, dedupe, and chaining:  
    Research → Generator → Backtester → (Trading).

---

## 🛠️ Dev Tips

- Re-run `pip install -e` after adding **new packages** or **entrypoints**.
- Keep shared contracts/JSON Schemas in `libs/mcp_common`.
- Version each MCP independently via its `pyproject.toml`.

---

## ⚖️ License

TBD.

---

### ✉️ Notes

- Runtime knobs via `.env`  
- Inspector config: `mcp.json`  
- Entry point: `python -m mcp_indicators.server`
