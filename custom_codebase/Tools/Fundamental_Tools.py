"""
Fundamental_Tools.py: Fundamental analysis tools using OpenBB SDK
"""

from typing import Dict, Any, Optional
from openbb import obb

# Import the conversion helper from utils module
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import _convert_openbb_result


def register_fundamental_tools(mcp):
    """Register all fundamental analysis tools with MCP server"""
    
    @mcp.tool(name="get_income_statement")
    def get_income_statement(
        symbol: str,
        period: str = "annual",
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Get income statement data for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: Period type - "annual" or "quarter" (default: "annual")
            limit: Number of periods to return (default: 5)
        
        Returns:
            Dict with income statement data
        """
        try:
            result = obb.equity.fundamental.income(
                symbol=symbol,
                period=period,
                limit=limit
            )
            return {
                "tool_name": "get_income_statement",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "get_income_statement", "error": str(e)}
    
    @mcp.tool(name="get_balance_sheet")
    def get_balance_sheet(
        symbol: str,
        period: str = "annual",
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Get balance sheet data for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: Period type - "annual" or "quarter" (default: "annual")
            limit: Number of periods to return (default: 5)
        
        Returns:
            Dict with balance sheet data
        """
        try:
            result = obb.equity.fundamental.balance(
                symbol=symbol,
                period=period,
                limit=limit
            )
            return {
                "tool_name": "get_balance_sheet",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "get_balance_sheet", "error": str(e)}
    
    @mcp.tool(name="get_cash_flow")
    def get_cash_flow(
        symbol: str,
        period: str = "annual",
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Get cash flow statement data for a stock.
        
        Args:
            symbol: Stock ticker symbol
            period: Period type - "annual" or "quarter" (default: "annual")
            limit: Number of periods to return (default: 5)
        
        Returns:
            Dict with cash flow data
        """
        try:
            result = obb.equity.fundamental.cash(
                symbol=symbol,
                period=period,
                limit=limit
            )
            return {
                "tool_name": "get_cash_flow",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "get_cash_flow", "error": str(e)}
    
    @mcp.tool(name="get_company_profile")
    def get_company_profile(
        symbol: str
    ) -> Dict[str, Any]:
        """
        Get company profile/overview for a stock.
        
        Args:
            symbol: Stock ticker symbol
        
        Returns:
            Dict with company profile data
        """
        try:
            result = obb.equity.profile(symbol=symbol)
            return {
                "tool_name": "get_company_profile",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "get_company_profile", "error": str(e)}
    
    @mcp.tool(name="get_earnings_calendar")
    def get_earnings_calendar(
        start_date: str,
        end_date: str,
        symbol: Optional[str] = None,
        current_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get earnings calendar for a date range. Optionally filter by symbol.
        If current_date is provided, only returns earnings up to that date (prevents lookahead bias).
        
        NOTE: This endpoint requires a premium FMP subscription. Returns a message if unavailable.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            symbol: Optional stock ticker symbol to filter results
            current_date: Optional current date to prevent lookahead bias
        
        Returns:
            Dict with earnings calendar data or error message
        """
        try:
            # If current_date is provided, limit end_date to current_date
            if current_date and current_date < end_date:
                end_date = current_date
            
            result = obb.equity.calendar.earnings(
                start_date=start_date,
                end_date=end_date,
                symbol=symbol
            )
            
            data = _convert_openbb_result(result)
            
            # If symbol is provided, filter results to only that symbol
            if symbol and isinstance(data, dict) and "data" in data:
                if isinstance(data["data"], list):
                    data["data"] = [item for item in data["data"] if item.get("symbol") == symbol]
            
            return {
                "tool_name": "get_earnings_calendar",
                "data": data
            }
        except Exception as e:
            error_str = str(e)
            # Check if it's a premium endpoint error
            if "Premium" in error_str or "402" in error_str or "subscription" in error_str.lower():
                return {
                    "tool_name": "get_earnings_calendar",
                    "data": [],
                    "message": "Earnings calendar data requires a premium FMP subscription. This feature is not available on the free tier. You can use get_company_profile to get basic earnings information.",
                    "premium_required": True
                }
            return {"tool_name": "get_earnings_calendar", "error": str(e)}
    
    @mcp.tool(name="get_analyst_estimates")
    def get_analyst_estimates(
        symbol: str
    ) -> Dict[str, Any]:
        """
        Get analyst estimates for a stock.
        
        Args:
            symbol: Stock ticker symbol
        
        Returns:
            Dict with analyst estimates data
        """
        try:
            result = obb.equity.estimates.consensus(symbol=symbol)
            return {
                "tool_name": "get_analyst_estimates",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "get_analyst_estimates", "error": str(e)}

