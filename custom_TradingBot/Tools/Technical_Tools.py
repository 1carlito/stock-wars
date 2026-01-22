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


# ============================================================================
# UTILITY: CHECK IF DATE IS TODAY
# ============================================================================

def _is_today(date_str: str) -> bool:
    """
    Check if a date string (YYYY-MM-DD) is today's date.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        True if date is today, False otherwise
    """
    try:
        from datetime import date
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        return target_date == date.today()
    except (ValueError, AttributeError):
        return False


# ============================================================================
# UTILITY: RESAMPLE 60m CANDLES TO 4h
# ============================================================================

def _resample_to_4h(intraday_data: Any) -> Any:
    """
    Resample 60-minute candle data to 4-hour OHLCV bars.

    This allows free tier users to get 4-hour data from yfinance's 60m candles.

    Args:
        intraday_data: List of 60m candle dicts or OpenBB OBBjets

    Returns:
        List of 4-hour candles with OHLCV data
    """
    try:
        import pandas as pd
    except ImportError:
        return intraday_data  # Fallback: return as-is

    if not intraday_data:
        return []

    # Convert to list of dicts
    candles_list = []
    for candle in intraday_data:
        if hasattr(candle, "model_dump"):
            candles_list.append(candle.model_dump())
        elif hasattr(candle, "dict"):
            candles_list.append(candle.dict())
        elif isinstance(candle, dict):
            candles_list.append(candle)

    if not candles_list:
        return []

    # Create DataFrame
    df = pd.DataFrame(candles_list)

    # Ensure date column is datetime
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)

    # Resample to 4h: OHLCV aggregation
    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }

    resampled = df.resample("4H").agg(agg_dict).dropna()

    # Convert back to list of dicts with date as column
    resampled = resampled.reset_index()
    return resampled.to_dict("records")


# ============================================================================
# ORCHESTRATOR: GET TECHNICAL DATA FOR DECISION CYCLE
# ============================================================================

