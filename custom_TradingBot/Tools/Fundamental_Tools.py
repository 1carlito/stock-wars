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

    @mcp.tool(name="get_fundamental_summary")
    @openbb_tool_wrapper("get_fundamental_summary")
    def get_fundamental_summary(symbol: str) -> Dict[str, Any]:
        """
        Get a comprehensive fundamental summary for a stock.
        This aggregates multiple OpenBB calls into one to ensure data availability and prevent tool errors.
        
        Includes:
        - Company Profile
        - Income Statement (last 4 years)
        - Balance Sheet (last 4 years)
        - Cash Flow (last 4 years)
        - Analyst Estimates
        
        Args:
            symbol: Stock ticker symbol (e.g., AAPL)
            
        Returns:
            Dict containing all fundamental data.
        """
        tool_name = "get_fundamental_summary"
        result = {"symbol": symbol}
        
        try:
            # 1. Company Profile
            try:
                prof = _cached_company_profile(symbol)
                # handle OBBject vs dict
                if hasattr(prof, "results") and prof.results:
                    p_data = prof.results[0]
                    result["profile"] = p_data.model_dump() if hasattr(p_data, "model_dump") else (p_data.dict() if hasattr(p_data, "dict") else p_data)
                elif isinstance(prof, dict):
                    result["profile"] = prof
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
                        
                    key_name = f"{stmt_type}_statement"
                    
                    if hasattr(data, "results") and data.results:
                        processed_list = []
                        for item in data.results:
                            val = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
                            processed_list.append(val)
                        result[key_name] = processed_list
                    elif isinstance(data, dict):
                        result[key_name] = data
                except Exception as e:
                    result[f"{stmt_type}_error"] = str(e)

            # 3. Analyst Estimates
            try:
                est = _cached_analyst_estimates(symbol)
                if hasattr(est, "results") and est.results:
                    processed_list = []
                    for item in est.results:
                        val = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
                        processed_list.append(val)
                    result["analyst_estimates"] = processed_list
                elif isinstance(est, dict):
                    result["analyst_estimates"] = est
            except Exception as e:
                result["estimates_error"] = str(e)

            return format_tool_result(tool_name, data=result)

        except Exception as e:
            return format_tool_result(tool_name, error=f"Summary calc failed: {e}")


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

