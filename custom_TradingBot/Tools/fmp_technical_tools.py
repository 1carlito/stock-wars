"""
FMP Technical Tools
===================
Technical analysis tools using FMP Direct API (Precomputed).
"""

from typing import Dict, Any, List
import requests
import os
import sys
from datetime import datetime, timedelta

# Import helpers from utils module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import format_tool_result

# FMP API configuration
FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_API_KEY = os.getenv("fmp_api_key")

def _fmp_get(endpoint: str, params: Dict[str, Any]) -> Any:
    """Helper to call FMP API endpoints."""
    if not FMP_API_KEY:
        raise ValueError("fmp_api_key not set in environment for FMP technical tools")
    if "apikey" not in params:
        params["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE_URL}{endpoint}"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _simplify_fmp_series(data: Any, keep_fields: Dict[str, Any]) -> Any:
    """Reduce FMP technical-indicator payloads to only the fields we actually need."""
    if not isinstance(data, list) or not data:
        return data

    simplified = []
    for row in data:
        if not isinstance(row, dict):
            continue
        entry = {}
        for field in keep_fields:
            if field in row:
                entry[field] = row[field]
        if entry:
            simplified.append(entry)
    return simplified


def register_fmp_technical_tools(mcp):
    """Register FMP technical tools with MCP server"""

    @mcp.tool(name="get_fmp_rsi")
    def get_fmp_rsi(
        symbol: str,
        start_date: str,
        end_date: str,
        period_length: int = 14,
        timeframe: str = "1day",
    ) -> Dict[str, Any]:
        """
        Get precomputed RSI from FMP technical-indicators API.
        """
        tool_name = "get_fmp_rsi"
        try:
            if not symbol:
                raise ValueError("get_fmp_rsi requires a non-empty symbol")

            # Ensure we have a reasonable date range request
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            if ed < sd:
                sd, ed = ed, sd
            if (ed - sd).days > 120:
                sd = ed - timedelta(days=120)

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
                "periodLength": int(period_length),
                "timeframe": timeframe,
                "from": sd.strftime("%Y-%m-%d"),
                "to": ed.strftime("%Y-%m-%d"),
            }
            raw = _fmp_get("/technical-indicators/rsi", params)
            # Keep only date, close (for price context), and RSI value
            data = _simplify_fmp_series(raw, ["date", "close", "rsi"])
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_ema")
    def get_fmp_ema(
        symbol: str,
        start_date: str,
        end_date: str,
        period_length: int = 50,
        timeframe: str = "1day",
    ) -> Dict[str, Any]:
        """
        Get precomputed EMA from FMP technical-indicators API.
        """
        tool_name = "get_fmp_ema"
        try:
            if not symbol:
                raise ValueError("get_fmp_ema requires a non-empty symbol")

            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            if ed < sd:
                sd, ed = ed, sd
            if (ed - sd).days > 120:
                sd = ed - timedelta(days=120)

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
                "periodLength": int(period_length),
                "timeframe": timeframe,
                "from": sd.strftime("%Y-%m-%d"),
                "to": ed.strftime("%Y-%m-%d"),
            }
            raw = _fmp_get("/technical-indicators/ema", params)
            # Keep only date, close, and EMA value
            data = _simplify_fmp_series(raw, ["date", "close", "ema"])
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_sma")
    def get_fmp_sma(
        symbol: str,
        start_date: str,
        end_date: str,
        period_length: int = 50,
        timeframe: str = "1day",
    ) -> Dict[str, Any]:
        """Get precomputed SMA (Simple Moving Average) from FMP."""
        tool_name = "get_fmp_sma"
        try:
            if not symbol:
                raise ValueError("get_fmp_sma requires a non-empty symbol")

            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            if ed < sd:
                sd, ed = ed, sd
            if (ed - sd).days > 120:
                sd = ed - timedelta(days=120)

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
                "periodLength": int(period_length),
                "timeframe": timeframe,
                "from": sd.strftime("%Y-%m-%d"),
                "to": ed.strftime("%Y-%m-%d"),
            }
            raw = _fmp_get("/technical-indicators/sma", params)
            data = _simplify_fmp_series(raw, ["date", "close", "sma"])
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_wma")
    def get_fmp_wma(
        symbol: str,
        start_date: str,
        end_date: str,
        period_length: int = 50,
        timeframe: str = "1day",
    ) -> Dict[str, Any]:
        """Get precomputed WMA (Weighted Moving Average) from FMP."""
        tool_name = "get_fmp_wma"
        try:
            if not symbol:
                raise ValueError("get_fmp_wma requires a non-empty symbol")

            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            if ed < sd:
                sd, ed = ed, sd
            if (ed - sd).days > 120:
                sd = ed - timedelta(days=120)

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
                "periodLength": int(period_length),
                "timeframe": timeframe,
                "from": sd.strftime("%Y-%m-%d"),
                "to": ed.strftime("%Y-%m-%d"),
            }
            raw = _fmp_get("/technical-indicators/wma", params)
            data = _simplify_fmp_series(raw, ["date", "close", "wma"])
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_real_time_quote")
    def get_fmp_real_time_quote(symbol: str) -> Dict[str, Any]:
        """
        Get real-time stock quote with current price and key market data from FMP.
        Returns current price, bid/ask spread, volume, market cap, PE ratio, and other metrics.
        """
        tool_name = "get_fmp_real_time_quote"
        try:
            if not symbol:
                raise ValueError("get_fmp_real_time_quote requires a non-empty symbol")

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
            }
            data = _fmp_get("/quote", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)