def get_technical_data_for_cycle(
    symbol: str,
    trade_date: str,
    time_of_day: str,
    user_tier: str = "free",
    has_fmp_access: bool = False,
    stored_daily_indicators: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Orchestrate technical data fetching based on date.

    Strategy:
    - TODAY's date: Use latest 30-minute intraday candle + current price (FMP if available)
    - BEFORE TODAY: Use daily candles (existing logic)

    Args:
        symbol: Stock ticker symbol
        trade_date: Date to analyze (YYYY-MM-DD)
        time_of_day: "1pm" or "7pm" (kept for backward compatibility)
        user_tier: "free" or "starter"
        has_fmp_access: Whether user has FMP API key
        stored_daily_indicators: Yesterday's daily indicators (cached for reference)

    Returns:
        Dict with current_price and technical indicators
    """
    result = {
        "symbol": symbol,
        "trade_date": trade_date,
        "time_of_day": time_of_day,
        "current_price": None,
        "timestamp": None,
        "technical_data": {},
        "source": None,
        "interval": None,
        "error": None,
    }

    try:
        # TODAY: Use latest 30-minute candle for intraday context
        if _is_today(trade_date):
            if has_fmp_access and user_tier == "starter":
                result = _get_fmp_30m_technical_data(symbol, trade_date, result)
            else:
                result = _get_yfinance_30m_technical_data(symbol, trade_date, result)
            return result

        # HISTORICAL: Fetch daily candle (just like before, unchanged)
        else:
            try:
                price_data = obb.equity.price.historical(
                    symbol=symbol,
                    start_date=trade_date,
                    end_date=trade_date,
                    interval="1d",
                    provider="yfinance",
                )

                if price_data and price_data.results and len(price_data.results) > 0:
                    daily_candle = price_data.results[0]
                    daily_dict = (
                        daily_candle.model_dump()
                        if hasattr(daily_candle, "model_dump")
                        else daily_candle.dict()
                        if hasattr(daily_candle, "dict")
                        else daily_candle
                    )
                    result["technical_data"] = {
                        "open": daily_dict.get("open"),
                        "high": daily_dict.get("high"),
                        "low": daily_dict.get("low"),
                        "close": daily_dict.get("close"),
                        "volume": daily_dict.get("volume"),
                        "timestamp": daily_dict.get("date"),
                    }
                    result["source"] = "yfinance"
                    result["interval"] = "daily"
                    result["current_price"] = daily_dict.get("close")
                    result["timestamp"] = daily_dict.get("date")
                else:
                    result["error"] = "No daily data available"

            except Exception as e:  # noqa: BLE001
                result["error"] = f"Daily data fetch failed: {e}"

            return result

    except Exception as e:  # noqa: BLE001
        result["error"] = f"Orchestrator error: {e}"
        return result


def _get_fmp_4h_technical_data(
    symbol: str, trade_date: str, result: Dict[str, Any]
) -> Dict[str, Any]:
    """Fetch 4-hour data from FMP (precomputed indicators)."""
    try:
        # Fetch 4-hour chart
        sd = datetime.strptime(trade_date, "%Y-%m-%d")
        ed = sd + timedelta(days=1)

        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "from": sd.strftime("%Y-%m-%d"),
            "to": ed.strftime("%Y-%m-%d"),
        }
        chart_data = _fmp_get("/historical-chart/4hour", params)

        if chart_data and isinstance(chart_data, list) and len(chart_data) > 0:
            # Get latest 4h candle
            latest_4h = chart_data[0]  # FMP returns newest first
            result["technical_data"] = {
                "open": latest_4h.get("open"),
                "high": latest_4h.get("high"),
                "low": latest_4h.get("low"),
                "close": latest_4h.get("close"),
                "volume": latest_4h.get("volume"),
                "timestamp": latest_4h.get("date"),
            }
            result["source"] = "fmp"
            result["interval"] = "4h"

        # Get current price from FMP quote
        quote_params: Dict[str, Any] = {"symbol": symbol.upper()}
        quote_data = _fmp_get("/quote", quote_params)

        if isinstance(quote_data, list) and len(quote_data) > 0:
            quote = quote_data[0]
            result["current_price"] = quote.get("price")
            result["timestamp"] = quote.get("timestamp")

        return result

    except Exception as e:  # noqa: BLE001
        result["error"] = f"FMP 4h fetch failed: {e}"
        return result


def _get_yfinance_4h_technical_data(
    symbol: str, trade_date: str, result: Dict[str, Any]
) -> Dict[str, Any]:
    """Fetch and resample yfinance 60m data to 4h candles."""
    try:
        # Fetch 60m intraday data for today
        price_data = obb.equity.price.historical(
            symbol=symbol,
            start_date=trade_date,
            end_date=trade_date,
            interval="60m",
            provider="yfinance",
            extended_hours=False,  # Regular hours for 4h resample
        )

        if not price_data or not price_data.results:
            result["error"] = "No 60m data available for resample"
            return result

        # Resample 60m to 4h
        candles_4h = _resample_to_4h(price_data.results)

        if candles_4h and len(candles_4h) > 0:
            latest_4h = candles_4h[-1]  # Last (most recent) 4h bar
            result["technical_data"] = {
                "open": latest_4h.get("open"),
                "high": latest_4h.get("high"),
                "low": latest_4h.get("low"),
                "close": latest_4h.get("close"),
                "volume": latest_4h.get("volume"),
                "timestamp": latest_4h.get("date"),
            }
            result["source"] = "yfinance_resampled"
            result["interval"] = "4h"

        # Get fresh 5m current price
        price_5m = obb.equity.price.historical(
            symbol=symbol,
            start_date=trade_date,
            end_date=trade_date,
            interval="5m",
            provider="yfinance",
            extended_hours=True,
        )

        if price_5m and price_5m.results:
            latest = price_5m.results[-1]
            latest_dict = (
                latest.model_dump()
                if hasattr(latest, "model_dump")
                else latest.dict()
                if hasattr(latest, "dict")
                else latest
            )
            result["current_price"] = latest_dict.get("close")
            result["timestamp"] = latest_dict.get("date")

        return result

    except Exception as e:  # noqa: BLE001
        result["error"] = f"yfinance 4h fetch failed: {e}"
        return result


# ============================================================================
# TODAY: GET 30-MINUTE INTRADAY DATA
# ============================================================================

def _get_fmp_30m_technical_data(
    symbol: str, trade_date: str, result: Dict[str, Any]
) -> Dict[str, Any]:
    """Fetch latest 30-minute candle from FMP for today's intraday context."""
    try:
        # Fetch 30-minute chart for today - just get latest candle
        sd = datetime.strptime(trade_date, "%Y-%m-%d")
        ed = sd + timedelta(days=1)

        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "from": sd.strftime("%Y-%m-%d"),
            "to": ed.strftime("%Y-%m-%d"),
        }
        chart_data = _fmp_get("/historical-chart/30min", params)

        if chart_data and isinstance(chart_data, list) and len(chart_data) > 0:
            # Get latest 30m candle (most recent - FMP returns newest first)
            latest_30m = chart_data[0]
            result["technical_data"] = {
                "open": latest_30m.get("open"),
                "high": latest_30m.get("high"),
                "low": latest_30m.get("low"),
                "close": latest_30m.get("close"),
                "volume": latest_30m.get("volume"),
                "timestamp": latest_30m.get("date"),
            }
            result["source"] = "fmp"
            result["interval"] = "30m"
        else:
            result["error"] = "No 30m data available from FMP"

        # Get current price from FMP quote for latest snapshot
        quote_params: Dict[str, Any] = {"symbol": symbol.upper()}
        quote_data = _fmp_get("/quote", quote_params)

        if isinstance(quote_data, list) and len(quote_data) > 0:
            quote = quote_data[0]
            result["current_price"] = quote.get("price")
            result["timestamp"] = quote.get("timestamp")

        return result

    except Exception as e:  # noqa: BLE001
        result["error"] = f"FMP 30m fetch failed: {e}"
        return result


