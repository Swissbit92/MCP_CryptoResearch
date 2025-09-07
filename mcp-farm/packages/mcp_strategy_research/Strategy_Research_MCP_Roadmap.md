# 🚀 Strategy Research MCP — Roadmap & Direction

> **Mission:** Build a reliable “discover → extract → normalize → backtest → learn” pipeline for TA-driven trading strategies with rock-solid provenance and reproducibility.

---

## 🧭 Guiding Principles

- 🧪 **Provenance-first:** Every artifact is reproducible, cited, and versioned.
- 📌 **Span-grounded extraction:** Rules are traceable to exact text spans (no hallucinations).
- 🔁 **Closed-loop learning:** Backtest results feed search focus, prompts, and ranking.
- 🛡️ **Politeness & licensing:** Respect robots.txt and document licenses.
- 🧱 **Composable MCPs:** Clear boundaries across acquisition, extraction, testing, and orchestration.

---

## 🗺️ Milestones

### 1) Orchestrate & Scale Discovery
- 🧠 **LangGraph coordinator** around MCPs (Indicators + Strategy Research; later Backtester/Generator).
- 🌐 **Source adapters** beyond arXiv/SSRN/IDEAS: curated blogs (Quantocracy, QuantStart, exchange research), GitHub notes, and conference proceedings.
- 🧾 **Doc store** with per-doc fingerprint, metadata (license/DOI/source type), and manifest (JSONL/Parquet).
- ⚡ **HTTP cache & de-dupe** across sources; explicit per-domain rate budgets.

### 2) Quality & Verification Layer
- 🧷 **Span-grounding:** Store character offsets for each extracted rule.
- 🧑‍⚖️ **Referee LLM:** Verify rule ↔ evidence alignment before normalization.
- 🧹 **Strategy linter:** Schema completeness, parameter sanity, indicator validation via Indicators MCP, and anti-lookahead checks.
- 🎚️ **Confidence model:** Score using evidence types, span coverage, source reputation, and extraction clarity.

### 3) Backtesting Loop (Closed-Loop)
- 🧩 **Generator handoff:** Feed normalized JSON to Strategy Generator MCP, then Backtester MCP.
- 🧪 **Micro-backtests:** Small OOS grid (symbols/timeframes/rolling windows). Capture Sharpe/CAGR/maxDD/tail/hit-rate/exposure.
- 🗂️ **Attach results:** Persist evaluation blocks inside `research://normalized/*` and leaderboard summary in `research://results/*`.
- 🏅 **Auto-ranking:** Robust metrics (e.g., ProbSharpe, underwater time) with complexity/overfit penalties.

### 4) Retrieval & Re-querying Intelligence
- 🗂️ **Local paper index (RAG):** Embed abstracts/sections; cross-encoder reranker; query by indicator combos & failure modes.
- 🎯 **Active search:** Underperformers trigger targeted re-search (e.g., “RSI divergence crypto drawdown mitigation”).
- 🧬 **Synonym expansion:** Harvest aliases/params/default thresholds from Indicators MCP to bias prompts and rules.

### 5) Human-in-the-Loop UX
- 📊 **Research dashboard:** Queue of candidates with spans, rule diffs, quick backtest sparklines, vote/notes.
- ✏️ **Inline editor:** Fix rules/params → round-trip normalized JSON; versioned.
- 🧰 **Curation dataset:** Every accept/reject/edit becomes training data for extractors and rerankers.

### 6) Ops, Packaging, and Safety
- 📦 **Containerize** servers; compose with LangGraph; `.env` templates.
- ✅ **CI/CD:** unit + contract tests for tools; live smoke with VCR cassettes for arXiv/SSRN.
- 👀 **Observability:** structured logs, timings, extraction pass rate, dedup ratio, error tags.
- ⚖️ **Licensing & ethics:** Store `license`, `robots` decision, and “commercial use safe?” flag per doc.
- 🧪 **Schema evolution:** versioned `strategy.v*`; migrations + compatibility checks.

### 7) Model Strategy (Local-first, Optional Cloud)
- 🧠 **Extractor ensemble:** Default local (Qwen 14B); “referee” (Llama 3.1 8B) for span checks; optional cloud flag for tough pages.
- 🪄 **Reranker:** Lightweight local cross-encoder (e.g., bge-reranker) for section selection before extraction.
- 🧾 **Few-shot bank:** Curated TA exemplars by indicator family (RSI/MACD/ATR/Bollinger/Volume). Auto-pick by detected indicators.

