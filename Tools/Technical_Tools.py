"""
Technical_Tools.py: Technical indicator tools using OpenBB SDK
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from openbb import obb

# Import the conversion helper from parent module
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from OpenBBMCPServer import _convert_openbb_result


def register_technical_tools(mcp):
    """Register all technical indicator tools with MCP server"""
    
    @mcp.tool(name="calculate_rsi")
    def calculate_rsi(
        symbol: str,
        period: int = 14,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate Relative Strength Index (RSI) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: RSI period (default: 14)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with RSI data
        """
        try:
            result = obb.technical.rsi(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date
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
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate MACD (Moving Average Convergence Divergence) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            fast: Fast period (default: 12)
            slow: Slow period (default: 26)
            signal: Signal period (default: 9)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with MACD data
        """
        try:
            result = obb.technical.macd(
                symbol=symbol,
                fast_period=fast,
                slow_period=slow,
                signal_period=signal,
                start_date=start_date,
                end_date=end_date
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
        period: int = 20,
        std_dev: float = 2.0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate Bollinger Bands for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: Period for moving average (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with Bollinger Bands data
        """
        try:
            result = obb.technical.bbands(
                symbol=symbol,
                period=period,
                std=std_dev,
                start_date=start_date,
                end_date=end_date
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
        period: int = 14,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate Average True Range (ATR) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: ATR period (default: 14)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with ATR data
        """
        try:
            result = obb.technical.atr(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date
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
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate On-Balance Volume (OBV) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with OBV data
        """
        try:
            result = obb.technical.obv(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
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
        period: int = 14,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate Average Directional Index (ADX) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: ADX period (default: 14)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with ADX data
        """
        try:
            result = obb.technical.adx(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date
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
        period: int = 50,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate Exponential Moving Average (EMA) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: EMA period (default: 50)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with EMA data
        """
        try:
            result = obb.technical.ema(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date
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
        period: int = 20,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate Commodity Channel Index (CCI) for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: CCI period (default: 20)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with CCI data
        """
        try:
            result = obb.technical.cci(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date
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

