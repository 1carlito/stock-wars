"""
OpenBB Fundamental Tools
========================
Fundamental analysis tools using OpenBB SDK.

Falls back to yfinance directly when OpenBB returns empty results
(known issue: OpenBB's yfinance provider breaks with pandas >= 3.0
due to deprecated Timestamp.utcnow usage).
"""

from typing import Dict, Any, List
from openbb import obb
from functools import lru_cache
import sys
import os
import requests

# Import helpers from utils module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import _convert_openbb_result, format_tool_result, openbb_tool_wrapper
from data_management.cache_manager import CacheManager

# Initialize cache
_cache_manager = CacheManager(cache_dir=os.path.join(parent_dir, ".cache"), ttl_hours=24)

# FMP fallback for earnings reports
FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_API_KEY = os.getenv("fmp_api_key")

def _fmp_get_simple(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Simple internal helper for isolated FMP calls (like earnings) within this module."""
    if not FMP_API_KEY:
        raise ValueError("FMP API key (fmp_api_key) is not set. Cannot fetch earnings data.")
    params["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        if not data:
            raise ValueError(f"FMP returned empty response for {endpoint}")
        return data
    except requests.RequestException as e:
        raise ValueError(f"FMP request failed for {endpoint}: {e}") from e


# ============================================================================
# YFINANCE DIRECT FALLBACK
# ============================================================================
# OpenBB's yfinance provider silently returns empty results with pandas >= 3.0.
# yfinance itself works fine — only the OpenBB wrapper is broken.
# These functions call yfinance directly as a fallback.

def _yf_df_to_records(df, limit: int = 5) -> List[Dict[str, Any]]:
    """Convert a yfinance DataFrame (columns=dates, index=metrics) to list of dicts."""
    if df is None or df.empty:
        return []
    records = []
    for col in df.columns[:limit]:
        row = {"period_ending": str(col.date()) if hasattr(col, "date") else str(col)}
        for metric in df.index:
            val = df.loc[metric, col]
            if hasattr(val, "item"):
                val = val.item()
            row[metric] = val
        records.append(row)
    return records


@lru_cache(maxsize=512)
def _yf_income_statement(symbol: str, period: str, limit: int) -> List[Dict[str, Any]]:
    """Fetch income statement directly from yfinance."""
    import yfinance as yf
    t = yf.Ticker(symbol)
    df = t.quarterly_income_stmt if period == "quarter" else t.income_stmt
    return _yf_df_to_records(df, limit)


@lru_cache(maxsize=512)
def _yf_balance_sheet(symbol: str, period: str, limit: int) -> List[Dict[str, Any]]:
    """Fetch balance sheet directly from yfinance."""
    import yfinance as yf
    t = yf.Ticker(symbol)
    df = t.quarterly_balance_sheet if period == "quarter" else t.balance_sheet
    return _yf_df_to_records(df, limit)


@lru_cache(maxsize=512)
def _yf_cash_flow(symbol: str, period: str, limit: int) -> List[Dict[str, Any]]:
    """Fetch cash flow directly from yfinance."""
    import yfinance as yf
    t = yf.Ticker(symbol)
    df = t.quarterly_cashflow if period == "quarter" else t.cashflow
    return _yf_df_to_records(df, limit)


def _fetch_yf_isolated(symbol: str, method: str, period: str, limit: int) -> List[Dict[str, Any]]:
    """
    Fetch yfinance fundamental data in an isolated subprocess.
    This bypasses process-level "pollution" caused by failed OpenBB calls.
    """
    import json
    import subprocess
    
    # Map method name to yfinance Ticker attribute
    attr = {
        "income": "quarterly_income_stmt" if period == "quarter" else "income_stmt",
        "balance": "quarterly_balance_sheet" if period == "quarter" else "balance_sheet",
        "cash": "quarterly_cashflow" if period == "quarter" else "cashflow"
    }.get(method)

    if not attr:
        return []

    code = f"""
import yfinance as yf
import json
import sys

def _yf_df_to_records(df, limit):
    if df is None or df.empty:
        return []
    records = []
    for col in df.columns[:limit]:
        row = {{"period_ending": str(col.date()) if hasattr(col, "date") else str(col)}}
        for metric in df.index:
            val = df.loc[metric, col]
            if hasattr(val, "item"):
                val = val.item()
            row[metric] = val
        records.append(row)
    return records

try:
    t = yf.Ticker("{symbol}")
    df = getattr(t, "{attr}")
    records = _yf_df_to_records(df, {limit})
    print(json.dumps(records))
except Exception:
    print(json.dumps([]))
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception:
        pass
    return []


# ============================================================================
# CACHED UNDERLYING CALLS (OpenBB -> yfinance direct fallback)
# ============================================================================

def _get_fundamental_data(cache_key_prefix: str, method: str, symbol: str, period: str, limit: int) -> List[Dict[str, Any]]:
    """
    Consolidated helper to fetch fundamental data with yfinance fallback.
    Tries direct yf first, then isolated yf if direct fails or is polluted.
    """
    cache_key = f"{cache_key_prefix}:{symbol}:{period}:{limit}"
    cached = _cache_manager.get(cache_key)
    if cached:
        return cached

    # 1. Try direct yf (might be polluted by OpenBB import/usage)
    data = []
    try:
        if method == "income":
            data = _yf_income_statement(symbol, period, limit)
        elif method == "balance":
            data = _yf_balance_sheet(symbol, period, limit)
        elif method == "cash":
            data = _yf_cash_flow(symbol, period, limit)
    except Exception:
        pass

    if not data:
        # 2. Try isolated yf (bypasses process pollution)
        data = _fetch_yf_isolated(symbol, method, period, limit)

    if data:
        _cache_manager.set(cache_key, data)
    return data


@lru_cache(maxsize=512)
def _cached_income_statement(symbol: str, period: str, limit: int):
    return _get_fundamental_data("income", "income", symbol, period, limit)


@lru_cache(maxsize=512)
def _cached_balance_sheet(symbol: str, period: str, limit: int):
    return _get_fundamental_data("balance", "balance", symbol, period, limit)


@lru_cache(maxsize=512)
def _cached_cash_flow(symbol: str, period: str, limit: int):
    return _get_fundamental_data("cash", "cash", symbol, period, limit)


@lru_cache(maxsize=512)
def _cached_company_profile(symbol: str):
    return obb.equity.profile(symbol=symbol)




def _cached_earnings_reports(symbol: str):
    """Fetch earnings reports from FMP. Not cached to avoid permanently caching errors/empty results."""
    params = {"symbol": symbol}
    return _fmp_get_simple("/earnings", params)

def register_openbb_fundamental_tools(mcp):
    """Register all OpenBB fundamental analysis tools with MCP server"""

    @mcp.tool(name="get_income_statement")
    @openbb_tool_wrapper("get_income_statement")
    def get_income_statement(
        symbol: str,
        period: str = "annual",
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Get income statement data for a stock."""
        return _cached_income_statement(symbol, period, limit)

    @mcp.tool(name="get_balance_sheet")
    @openbb_tool_wrapper("get_balance_sheet")
    def get_balance_sheet(
        symbol: str,
        period: str = "annual",
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Get balance sheet data for a stock."""
        return _cached_balance_sheet(symbol, period, limit)

    @mcp.tool(name="get_cash_flow")
    @openbb_tool_wrapper("get_cash_flow")
    def get_cash_flow(
        symbol: str,
        period: str = "annual",
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Get cash flow statement data for a stock."""
        return _cached_cash_flow(symbol, period, limit)

    @mcp.tool(name="get_company_profile")
    @openbb_tool_wrapper("get_company_profile")
    def get_company_profile(symbol: str) -> Dict[str, Any]:
        """Get company profile/overview for a stock."""
        return _cached_company_profile(symbol)

    @mcp.tool(name="get_earnings_reports")
    def get_earnings_reports(
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Get historical earnings reports.
        """
        tool_name = "get_earnings_reports"
        try:
            result = _cached_earnings_reports(symbol)
            return format_tool_result(tool_name, data=result)
        except Exception as e:
            return format_tool_result(tool_name, error=e)


    @mcp.tool(name="get_fundamental_summary")
    def get_fundamental_summary(symbol: str) -> Dict[str, Any]:
        """
        Get a comprehensive fundamental summary for a stock.
        This aggregates profile and financial statements into one call.
        """
        tool_name = "get_fundamental_summary"
        result = {"symbol": symbol}

        # 1. Company Profile
        try:
            prof = _cached_company_profile(symbol)
            result["profile"] = _convert_openbb_result(prof)
        except Exception as e:
            result["profile_error"] = str(e)

        # 2. Financial Statements (Income, Balance, Cash) - Limit 4 years
        limit = 4
        for stmt_type in ["income", "balance", "cash"]:
            try:
                if stmt_type == "income":
                    data = _cached_income_statement(symbol, "annual", limit)
                elif stmt_type == "balance":
                    data = _cached_balance_sheet(symbol, "annual", limit)
                else:
                    data = _cached_cash_flow(symbol, "annual", limit)
                
                result[f"{stmt_type}_statement"] = _convert_openbb_result(data)
            except Exception as e:
                result[f"{stmt_type}_error"] = str(e)

        return format_tool_result(tool_name, data=result)
