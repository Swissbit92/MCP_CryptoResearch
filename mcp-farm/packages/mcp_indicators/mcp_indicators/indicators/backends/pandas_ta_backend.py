# mcp-farm/packages/mcp_indicators/mcp_indicators/indicators/backends/pandas_ta_backend.py
"""
pandas-ta backend adapter for the Indicator Registry.

• Lazily imports pandas_ta.
• Invokes the target function by name with keyword args.
• Attaches any returned Series/DataFrame columns to the input df in-place.
"""
from __future__ import annotations

from typing import Any
import importlib

def _import_pandas_ta():
    try:
        return importlib.import_module("pandas_ta")
    except Exception as e:
        raise ImportError(
            "pandas-ta is required for backend='pandas_ta'. Install with: pip install pandas-ta"
        ) from e

def call(df, func_name: str, **kwargs: Any) -> None:
    ta = _import_pandas_ta()
    if not hasattr(ta, func_name):
        raise AttributeError(f"pandas_ta has no function '{func_name}'")
    fn = getattr(ta, func_name)
    out = fn(**kwargs)
    if out is None:
        return
    # normalize to DataFrame-like
    if hasattr(out, "to_frame") and not hasattr(out, "columns"):
        out_df = out.to_frame()
    else:
        out_df = out
    for col in out_df.columns:
        df[col] = out_df[col]
