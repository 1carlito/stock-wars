"""
Technical_Tools.py: Technical indicator tools using OpenBB SDK
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from openbb import obb

# Import the conversion helper from utils module
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import _convert_openbb_result


def _fetch_price_data(symbol: str, start_date: str, end_date: str):
    """Helper function to fetch price data for technical indicators"""
    price_result = obb.equity.price.historical(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date
    )
    if hasattr(price_result, 'results') and price_result.results:
        return price_result.results
    else:
        raise ValueError(f"No price data returned for {symbol} from {start_date} to {end_date}")


def register_technical_tools(mcp):
    """Register all technical indicator tools with MCP server"""
    
    @mcp.tool(name="calculate_rsi")
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
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Calculate RSI on the price data
            result = obb.technical.rsi(
                data=price_data,
                target=target,
                length=length
            )
            return {
                "tool_name": "calculate_rsi",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "calculate_rsi", "error": str(e)}
    
    @mcp.tool(name="calculate_macd")
    def calculate_macd(
        symbol: str,
        start_date: str,
        end_date: str,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        target: str = "close"
    ) -> Dict[str, Any]:
        """
        Calculate MACD (Moving Average Convergence Divergence) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD) - required
            end_date: End date (YYYY-MM-DD) - required
            fast: Fast period (default: 12)
            slow: Slow period (default: 26)
            signal: Signal period (default: 9)
            target: Target column name (default: "close")
        
        Returns:
            Dict with MACD data
        """
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Calculate MACD on the price data
            result = obb.technical.macd(
                data=price_data,
                target=target,
                fast=fast,
                slow=slow,
                signal=signal
            )
            return {
                "tool_name": "calculate_macd",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "calculate_macd", "error": str(e)}
    
    @mcp.tool(name="calculate_bbands")
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
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Calculate Bollinger Bands on the price data
            result = obb.technical.bbands(
                data=price_data,
                target=target,
                length=length,
                std=std
            )
            return {
                "tool_name": "calculate_bbands",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "calculate_bbands", "error": str(e)}
    
    @mcp.tool(name="calculate_atr")
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
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Calculate ATR on the price data
            result = obb.technical.atr(
                data=price_data,
                length=length
            )
            return {
                "tool_name": "calculate_atr",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "calculate_atr", "error": str(e)}
    
    @mcp.tool(name="calculate_obv")
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
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Calculate OBV on the price data
            result = obb.technical.obv(
                data=price_data
            )
            return {
                "tool_name": "calculate_obv",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "calculate_obv", "error": str(e)}
    
    @mcp.tool(name="calculate_adx")
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
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Calculate ADX on the price data
            result = obb.technical.adx(
                data=price_data,
                length=length
            )
            return {
                "tool_name": "calculate_adx",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "calculate_adx", "error": str(e)}
    
    @mcp.tool(name="calculate_ema")
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
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Calculate EMA on the price data
            result = obb.technical.ema(
                data=price_data,
                target=target,
                length=length
            )
            return {
                "tool_name": "calculate_ema",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "calculate_ema", "error": str(e)}
    
    @mcp.tool(name="calculate_cci")
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
        try:
            # Fetch price data first
            price_data = _fetch_price_data(symbol, start_date, end_date)
            
            # Calculate CCI on the price data
            result = obb.technical.cci(
                data=price_data,
                length=length
            )
            return {
                "tool_name": "calculate_cci",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "calculate_cci", "error": str(e)}
    
    @mcp.tool(name="get_price_history")
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
        try:
            result = obb.equity.price.historical(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )
            return {
                "tool_name": "get_price_history",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "get_price_history", "error": str(e)}
    
    @mcp.tool(name="get_current_price")
    def get_current_price(
        symbol: str,
        current_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get current price for a stock. If current_date is provided, gets price as of that date.
        
        Args:
            symbol: Stock ticker symbol
            current_date: Date to get price for (YYYY-MM-DD), defaults to most recent
        
        Returns:
            Dict with current price data
        """
        try:
            if current_date:
                # Get price for specific date
                result = obb.equity.price.historical(
                    symbol=symbol,
                    start_date=current_date,
                    end_date=current_date
                )
            else:
                # Get most recent price
                result = obb.equity.price.quote(symbol=symbol)
            
            return {
                "tool_name": "get_current_price",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "get_current_price", "error": str(e)}

