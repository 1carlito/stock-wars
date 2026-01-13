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
def _cached_earnings_calendar(start_date: str, end_date: str, symbol: Optional[str]):
    return obb.equity.calendar.earnings(
        start_date=start_date,
        end_date=end_date,
        symbol=symbol,
    )

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
    
    @mcp.tool(name="get_earnings_calendar")
    def get_earnings_calendar(
        start_date: str,
        end_date: str,
        symbol: Optional[str] = None,
        current_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get earnings calendar for a date range. Optionally filter by symbol.
        If current_date is provided, only returns earnings up to that date (prevents lookahead bias).

        NOTE: This endpoint may require a premium FMP subscription. When unavailable,
        a friendly message is returned instead of a raw 402 error.
        """
        tool_name = "get_earnings_calendar"
        try:
            # If current_date is provided, limit end_date to current_date
            if current_date and current_date < end_date:
                end_date = current_date

            # Use cached underlying earnings call
            result = _cached_earnings_calendar(start_date, end_date, symbol)
            data = _convert_openbb_result(result)

            # If symbol is provided, filter results to only that symbol
            if symbol and isinstance(data, dict) and "data" in data:
                if isinstance(data["data"], list):
                    data["data"] = [
                        item for item in data["data"] if item.get("symbol") == symbol
                    ]

            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001 - we want to surface any tool error
            # Prefer a clean premium subscription message when applicable
            return handle_premium_error(
                tool_name,
                e,
                fallback_message=(
                    "Earnings calendar data requires a premium FMP subscription. "
                    "This feature is not available on the free tier. "
                    "You can use get_company_profile to get basic earnings information."
                ),
            )
    
    @mcp.tool(name="get_analyst_estimates")
    @openbb_tool_wrapper("get_analyst_estimates")
    def get_analyst_estimates(symbol: str) -> Dict[str, Any]:
        """Get analyst estimates for a stock."""
        return _cached_analyst_estimates(symbol)

    @mcp.tool(name="get_key_metrics")
    def get_key_metrics(symbol: str) -> Dict[str, Any]:
        """
        Get key financial metrics and ratios (TTM - Trailing Twelve Months).

        Returns essential metrics including PE ratio, PB ratio, ROE, ROA, debt-to-equity,
        current ratio, and other financial health indicators.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with key metrics including PE, PB, ROE, ROA, debt-to-equity, etc.
        """
        tool_name = "get_key_metrics"
        try:
            if not symbol:
                raise ValueError("get_key_metrics requires a non-empty symbol")

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
            }
            data = _fmp_get("/key-metrics-ttm", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_financial_scores")
    def get_financial_scores(symbol: str) -> Dict[str, Any]:
        """
        Get financial health scores for company valuation and risk assessment.

        Returns Altman Z-Score and Piotroski Score:
        - Altman Z-Score: Bankruptcy prediction (>2.99=Safe, 1.81-2.99=Gray, <1.81=Distress)
        - Piotroski Score: Financial strength assessment (0-9 scale, >5=Strong)

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with Altman Z-Score, Piotroski Score, and interpretation
        """
        tool_name = "get_financial_scores"
        try:
            if not symbol:
                raise ValueError("get_financial_scores requires a non-empty symbol")

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
            }
            data = _fmp_get("/financial-score", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

