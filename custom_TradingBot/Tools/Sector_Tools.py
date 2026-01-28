"""
Sector_Tools.py: Sector ranking tools using FMP API.

Provides sector-level analysis and ranking for use in portfolio tie-breaking
and sector exposure monitoring.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import sys
import os
import requests

# Import helpers from utils module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import format_tool_result

FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_API_KEY = os.getenv("fmp_api_key")


def _fmp_get(path: str, params: Dict[str, Any]) -> Any:
    """Thin wrapper around FMP GET requests for sector tools."""
    if not FMP_API_KEY:
        raise RuntimeError("fmp_api_key not set in environment for FMP sector tools")
    q = dict(params)
    q["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE_URL}{path}"
    resp = requests.get(url, params=q, timeout=30)
    resp.raise_for_status()
    return resp.json()


def register_sector_tools(mcp):
    """Register all sector analysis tools with MCP server"""

    @mcp.tool(name="get_sector_rankings")
    def get_sector_rankings(current_date: str) -> Dict[str, Any]:
        """
        Get sector rankings for tie-breaking trading decisions.

        Returns hardcoded S&P 500 sector rankings used for portfolio allocation.
        Stocks in same sector are grouped; rank determines trade priority.

        Args:
            current_date: Current trading date (YYYY-MM-DD) for context

        Returns:
            Dict with ranked sectors and classification system
        """
        tool_name = "get_sector_rankings"
        try:
            # S&P 500 sector list with default ranking
            # Can be updated dynamically with market data if available
            sectors = [
                {
                    "name": "Technology",
                    "score": 85.0,
                    "rank": 1,
                    "momentum": "strong",
                    "weight": 0.28,
                },
                {
                    "name": "Healthcare",
                    "score": 72.0,
                    "rank": 2,
                    "momentum": "moderate",
                    "weight": 0.13,
                },
                {
                    "name": "Financials",
                    "score": 68.0,
                    "rank": 3,
                    "momentum": "moderate",
                    "weight": 0.13,
                },
                {
                    "name": "Industrials",
                    "score": 62.0,
                    "rank": 4,
                    "momentum": "neutral",
                    "weight": 0.08,
                },
                {
                    "name": "Consumer Discretionary",
                    "score": 58.0,
                    "rank": 5,
                    "momentum": "neutral",
                    "weight": 0.12,
                },
                {
                    "name": "Energy",
                    "score": 55.0,
                    "rank": 6,
                    "momentum": "weak",
                    "weight": 0.04,
                },
                {
                    "name": "Materials",
                    "score": 52.0,
                    "rank": 7,
                    "momentum": "neutral",
                    "weight": 0.03,
                },
                {
                    "name": "Real Estate",
                    "score": 48.0,
                    "rank": 8,
                    "momentum": "weak",
                    "weight": 0.03,
                },
                {
                    "name": "Utilities",
                    "score": 45.0,
                    "rank": 9,
                    "momentum": "weak",
                    "weight": 0.03,
                },
                {
                    "name": "Consumer Staples",
                    "score": 42.0,
                    "rank": 10,
                    "momentum": "weak",
                    "weight": 0.07,
                },
                {
                    "name": "Communication Services",
                    "score": 40.0,
                    "rank": 11,
                    "momentum": "very_weak",
                    "weight": 0.07,
                },
            ]

            return format_tool_result(
                tool_name,
                data={
                    "sectors": sectors,
                    "date": current_date,
                    "total_sectors": len(sectors),
                    "note": "Default S&P 500 sector ranking for tie-breaking",
                }
            )

        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_sector_exposure")
    def get_sector_exposure(portfolio_state: Dict[str, Any], current_date: str) -> Dict[str, Any]:
        """
        Calculate sector exposure for current portfolio.

        Analyzes all positions in the portfolio and groups by sector.
        Useful for portfolio risk assessment and rebalancing.

        Args:
            portfolio_state: Current portfolio state dict with positions
            current_date: Current trading date (YYYY-MM-DD)

        Returns:
            Dict with sector exposure breakdown and concentration metrics
        """
        tool_name = "get_sector_exposure"
        try:
            # For now, return basic structure
            # Full implementation would fetch company sectors via FMP
            return format_tool_result(
                tool_name,
                data={
                    "date": current_date,
                    "sectors": {},
                    "message": "Requires company profile data to map symbols to sectors"
                }
            )

        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_company_sector")
    def get_company_sector(symbol: str) -> Dict[str, Any]:
        """
        Get sector classification for a stock symbol.

        Uses FMP company profile API to retrieve the sector.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with sector, industry, and classification
        """
        tool_name = "get_company_sector"
        try:
            if not symbol:
                raise ValueError("get_company_sector requires a non-empty symbol")

            # Fetch company profile from FMP
            data = _fmp_get(
                f"/profile/{symbol.upper()}",
                {}
            )

            if not data or not isinstance(data, list) or len(data) == 0:
                return format_tool_result(
                    tool_name,
                    error=f"No profile data for symbol {symbol}"
                )

            company = data[0]
            sector = company.get("sector", "Unknown")
            industry = company.get("industry", "Unknown")

            return format_tool_result(
                tool_name,
                data={
                    "symbol": symbol.upper(),
                    "sector": sector,
                    "industry": industry,
                    "exchange": company.get("exchange", "Unknown"),
                }
            )

        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)
