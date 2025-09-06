# mcp-farm/packages/mcp_indicators/mcp_indicators/indicators/registry.py
"""
Pluggable, AI-friendly Indicator Registry.

Goals
-----
• Single source of truth for indicator *concepts* (name, params, descriptions, synonyms)
  and *compute bindings* (pandas-ta now; TA-Lib/vectorbt later).
• Rich metadata for AI/NLP: synonyms (multi-language), keywords, regex templates
  with {WINDOW} / {FAST}/{SLOW}/{SIGNAL}/{STDEV}/{THRESHOLD} placeholders, default thresholds,
  output name patterns to map library columns, and *mathematical formulas*.
• Public API:
    - IndicatorRegistry()
    - .list() -> [canonical names]
    - .resolve(name_or_alias) -> IndicatorDef
    - .describe(name) -> dict for UI/docs
    - .validate_params(name, params) -> filled/validated dict
    - .compute(df, name, params, backend="pandas_ta") -> {"columns":[...], "spec":{...}}
    - .get_regex_package(name, lang="en") -> compiled regex dict for detection
    - .export_json(path) -> write metadata to JSON for KG ingestion

Design
------
• Indicators are defined once; bindings map canonical param names to backend args.
• Column names are NOT hardcoded; we diff df.columns before/after backend call.
  "output_schema" supplies regex patterns to help downstream systems map columns.
• Each indicator can carry a FormulaSpec with LaTeX, pseudocode, and notes.

License: MIT
"""
from __future__ import annotations

import json
import re
import importlib
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# ---------------------------------
# Input aliasing for OHLCV columns
# ---------------------------------

_PRICE_ALIASES = {
    "open":   ["open", "Open", "OPEN", "o", "O"],
    "high":   ["high", "High", "HIGH", "h", "H"],
    "low":    ["low", "Low", "LOW", "l", "L"],
    "close":  ["close", "Close", "CLOSE", "c", "C", "price", "Price", "adj_close", "Adj Close"],
    "volume": ["volume", "Volume", "VOLUME", "vol", "Vol", "VOL"],
}

def _find_series(df, logical_name: str):
    for c in _PRICE_ALIASES.get(logical_name, []):
        if c in df.columns:
            return df[c]
    if logical_name in df.columns:  # final fallback
        return df[logical_name]
    raise KeyError(f"Required input '{logical_name}' not found in DataFrame columns: {df.columns.tolist()}")

# ---------------------------------
# Data classes
# ---------------------------------

@dataclass
class ParamSpec:
    name: str
    type: str      # "int","float","bool","str"
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[List[Any]] = None
    description: str = ""

@dataclass
class BackendBinding:
    backend: str   # "pandas_ta", "talib", "vectorbt"
    func: str      # target function name in the backend
    param_map: Dict[str, str] = field(default_factory=dict)   # canonical param -> backend arg
    input_map: Dict[str, str] = field(default_factory=dict)   # logical input -> backend arg

@dataclass
class OutputColumn:
    """Describe output columns to aid downstream mapping."""
    name_pattern: str            # regex, e.g., r"^RSI_(?P<window>\\d+)$"
    description: str = ""
    role: str = ""               # "main", "signal", "hist", "upper", "lower", "middle", etc.

@dataclass
class NLPHints:
    """Optional AI/regex metadata."""
    keywords: List[str] = field(default_factory=list)          # lightweight terms
    negative_keywords: List[str] = field(default_factory=list) # avoid false positives
    synonyms_by_lang: Dict[str, List[str]] = field(default_factory=dict) # {"en":[...], "de":[...]}
    regex_templates: List[str] = field(default_factory=list)   # e.g., r"\\bRSI\\s*\\(\\s*{WINDOW}\\s*\\)"
    examples: List[str] = field(default_factory=list)          # natural phrases for tests

@dataclass
class FormulaSpec:
    """Mathematical definition for documentation, validation, or KG export."""
    latex: str = ""                 # LaTeX string
    pseudocode: List[str] = field(default_factory=list)  # short steps
    notes: str = ""                 # caveats, standard defaults, bounds, variants

@dataclass
class IndicatorDef:
    # Concept
    name: str
    group: str                 # "trend","momentum","volatility","volume","price"
    description: str
    inputs: List[str]          # subset of ["open","high","low","close","volume"]
    params: List[ParamSpec]
    # Aliases & labels
    synonyms: List[str] = field(default_factory=list)           # quick aliases (no lang)
    source_labels: Dict[str, str] = field(default_factory=dict) # {"pandas_ta":"rsi","talib":"RSI","tradingview":"RSI"}
    # Defaults & output schema
    default_thresholds: Dict[str, float] = field(default_factory=dict) # {"overbought":70,"oversold":30}
    output_schema: List[OutputColumn] = field(default_factory=list)
    # Bindings
    bindings: List[BackendBinding] = field(default_factory=list)
    # NLP metadata
    nlp: NLPHints = field(default_factory=NLPHints)
    # Formulas
    formula: Optional[FormulaSpec] = None
    # Tags for taxonomy/graph
    tags: List[str] = field(default_factory=list)               # ["oscillator","reversal","mean-reversion"]
    references: List[Dict[str, str]] = field(default_factory=list) # [{"title":"...", "url":"..."}]

    # Helpers
    def param_defaults(self) -> Dict[str, Any]:
        return {p.name: p.default for p in self.params}

    def param_types(self) -> Dict[str, str]:
        return {p.name: p.type for p in self.params}

# ---------------------------------
# Registry
# ---------------------------------

