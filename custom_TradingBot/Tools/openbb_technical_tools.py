"""
OpenBB Technical Tools
======================
Technical indicator tools using OpenBB SDK.
"""

from typing import Dict, Any, Optional, List
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
from data_management.cache_manager import CacheManager

# Initialize cache
_cache_manager = CacheManager(cache_dir=os.path.join(parent_dir, ".cache"), ttl_hours=24)

# ============================================================================
# PRICE FETCHING HELPER (With Caching)
# ============================================================================

@lru_cache(maxsize=512)
def _cached_price_history_l1(symbol: str, start_date: str, end_date: str):
    """L1 in-memory cache."""
    return obb.equity.price.historical(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )

def _cached_price_history(symbol: str, start_date: str, end_date: str):
    """Dual-layer cache wrapper."""
    cache_key = f"price:{symbol}:{start_date}:{end_date}"
    cached_result = _cache_manager.get(cache_key)
    if cached_result is not None:
        return cached_result
    result = _cached_price_history_l1(symbol, start_date, end_date)
    _cache_manager.set(cache_key, result)
    return result

def _fetch_price_data(symbol: str, start_date: str, end_date: str):
    """Helper function to fetch price data with handling for OBBject/dict."""
    price_result = _cached_price_history(symbol, start_date, end_date)

    results = None
    if hasattr(price_result, "results"):
        results = price_result.results
    elif isinstance(price_result, dict) and "results" in price_result:
        results = price_result["results"]

    if results:
        # Prefer DataFrame for robustness
        if hasattr(results, "to_dataframe"):
            df = results.to_dataframe()
            if not df.index.is_unique:
                df = df[~df.index.duplicated(keep="last")]
            df = df.sort_index()
            return df
        
        # Fallback list de-duplication
        if isinstance(results, list):
            seen_dates = set()
            cleaned = []
            for row in results:
                date_val = None
                if hasattr(row, "date"): date_val = getattr(row, "date")
                elif isinstance(row, dict): date_val = row.get("date")
                
                if date_val in seen_dates: continue
                if date_val is not None: seen_dates.add(date_val)
                cleaned.append(row)
            return cleaned

        return results
    raise ValueError(f"No price data returned for {symbol} from {start_date} to {end_date}")


