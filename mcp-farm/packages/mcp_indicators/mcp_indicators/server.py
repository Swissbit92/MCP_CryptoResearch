# mcp-farm/packages/mcp_indicators/mcp_indicators/server.py
# server.py — Indicators MCP (FastMCP)
# - Resource signatures match URI templates (no extra params)
# - No `from __future__ import annotations` to avoid dataclass/CLI import issues
# - Uses a simple global app context compatible with current FastMCP

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import pandas as pd
from mcp.server.fastmcp import FastMCP

from mcp_indicators.indicators.registry import IndicatorRegistry
import os
from dotenv import load_dotenv
load_dotenv()

# replace your hard-coded constant:
PREVIEW_ROWS = int(os.getenv("INDICATORS_MCP_PREVIEW_ROWS", "5"))


# ------------------------- App-wide state -------------------------

@dataclass
class AppCtx:
    reg: IndicatorRegistry
    datasets: dict[str, pd.DataFrame]


APP: Optional[AppCtx] = None  # set/unset in lifespan


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Create the registry + in-memory dataset store for the server lifetime."""
    global APP
    APP = AppCtx(reg=IndicatorRegistry(), datasets={})
    try:
        yield APP
    finally:
        APP = None


mcp = FastMCP("Indicators MCP", lifespan=lifespan)


# ------------------------------ TOOLS ------------------------------

@mcp.tool()
def list_indicators() -> List[str]:
    """Return canonical indicator names."""
    assert APP is not None
    return APP.reg.list()


@mcp.tool()
def describe_indicator(name: str) -> Dict[str, Any]:
    """Describe indicator metadata (params, outputs, etc.)."""
    assert APP is not None
    return APP.reg.describe(name)


@mcp.tool()
def validate_params(name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fill defaults and type/range-check params for an indicator."""
    assert APP is not None
    return APP.reg.validate_params(name, params or {})


@mcp.tool()
def load_csv_dataset(
    dataset_id: str,
    path: str,
    date_col: Optional[str] = None,
    tz: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load an OHLCV CSV into memory as dataset `dataset_id`.
    If date_col is provided and exists, it becomes the (tz-aware) index.
    """
    assert APP is not None
    df = pd.read_csv(path)
    if date_col and date_col in df.columns:
        ts = pd.to_datetime(df[date_col], utc=True, errors="coerce")
        if tz:
            ts = ts.dt.tz_convert(tz)
        df = df.set_index(ts).drop(columns=[date_col]).sort_index()
    APP.datasets[dataset_id] = df
    return {"dataset_id": dataset_id, "rows": int(df.shape[0]), "columns": df.columns.tolist()}


@mcp.tool()
def compute_indicator(
    dataset_id: str,
    name: str,
    params: Optional[Dict[str, Any]] = None,
    backend: str = "pandas_ta",
) -> Dict[str, Any]:
    """
    Compute an indicator on a loaded dataset (mutates the in-memory DF by adding columns).
    Returns the new columns and the spec used for compute.
    """
    assert APP is not None
    if dataset_id not in APP.datasets:
        raise ValueError(f"unknown dataset_id: {dataset_id}")
    df = APP.datasets[dataset_id]
    res = APP.reg.compute(df, name_or_alias=name, params=params or {}, backend=backend)
    return {
        "dataset_id": dataset_id,
        "new_columns": res["columns"],
        "spec": res["spec"],
        "row_count": int(df.shape[0]),
    }


@mcp.tool()
def preview_ohlcv(dataset_id: str, limit: int = 5) -> Dict[str, Any]:
    """
    Preview the first `limit` rows of a loaded dataset.
    (Use this tool if you want a custom preview length.)
    """
    assert APP is not None
    if dataset_id not in APP.datasets:
        raise ValueError(f"unknown dataset_id: {dataset_id}")
    df = APP.datasets[dataset_id]
    head = df.head(limit).reset_index().copy()
    # ensure datetimes serialize cleanly to JSON
    for col in head.columns:
        if pd.api.types.is_datetime64_any_dtype(head[col]):
            head[col] = head[col].astype(str)
    return {
        "dataset_id": dataset_id,
        "columns": df.columns.tolist(),
        "rows_preview": head.to_dict(orient="records"),
    }


# ---------------------------- RESOURCES ----------------------------

@mcp.resource("indicators://index")
def indicators_index() -> List[str]:
    """Read-only index of indicator names (resource view)."""
    assert APP is not None
    return APP.reg.list()


@mcp.resource("indicators://{name}")
def indicator_resource(name: str) -> Dict[str, Any]:
    """Read-only descriptor for a single indicator (resource view)."""
    assert APP is not None
    return APP.reg.describe(name)


@mcp.resource("ohlcv://{dataset_id}")
def ohlcv_preview(dataset_id: str) -> Dict[str, Any]:
    """
    Read-only top-row preview of a loaded dataset.
    Resource function parameters must match the URI exactly (no extras).
    """
    assert APP is not None
    if dataset_id not in APP.datasets:
        raise ValueError(f"unknown dataset_id: {dataset_id}")
    df = APP.datasets[dataset_id]
    head = df.head(PREVIEW_ROWS).reset_index().copy()
    # ensure datetimes serialize cleanly to JSON
    for col in head.columns:
        if pd.api.types.is_datetime64_any_dtype(head[col]):
            head[col] = head[col].astype(str)
    return {
        "dataset_id": dataset_id,
        "columns": df.columns.tolist(),
        "rows_preview": head.to_dict(orient="records"),
    }


# ----------------------------- PROMPT ------------------------------

@mcp.prompt()
def indicator_query() -> str:
    """
    Instruction snippet for hosts/agents:
    1) list_indicators -> describe_indicator -> validate_params
    2) load_csv_dataset(dataset_id, path, date_col)
    3) compute_indicator(dataset_id, name, params)
    4) Preview via resource ohlcv://{dataset_id} or tool preview_ohlcv(dataset_id, limit)
    """
    return (
        "Use list_indicators → describe_indicator → validate_params.\n"
        "Load data with load_csv_dataset(dataset_id, path, date_col).\n"
        "Compute with compute_indicator(dataset_id, name, params).\n"
        "Preview via ohlcv://{dataset_id} or preview_ohlcv(dataset_id, limit)."
    )


# ----------------------------- ENTRY -------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
