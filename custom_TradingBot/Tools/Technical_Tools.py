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
from cache_manager import CacheManager

FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_API_KEY = os.getenv("fmp_api_key")

# Initialize dual-layer cache: L2 file-based cache (persists across restarts)
_cache_manager = CacheManager(cache_dir=os.path.join(parent_dir, ".cache"), ttl_hours=24)


@lru_cache(maxsize=512)
def _cached_price_history_l1(symbol: str, start_date: str, end_date: str):
    """L1 in-memory cache (fast, lost on restart).

    Keyed by (symbol, start_date, end_date). This improves performance within:
      - A single decision (multiple indicators reuse the same window)
      - Across decisions in the same process run
    """
    return obb.equity.price.historical(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


def _cached_price_history(symbol: str, start_date: str, end_date: str):
    """Dual-layer cache wrapper: L2 file-based + L1 in-memory.

    Check sequence:
      1. L2 file cache (persistent, survives restarts)
      2. L1 @lru_cache memory cache (fast, lost on restart)
      3. API call to OpenBB
      4. Store in L2 file cache for next restart

    Args:
        symbol: Stock ticker symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Price history result from OpenBB
    """
    cache_key = f"price:{symbol}:{start_date}:{end_date}"

    # Try L2 file cache first
    cached_result = _cache_manager.get(cache_key)
    if cached_result is not None:
        return cached_result

    # L2 miss: Call L1 (memory cache + API)
    result = _cached_price_history_l1(symbol, start_date, end_date)

    # Store in L2 for next restart
    _cache_manager.set(cache_key, result)

    return result


def _fetch_price_data(symbol: str, start_date: str, end_date: str):
    """Helper function to fetch price data for technical indicators (with caching).

    Handles both OBBject (from API) and dict (from cache).
    """
    price_result = _cached_price_history(symbol, start_date, end_date)

    # Handle both OBBject (from API) and dict (from cache)
    results = None
    if hasattr(price_result, "results"):
        # OBBject from API call
        results = price_result.results
    elif isinstance(price_result, dict) and "results" in price_result:
        # Dict from file cache - extract results
        results = price_result["results"]

    if results:
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

    @mcp.tool(name="get_fmp_sma")
    def get_fmp_sma(
        symbol: str,
        start_date: str,
        end_date: str,
        period_length: int = 50,
        timeframe: str = "1day",
    ) -> Dict[str, Any]:
        """
        Get precomputed SMA (Simple Moving Average) from FMP technical-indicators API.
        Uses /technical-indicators/sma with from/to date range.
        """
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
            data = _fmp_get("/technical-indicators/sma", params)
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
        """
        Get precomputed WMA (Weighted Moving Average) from FMP technical-indicators API.
        Uses /technical-indicators/wma with from/to date range.
        """
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
            data = _fmp_get("/technical-indicators/wma", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_bbands")
    def get_fmp_bbands(
        symbol: str,
        start_date: str,
        end_date: str,
        period_length: int = 20,
        timeframe: str = "1day",
    ) -> Dict[str, Any]:
        """
        Get Bollinger Bands indicator from FMP.

        Bollinger Bands consist of:
        - Moving average (middle band)
        - Upper band: MA + (2 * std dev)
        - Lower band: MA - (2 * std dev)

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period_length: Period for MA calculation (default: 20)
            timeframe: "1day" or "4hour" (default: "1day")

        Returns:
            Dict with Bollinger Bands data
        """
        tool_name = "get_fmp_bbands"
        try:
            if not symbol:
                raise ValueError("get_fmp_bbands requires a non-empty symbol")

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
            data = _fmp_get("/technical-indicators/bbands", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_fmp_obv")
    def get_fmp_obv(
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1day",
    ) -> Dict[str, Any]:
        """
        Get On-Balance Volume (OBV) indicator from FMP.

        OBV measures cumulative buying/selling pressure:
        - If close > previous close: Add volume to OBV
        - If close < previous close: Subtract volume from OBV
        - If close = previous close: OBV unchanged

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            timeframe: "1day" or "4hour" (default: "1day")

        Returns:
            Dict with OBV data
        """
        tool_name = "get_fmp_obv"
        try:
            if not symbol:
                raise ValueError("get_fmp_obv requires a non-empty symbol")

            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")

            if ed < sd:
                sd, ed = ed, sd
            if (ed - sd).days > 120:
                sd = ed - timedelta(days=120)

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "from": sd.strftime("%Y-%m-%d"),
                "to": ed.strftime("%Y-%m-%d"),
            }
            data = _fmp_get("/technical-indicators/obv", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_4hour_chart")
    def get_4hour_chart(
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Get 4-hour OHLCV chart data from FMP for intraday analysis.

        Perfect for 4-hour interval trading and twice-daily portfolio cycles.
        Returns: Open, High, Low, Close, Volume for each 4-hour candle.

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dict with 4-hour OHLCV bars
        """
        tool_name = "get_4hour_chart"
        try:
            if not symbol:
                raise ValueError("get_4hour_chart requires a non-empty symbol")

            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")

            if ed < sd:
                sd, ed = ed, sd

            # Clamp to max 120 days for performance
            if (ed - sd).days > 120:
                sd = ed - timedelta(days=120)

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
                "from": sd.strftime("%Y-%m-%d"),
                "to": ed.strftime("%Y-%m-%d"),
            }
            data = _fmp_get("/historical-chart/4hour", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_real_time_quote")
    def get_real_time_quote(symbol: str) -> Dict[str, Any]:
        """
        Get real-time stock quote with current price and key market data.

        Returns current price, bid/ask spread, volume, market cap, PE ratio, and other metrics.
        Updated in real-time during market hours.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with real-time quote data including price, change, volume, market cap, PE ratio
        """
        tool_name = "get_real_time_quote"
        try:
            if not symbol:
                raise ValueError("get_real_time_quote requires a non-empty symbol")

            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
            }
            data = _fmp_get("/quote", params)
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_premarket_context")
    def get_premarket_context(symbol: str, trade_date: str) -> Dict[str, Any]:
        """
        Analyze gap and early morning momentum for pre-market context.

        Provides market gap (previous close to market open) and early morning
        price action (9:30am-10am) to inform trading decisions at 10am ET.

        Args:
            symbol: Stock ticker symbol
            trade_date: Trading date (YYYY-MM-DD format)

        Returns:
            Dict with gap percentage, direction, early momentum, and key price levels
        """
        tool_name = "get_premarket_context"
        try:
            if not symbol:
                raise ValueError("get_premarket_context requires a non-empty symbol")

            symbol = symbol.upper()

            # 1. Get yesterday's close (date before trade_date)
            try:
                yesterday = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

                # Try to fetch historical data for yesterday
                hist_params: Dict[str, Any] = {
                    "symbol": symbol,
                    "from": yesterday,
                    "to": yesterday,
                }
                hist_data = _fmp_get("/historical-price-full", hist_params)

                if not hist_data or len(hist_data) == 0:
                    # If no data, use OpenBB as fallback
                    hist_data = obb.equity.price.historical(
                        symbol=symbol,
                        start_date=yesterday,
                        end_date=yesterday,
                    )

                prev_close = hist_data[0].get("close", 0) if hist_data else 0
            except Exception:
                prev_close = 0

            # 2. Get today's opening (from real-time quote or 4-hour chart)
            try:
                quote_params: Dict[str, Any] = {"symbol": symbol}
                quote_data = _fmp_get("/quote", quote_params)
                market_open = quote_data[0].get("open", 0) if quote_data else 0
                current_price = quote_data[0].get("price", 0) if quote_data else 0
            except Exception:
                market_open = 0
                current_price = 0

            # 3. Calculate gap
            if prev_close != 0:
                gap_pct = ((market_open - prev_close) / prev_close) * 100
                gap_usd = market_open - prev_close
            else:
                gap_pct = 0
                gap_usd = 0

            gap_direction = "UP" if gap_usd > 0 else "DOWN" if gap_usd < 0 else "FLAT"

            # 4. Determine early momentum (9:30am open to current 10am price)
            if market_open != 0:
                move_from_open = current_price - market_open
                move_pct = (move_from_open / market_open) * 100
                momentum_direction = "CONTINUATION" if (move_from_open > 0 and gap_usd > 0) or (move_from_open < 0 and gap_usd < 0) else "REVERSAL"
            else:
                move_from_open = 0
                move_pct = 0
                momentum_direction = "UNKNOWN"

            return format_tool_result(
                tool_name,
                data={
                    "trade_date": trade_date,
                    "symbol": symbol,
                    "gap_analysis": {
                        "previous_close": round(prev_close, 2),
                        "market_open": round(market_open, 2),
                        "gap_usd": round(gap_usd, 2),
                        "gap_percent": round(gap_pct, 2),
                        "gap_direction": gap_direction,
                    },
                    "early_momentum": {
                        "current_price": round(current_price, 2),
                        "move_from_open_usd": round(move_from_open, 2),
                        "move_from_open_percent": round(move_pct, 2),
                        "momentum_type": momentum_direction,
                    },
                    "interpretation": f"Gap {gap_direction} {abs(gap_pct):.2f}% with {momentum_direction.lower()} momentum"
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=str(e))