def register_openbb_technical_tools(mcp):
    """Register all OpenBB technical indicator tools with MCP server"""
    
    @mcp.tool(name="calculate_rsi")
    @openbb_tool_wrapper("calculate_rsi")
    def calculate_rsi(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        length: int = 14,
        target: str = "close"
    ) -> Dict[str, Any]:
        """Calculate RSI (returns full time series)."""
        tool_name = "calculate_rsi"
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=150)).strftime("%Y-%m-%d")

        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
        e_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if (e_dt - s_dt).days < 90:
            s_dt = e_dt - timedelta(days=90)
            start_date = s_dt.strftime("%Y-%m-%d")

        price_data = _fetch_price_data(symbol, start_date, end_date)
        rsi_result = obb.technical.rsi(data=price_data, target=target, length=length)

        if not rsi_result or not rsi_result.results:
            raise ValueError("Could not calculate RSI")

        # Return full series for analysis
        results_list = []
        for item in rsi_result.results:
            item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
            
            # Find correct RSI key
            rsi_val = None
            for k, v in item_dict.items():
                if 'RSI' in str(k).upper():
                    rsi_val = v
                    break
            
            results_list.append({
                "date": item_dict.get("date"),
                "rsi": rsi_val,
                "close": item_dict.get("close")
            })

        return results_list

    @mcp.tool(name="calculate_adx")
    @openbb_tool_wrapper("calculate_adx")
    def calculate_adx(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        length: int = 14
    ) -> Dict[str, Any]:
        """Calculate ADX (returns full time series)."""
        tool_name = "calculate_adx"
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=150)).strftime("%Y-%m-%d")

        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
        e_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if (e_dt - s_dt).days < 90:
            s_dt = e_dt - timedelta(days=90)
            start_date = s_dt.strftime("%Y-%m-%d")

        price_data = _fetch_price_data(symbol, start_date, end_date)
        adx_result = obb.technical.adx(data=price_data, length=length)

        if not adx_result or not adx_result.results:
            raise ValueError("Could not calculate ADX")

        results_list = []
        for item in adx_result.results:
            item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
            
            adx_val = None
            for k, v in item_dict.items():
                if 'ADX' in str(k).upper() and 'DMP' not in str(k).upper() and 'DMN' not in str(k).upper():
                    adx_val = v
                    break
            
            results_list.append({
                "date": item_dict.get("date"),
                "adx": adx_val
            })

        return results_list

    @mcp.tool(name="calculate_bbands")
    @openbb_tool_wrapper("calculate_bbands")
    def calculate_bbands(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        length: int = 20,
        std: float = 2.0
    ) -> Dict[str, Any]:
        """Calculate Bollinger Bands (returns full time series)."""
        tool_name = "calculate_bbands"
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=150)).strftime("%Y-%m-%d")

        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
        e_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if (e_dt - s_dt).days < 90:
            s_dt = e_dt - timedelta(days=90)
            start_date = s_dt.strftime("%Y-%m-%d")

        price_data = _fetch_price_data(symbol, start_date, end_date)
        bb_result = obb.technical.bbands(data=price_data, length=length, std=std)

        if not bb_result or not bb_result.results:
            raise ValueError("Could not calculate BBands")

        results_list = []
        for item in bb_result.results:
            item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
            
            # Fuzzy extraction for bands
            upper, middle, lower = None, None, None
            for k, v in item_dict.items():
                uk = str(k).upper()
                if "UPPER" in uk or "BBU" in uk: upper = v
                elif "MIDDLE" in uk or "BBM" in uk: middle = v
                elif "LOWER" in uk or "BBL" in uk: lower = v

            results_list.append({
                "date": item_dict.get("date"),
                "upper": upper,
                "middle": middle,
                "lower": lower,
            })

        return results_list

    @mcp.tool(name="calculate_macd")
    @openbb_tool_wrapper("calculate_macd")
    def calculate_macd(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, Any]:
        """Calculate MACD (returns full time series)."""
        tool_name = "calculate_macd"
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=150)).strftime("%Y-%m-%d")

        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
        e_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if (e_dt - s_dt).days < 90:
            s_dt = e_dt - timedelta(days=90)
            start_date = s_dt.strftime("%Y-%m-%d")

        price_data = _fetch_price_data(symbol, start_date, end_date)
        macd_result = obb.technical.macd(data=price_data, fast=fast, slow=slow, signal=signal)

        if not macd_result or not macd_result.results:
            raise ValueError("Could not calculate MACD")

        results_list = []
        for item in macd_result.results:
            item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
            
            mac, sig, hist = None, None, None
            for k, v in item_dict.items():
                uk = str(k).upper()
                # Need to be careful not to mix up MACD and MACD_Signal or MACD_Hist
                # But typically keys are like "MACD_12_26_9", "MACDs_12_26_9", "MACDh_12_26_9"
                if "MACD" in uk and "S" not in uk and "H" not in uk: mac = v
                elif "SIGNAL" in uk or "MACDS" in uk: sig = v
                elif "HIST" in uk or "MACDH" in uk: hist = v

            results_list.append({
                "date": item_dict.get("date"),
                "macd": mac,
                "signal": sig,
                "histogram": hist,
            })

        return results_list

    @mcp.tool(name="calculate_obv")
    @openbb_tool_wrapper("calculate_obv")
    def calculate_obv(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculate OBV (returns full time series)."""
        tool_name = "calculate_obv"
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=150)).strftime("%Y-%m-%d")

        price_data = _fetch_price_data(symbol, start_date, end_date)
        obv_result = obb.technical.obv(data=price_data)

        if not obv_result or not obv_result.results:
            raise ValueError("Could not calculate OBV")

        results_list = []
        for item in obv_result.results:
            item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
            
            # Fuzzy extraction
            val = None
            for k, v in item_dict.items():
                if "OBV" in str(k).upper():
                    val = v
                    break

            results_list.append({
                "date": item_dict.get("date"),
                "obv": val
            })

        return results_list
            
    @mcp.tool(name="calculate_cci")
    @openbb_tool_wrapper("calculate_cci")
    def calculate_cci(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        length: int = 14
    ) -> Dict[str, Any]:
        """Calculate CCI."""
        tool_name = "calculate_cci"
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=150)).strftime("%Y-%m-%d")

        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
        e_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if (e_dt - s_dt).days < 90:
            s_dt = e_dt - timedelta(days=90)
            start_date = s_dt.strftime("%Y-%m-%d")
            
        price_data = _fetch_price_data(symbol, start_date, end_date)
        cci_result = obb.technical.cci(data=price_data, length=length)
        
        if not cci_result or not cci_result.results:
            raise ValueError("Could not calculate CCI")

        results_list = []
        for item in cci_result.results:
            item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
            
            val = None
            for k, v in item_dict.items():
                if "CCI" in str(k).upper():
                    val = v
                    break

            results_list.append({
                "date": item_dict.get("date"),
                "cci": val
            })

        return results_list

    @mcp.tool(name="calculate_atr")
    @openbb_tool_wrapper("calculate_atr")
    def calculate_atr(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        length: int = 14
    ) -> Dict[str, Any]:
        """Calculate ATR."""
        tool_name = "calculate_atr"
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=150)).strftime("%Y-%m-%d")

        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
        e_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if (e_dt - s_dt).days < 90:
            s_dt = e_dt - timedelta(days=90)
            start_date = s_dt.strftime("%Y-%m-%d")

        price_data = _fetch_price_data(symbol, start_date, end_date)
        atr_result = obb.technical.atr(data=price_data, length=length)
        
        if not atr_result or not atr_result.results:
            raise ValueError("Could not calculate ATR")

        results_list = []
        for item in atr_result.results:
            item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
            
            val = None
            for k, v in item_dict.items():
                if "ATR" in str(k).upper():
                    val = v
                    break

            results_list.append({
                "date": item_dict.get("date"),
                "atr": val
            })

        return results_list

    @mcp.tool(name="calculate_ema")
    @openbb_tool_wrapper("calculate_ema")
    def calculate_ema(
        symbol: str, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None, 
        length: int = 14
    ) -> Dict[str, Any]:
        """Calculate EMA via OpenBB."""
        tool_name = "calculate_ema"
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=150)).strftime("%Y-%m-%d")

        # Need history
        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
        e_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if (e_dt - s_dt).days < length * 2:
            s_dt = e_dt - timedelta(days=length*3) # Safe buffer
            start_date = s_dt.strftime("%Y-%m-%d")
        
        price_data = _fetch_price_data(symbol, start_date, end_date)
        ema_result = obb.technical.ema(data=price_data, length=length)
        if not ema_result or not ema_result.results:
            raise ValueError("Could not calculate EMA")

        results_list = []
        for item in ema_result.results:
            item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
            
            val = None
            for k, v in item_dict.items():
                if "EMA" in str(k).upper():
                    val = v
                    break

            results_list.append({
                "date": item_dict.get("date"),
                "ema": val
            })

        return results_list

    @mcp.tool(name="get_technical_summary")
    @openbb_tool_wrapper("get_technical_summary")
    def get_technical_summary(
        symbol: str,
        end_date: str,
        lookback_days: int = 90
    ) -> Dict[str, Any]:
        """
        Calculate a comprehensive set of technical indicators for a given date using OpenBB.
        """
        tool_name = "get_technical_summary"
        try:
            # Auto-calculate start date
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            sd = ed - timedelta(days=lookback_days)
            start_date = sd.strftime("%Y-%m-%d")

            # 1. Fetch Price History ONCE
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Helper to get series of values (last N days)
            def _get_series(data, key_fragment, num_days=60):
                if not data or not hasattr(data, "results") or not data.results:
                    return []
                all_results = data.results
                series_data = all_results[-num_days:] if len(all_results) > num_days else all_results
                values = []
                for item in series_data:
                    item_dict = item.model_dump() if hasattr(item, "model_dump") else (item.dict() if hasattr(item, "dict") else item)
                    found_val = None
                    for k, v in item_dict.items():
                        if key_fragment.lower() in str(k).lower():
                            found_val = v
                            break
                    values.append(found_val)
                return values

            # Helper to get corresponding dates
            def _get_dates(data, num_days=60):
                if not data or not hasattr(data, "results") or not data.results:
                    return []
                series_data = data.results[-num_days:] if len(data.results) > num_days else data.results
                dates = []
                for item in series_data:
                    d = None
                    if hasattr(item, "date"): d = item.date
                    elif isinstance(item, dict): d = item.get("date")
                    if d: dates.append(str(d))
                return dates

            indicators = {}
            
            # 2. RSI (14)
            try:
                rsi = obb.technical.rsi(data=price_data, length=14)
                indicators["RSI_14"] = _get_series(rsi, "rsi", num_days=lookback_days)
            except Exception:
                indicators["RSI_14"] = []

            # 3. MACD (12, 26, 9)
            try:
                macd = obb.technical.macd(data=price_data, fast=12, slow=26, signal=9)
                indicators["MACD"] = _get_series(macd, "macd", num_days=lookback_days)
                indicators["MACD_Signal"] = _get_series(macd, "signal", num_days=lookback_days)
                indicators["MACD_Hist"] = _get_series(macd, "hist", num_days=lookback_days)
            except Exception:
                indicators["MACD"] = []
                
            # 4. BBands (20, 2)
            try:
                bb = obb.technical.bbands(data=price_data, length=20, std=2)
                indicators["BB_Upper"] = _get_series(bb, "upper", num_days=lookback_days)
                indicators["BB_Middle"] = _get_series(bb, "middle", num_days=lookback_days)
                indicators["BB_Lower"] = _get_series(bb, "lower", num_days=lookback_days)
            except Exception:
                indicators["BB_Upper"] = []

            # 5. ADX (14)
            try:
                adx = obb.technical.adx(data=price_data, length=14)
                indicators["ADX_14"] = _get_series(adx, "adx", num_days=lookback_days)
            except Exception:
                indicators["ADX_14"] = []

            # 6. ATR (14)
            try:
                atr = obb.technical.atr(data=price_data, length=14)
                indicators["ATR_14"] = _get_series(atr, "atr", num_days=lookback_days)
            except Exception:
                indicators["ATR_14"] = []
                
            # 7. CCI (20)
            try:
                cci = obb.technical.cci(data=price_data, length=20)
                indicators["CCI_20"] = _get_series(cci, "cci", num_days=lookback_days)
            except Exception:
                indicators["CCI_20"] = []
                
            # 8. OBV
            try:
                obv = obb.technical.obv(data=price_data)
                indicators["OBV"] = _get_series(obv, "obv", num_days=lookback_days)
            except Exception:
                indicators["OBV"] = []
                
            # 9. EMA (20) & SMA (50)
            try:
                ema = obb.technical.ema(data=price_data, length=20)
                indicators["EMA_20"] = _get_series(ema, "ema", num_days=lookback_days)
            except Exception:
                indicators["EMA_20"] = []

            try:
                sma = obb.technical.sma(data=price_data, length=50)
                indicators["SMA_50"] = _get_series(sma, "sma", num_days=lookback_days)
            except Exception:
                indicators["SMA_50"] = []

            # Get Price Series
            dates = []
            closes = []
            try:
                if hasattr(price_data, "results") and price_data.results:
                    subset = price_data.results[-lookback_days:] if len(price_data.results) > lookback_days else price_data.results
                    for item in subset:
                        d = None
                        c = None
                        if hasattr(item, "date"): d = item.date
                        elif isinstance(item, dict): d = item.get("date")
                        
                        if hasattr(item, "close"): c = item.close
                        elif isinstance(item, dict): c = item.get("close")
                        
                        if d: dates.append(str(d))
                        if c: closes.append(c)
            except Exception:
                pass

            return format_tool_result(
                tool_name,
                data={
                    "symbol": symbol,
                    "end_date": end_date,
                    "dates": dates,
                    "closing_prices": closes,
                    "indicators": indicators
                }
            )

        except Exception as e:
            return format_tool_result(tool_name, error=f"Summary calc failed: {e}")
