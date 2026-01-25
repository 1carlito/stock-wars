"""
Fundamental_Tools.py: Fundamental analysis tools using OpenBB SDK + FMP API
"""

from typing import Dict, Any, Optional
from openbb import obb
from functools import lru_cache
import sys
import os
import requests
from datetime import datetime, timedelta

# Import helpers from utils module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import _convert_openbb_result, format_tool_result, handle_premium_error, openbb_tool_wrapper

# FMP API configuration
FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_API_KEY = os.getenv("fmp_api_key")


def _fmp_get(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to call FMP API endpoints with error handling."""
    if not FMP_API_KEY:
        raise ValueError("FMP API key not configured (fmp_api_key env var missing)")

    params["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE_URL}{endpoint}"

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"FMP API error: {str(e)}")

# ============================================================================
# CACHED UNDERLYING OPENBB CALLS
# ============================================================================


@lru_cache(maxsize=512)
def _cached_income_statement(symbol: str, period: str, limit: int):
    return obb.equity.fundamental.income(symbol=symbol, period=period, limit=limit)


@lru_cache(maxsize=512)
def _cached_balance_sheet(symbol: str, period: str, limit: int):
    return obb.equity.fundamental.balance(symbol=symbol, period=period, limit=limit)


@lru_cache(maxsize=512)
def _cached_cash_flow(symbol: str, period: str, limit: int):
    return obb.equity.fundamental.cash(symbol=symbol, period=period, limit=limit)


@lru_cache(maxsize=512)
def _cached_company_profile(symbol: str):
    return obb.equity.profile(symbol=symbol)


@lru_cache(maxsize=512)
def _cached_analyst_estimates(symbol: str):
    return obb.equity.estimates.consensus(symbol=symbol)


@lru_cache(maxsize=512)
def _cached_earnings_reports(symbol: str):
    # Using FMP direct call for earnings reports as requested
    params = {"symbol": symbol}
    return _fmp_get("/earnings", params)

def register_fundamental_tools(mcp):
    """Register all fundamental analysis tools with MCP server"""
    
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
            # Use cached underlying earnings call
            result = _cached_earnings_reports(symbol)
            return format_tool_result(tool_name, data=result)
        except Exception as e:
            return format_tool_result(tool_name, error=e)
    
    @mcp.tool(name="get_analyst_estimates")
    @openbb_tool_wrapper("get_analyst_estimates")
    def get_analyst_estimates(symbol: str) -> Dict[str, Any]:
        """Get analyst estimates for a stock."""
        return _cached_analyst_estimates(symbol)

    @mcp.tool(name="get_key_metrics")
    def get_key_metrics(symbol: str) -> Dict[str, Any]:
        """
        Get key financial metrics and ratios (TTM - Trailing Twelve Months).
        """
        tool_name = "get_key_metrics"
        try:
            if not symbol:
                raise ValueError("get_key_metrics requires a non-empty symbol")

            params = {"symbol": symbol.upper()}
            data = _fmp_get("/key-metrics", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    # =========================================================================
    # FMP DIRECT IMPLEMENTATIONS
    # =========================================================================

    @mcp.tool(name="get_fmp_income_statement")
    def get_fmp_income_statement(symbol: str, limit: int = 5) -> Dict[str, Any]:
        """Get income statement via FMP direct API."""
        tool_name = "get_fmp_income_statement"
        try:
            params = {"symbol": symbol.upper(), "limit": limit}
            data = _fmp_get("/income-statement", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_balance_sheet")
    def get_fmp_balance_sheet(symbol: str, limit: int = 5) -> Dict[str, Any]:
        """Get balance sheet via FMP direct API."""
        tool_name = "get_fmp_balance_sheet"
        try:
            params = {"symbol": symbol.upper(), "limit": limit}
            data = _fmp_get("/balance-sheet-statement", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_key_metrics")
    def get_fmp_key_metrics(symbol: str, limit: int = 5) -> Dict[str, Any]:
        """Get key metrics (historical) via FMP direct API."""
        tool_name = "get_fmp_key_metrics"
        try:
            params = {"symbol": symbol.upper(), "limit": limit}
            data = _fmp_get("/key-metrics", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_ratings")
    def get_fmp_ratings(symbol: str) -> Dict[str, Any]:
        """Get analyst ratings snapshot via FMP direct API."""
        tool_name = "get_fmp_ratings"
        try:
            params = {"symbol": symbol.upper()}
            data = _fmp_get("/ratings-snapshot", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_price_targets")
    def get_fmp_price_targets(symbol: str) -> Dict[str, Any]:
        """Get price target summary via FMP direct API."""
        tool_name = "get_fmp_price_targets"
        try:
            params = {"symbol": symbol.upper()}
            data = _fmp_get("/price-target-summary", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:
            return format_tool_result(tool_name, error=e)