class IndicatorRegistry:
    def __init__(self):
        self._defs: Dict[str, IndicatorDef] = {}
        self._syn_index: Dict[str, str] = {}  # alias(lower) -> canonical
        self._load_builtin_definitions()

    # ---- Public API ----

    def list(self) -> List[str]:
        return sorted(self._defs.keys())

    def resolve(self, name_or_alias: str) -> IndicatorDef:
        key = name_or_alias.strip().lower()
        if key in self._defs:  # exact canonical in lower
            return self._defs[key]
        if key in self._syn_index:
            return self._defs[self._syn_index[key]]
        # try raw (case-sensitive) canonical
        if name_or_alias in self._defs:
            return self._defs[name_or_alias]
        raise KeyError(f"Unknown indicator: '{name_or_alias}'. Known: {self.list()}")

    def describe(self, name_or_alias: str) -> Dict[str, Any]:
        idef = self.resolve(name_or_alias)
        d = asdict(idef)
        d["output_schema"] = [asdict(oc) if isinstance(oc, OutputColumn) else oc for oc in idef.output_schema]
        return d

    def validate_params(self, name_or_alias: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        idef = self.resolve(name_or_alias)
        params = params or {}
        out = idef.param_defaults()
        out.update(params)
        pmap = {p.name: p for p in idef.params}
        for k, v in out.items():
            if k not in pmap:
                raise ValueError(f"Unknown param '{k}' for {idef.name}")
            spec = pmap[k]
            if spec.type == "int":
                out[k] = int(v)
            elif spec.type == "float":
                out[k] = float(v)
            elif spec.type == "bool":
                if isinstance(v, bool):
                    pass
                else:
                    sv = str(v).lower()
                    if sv in ("1","true","yes","y"):
                        out[k] = True
                    elif sv in ("0","false","no","n"):
                        out[k] = False
                    else:
                        raise ValueError(f"Param '{k}' expects bool, got {v!r}")
            elif spec.type == "str":
                out[k] = str(v)
            val = out[k]
            if spec.min is not None and float(val) < spec.min:
                raise ValueError(f"Param '{k}'={val} < min {spec.min}")
            if spec.max is not None and float(val) > spec.max:
                raise ValueError(f"Param '{k}'={val} > max {spec.max}")
            if spec.choices is not None and val not in spec.choices:
                raise ValueError(f"Param '{k}'={val} not in {spec.choices}")
        return out

    def compute(self, df, name_or_alias: str, params: Optional[Dict[str, Any]] = None, backend: str = "pandas_ta") -> Dict[str, Any]:
        idef = self.resolve(name_or_alias)
        binding = next((b for b in idef.bindings if b.backend == backend), None)
        if not binding:
            raise NotImplementedError(f"{idef.name} has no binding for backend '{backend}'.")
        pvals = self.validate_params(idef.name, params)
        backend_args = {binding.param_map.get(k, k): v for k, v in pvals.items()}
        input_kwargs = {argname: _find_series(df, logical) for logical, argname in binding.input_map.items()}
        base_pkg = __package__ or "mcp_indicators.indicators"
        adapter = importlib.import_module(f"{base_pkg}.backends.pandas_ta_backend") if backend == "pandas_ta" else None
        if adapter is None:
            raise NotImplementedError(f"Backend '{backend}' not implemented")
        before = set(df.columns)
        adapter.call(df, func_name=binding.func, **{**input_kwargs, **backend_args})
        new_cols = [c for c in df.columns if c not in before]
        return {
            "columns": new_cols,
            "spec": {
                "name": idef.name,
                "params": pvals,
                "backend": backend,
                "func": binding.func,
                "inputs": idef.inputs,
            },
        }

    def get_regex_package(self, name_or_alias: str, lang: str = "en") -> Dict[str, Any]:
        """
        Build AI/NLP regex helpers for detection.
        Returns:
          {
            "synonyms": compiled_pattern,
            "templates": [compiled_template_regexes...],
            "keywords": set([...]),
            "negative_keywords": set([...]),
            "default_thresholds": {...}
          }
        """
        idef = self.resolve(name_or_alias)
        syns = set([idef.name] + idef.synonyms)
        syns |= set(idef.nlp.synonyms_by_lang.get(lang, []))
        syns |= set([
            idef.source_labels.get("tradingview",""),
            idef.source_labels.get("talib",""),
            idef.source_labels.get("pandas_ta","")
        ])
        syns = {s for s in syns if s}
        escaped = [re.escape(s) for s in sorted(syns, key=len, reverse=True)]
        synonyms_pat = re.compile(r"(?i)\b(" + "|".join(escaped) + r")\b") if escaped else re.compile(r"(?!x)x")
        compiled_templates = []
        repl = {
            "{WINDOW}": r"(?P<window>\d{1,3})",
            "{FAST}": r"(?P<fast>\d{1,3})",
            "{SLOW}": r"(?P<slow>\d{1,3})",
            "{SIGNAL}": r"(?P<signal>\d{1,3})",
            "{STDEV}": r"(?P<stdev>\d{1,2}(?:\.\d+)?)",
            "{THRESHOLD}": r"(?P<thresh>-?\d{1,3}(?:\.\d+)?)",
        }
        for tmpl in idef.nlp.regex_templates:
            pat = tmpl
            for k, v in repl.items():
                pat = pat.replace(k, v)
            compiled_templates.append(re.compile(pat, flags=re.IGNORECASE))
        return {
            "synonyms": synonyms_pat,
            "templates": compiled_templates,
            "keywords": set(idef.nlp.keywords),
            "negative_keywords": set(idef.nlp.negative_keywords),
            "default_thresholds": dict(idef.default_thresholds),
        }

    def export_json(self, path: str) -> None:
        """Export metadata for all indicators (concepts + labels + NLP hints + formulas; no data)."""
        out = []
        for name in self.list():
            out.append(self.describe(name))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

    def register(self, idef: IndicatorDef):
        if idef.name in self._defs:
            raise ValueError(f"Indicator '{idef.name}' already registered")
        self._defs[idef.name] = idef
        all_aliases = {idef.name} | set(idef.synonyms)
        for _, arr in idef.nlp.synonyms_by_lang.items():
            all_aliases |= set(arr)
        for _, v in idef.source_labels.items():
            if v:
                all_aliases.add(v)
        for alias in all_aliases:
            self._syn_index[alias.lower()] = idef.name

    # ---- Builtins ----

    def _load_builtin_definitions(self):
        P = ParamSpec
        B = BackendBinding
        OC = OutputColumn
        NL = NLPHints
        FS = FormulaSpec

        def _def(name, group, desc, inputs, params, synonyms, src_labels, defaults, out_schema, nlp, tags, refs, func, param_map, input_map, formula: Optional[FS]):
            self.register(IndicatorDef(
                name=name, group=group, description=desc, inputs=inputs, params=params,
                synonyms=synonyms, source_labels=src_labels,
                default_thresholds=defaults, output_schema=out_schema,
                nlp=nlp, tags=tags, references=refs, formula=formula,
                bindings=[B("pandas_ta", func, param_map, input_map)]
            ))

        # -------------------------------------------------------
        # Momentum / Oscillators
        # -------------------------------------------------------

        _def(
            name="RSI",
            group="momentum",
            desc="Relative Strength Index, momentum oscillator scaled 0–100.",
            inputs=["close"],
            params=[P("window","int",14,1,None,"Averaging length")],
            synonyms=["relative strength index"],
            src_labels={"pandas_ta":"rsi","talib":"RSI","tradingview":"RSI"},
            defaults={"overbought":70.0,"oversold":30.0},
            out_schema=[OC(r"^RSI_(?P<window>\d+)$","RSI value","main")],
            nlp=NL(
                keywords=["oscillator","momentum","overbought","oversold"],
                synonyms_by_lang={"en":["RSI","Relative Strength Index"], "de":["Relative-Stärke-Index","RSI"], "it":["Indice di Forza Relativa","RSI"]},
                regex_templates=[r"\bRSI\s*\(\s*{WINDOW}\s*\)", r"\bRelative\s+Strength\s+Index\b\s*\(\s*{WINDOW}\s*\)", r"\bRSI\b\s*(?:<=|<|>=|>)\s*{THRESHOLD}"],
                examples=["RSI(14) crosses above 30", "RSI(14) > 70 indicates overbought"],
            ),
            tags=["oscillator","momentum","bounded","0-100"],
            refs=[{"title":"RSI"}],
            func="rsi",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"RSI_t = 100 - \frac{100}{1 + RS_t},\quad RS_t=\frac{\text{RMA}(\text{gain}, n)}{\text{RMA}(\text{loss}, n)}",
                pseudocode=[
                    "gain = max(ΔClose, 0); loss = max(-ΔClose, 0)",
                    "avgGain = RMA(gain, n); avgLoss = RMA(loss, n)",
                    "RS = avgGain / avgLoss",
                    "RSI = 100 - 100 / (1 + RS)",
                ],
                notes="Wilder's smoothing (RMA). Bounded [0,100]."
            ),
        )

        _def(
            name="MFI",
            group="momentum",
            desc="Money Flow Index; volume-weighted RSI-like oscillator (0–100).",
            inputs=["high","low","close","volume"],
            params=[P("window","int",14,1,None,"Window")],
            synonyms=["money flow index"],
            src_labels={"pandas_ta":"mfi","talib":"MFI","tradingview":"MFI"},
            defaults={"overbought":80.0,"oversold":20.0},
            out_schema=[OC(r"^MFI_(?P<window>\d+)$","MFI value","main")],
            nlp=NL(
                keywords=["money flow","oscillator","volume"],
                synonyms_by_lang={"en":["MFI","Money Flow Index"]},
                regex_templates=[r"\bMFI\s*\(\s*{WINDOW}\s*\)", r"\bMFI\b\s*(?:<=|<|>=|>)\s*{THRESHOLD}"],
            ),
            tags=["oscillator","volume","bounded","0-100"],
            refs=[{"title":"MFI"}],
            func="mfi",
            param_map={"window":"length"},
            input_map={"high":"high","low":"low","close":"close","volume":"volume"},
            formula=FS(
                latex=r"\text{TP}_t=\frac{H_t+L_t+C_t}{3},\ \text{MF}_t=\text{TP}_t\cdot V_t,\ \text{MFR}_t=\frac{\sum \text{MF}^+}{\sum \text{MF}^-},\ \text{MFI}=100-\frac{100}{1+\text{MFR}}",
                pseudocode=[
                    "TP=(H+L+C)/3; MF=TP*Volume",
                    "Positive MF: TP_t>TP_{t-1}; Negative otherwise",
                    "MFR = sum_pos(MF, n)/sum_neg(MF, n)",
                    "MFI = 100 - 100/(1+MFR)",
                ],
                notes="Oscillator bounded [0,100]. Uses volume."
            ),
        )

        _def(
            name="MACD",
            group="momentum",
            desc="Moving Average Convergence Divergence; fast EMA minus slow EMA with signal line.",
            inputs=["close"],
            params=[P("fast","int",12,1,None,"Fast EMA length"), P("slow","int",26,1,None,"Slow EMA length"), P("signal","int",9,1,None,"Signal EMA length")],
            synonyms=["moving average convergence divergence"],
            src_labels={"pandas_ta":"macd","talib":"MACD","tradingview":"MACD"},
            defaults={"zero_line":0.0},
            out_schema=[
                OC(r"^MACD_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$","MACD line","main"),
                OC(r"^MACDs_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$","Signal","signal"),
                OC(r"^MACDh_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$","Histogram","hist"),
            ],
            nlp=NL(
                keywords=["convergence","divergence","histogram","zero line"],
                synonyms_by_lang={"en":["MACD","Moving Average Convergence Divergence"]},
                regex_templates=[r"\bMACD\s*\(\s*{FAST}\s*,\s*{SLOW}\s*,\s*{SIGNAL}\s*\)", r"\bMACD(?:h)?\b\s*(?:<=|<|>=|>)\s*{THRESHOLD}"],
            ),
            tags=["crossover","momentum"],
            refs=[{"title":"MACD"}],
            func="macd",
            param_map={"fast":"fast","slow":"slow","signal":"signal"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{MACD}_t=\text{EMA}_{f}(C_t)-\text{EMA}_{s}(C_t),\quad \text{Signal}_t=\text{EMA}_{sig}(\text{MACD}_t),\quad \text{Hist}_t=\text{MACD}_t-\text{Signal}_t",
                pseudocode=[
                    "macd = EMA(close, fast) - EMA(close, slow)",
                    "signal = EMA(macd, signal_len)",
                    "hist = macd - signal",
                ],
                notes="Zero-line at 0. Common default (12,26,9)."
            ),
        )

        _def(
            name="PPO",
            group="momentum",
            desc="Percentage Price Oscillator; MACD-like oscillator in percent.",
            inputs=["close"],
            params=[P("fast","int",12,1,None,"Fast EMA"), P("slow","int",26,1,None,"Slow EMA"), P("signal","int",9,1,None,"Signal EMA")],
            synonyms=["percentage price oscillator"],
            src_labels={"pandas_ta":"ppo","talib":"PPO","tradingview":"PPO"},
            defaults={"zero_line":0.0},
            out_schema=[
                OC(r"^PPO_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$","PPO line","main"),
                OC(r"^PPOs_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$","Signal","signal"),
                OC(r"^PPOh_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$","Histogram","hist"),
            ],
            nlp=NL(
                keywords=["percentage","oscillator","zero line"],
                synonyms_by_lang={"en":["PPO","Percentage Price Oscillator"]},
                regex_templates=[r"\bPPO\s*\(\s*{FAST}\s*,\s*{SLOW}\s*,\s*{SIGNAL}\s*\)", r"\bPPO(?:h)?\b\s*(?:<=|<|>=|>)\s*{THRESHOLD}"],
            ),
            tags=["crossover","momentum"],
            refs=[{"title":"PPO"}],
            func="ppo",
            param_map={"fast":"fast","slow":"slow","signal":"signal"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{PPO}_t=100\cdot\frac{\text{EMA}_{f}(C_t)-\text{EMA}_{s}(C_t)}{\text{EMA}_{s}(C_t)};\ \text{Signal}=\text{EMA}(\text{PPO},sig);\ \text{Hist}=\text{PPO}-\text{Signal}",
                pseudocode=[
                    "ppo = 100 * (EMA(close, fast)-EMA(close, slow)) / EMA(close, slow)",
                    "signal = EMA(ppo, signal_len); hist = ppo - signal",
                ],
                notes="Percent version of MACD."
            ),
        )

        _def(
            name="MOM",
            group="momentum",
            desc="Momentum; difference between current price and that n periods ago.",
            inputs=["close"],
            params=[P("window","int",10,1,None,"Lookback")],
            synonyms=["momentum"],
            src_labels={"pandas_ta":"mom","talib":"MOM","tradingview":"MOM"},
            defaults={"zero_line":0.0},
            out_schema=[OC(r"^MOM_(?P<window>\d+)$","Momentum value","main")],
            nlp=NL(keywords=["momentum","rate"], synonyms_by_lang={"en":["Momentum","MOM"]}, regex_templates=[r"\bMOM\s*\(\s*{WINDOW}\s*\)"]),
            tags=["momentum"],
            refs=[{"title":"Momentum"}],
            func="mom",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{MOM}_t = C_t - C_{t-n}",
                pseudocode=["MOM = close_t - close_{t-n}"],
                notes="Zero-centered."
            ),
        )

        _def(
            name="ROC",
            group="momentum",
            desc="Rate of Change; percent change over a window.",
            inputs=["close"],
            params=[P("window","int",10,1,None,"Lookback")],
            synonyms=["rate of change","roc pct"],
            src_labels={"pandas_ta":"roc","talib":"ROC","tradingview":"ROC"},
            defaults={"zero_line":0.0},
            out_schema=[OC(r"^ROC_(?P<window>\d+)$","Rate of Change","main")],
            nlp=NL(keywords=["percentage","change","momentum"], synonyms_by_lang={"en":["ROC","Rate of Change"]}, regex_templates=[r"\bROC\s*\(\s*{WINDOW}\s*\)"]),
            tags=["momentum"],
            refs=[{"title":"ROC"}],
            func="roc",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{ROC}_t = 100\cdot\frac{C_t - C_{t-n}}{C_{t-n}}",
                pseudocode=["ROC = 100 * (close_t - close_{t-n}) / close_{t-n}"],
                notes="Percent form."
            ),
        )

        _def(
            name="TSI",
            group="momentum",
            desc="True Strength Index; double-smoothed momentum oscillator.",
            inputs=["close"],
            params=[P("fast","int",13,1,None,"Fast"), P("slow","int",25,1,None,"Slow")],
            synonyms=["true strength index"],
            src_labels={"pandas_ta":"tsi","tradingview":"TSI"},
            defaults={"zero_line":0.0},
            out_schema=[OC(r"^TSI_(?P<fast>\d+)_(?P<slow>\d+)$","TSI","main")],
            nlp=NL(keywords=["oscillator","double smoothed"], synonyms_by_lang={"en":["TSI","True Strength Index"]}, regex_templates=[r"\bTSI\s*\(\s*{FAST}\s*,\s*{SLOW}\s*\)"]),
            tags=["momentum","oscillator"],
            refs=[{"title":"TSI"}],
            func="tsi",
            param_map={"fast":"fast","slow":"slow"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{pc}_t=C_t-C_{t-1};\ r=\text{EMA}_{f}(\text{EMA}_{s}(\text{pc}));\ a=\text{EMA}_{f}(\text{EMA}_{s}(|\text{pc}|));\ \text{TSI}=100\cdot r/a",
                pseudocode=[
                    "pc = diff(close)",
                    "r = EMA(EMA(pc, slow), fast)",
                    "a = EMA(EMA(abs(pc), slow), fast)",
                    "TSI = 100 * r / a",
                ],
                notes="Zero-centered."
            ),
        )

        _def(
            name="TRIX",
            group="momentum",
            desc="TRIX; rate of change of triple-smoothed EMA.",
            inputs=["close"],
            params=[P("window","int",15,1,None,"Window")],
            synonyms=["triple ema oscillator","triple ema rate"],
            src_labels={"pandas_ta":"trix","talib":"TRIX","tradingview":"TRIX"},
            defaults={"zero_line":0.0},
            out_schema=[OC(r"^TRIX_(?P<window>\d+)$","TRIX","main")],
            nlp=NL(keywords=["triple ema","momentum"], synonyms_by_lang={"en":["TRIX"]}, regex_templates=[r"\bTRIX\s*\(\s*{WINDOW}\s*\)"]),
            tags=["momentum","oscillator"],
            refs=[{"title":"TRIX"}],
            func="trix",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"E1=\text{EMA}_n(C),\ E2=\text{EMA}_n(E1),\ E3=\text{EMA}_n(E2);\ \text{TRIX}=100\cdot\frac{E3_t-E3_{t-1}}{E3_{t-1}}",
                pseudocode=["E3 = EMA(EMA(EMA(close,n),n),n)", "TRIX = 100 * roc(E3,1)"],
                notes="Zero-centered."
            ),
        )

        _def(
            name="CCI",
            group="momentum",
            desc="Commodity Channel Index; deviation from moving average of typical price.",
            inputs=["high","low","close"],
            params=[P("window","int",20,1,None,"Window"), P("c","float",0.015,0.001,1.0,"Constant")],
            synonyms=["commodity channel index"],
            src_labels={"pandas_ta":"cci","talib":"CCI","tradingview":"CCI"},
            defaults={"overbought":100.0,"oversold":-100.0},
            out_schema=[OC(r"^CCI_(?P<window>\d+)$","CCI","main")],
            nlp=NL(keywords=["deviation","mean","channel"], synonyms_by_lang={"en":["CCI","Commodity Channel Index"]}, regex_templates=[r"\bCCI\s*\(\s*{WINDOW}\s*\)"]),
            tags=["momentum","mean-reversion"],
            refs=[{"title":"CCI"}],
            func="cci",
            param_map={"window":"length","c":"c"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"\text{TP}=\frac{H+L+C}{3};\ \text{CCI}=\frac{\text{TP}-\text{SMA}_n(\text{TP})}{c\cdot \text{MAD}_n(\text{TP})}",
                pseudocode=[
                    "TP=(H+L+C)/3",
                    "dev = |TP - SMA(TP,n)|; MAD = SMA(dev,n)",
                    "CCI = (TP - SMA(TP,n)) / (c * MAD)",
                ],
                notes="c default ~0.015 so ±100 notable."
            ),
        )

        _def(
            name="CMO",
            group="momentum",
            desc="Chande Momentum Oscillator; scaled momentum oscillator.",
            inputs=["close"],
            params=[P("window","int",14,1,None,"Window")],
            synonyms=["chande momentum oscillator"],
            src_labels={"pandas_ta":"cmo","tradingview":"CMO"},
            defaults={"overbought":50.0,"oversold":-50.0},
            out_schema=[OC(r"^CMO_(?P<window>\d+)$","CMO","main")],
            nlp=NL(keywords=["oscillator","momentum"], synonyms_by_lang={"en":["CMO","Chande Momentum Oscillator"]}, regex_templates=[r"\bCMO\s*\(\s*{WINDOW}\s*\)"]),
            tags=["momentum","oscillator"],
            refs=[{"title":"CMO"}],
            func="cmo",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{CMO}=100\cdot\frac{\sum \text{gain}_n - \sum \text{loss}_n}{\sum \text{gain}_n + \sum \text{loss}_n}",
                pseudocode=[
                    "gain = max(ΔC,0); loss = max(-ΔC,0)",
                    "CMO = 100 * (sum(gain,n)-sum(loss,n)) / (sum(gain,n)+sum(loss,n))",
                ],
                notes="Bounded [-100,100]."
            ),
        )

        _def(
            name="WilliamsR",
            group="momentum",
            desc="Williams %R; momentum oscillator scaled −100 to 0.",
            inputs=["high","low","close"],
            params=[P("window","int",14,1,None,"Window")],
            synonyms=["williams r","%r","williams percent r"],
            src_labels={"pandas_ta":"willr","talib":"WILLR","tradingview":"W%R"},
            defaults={"overbought":-20.0,"oversold":-80.0},
            out_schema=[OC(r"^WILLR_(?P<window>\d+)$","Williams %R","main")],
            nlp=NL(keywords=["oscillator","bounded"], synonyms_by_lang={"en":["Williams %R","W%R"]}, regex_templates=[r"\bW(?:illiams)?\s*%?R\s*\(\s*{WINDOW}\s*\)"]),
            tags=["momentum","oscillator","bounded"],
            refs=[{"title":"Williams %R"}],
            func="willr",
            param_map={"window":"length"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"\%R_t = -100\cdot\frac{HH_n - C_t}{HH_n - LL_n}",
                pseudocode=["%R = -100 * (highest_high(n) - close) / (highest_high(n) - lowest_low(n))"],
                notes="Ranges [-100,0]."
            ),
        )

        _def(
            name="Stoch",
            group="momentum",
            desc="Stochastic Oscillator (Full) with %K/%D and smoothing.",
            inputs=["high","low","close"],
            params=[P("k","int",14,1,None,"K length"), P("d","int",3,1,None,"D length"), P("smooth_k","int",3,1,None,"Smooth K")],
            synonyms=["stochastic","stochastic oscillator","stoch full"],
            src_labels={"pandas_ta":"stoch","talib":"STOCH","tradingview":"Stoch"},
            defaults={"overbought":80.0,"oversold":20.0},
            out_schema=[
                OC(r"^STOCHk_(?P<k>\d+)_(?P<d>\d+)_(?P<smooth_k>\d+)$","%K","main"),
                OC(r"^STOCHd_(?P<k>\d+)_(?P<d>\d+)_(?P<smooth_k>\d+)$","%D","signal"),
            ],
            nlp=NL(
                keywords=["stochastic","%K","%D","oscillator"],
                synonyms_by_lang={"en":["Stochastic Oscillator","Stoch"]},
                regex_templates=[r"\bStoch(?:astic)?\s*\(\s*\d+.*\)", r"\b%K\b|\b%D\b", r"\bStoch\b\s*(?:<=|<|>=|>)\s*{THRESHOLD}"],
            ),
            tags=["oscillator","momentum"],
            refs=[{"title":"Stochastic Oscillator"}],
            func="stoch",
            param_map={"k":"k","d":"d","smooth_k":"smooth_k"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"\%K=100\cdot\frac{C-LL_n}{HH_n-LL_n},\quad \%D=\text{SMA}_d(\%K)",
                pseudocode=["K = 100*(close - lowest_low(n)) / (highest_high(n)-lowest_low(n))", "D = SMA(K, d)"],
                notes="Full Stoch allows extra smoothing on %K."
            ),
        )

        _def(
            name="StochRSI",
            group="momentum",
            desc="Stochastic RSI; stochastic oscillator applied to RSI.",
            inputs=["close"],
            params=[P("window","int",14,1,None,"RSI window"), P("k","int",14,1,None,"%K length"), P("d","int",3,1,None,"%D length")],
            synonyms=["stoch rsi","stochrsi"],
            src_labels={"pandas_ta":"stochrsi","tradingview":"Stoch RSI"},
            defaults={"overbought":0.8,"oversold":0.2},
            out_schema=[
                OC(r"^STOCHRSIk_(?P<window>\d+)_(?P<k>\d+)_(?P<d>\d+)$","%K of StochRSI","main"),
                OC(r"^STOCHRSId_(?P<window>\d+)_(?P<k>\d+)_(?P<d>\d+)$","%D of StochRSI","signal"),
            ],
            nlp=NL(
                keywords=["stochastic rsi","oscillator"],
                synonyms_by_lang={"en":["Stoch RSI","Stochastic RSI"]},
                regex_templates=[r"\bStoch(?:astic)?\s*RSI\b"],
            ),
            tags=["oscillator","momentum","bounded"],
            refs=[{"title":"Stochastic RSI"}],
            func="stochrsi",
            param_map={"window":"length","k":"rsi_length","d":"d"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{RSI}_t \text{ first};\ \%K_{RSI}= \frac{\text{RSI}_t-\min(\text{RSI})}{\max(\text{RSI})-\min(\text{RSI})},\ \%D=\text{SMA}_d(\%K_{RSI})",
                pseudocode=[
                    "r = RSI(close, n)",
                    "K = (r - min(r, k)) / (max(r, k) - min(r, k))",
                    "D = SMA(K, d)",
                ],
                notes="K,D in [0,1] in this normalized form; many platforms scale to [0,100]."
            ),
        )

        _def(
            name="Aroon",
            group="momentum",
            desc="Aroon Up/Down and Oscillator; time since highs/lows.",
            inputs=["close"],
            params=[P("window","int",25,1,None,"Window")],
            synonyms=["aroon oscillator"],
            src_labels={"pandas_ta":"aroon","tradingview":"Aroon"},
            defaults={"overbought":80.0,"oversold":20.0},
            out_schema=[
                OC(r"^AROONU_(?P<window>\d+)$","Aroon Up","upper"),
                OC(r"^AROOND_(?P<window>\d+)$","Aroon Down","lower"),
                OC(r"^AROONOSC_(?P<window>\d+)$","Aroon Oscillator","main"),
            ],
            nlp=NL(
                keywords=["time high","time low","up","down"],
                synonyms_by_lang={"en":["Aroon","Aroon Oscillator"]},
                regex_templates=[r"\bAroon\s*\(\s*{WINDOW}\s*\)"],
            ),
            tags=["momentum","trend-detection"],
            refs=[{"title":"Aroon"}],
            func="aroon",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{Up}=100\cdot\frac{n - \text{bars\_since\_HH}_n}{n},\ \text{Down}=100\cdot\frac{n - \text{bars\_since\_LL}_n}{n},\ \text{Osc}=\text{Up}-\text{Down}",
                pseudocode=[
                    "Up = 100*(n - bars_since_high(n))/n",
                    "Down = 100*(n - bars_since_low(n))/n",
                    "Osc = Up - Down",
                ],
                notes="Measures how recently highs/lows occurred."
            ),
        )

        _def(
            name="DPO",
            group="momentum",
            desc="Detrended Price Oscillator; removes trend to highlight cycles.",
            inputs=["close"],
            params=[P("window","int",20,1,None,"Window")],
            synonyms=["detrended price oscillator"],
            src_labels={"pandas_ta":"dpo","tradingview":"DPO"},
            defaults={"zero_line":0.0},
            out_schema=[OC(r"^DPO_(?P<window>\d+)$","DPO","main")],
            nlp=NL(keywords=["cycle","detrended"], synonyms_by_lang={"en":["DPO"]}, regex_templates=[r"\bDPO\s*\(\s*{WINDOW}\s*\)"]),
            tags=["momentum","cycle"],
            refs=[{"title":"DPO"}],
            func="dpo",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{DPO}_t = C_{t-k} - \text{SMA}_n(C_t),\quad k=\left\lfloor \frac{n}{2}+1\right\rfloor",
                pseudocode=["k=floor(n/2+1); DPO = close_{t-k} - SMA(close,n)"],
                notes="Centers the MA to remove trend."
            ),
        )

        _def(
            name="Vortex",
            group="momentum",
            desc="Vortex Indicator; positive and negative trend movement (+VI, −VI).",
            inputs=["high","low","close"],
            params=[P("window","int",14,1,None,"Window")],
            synonyms=["vi"],
            src_labels={"pandas_ta":"vortex","tradingview":"Vortex"},
            defaults={"cross_signal":1.0},
            out_schema=[
                OC(r"^VTXP_(?P<window>\d+)$","+VI","main"),
                OC(r"^VTXM_(?P<window>\d+)$","-VI","signal"),
            ],
            nlp=NL(keywords=["vortex","+vi","-vi","trend"], synonyms_by_lang={"en":["Vortex","+VI","-VI"]}, regex_templates=[r"\bVortex\s*\(\s*{WINDOW}\s*\)"]),
            tags=["trend","crossover"],
            refs=[{"title":"Vortex"}],
            func="vortex",
            param_map={"window":"length"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"\text{VM}^+=\sum|H_t-L_{t-1}|,\ \text{VM}^-=\sum|L_t-H_{t-1}|,\ \text{TR}=\sum \text{TrueRange},\ +VI=\text{VM}^+/\text{TR},\ -VI=\text{VM}^-/\text{TR}",
                pseudocode=[
                    "VM+ = sum(|H_t - L_{t-1}|, n); VM- = sum(|L_t - H_{t-1}|, n)",
                    "TR = sum(true_range, n)",
                    "+VI = VM+ / TR; -VI = VM- / TR",
                ],
                notes="Crossovers indicate trend changes."
            ),
        )

        _def(
            name="Coppock",
            group="momentum",
            desc="Coppock Curve; long-term momentum indicator based on ROC and WMA.",
            inputs=["close"],
            params=[P("wlong","int",11,1,None,"Long ROC"), P("wshort","int",14,1,None,"Short ROC"), P("wma","int",10,1,None,"WMA length")],
            synonyms=["coppock curve"],
            src_labels={"pandas_ta":"coppock","tradingview":"Coppock"},
            defaults={"zero_line":0.0},
            out_schema=[OC(r"^COPP(?:C)?_(?P<wlong>\d+)_(?P<wshort>\d+)_(?P<wma>\d+)$","Coppock","main")],
            nlp=NL(keywords=["long-term","momentum"], synonyms_by_lang={"en":["Coppock Curve"]}, regex_templates=[r"\bCoppock\b"]),
            tags=["momentum","long-term"],
            refs=[{"title":"Coppock"}],
            func="coppock",
            param_map={"wlong":"wlong","wshort":"wshort","wma":"wma"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{Coppock}=\text{WMA}_{wma}\big(\text{ROC}_{wlong}(C)+\text{ROC}_{wshort}(C)\big)",
                pseudocode=["Coppock = WMA( ROC(close,wlong) + ROC(close,wshort), wma )"],
                notes="Often monthly data."
            ),
        )

        # -------------------------------------------------------
        # Trend / Moving Averages
        # -------------------------------------------------------

        _def(
            name="SMA",
            group="trend",
            desc="Simple Moving Average over a fixed window.",
            inputs=["close"],
            params=[P("window","int",20,1,None,"Window length")],
            synonyms=["simple moving average","moving average","ma"],
            src_labels={"pandas_ta":"sma","talib":"SMA","tradingview":"SMA"},
            defaults={},
            out_schema=[OC(r"^SMA_(?P<window>\d+)$","SMA value","main")],
            nlp=NL(keywords=["moving average","smoothing"], synonyms_by_lang={"en":["SMA","Simple Moving Average"]}, regex_templates=[r"\bSMA\s*\(\s*{WINDOW}\s*\)"]),
            tags=["smoothing","trend"],
            refs=[{"title":"SMA"}],
            func="sma",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{SMA}_t = \frac{1}{n}\sum_{i=0}^{n-1} C_{t-i}",
                pseudocode=["SMA = mean(close over last n)"],
                notes="Equal weights."
            ),
        )

        _def(
            name="EMA",
            group="trend",
            desc="Exponential Moving Average with higher weight on recent prices.",
            inputs=["close"],
            params=[P("window","int",20,1,None,"Window length")],
            synonyms=["exponential moving average"],
            src_labels={"pandas_ta":"ema","talib":"EMA","tradingview":"EMA"},
            defaults={},
            out_schema=[OC(r"^EMA_(?P<window>\d+)$","EMA value","main")],
            nlp=NL(keywords=["moving average","smoothing","exponential"], synonyms_by_lang={"en":["EMA","Exponential Moving Average"]}, regex_templates=[r"\bEMA\s*\(\s*{WINDOW}\s*\)"]),
            tags=["smoothing","trend"],
            refs=[{"title":"EMA"}],
            func="ema",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\alpha=\frac{2}{n+1};\ \text{EMA}_t=\alpha C_t + (1-\alpha)\text{EMA}_{t-1}",
                pseudocode=["alpha = 2/(n+1); EMA_t = alpha*close + (1-alpha)*EMA_{t-1}"],
                notes="Recursive filter."
            ),
        )

        _def(
            name="WMA",
            group="trend",
            desc="Weighted Moving Average; applies linearly increasing weights.",
            inputs=["close"],
            params=[P("window","int",20,1,None,"Window")],
            synonyms=["weighted moving average"],
            src_labels={"pandas_ta":"wma","talib":"WMA","tradingview":"WMA"},
            defaults={},
            out_schema=[OC(r"^WMA_(?P<window>\d+)$","WMA value","main")],
            nlp=NL(keywords=["weighted","moving average"], synonyms_by_lang={"en":["WMA","Weighted Moving Average"]}, regex_templates=[r"\bWMA\s*\(\s*{WINDOW}\s*\)"]),
            tags=["smoothing","trend"],
            refs=[{"title":"WMA"}],
            func="wma",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{WMA}_t=\frac{\sum_{i=1}^{n} i\cdot C_{t-n+i}}{\sum_{i=1}^{n} i}",
                pseudocode=["weights=1..n; WMA = sum(weights*close)/sum(weights)"],
                notes="Linear weights."
            ),
        )

        _def(
            name="HMA",
            group="trend",
            desc="Hull Moving Average; reduces lag via WMA combinations.",
            inputs=["close"],
            params=[P("window","int",20,1,None,"Window")],
            synonyms=["hull moving average"],
            src_labels={"pandas_ta":"hma","tradingview":"HMA"},
            defaults={},
            out_schema=[OC(r"^HMA_(?P<window>\d+)$","HMA value","main")],
            nlp=NL(keywords=["hull","moving average","low-lag"], synonyms_by_lang={"en":["Hull Moving Average","HMA"]}, regex_templates=[r"\bHMA\s*\(\s*{WINDOW}\s*\)"]),
            tags=["smoothing","trend","low-lag"],
            refs=[{"title":"HMA"}],
            func="hma",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{HMA}_n = \text{WMA}_{\sqrt{n}}\!\big(2\cdot \text{WMA}_{n/2}(C) - \text{WMA}_{n}(C)\big)",
                pseudocode=["hma = WMA( 2*WMA(close, n/2) - WMA(close,n), sqrt(n) )"],
                notes="Uses integer rounding for n/2 and sqrt(n)."
            ),
        )

        _def(
            name="RMA",
            group="trend",
            desc="Wilder's Moving Average (RMA); smooth variant used in RSI.",
            inputs=["close"],
            params=[P("window","int",14,1,None,"Window")],
            synonyms=["wilder","rsi_ma"],
            src_labels={"pandas_ta":"rma","tradingview":"RMA"},
            defaults={},
            out_schema=[OC(r"^RMA_(?P<window>\d+)$","RMA value","main")],
            nlp=NL(keywords=["wilder","moving average"], synonyms_by_lang={"en":["RMA","Wilder's Moving Average"]}, regex_templates=[r"\bRMA\s*\(\s*{WINDOW}\s*\)"]),
            tags=["smoothing","trend"],
            refs=[{"title":"RMA"}],
            func="rma",
            param_map={"window":"length"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{RMA}_t = \text{RMA}_{t-1} + \frac{C_t - \text{RMA}_{t-1}}{n}",
                pseudocode=["RMA_t = RMA_{t-1} + (close - RMA_{t-1})/n"],
                notes="Equivalent to Wilder's smoothing."
            ),
        )

        _def(
            name="KAMA",
            group="trend",
            desc="Kaufman Adaptive Moving Average (KAMA); adapts to market noise.",
            inputs=["close"],
            params=[P("window","int",10,1,None,"Efficiency window"), P("fast","int",2,1,None,"Fast EMA"), P("slow","int",30,1,None,"Slow EMA")],
            synonyms=["kaufman adaptive moving average","kaufman"],
            src_labels={"pandas_ta":"kama","tradingview":"KAMA"},
            defaults={},
            out_schema=[OC(r"^KAMA_(?P<window>\d+)_(?P<fast>\d+)_(?P<slow>\d+)$","KAMA value","main")],
            nlp=NL(keywords=["adaptive","noise","moving average"], synonyms_by_lang={"en":["KAMA","Kaufman Adaptive Moving Average"]}, regex_templates=[r"\bKAMA\s*\(\s*{WINDOW}\s*,\s*{FAST}\s*,\s*{SLOW}\s*\)"]),
            tags=["smoothing","adaptive","trend"],
            refs=[{"title":"KAMA"}],
            func="kama",
            param_map={"window":"length","fast":"fast","slow":"slow"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"\text{ER}=\frac{|C_t-C_{t-n}|}{\sum_{i=1}^{n}|C_{t-i}-C_{t-i-1}|},\ \alpha=(\text{ER}\cdot(\alpha_f-\alpha_s)+\alpha_s)^2,\ \text{KAMA}_t=\text{KAMA}_{t-1}+\alpha(C_t-\text{KAMA}_{t-1})",
                pseudocode=[
                    "ER = |C_t - C_{t-n}| / sum(|ΔC|, n)",
                    "alpha_f=2/(fast+1); alpha_s=2/(slow+1)",
                    "alpha=(ER*(alpha_f-alpha_s)+alpha_s)^2",
                    "KAMA_t=KAMA_{t-1}+alpha*(C_t-KAMA_{t-1})",
                ],
                notes="Adaptive smoothing."
            ),
        )

        # -------------------------------------------------------
        # Volatility
        # -------------------------------------------------------

        _def(
            name="BBANDS",
            group="volatility",
            desc="Bollinger Bands: middle (SMA) with upper/lower bands at ±k * stddev.",
            inputs=["close"],
            params=[P("window","int",20,1,None,"SMA window"), P("stdev","float",2.0,0.5,5.0,"StdDev mult")],
            synonyms=["bollinger bands","bb"],
            src_labels={"pandas_ta":"bbands","talib":"BBANDS","tradingview":"BB"},
            defaults={},
            out_schema=[
                OC(r"^BBL_(?P<window>\d+)_(?P<stdev>\d+(?:\.\d+)?)$","Lower band","lower"),
                OC(r"^BBM_(?P<window>\d+)_(?P<stdev>\d+(?:\.\d+)?)$","Middle band","middle"),
                OC(r"^BBU_(?P<window>\d+)_(?P<stdev>\d+(?:\.\d+)?)$","Upper band","upper"),
                OC(r"^BBB_(?P<window>\d+)_(?P<stdev>\d+(?:\.\d+)?)$","Bandwidth","other"),
                OC(r"^BBP_(?P<window>\d+)_(?P<stdev>\d+(?:\.\d+)?)$","Percent B","other"),
            ],
            nlp=NL(
                keywords=["volatility","bands","upper","lower","percent b"],
                synonyms_by_lang={"en":["Bollinger Bands","BB"]},
                regex_templates=[r"\bBollinger\s+Bands\b", r"\bBB\s*\(\s*{WINDOW}\s*,\s*{STDEV}\s*\)"],
            ),
            tags=["volatility","envelope"],
            refs=[{"title":"Bollinger Bands"}],
            func="bbands",
            param_map={"window":"length","stdev":"std"},
            input_map={"close":"close"},
            formula=FS(
                latex=r"M=\text{SMA}_n(C),\ U=M+k\sigma_n(C),\ L=M-k\sigma_n(C),\ \%B=\frac{C-L}{U-L},\ \text{BW}=\frac{U-L}{M}",
                pseudocode=[
                    "M = SMA(close,n); SD = stdev(close,n)",
                    "Upper = M + k*SD; Lower = M - k*SD",
                    "%B = (close - Lower)/(Upper - Lower); BW = (Upper-Lower)/M",
                ],
                notes="k commonly 2."
            ),
        )

        _def(
            name="ATR",
            group="volatility",
            desc="Average True Range; absolute volatility measure.",
            inputs=["high","low","close"],
            params=[P("window","int",14,1,None,"ATR window")],
            synonyms=["average true range"],
            src_labels={"pandas_ta":"atr","talib":"ATR","tradingview":"ATR"},
            defaults={},
            out_schema=[OC(r"^ATRr?_(?P<window>\d+)$","ATR value","main")],
            nlp=NL(keywords=["volatility","true range"], synonyms_by_lang={"en":["ATR","Average True Range"]}, regex_templates=[r"\bATR\s*\(\s*{WINDOW}\s*\)"]),
            tags=["volatility"],
            refs=[{"title":"ATR"}],
            func="atr",
            param_map={"window":"length"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"\text{TR}=\max(H-L, |H-C_{t-1}|, |L-C_{t-1}|),\ \text{ATR}=\text{RMA}_n(\text{TR})",
                pseudocode=["TR = max(H-L, |H-prevC|, |L-prevC|)", "ATR = RMA(TR, n)"],
                notes="Wilder's smoothing."
            ),
        )

        _def(
            name="KC",
            group="volatility",
            desc="Keltner Channels; EMA-based middle with ATR-multiplied bands.",
            inputs=["high","low","close"],
            params=[P("window","int",20,1,None,"EMA length"), P("atr_window","int",10,1,None,"ATR length"), P("mult","float",2.0,0.5,5.0,"ATR multiplier")],
            synonyms=["keltner channels","keltner"],
            src_labels={"pandas_ta":"kc","tradingview":"KC"},
            defaults={},
            out_schema=[
                OC(r"^KCL[ae]?_(?P<window>\d+)_(?P<mult>\d+(?:\.\d+)?)$","Lower band","lower"),
                OC(r"^KCM[ae]?_(?P<window>\d+)_(?P<mult>\d+(?:\.\d+)?)$","Middle (basis)","middle"),
                OC(r"^KCU[ae]?_(?P<window>\d+)_(?P<mult>\d+(?:\.\d+)?)$","Upper band","upper"),
                OC(r"^KCB_(?P<window>\d+)_(?P<mult>\d+(?:\.\d+)?)$","Band width","other"),
            ],
            nlp=NL(keywords=["volatility","envelope","atr"], synonyms_by_lang={"en":["Keltner Channels","KC"]}, regex_templates=[r"\bKeltner\s+Channels\b"]),
            tags=["volatility","envelope"],
            refs=[{"title":"Keltner Channels"}],
            func="kc",
            param_map={"window":"length","atr_window":"length_atr","mult":"scalar"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"B=\text{EMA}_n(C),\ \text{ATR}_m,\ U=B+k\cdot \text{ATR}_m,\ L=B-k\cdot \text{ATR}_m",
                pseudocode=["Basis = EMA(close,n); atr = ATR(m)", "Upper = Basis + k*atr; Lower = Basis - k*atr"],
                notes="EMA basis vs Bollinger's SMA."
            ),
        )

        _def(
            name="Donchian",
            group="volatility",
            desc="Donchian Channels; highest high/lowest low over a window.",
            inputs=["high","low"],
            params=[P("window","int",20,1,None,"Window")],
            synonyms=["donchian channels","dc"],
            src_labels={"pandas_ta":"donchian","tradingview":"Donchian"},
            defaults={},
            out_schema=[
                OC(r"^DCL_(?P<window>\d+)$","Lower channel","lower"),
                OC(r"^DCM_(?P<window>\d+)$","Middle channel","middle"),
                OC(r"^DCU_(?P<window>\d+)$","Upper channel","upper"),
            ],
            nlp=NL(keywords=["channel","breakout"], synonyms_by_lang={"en":["Donchian Channels","Donchian"]}, regex_templates=[r"\bDonchian\s*\(\s*{WINDOW}\s*\)"]),
            tags=["volatility","breakout"],
            refs=[{"title":"Donchian Channels"}],
            func="donchian",
            param_map={"window":"lower_length"},
            input_map={"high":"high","low":"low"},
            formula=FS(
                latex=r"U=\max(H_{t-n+1..t}),\ L=\min(L_{t-n+1..t}),\ M=\frac{U+L}{2}",
                pseudocode=["Upper = highest_high(n); Lower = lowest_low(n); Middle = (Upper+Lower)/2"],
                notes="Pure price channels."
            ),
        )

        _def(
            name="Ichimoku",
            group="volatility",
            desc="Ichimoku Cloud; Tenkan, Kijun, Senkou spans and Chikou.",
            inputs=["high","low","close"],
            params=[P("tenkan","int",9,1,None,"Conversion line"), P("kijun","int",26,1,None,"Base line"), P("senkou","int",52,1,None,"Span B")],
            synonyms=["ichimoku cloud","ichimoku kinko hyo","ichimoku kinko"],
            src_labels={"pandas_ta":"ichimoku","tradingview":"Ichimoku"},
            defaults={},
            out_schema=[
                OC(r"^ITS_(?P<tenkan>\d+)$","Tenkan-sen","main"),
                OC(r"^IKS_(?P<kijun>\d+)$","Kijun-sen","signal"),
                OC(r"^ISA_(?P<tenkan>\d+)$","Senkou Span A","upper"),
                OC(r"^ISB_(?P<senkou>\d+)$","Senkou Span B","lower"),
                OC(r"^ICS_(?P<kijun>\d+)$","Chikou Span","other"),
            ],
            nlp=NL(keywords=["cloud","span","tenkan","kijun","senkou","chikou"], synonyms_by_lang={"en":["Ichimoku Cloud","Ichimoku"]}, regex_templates=[r"\bIchimoku\b"]),
            tags=["trend","volatility","support-resistance"],
            refs=[{"title":"Ichimoku"}],
            func="ichimoku",
            param_map={"tenkan":"tenkan","kijun":"kijun","senkou":"senkou"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"\begin{aligned} &\text{Tenkan}=\frac{\max(H,9)+\min(L,9)}{2},\ \text{Kijun}=\frac{\max(H,26)+\min(L,26)}{2},\\ &\text{SenkouA}=\frac{\text{Tenkan}+\text{Kijun}}{2}\text{ (shift +26)},\ \text{SenkouB}=\frac{\max(H,52)+\min(L,52)}{2}\text{ (shift +26)},\\ &\text{Chikou}=C\text{ (shift −26)} \end{aligned}",
                pseudocode=[
                    "Tenkan=(HH(9)+LL(9))/2; Kijun=(HH(26)+LL(26))/2",
                    "SenkouA=(Tenkan+Kijun)/2 shifted +26",
                    "SenkouB=(HH(52)+LL(52))/2 shifted +26",
                    "Chikou=close shifted -26",
                ],
                notes="Shifts depend on platform plotting."
            ),
        )

        _def(
            name="Supertrend",
            group="volatility",
            desc="Supertrend indicator using ATR; returns direction and lines.",
            inputs=["high","low","close"],
            params=[P("atr_window","int",7,1,None,"ATR window"), P("mult","float",3.0,0.5,10.0,"Multiplier")],
            synonyms=["super trend","supertrend"],
            src_labels={"pandas_ta":"supertrend","tradingview":"Supertrend"},
            defaults={},
            out_schema=[
                OC(r"^SUPERT_(?P<atr_window>\d+)_(?P<mult>\d+(?:\.\d+)?)$","Supertrend line","main"),
                OC(r"^SUPERTd_(?P<atr_window>\d+)_(?P<mult>\d+(?:\.\d+)?)$","Direction (+1/-1)","signal"),
                OC(r"^SUPERTl_(?P<atr_window>\d+)_(?P<mult>\d+(?:\.\d+)?)$","Long line","upper"),
                OC(r"^SUPERTs_(?P<atr_window>\d+)_(?P<mult>\d+(?:\.\d+)?)$","Short line","lower"),
            ],
            nlp=NL(keywords=["atr","trend","direction"], synonyms_by_lang={"en":["Supertrend"]}, regex_templates=[r"\bSupertrend\b"]),
            tags=["trend","volatility","stop-trail"],
            refs=[{"title":"Supertrend"}],
            func="supertrend",
            param_map={"atr_window":"length","mult":"mult"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"\text{HL2}=(H+L)/2;\ \text{BasicUpper}=\text{HL2}+m\cdot \text{ATR},\ \text{BasicLower}=\text{HL2}-m\cdot \text{ATR};\ \text{lines filtered by direction and crossover rules}",
                pseudocode=[
                    "hl2=(H+L)/2; atr=ATR(n)",
                    "basic_upper=hl2 + m*atr; basic_lower=hl2 - m*atr",
                    "final lines follow trailing rules; direction flips on close cross",
                ],
                notes="Multiple equivalent rule-sets exist; visual parity matters."
            ),
        )

        _def(
            name="PSAR",
            group="volatility",
            desc="Parabolic SAR; trend-following stop and reverse.",
            inputs=["high","low"],
            params=[P("af_start","float",0.02,0.001,1.0,"Start AF"), P("af_step","float",0.02,0.001,1.0,"AF step"), P("af_max","float",0.2,0.01,1.0,"Max AF")],
            synonyms=["parabolic sar","sar"],
            src_labels={"pandas_ta":"psar","talib":"SAR","tradingview":"SAR"},
            defaults={},
            out_schema=[OC(r"^PSAR[a-z]?_(?P<af_start>\d+(?:\.\d+)?)_(?P<af_max>\d+(?:\.\d+)?)$","PSAR","main")],
            nlp=NL(keywords=["stop and reverse","trend"], synonyms_by_lang={"en":["Parabolic SAR","SAR"]}, regex_templates=[r"\bP(?:arabolic\s+)?SAR\b"]),
            tags=["trend","stop-trail"],
            refs=[{"title":"Parabolic SAR"}],
            func="psar",
            param_map={"af_start":"af","af_step":"max_af","af_max":"max_af"},
            input_map={"high":"high","low":"low"},
            formula=FS(
                latex=r"\text{PSAR}_{t+1}=\text{PSAR}_t + AF\cdot(EP - \text{PSAR}_t);\ AF\in[AF_0,AF_{\max}]\ \text{increments when new EP (extreme point) occurs; direction flips on penetration}",
                pseudocode=[
                    "Initialize trend and EP (extreme point)",
                    "PSAR_next = PSAR + AF*(EP - PSAR)",
                    "Increase AF by step when new EP; cap at AF_max",
                    "Flip direction when price crosses PSAR",
                ],
                notes="Classic Wilder method."
            ),
        )

        # -------------------------------------------------------
        # Volume / Price-derived
        # -------------------------------------------------------

        _def(
            name="OBV",
            group="volume",
            desc="On-Balance Volume; cumulative volume flow signaled by price direction.",
            inputs=["close","volume"],
            params=[],
            synonyms=["on balance volume"],
            src_labels={"pandas_ta":"obv","talib":"OBV","tradingview":"OBV"},
            defaults={},
            out_schema=[OC(r"^OBV$","On-Balance Volume","main")],
            nlp=NL(keywords=["volume","accumulation","distribution"], synonyms_by_lang={"en":["OBV","On-Balance Volume"]}, regex_templates=[r"\bOBV\b"]),
            tags=["volume","flow"],
            refs=[{"title":"OBV"}],
            func="obv",
            param_map={},
            input_map={"close":"close","volume":"volume"},
            formula=FS(
                latex=r"\text{OBV}_t=\text{OBV}_{t-1} + \begin{cases} V_t,& C_t>C_{t-1}\\ -V_t,& C_t<C_{t-1}\\ 0,& \text{otherwise}\end{cases}",
                pseudocode=[
                    "if close>prev_close: OBV += volume",
                    "elif close<prev_close: OBV -= volume",
                    "else: OBV unchanged",
                ],
                notes="Cumulative volume flow."
            ),
        )

        _def(
            name="CMF",
            group="volume",
            desc="Chaikin Money Flow; money flow over a window.",
            inputs=["high","low","close","volume"],
            params=[P("window","int",20,1,None,"Window")],
            synonyms=["chaikin money flow"],
            src_labels={"pandas_ta":"cmf","tradingview":"CMF"},
            defaults={"zero_line":0.0},
            out_schema=[OC(r"^CMF_(?P<window>\d+)$","CMF","main")],
            nlp=NL(keywords=["accumulation","distribution","money flow"], synonyms_by_lang={"en":["CMF","Chaikin Money Flow"]}, regex_templates=[r"\bCMF\s*\(\s*{WINDOW}\s*\)"]),
            tags=["volume","flow"],
            refs=[{"title":"CMF"}],
            func="cmf",
            param_map={"window":"length"},
            input_map={"high":"high","low":"low","close":"close","volume":"volume"},
            formula=FS(
                latex=r"\text{MFM}=\frac{(C-L)-(H-C)}{H-L},\ \text{MFV}=\text{MFM}\cdot V,\ \text{CMF}=\frac{\sum \text{MFV}}{\sum V}",
                pseudocode=[
                    "mfm = ((C-L)-(H-C))/(H-L)",
                    "mfv = mfm * volume",
                    "CMF = sum(mfv,n) / sum(volume,n)",
                ],
                notes="Bounds approximate [-1,1] when H!=L."
            ),
        )

        _def(
            name="ADL",
            group="volume",
            desc="Accumulation/Distribution Line; cumulative money flow line.",
            inputs=["high","low","close","volume"],
            params=[],
            synonyms=["chaikin ad line","accumulation distribution"],
            src_labels={"pandas_ta":"ad","tradingview":"ADL"},
            defaults={},
            out_schema=[OC(r"^AD$|^ADL$","ADL","main")],
            nlp=NL(keywords=["accumulation","distribution","line"], synonyms_by_lang={"en":["ADL","Accumulation/Distribution"]}, regex_templates=[r"\bADL\b"]),
            tags=["volume","flow"],
            refs=[{"title":"ADL"}],
            func="ad",
            param_map={},
            input_map={"high":"high","low":"low","close":"close","volume":"volume"},
            formula=FS(
                latex=r"\text{CLV}=\frac{(C-L)-(H-C)}{H-L},\ \text{ADL}_t=\text{ADL}_{t-1}+\text{CLV}_t\cdot V_t",
                pseudocode=["CLV=((C-L)-(H-C))/(H-L)", "ADL += CLV*Volume"],
                notes="Cumulative; denominator guard when H=L."
            ),
        )

        _def(
            name="NVI",
            group="volume",
            desc="Negative Volume Index; tracks days when volume declines.",
            inputs=["close","volume"],
            params=[],
            synonyms=["negative volume index"],
            src_labels={"pandas_ta":"nvi","tradingview":"NVI"},
            defaults={},
            out_schema=[OC(r"^NVI$","NVI","main")],
            nlp=NL(keywords=["volume","index","negative"], synonyms_by_lang={"en":["NVI","Negative Volume Index"]}, regex_templates=[r"\bNVI\b"]),
            tags=["volume","index"],
            refs=[{"title":"NVI"}],
            func="nvi",
            param_map={},
            input_map={"close":"close","volume":"volume"},
            formula=FS(
                latex=r"\text{If }V_t<V_{t-1}:\ \text{NVI}_t=\text{NVI}_{t-1}\left(1+\frac{C_t-C_{t-1}}{C_{t-1}}\right);\ \text{else NVI}_t=\text{NVI}_{t-1}",
                pseudocode=["if vol_t < vol_{t-1}: NVI *= (1 + ret); else unchanged"],
                notes="Base can be set to 1000."
            ),
        )

        _def(
            name="PVI",
            group="volume",
            desc="Positive Volume Index; tracks days when volume increases.",
            inputs=["close","volume"],
            params=[],
            synonyms=["positive volume index"],
            src_labels={"pandas_ta":"pvi","tradingview":"PVI"},
            defaults={},
            out_schema=[OC(r"^PVI$","PVI","main")],
            nlp=NL(keywords=["volume","index","positive"], synonyms_by_lang={"en":["PVI","Positive Volume Index"]}, regex_templates=[r"\bPVI\b"]),
            tags=["volume","index"],
            refs=[{"title":"PVI"}],
            func="pvi",
            param_map={},
            input_map={"close":"close","volume":"volume"},
            formula=FS(
                latex=r"\text{If }V_t>V_{t-1}:\ \text{PVI}_t=\text{PVI}_{t-1}\left(1+\frac{C_t-C_{t-1}}{C_{t-1}}\right);\ \text{else PVI}_t=\text{PVI}_{t-1}",
                pseudocode=["if vol_t > vol_{t-1}: PVI *= (1 + ret); else unchanged"],
                notes="Base can be set to 1000."
            ),
        )

        _def(
            name="VWAP",
            group="price",
            desc="Volume Weighted Average Price; session-weighted average.",
            inputs=["high","low","close","volume"],
            params=[],
            synonyms=["vwap"],
            src_labels={"pandas_ta":"vwap","tradingview":"VWAP"},
            defaults={},
            out_schema=[OC(r"^VWAP.*$","VWAP (session)","main")],
            nlp=NL(keywords=["volume weighted","average price","session"], synonyms_by_lang={"en":["VWAP"]}, regex_templates=[r"\bVWAP\b"]),
            tags=["price","session"],
            refs=[{"title":"VWAP"}],
            func="vwap",
            param_map={},
            input_map={"high":"high","low":"low","close":"close","volume":"volume"},
            formula=FS(
                latex=r"\text{TP}=\frac{H+L+C}{3};\ \text{VWAP}_t=\frac{\sum_{i=1}^{t} \text{TP}_i V_i}{\sum_{i=1}^{t} V_i}\ \text{(per session)}",
                pseudocode=["tp=(H+L+C)/3; cum(tp*vol)/cum(vol) within session"],
                notes="Resets each session/day unless specified otherwise."
            ),
        )

        _def(
            name="EOM",
            group="price",
            desc="Ease of Movement; price change relative to volume.",
            inputs=["high","low","volume"],
            params=[P("window","int",14,1,None,"Window")],
            synonyms=["ease of movement"],
            src_labels={"pandas_ta":"eom","tradingview":"EOM"},
            defaults={"zero_line":0.0},
            out_schema=[OC(r"^EOM_(?P<window>\d+)$","EOM","main")],
            nlp=NL(keywords=["ease of movement","volume","price"], synonyms_by_lang={"en":["EOM","Ease of Movement"]}, regex_templates=[r"\bEOM\s*\(\s*{WINDOW}\s*\)"]),
            tags=["price","volume"],
            refs=[{"title":"EOM"}],
            func="eom",
            param_map={"window":"length"},
            input_map={"high":"high","low":"low","volume":"volume"},
            formula=FS(
                latex=r"\text{MidMove}=\frac{(H+L)/2-(H_{-1}+L_{-1})/2}{1};\ \text{BoxRatio}=\frac{V}{H-L};\ \text{EOM}=\frac{\text{MidMove}}{\text{BoxRatio}}",
                pseudocode=["mid = ((H+L)/2 - (H_prev+L_prev)/2)", "box_ratio = volume / (H-L)", "EOM = mid / box_ratio; SMA(EOM,n) often used"],
                notes="Often smoothed."
            ),
        )

        _def(
            name="ADX",
            group="trend",
            desc="Average Directional Index; trend strength with +DI / -DI.",
            inputs=["high","low","close"],
            params=[P("window","int",14,1,None,"ADX length")],
            synonyms=["average directional index","dmi"],
            src_labels={"pandas_ta":"adx","talib":"ADX","tradingview":"ADX"},
            defaults={"threshold":25.0},
            out_schema=[
                OC(r"^ADX_(?P<window>\d+)$","ADX","main"),
                OC(r"^(?:\+DI|DMP)_(?P<window>\d+)$","+DI","upper"),
                OC(r"^(?:-DI|DMN)_(?P<window>\d+)$","-DI","lower"),
            ],
            nlp=NL(keywords=["trend strength","directional movement","+DI","-DI"], synonyms_by_lang={"en":["ADX","Average Directional Index","DMI"]}, regex_templates=[r"\bADX\s*\(\s*{WINDOW}\s*\)"]),
            tags=["trend","strength"],
            refs=[{"title":"ADX"}],
            func="adx",
            param_map={"window":"length"},
            input_map={"high":"high","low":"low","close":"close"},
            formula=FS(
                latex=r"\begin{aligned}&+DM=\max(H_t-H_{t-1},0),\ -DM=\max(L_{t-1}-L_t,0)\\ &\text{TR}=\max(H-L,|H-C_{t-1}|,|L-C_{t-1}|)\\ &+DI=100\cdot\frac{\text{RMA}(+DM,n)}{\text{ATR}_n},\ -DI=100\cdot\frac{\text{RMA}(-DM,n)}{\text{ATR}_n}\\ &DX=100\cdot\frac{|+DI-(-DI)|}{+DI+(-DI)},\ \text{ADX}=\text{RMA}(DX,n)\end{aligned}",
                pseudocode=[
                    "+DM = max(H - prevH, 0) if > (prevL - L) else 0",
                    "-DM = max(prevL - L, 0) if > (H - prevH) else 0",
                    "TR = max(H-L, |H-prevC|, |L-prevC|); ATR = RMA(TR,n)",
                    "+DI = 100 * RMA(+DM,n)/ATR; -DI = 100 * RMA(-DM,n)/ATR",
                    "DX = 100 * abs(+DI - -DI)/(+DI + -DI); ADX = RMA(DX,n)",
                ],
                notes="Classic Wilder formulation."
            ),
        )
