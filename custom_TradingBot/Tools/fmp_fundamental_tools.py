"""
FMP Fundamental Tools
=====================
Fundamental analysis tools using FMP Direct API.
"""

from typing import Dict, Any
import requests
import os
import sys

# Import helpers from utils module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import format_tool_result

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

def register_fmp_fundamental_tools(mcp):
    """Register FMP fundamental analysis tools with MCP server"""

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

    @mcp.tool(name="get_key_metrics")
    def get_key_metrics(symbol: str) -> Dict[str, Any]:
        """
        Get key financial metrics and ratios (TTM - Trailing Twelve Months).
        (Aliases to FMP implementation)
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