def _get_yfinance_30m_technical_data(
    symbol: str, trade_date: str, result: Dict[str, Any]
) -> Dict[str, Any]:
    """Fetch latest 30m candle from yfinance for today's intraday context."""
    try:
        # Fetch 30m intraday data for today
        price_data = obb.equity.price.historical(
            symbol=symbol,
            start_date=trade_date,
            end_date=trade_date,
            interval="30m",
            provider="yfinance",
            extended_hours=False,  # Regular hours only
        )

        if not price_data or not price_data.results:
            result["error"] = "No 30m data available"
            return result

        # Get latest 30m candle (most recent)
        candles_list = price_data.results
        if isinstance(candles_list, list) and len(candles_list) > 0:
            latest_30m = candles_list[-1]
            latest_dict = (
                latest_30m.model_dump()
                if hasattr(latest_30m, "model_dump")
                else latest_30m.dict()
                if hasattr(latest_30m, "dict")
                else latest_30m
            )
            result["technical_data"] = {
                "open": latest_dict.get("open"),
                "high": latest_dict.get("high"),
                "low": latest_dict.get("low"),
                "close": latest_dict.get("close"),
                "volume": latest_dict.get("volume"),
                "timestamp": latest_dict.get("date"),
            }
            result["source"] = "yfinance"
            result["interval"] = "30m"
            result["current_price"] = latest_dict.get("close")
            result["timestamp"] = latest_dict.get("date")
        else:
            result["error"] = "No 30m candles found"

        return result

    except Exception as e:  # noqa: BLE001
        result["error"] = f"yfinance 30m fetch failed: {e}"
        return result


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


