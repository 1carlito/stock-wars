"""
Technical_Tools.py: Technical indicator tools using OpenBB SDK
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from openbb import obb

# Import helpers from utils module
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import openbb_tool_wrapper


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
    
    @mcp.tool(name="calculate_macd")
    @openbb_tool_wrapper("calculate_macd")
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
        # Fetch price data first
        price_data = _fetch_price_data(symbol, start_date, end_date)

        # Calculate MACD on the price data
        return obb.technical.macd(
            data=price_data,
            target=target,
            fast=fast,
            slow=slow,
            signal=signal,
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
        return obb.equity.price.historical(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
    
    @mcp.tool(name="get_current_price")
    @openbb_tool_wrapper("get_current_price")
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
        if current_date:
            # Get price for specific date
            return obb.equity.price.historical(
                symbol=symbol,
                start_date=current_date,
                end_date=current_date,
            )
        # Get most recent price
        return obb.equity.price.quote(symbol=symbol)