### 8) Productize the Dataset
- 🧊 **Snapshots:** Export `normalized` + `results` to S3/Drive with checksums.
- 🔎 **Searchable catalogue:** Web UI filters (indicator set, timeframe, asset class, metric thresholds).
- 🧭 **Release process:** Semantic versioning + changelog; reproducible seeds recorded.

---

## 📐 Current Capabilities (v0.1 Snapshot)

**Servers:** Indicators MCP (unchanged) + Strategy Research MCP  
**Discovery:** arXiv (API fast-path), SSRN & IDEAS (Brave allowlists)  
**Fetcher:** robots-aware; HTML/PDF ⇒ text; persists `research://raw/*`  
**Extractor:** LangChain + OllamaLLM; chunking + cross-chunk dedup; synonyms via `llm_hint`  
**Normalizer:** Canonicalizes indicators; stringifies structured rules (e.g., `trailing_stop(ATR, multiple=2.0)`); coerces sources/backtest_hints; validates against `strategy.v1`  
**Storage:** `research://normalized/*`, `research://results/*` with near-duplicate pruning

```text
         +----------------+       +-------------------+       +------------------+
         |  Indicators    |       | Strategy Research |       |  Backtester/     |
         |     MCP        |       |       MCP         |       |  Generator MCPs  |
         +--------+-------+       +-----+------+------+       +---------+--------+
                  |                     |      |                        |
                  | list indicators     |      | normalize/save         |
                  | + synonyms          |      | bundle                 |
                  v                     v      v                        |
             +---------+       +-----------------------+                |
             | Search  |-----> | fetch → extract →     |                |
             | (arXiv/ |       | normalize → dedup     |------> backtest/results
             | SSRN/   |       +-----------------------+                |
             | IDEAS)  |                                               v
             +---------+                                      +------------------+
                                                             | Ranking & Review |
                                                             +------------------+
```

---

## 📊 KPIs to Track

- ✅ **Extraction pass rate** (valid schema / total pages)
- 📎 **Grounding coverage** (% rules with evidence spans)
- ♻️ **Duplicate rate** pre/post dedup
- 🏃 **Backtest throughput** (strategies/day) & **win-rate** vs baselines
- ⏱️ **Time-to-insight** (doc fetch → ranked result)
- 🛠️ **Human correction rate** (lower is better)

---

## 🧩 Decisions to Make Now

1) **Source policy:** Which blogs/forums are “in” vs “out” (licensing + quality)?  
2) **Backtest budget:** What micro-grid (symbols/timeframes) is acceptable daily?  
3) **Confidence cutline:** Minimum score to auto-queue for backtesting?  
4) **Storage backend:** Remain filesystem or promote to SQLite/Parquet + tiny index?

---

## 🏁 Quick Next Actions

- 🧷 Implement **span-grounding** & the **referee LLM** gate.
- 🕸️ Add **curated blog adapters** (with robots/licensing metadata).
- 🧪 Wire the **backtesting loop** (micro-grid + leaderboard) and attach results to artifacts.
- 🧰 Stand up a **minimal dashboard** (spans, diffs, backtest sparkline, approve/reject).
- 🧱 Add **contract tests** for tools + VCR-smoked live sources.

> When you’re ready, I can scaffold the LangGraph orchestrator skeleton that runs: _discover → fetch → extract → normalize → verify → backtest → rank → bundle_.

---

### 🔧 Env Knobs (for reference)

- **Models:** `OLLAMA_MODEL` (default `qwen2.5:14b-instruct`), `OLLAMA_MODEL_FALLBACK` (`llama3.1:8b-instruct`)
- **Chunking/Dedup:** `RESEARCH_CHUNK_SIZE_CHARS`, `RESEARCH_CHUNK_OVERLAP_CHARS`, `RESEARCH_MAX_CHUNKS`, `RESEARCH_MAX_CANDIDATES`
- **Search:** `BRAVE_API_KEY` (for SSRN/IDEAS), arXiv needs none
- **Fetcher:** `RESEARCH_USER_AGENT` (robots-aware politeness)

---

*Version: v0.1 roadmap, generated for Strategy Research MCP.*