def _simplify_fmp_series(data: Any, keep_fields: Dict[str, Any]) -> Any:
    """
    Reduce FMP technical-indicator payloads to only the fields we actually need.

    FMP returns full OHLCV bars plus indicator values for each date. For LLM
    reasoning we only need:
      - the indicator value(s)
      - date (and sometimes close) for context.
    """
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
        Calculate Relative Strength Index (RSI) for a stock (returns current value only).

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: RSI period (default: 14)
            target: Target column name (default: "close")

        Returns:
            Dict with current RSI value
        """
        tool_name = "calculate_rsi"
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)

            # Calculate RSI on the price data
            rsi_result = obb.technical.rsi(
                data=price_data,
                target=target,
                length=length,
            )

            if not rsi_result or not rsi_result.results:
                return format_tool_result(tool_name, error="Could not calculate RSI")

            # Get latest value only (no history)
            latest = rsi_result.results[-1]

            # Convert to dict if it's an OBBject
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            # Find RSI column (naming varies)
            rsi_key = None
            for key in latest_dict.keys():
                if 'RSI' in str(key).upper():
                    rsi_key = key
                    break

            return format_tool_result(
                tool_name,
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "rsi": latest_dict.get(rsi_key) if rsi_key else None,
                    "current_close": latest_dict.get("close"),
                    "length": length,
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)
    
    @mcp.tool(name="calculate_adx")
    @openbb_tool_wrapper("calculate_adx")
    def calculate_adx(
        symbol: str,
        start_date: str,
        end_date: str,
        length: int = 14
    ) -> Dict[str, Any]:
        """
        Calculate Average Directional Index (ADX) for a stock (returns current value only).

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: ADX period (default: 14)

        Returns:
            Dict with current ADX value
        """
        tool_name = "calculate_adx"
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)

            # Calculate ADX on the price data
            adx_result = obb.technical.adx(
                data=price_data,
                length=length,
            )

            if not adx_result or not adx_result.results:
                return format_tool_result(tool_name, error="Could not calculate ADX")

            # Get latest value only (no history)
            latest = adx_result.results[-1]

            # Convert to dict if it's an OBBject
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            # Find ADX column (naming varies)
            adx_key = None
            for key in latest_dict.keys():
                if 'ADX' in str(key).upper():
                    adx_key = key
                    break

            return format_tool_result(
                tool_name,
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "adx": latest_dict.get(adx_key) if adx_key else None,
                    "current_close": latest_dict.get("close"),
                    "length": length,
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)
    
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
        Calculate Exponential Moving Average (EMA) for a stock (returns current value only).

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: EMA period (default: 50)
            target: Target column name (default: "close")

        Returns:
            Dict with current EMA value
        """
        tool_name = "calculate_ema"
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)

            # Calculate EMA on the price data
            ema_result = obb.technical.ema(
                data=price_data,
                target=target,
                length=length,
            )

            if not ema_result or not ema_result.results:
                return format_tool_result(tool_name, error="Could not calculate EMA")

            # Get latest value only (no history)
            latest = ema_result.results[-1]

            # Convert to dict if it's an OBBject
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            # Find EMA column (naming varies)
            ema_key = None
            for key in latest_dict.keys():
                if 'EMA' in str(key).upper():
                    ema_key = key
                    break

            return format_tool_result(
                tool_name,
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "ema": latest_dict.get(ema_key) if ema_key else None,
                    "current_close": latest_dict.get("close"),
                    "length": length,
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)
    
    @mcp.tool(name="calculate_cci")
    @openbb_tool_wrapper("calculate_cci")
    def calculate_cci(
        symbol: str,
        start_date: str,
        end_date: str,
        length: int = 20
    ) -> Dict[str, Any]:
        """
        Calculate Commodity Channel Index (CCI) for a stock (returns current value only).

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            length: CCI period (default: 20)

        Returns:
            Dict with current CCI value
        """
        tool_name = "calculate_cci"
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)

            # Calculate CCI on the price data
            cci_result = obb.technical.cci(
                data=price_data,
                length=length,
            )

            if not cci_result or not cci_result.results:
                return format_tool_result(tool_name, error="Could not calculate CCI")

            # Get latest value only (no history)
            latest = cci_result.results[-1]

            # Convert to dict if it's an OBBject
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            # Find CCI column (naming varies)
            cci_key = None
            for key in latest_dict.keys():
                if 'CCI' in str(key).upper():
                    cci_key = key
                    break

            return format_tool_result(
                tool_name,
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "cci": latest_dict.get(cci_key) if cci_key else None,
                    "current_close": latest_dict.get("close"),
                    "length": length,
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)
    
    @mcp.tool(name="get_current_price_yfinance")
    def get_current_price_yfinance(symbol: str) -> Dict[str, Any]:
        """
        Get current price via latest intraday 5m candle (FREE - yfinance).

        Returns the price from the most recent 5-minute candle.
        No API key required - uses yfinance via OpenBB.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")

        Returns:
            Dict with current price, timestamp, and latest candle data
        """
        tool_name = "get_current_price_yfinance"
        try:
            # Fetch today's 5m data
            today = datetime.now().date().strftime("%Y-%m-%d")
            price_data = obb.equity.price.historical(
                symbol=symbol,
                start_date=today,
                end_date=today,
                interval="5m",
                provider="yfinance",
                extended_hours=True,
            )

            if not price_data or not price_data.results:
                return format_tool_result(
                    tool_name,
                    error=f"No 5m data for {symbol} today (market may be closed)"
                )

            # Get latest candle
            latest = price_data.results[-1]

            # Convert to dict
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            return format_tool_result(
                tool_name,
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "price": latest_dict.get("close"),
                    "open": latest_dict.get("open"),
                    "high": latest_dict.get("high"),
                    "low": latest_dict.get("low"),
                    "volume": latest_dict.get("volume"),
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

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


    @mcp.tool(name="get_openbb_bbands")
    @openbb_tool_wrapper("get_openbb_bbands")
    def get_openbb_bbands(
        symbol: str,
        length: int = 20,
        std: float = 2.0,
        target: str = "close",
        days_back: int = 60
    ) -> Dict[str, Any]:
        """
        Get Bollinger Bands for a stock (returns current values only).

        Fetches historical data (default 60 days), calculates BBands, returns only
        the latest upper/middle/lower band values plus current close price.

        Args:
            symbol: Stock ticker symbol
            length: Period for moving average (default: 20)
            std: Standard deviation multiplier (default: 2.0)
            target: Target column (default: "close")
            days_back: Days of history to fetch for calculation (default: 60)

        Returns:
            Dict with current BBands values (upper_band, middle_band, lower_band, close)
        """
        try:
            # Calculate end date as today, start date as days_back ago
            end_date = (datetime.now().date()).strftime("%Y-%m-%d")
            start_date = (datetime.now().date() - timedelta(days=days_back)).strftime("%Y-%m-%d")

            # Fetch price data
            price_data = _fetch_price_data(symbol, start_date, end_date)

            # Calculate BBands
            bbands_result = obb.technical.bbands(
                data=price_data,
                target=target,
                length=length,
                std=std,
                mamode="sma"
            )

            if not bbands_result or not bbands_result.results:
                return format_tool_result("get_openbb_bbands", error="Could not calculate BBands")

            # Get latest values only (no history)
            latest = bbands_result.results[-1]

            # Convert to dict if it's an OBBject
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            # Find BBands column names (pandas_ta naming varies)
            upper_key = None
            middle_key = None
            lower_key = None

            for key in latest_dict.keys():
                key_str = str(key).upper()
                if 'BBU' in key_str or 'BB_UPPER' in key_str:
                    upper_key = key
                elif 'BBM' in key_str or 'BB_MIDDLE' in key_str:
                    middle_key = key
                elif 'BBL' in key_str or 'BB_LOWER' in key_str:
                    lower_key = key

            return format_tool_result(
                "get_openbb_bbands",
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "upper_band": latest_dict.get(upper_key) if upper_key else None,
                    "middle_band": latest_dict.get(middle_key) if middle_key else None,
                    "lower_band": latest_dict.get(lower_key) if lower_key else None,
                    "current_close": latest_dict.get("close"),
                    "length": length,
                    "std_dev": std,
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result("get_openbb_bbands", error=e)

    @mcp.tool(name="get_openbb_macd")
    @openbb_tool_wrapper("get_openbb_macd")
    def get_openbb_macd(
        symbol: str,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        target: str = "close",
        days_back: int = 100
    ) -> Dict[str, Any]:
        """
        Get MACD (Moving Average Convergence Divergence) for a stock (returns current values only).

        Fetches historical data (default 100 days), calculates MACD, returns only
        the latest MACD line, signal line, and histogram values.

        Args:
            symbol: Stock ticker symbol
            fast: Fast EMA period (default: 12)
            slow: Slow EMA period (default: 26)
            signal: Signal line EMA period (default: 9)
            target: Target column (default: "close")
            days_back: Days of history to fetch for calculation (default: 100)

        Returns:
            Dict with current MACD values (macd_line, signal_line, histogram, close)
        """
        try:
            # Calculate end date as today, start date as days_back ago
            end_date = (datetime.now().date()).strftime("%Y-%m-%d")
            start_date = (datetime.now().date() - timedelta(days=days_back)).strftime("%Y-%m-%d")

            # Fetch price data
            price_data = _fetch_price_data(symbol, start_date, end_date)

            # Calculate MACD
            macd_result = obb.technical.macd(
                data=price_data,
                target=target,
                fast=fast,
                slow=slow,
                signal=signal
            )

            if not macd_result or not macd_result.results:
                return format_tool_result("get_openbb_macd", error="Could not calculate MACD")

            # Get latest values only (no history)
            latest = macd_result.results[-1]

            # Convert to dict if it's an OBBject
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            # Find MACD column names (pandas_ta naming varies)
            macd_key = None
            signal_key = None
            histogram_key = None

            for key in latest_dict.keys():
                key_str = str(key).upper()
                if 'MACD' in key_str and 'SIGNAL' not in key_str and 'HIST' not in key_str:
                    macd_key = key
                elif 'SIGNAL' in key_str or 'MACDS' in key_str:
                    signal_key = key
                elif 'HIST' in key_str or 'MACDH' in key_str:
                    histogram_key = key

            macd_value = latest_dict.get(macd_key) if macd_key else None
            signal_value = latest_dict.get(signal_key) if signal_key else None
            histogram_value = latest_dict.get(histogram_key) if histogram_key else (
                macd_value - signal_value if macd_value and signal_value else None
            )

            return format_tool_result(
                "get_openbb_macd",
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "macd_line": macd_value,
                    "signal_line": signal_value,
                    "histogram": histogram_value,
                    "current_close": latest_dict.get("close"),
                    "fast_period": fast,
                    "slow_period": slow,
                    "signal_period": signal,
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result("get_openbb_macd", error=e)

    @mcp.tool(name="get_openbb_obv")
    @openbb_tool_wrapper("get_openbb_obv")
    def get_openbb_obv(
        symbol: str,
        days_back: int = 60
    ) -> Dict[str, Any]:
        """
        Get On-Balance Volume (OBV) for a stock (returns current value only).

        Fetches historical data (default 60 days), calculates OBV, returns only
        the latest OBV value plus current close and volume.

        Args:
            symbol: Stock ticker symbol
            days_back: Days of history to fetch for calculation (default: 60)

        Returns:
            Dict with current OBV value (obv, current_close, current_volume)
        """
        try:
            # Calculate end date as today, start date as days_back ago
            end_date = (datetime.now().date()).strftime("%Y-%m-%d")
            start_date = (datetime.now().date() - timedelta(days=days_back)).strftime("%Y-%m-%d")

            # Fetch price data
            price_data = _fetch_price_data(symbol, start_date, end_date)

            # Calculate OBV
            obv_result = obb.technical.obv(data=price_data, offset=0)

            if not obv_result or not obv_result.results:
                return format_tool_result("get_openbb_obv", error="Could not calculate OBV")

            # Get latest values only (no history)
            latest = obv_result.results[-1]

            # Convert to dict if it's an OBBject
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            return format_tool_result(
                "get_openbb_obv",
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "obv": latest_dict.get("OBV_0"),
                    "current_close": latest_dict.get("close"),
                    "current_volume": latest_dict.get("volume"),
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result("get_openbb_obv", error=e)

    @mcp.tool(name="get_openbb_vwap")
    @openbb_tool_wrapper("get_openbb_vwap")
    def get_openbb_vwap(
        symbol: str,
        anchor: str = "D"
    ) -> Dict[str, Any]:
        """
        Get Volume-Weighted Average Price (VWAP) for current trading day (returns current value only).

        Fetches intraday 5-minute candle data for today, calculates VWAP, returns only
        the latest VWAP value plus current close and volume.

        Args:
            symbol: Stock ticker symbol
            anchor: Anchor period for VWAP (default: "D" for daily)

        Returns:
            Dict with current VWAP value (vwap, current_close, current_volume)
        """
        try:
            today = datetime.now().date().strftime("%Y-%m-%d")

            # Fetch intraday data (5m candles) for today
            price_data = _fetch_price_data(symbol, today, today)

            # Calculate VWAP
            vwap_result = obb.technical.vwap(data=price_data, anchor=anchor, offset=0)

            if not vwap_result or not vwap_result.results:
                return format_tool_result("get_openbb_vwap", error="Could not calculate VWAP")

            # Get latest values only (no history)
            latest = vwap_result.results[-1]

            # Convert to dict if it's an OBBject
            if hasattr(latest, "model_dump"):
                latest_dict = latest.model_dump()
            elif hasattr(latest, "dict"):
                latest_dict = latest.dict()
            elif isinstance(latest, dict):
                latest_dict = latest
            else:
                latest_dict = {}

            vwap_key = f'VWAP_{anchor}'

            return format_tool_result(
                "get_openbb_vwap",
                data={
                    "symbol": symbol,
                    "timestamp": latest_dict.get("date"),
                    "vwap": latest_dict.get(vwap_key),
                    "current_close": latest_dict.get("close"),
                    "current_volume": latest_dict.get("volume"),
                    "anchor": anchor,
                }
            )
        except Exception as e:  # noqa: BLE001
            return format_tool_result("get_openbb_vwap", error=e)

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
            raw = _fmp_get("/technical-indicators/sma", params)
            # Keep only date, close, and SMA value
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
            raw = _fmp_get("/technical-indicators/wma", params)
            # Keep only date, close, and WMA value
            data = _simplify_fmp_series(raw, ["date", "close", "wma"])
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
