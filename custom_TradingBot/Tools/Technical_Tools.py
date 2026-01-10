"""
Technical_Tools.py: Technical indicator tools using OpenBB SDK + FMP precomputed indicators.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import lru_cache
import sys
import os
import requests
from openbb import obb

# Import helpers from utils module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import openbb_tool_wrapper, format_tool_result

FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_API_KEY = os.getenv("fmp_api_key")


@lru_cache(maxsize=512)
def _cached_price_history(symbol: str, start_date: str, end_date: str):
    """Cached wrapper around OpenBB price history to avoid duplicate requests.

    Keyed by (symbol, start_date, end_date). This improves performance both:
      - Within a single decision (multiple indicators reuse the same window)
      - Across backtest days, when the exact same window is requested again.
    """
    return obb.equity.price.historical(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


def _fetch_price_data(symbol: str, start_date: str, end_date: str):
    """Helper function to fetch price data for technical indicators (with caching)."""
    price_result = _cached_price_history(symbol, start_date, end_date)
    if hasattr(price_result, "results") and price_result.results:
        results = price_result.results
        # Prefer a DataFrame when available so we can de-duplicate and sort
        if hasattr(results, "to_dataframe"):
            df = results.to_dataframe()
            # Drop duplicate index entries that can cause technical functions to fail
            if not df.index.is_unique:
                df = df[~df.index.duplicated(keep="last")]
            df = df.sort_index()
            return df

        # Fallback: de-duplicate list-like data by date, if present
        if isinstance(results, list):
            seen_dates = set()
            cleaned = []
            for row in results:
                date_val = None
                if hasattr(row, "date"):
                    date_val = getattr(row, "date")
                elif isinstance(row, dict):
                    date_val = row.get("date")
                if date_val in seen_dates:
                    continue
                if date_val is not None:
                    seen_dates.add(date_val)
                cleaned.append(row)
            return cleaned

        return results
    raise ValueError(f"No price data returned for {symbol} from {start_date} to {end_date}")


def _fmp_get(path: str, params: Dict[str, Any]) -> Any:
    """Thin wrapper around FMP GET requests for technical indicators."""
    if not FMP_API_KEY:
        raise RuntimeError("fmp_api_key not set in environment for FMP technical tools")
    q = dict(params)
    q["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE_URL}{path}"
    resp = requests.get(url, params=q, timeout=30)
    resp.raise_for_status()
    return resp.json()


def register_technical_tools(mcp):
    """Register all technical indicator tools with MCP server"""
    
    @mcp.tool(name="calculate_rsi")
    @openbb_tool_wrapper("calculate_rsi")
    def calculate_rsi(
        symbol: str,
        start_date: str,
        end_date: str,
        length: int = 14,
        target: str = "close"
    ) -> Dict[str, Any]:
        """
        Calculate Relative Strength Index (RSI) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: RSI period (default: 14)
            target: Target column name (default: "close")
        
        Returns:
            Dict with RSI data
        """
        # Fetch price data first
        price_data = _fetch_price_data(symbol, start_date, end_date)

        # Calculate RSI on the price data
        return obb.technical.rsi(
            data=price_data,
            target=target,
            length=length,
        )
    
    @mcp.tool(name="calculate_bbands")
    @openbb_tool_wrapper("calculate_bbands")
    def calculate_bbands(
        symbol: str,
        start_date: str,
        end_date: str,
        length: int = 20,
        std: float = 2.0,
        target: str = "close"
    ) -> Dict[str, Any]:
        """
        Calculate Bollinger Bands for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: Period for moving average (default: 20)
            std: Standard deviation multiplier (default: 2.0)
            target: Target column name (default: "close")
        
        Returns:
            Dict with Bollinger Bands data
        """
        # Fetch price data first
        price_data = _fetch_price_data(symbol, start_date, end_date)

        # Calculate Bollinger Bands on the price data
        return obb.technical.bbands(
            data=price_data,
            target=target,
            length=length,
            std=std,
        )
    
    @mcp.tool(name="calculate_atr")
    @openbb_tool_wrapper("calculate_atr")
    def calculate_atr(
        symbol: str,
        start_date: str,
        end_date: str,
        length: int = 14
    ) -> Dict[str, Any]:
        """
        Calculate Average True Range (ATR) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: ATR period (default: 14)
        
        Returns:
            Dict with ATR data
        """
        # Fetch price data first
        price_data = _fetch_price_data(symbol, start_date, end_date)

        # Calculate ATR on the price data
        return obb.technical.atr(
            data=price_data,
            length=length,
        )
    
    @mcp.tool(name="calculate_obv")
    @openbb_tool_wrapper("calculate_obv")
    def calculate_obv(
        symbol: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Calculate On-Balance Volume (OBV) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
        
        Returns:
            Dict with OBV data
        """
        # Fetch price data first
        price_data = _fetch_price_data(symbol, start_date, end_date)

        # Calculate OBV on the price data
        return obb.technical.obv(data=price_data)
    
    @mcp.tool(name="calculate_adx")
    @openbb_tool_wrapper("calculate_adx")
    def calculate_adx(
        symbol: str,
        start_date: str,
        end_date: str,
        length: int = 14
    ) -> Dict[str, Any]:
        """
        Calculate Average Directional Index (ADX) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: ADX period (default: 14)
        
        Returns:
            Dict with ADX data
        """
        # Fetch price data first
        price_data = _fetch_price_data(symbol, start_date, end_date)

        # Calculate ADX on the price data
        return obb.technical.adx(
            data=price_data,
            length=length,
        )
    
    @mcp.tool(name="calculate_ema")
    @openbb_tool_wrapper("calculate_ema")
    def calculate_ema(
        symbol: str,
        start_date: str,
        end_date: str,
        length: int = 50,
        target: str = "close"
    ) -> Dict[str, Any]:
        """
        Calculate Exponential Moving Average (EMA) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: EMA period (default: 50)
            target: Target column name (default: "close")
        
        Returns:
            Dict with EMA data
        """
        # Fetch price data first
        price_data = _fetch_price_data(symbol, start_date, end_date)

        # Calculate EMA on the price data
        return obb.technical.ema(
            data=price_data,
            target=target,
            length=length,
        )
    
    @mcp.tool(name="calculate_cci")
    @openbb_tool_wrapper("calculate_cci")
    def calculate_cci(
        symbol: str,
        start_date: str,
        end_date: str,
        length: int = 20
    ) -> Dict[str, Any]:
        """
        Calculate Commodity Channel Index (CCI) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: CCI period (default: 20)
        
        Returns:
            Dict with CCI data
        """
        # Fetch price data first
        price_data = _fetch_price_data(symbol, start_date, end_date)

        # Calculate CCI on the price data
        return obb.technical.cci(
            data=price_data,
            length=length,
        )
    
    @mcp.tool(name="get_price_history")
    @openbb_tool_wrapper("get_price_history")
    def get_price_history(
        symbol: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Get historical price data for a stock.

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dict with price history data
        """
        # Reuse the same cached underlying call used by technical indicators
        return _cached_price_history(symbol, start_date, end_date)
    
    @mcp.tool(name="get_current_price")
    @openbb_tool_wrapper("get_current_price")
    def get_current_price(
        symbol: str,
        current_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get current price for a stock. If current_date is provided, gets price as of that date.
        """
        if current_date:
            return obb.equity.price.historical(
                symbol=symbol,
                start_date=current_date,
                end_date=current_date,
            )
        return obb.equity.price.quote(symbol=symbol)

    # -----------------------------------------------------------------------
    # FMP PRECOMPUTED TECHNICAL INDICATORS (RSI, EMA)
    # -----------------------------------------------------------------------

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
        Uses /technical-indicators/rsi with from/to date range.
        """
        tool_name = "get_fmp_rsi"
        try:
            if not symbol:
                raise ValueError("get_fmp_rsi requires a non-empty symbol")

            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            if ed < sd:
                sd, ed = ed, sd
            # Clamp to max ~120 days window
            if (ed - sd).days > 120:
                sd = ed - timedelta(days=120)

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
                "periodLength": int(period_length),
                "timeframe": timeframe,
                "from": sd.strftime("%Y-%m-%d"),
                "to": ed.strftime("%Y-%m-%d"),
            }
            data = _fmp_get("/technical-indicators/rsi", params)
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
        Uses /technical-indicators/ema with from/to date range.
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
            data = _fmp_get("/technical-indicators/ema", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

