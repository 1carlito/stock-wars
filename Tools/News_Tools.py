"""
News_Tools.py: News and market data tools using OpenBB SDK
"""


"""
from typing import Dict, Any, Optional
from openbb import obb

# Import the conversion helper from parent module
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from OpenBBMCPServer import _convert_openbb_result


def register_news_tools(mcp):
    - Register all news and market data tools with MCP server -
    
    @mcp.tool(name="get_news")
    def get_news(
        symbol: Optional[str] = None,
        limit: int = 10,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:

        Get news articles for a stock or general market news.
        
        Args:
            symbol: Optional stock ticker symbol to filter news
            limit: Maximum number of articles to return (default: 10)
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
        
        Returns:
            Dict with news data
        """
        try:
            if symbol:
                result = obb.news.company(symbol=symbol, limit=limit)
            else:
                result = obb.news.world(limit=limit)
            
            data = _convert_openbb_result(result)
            
            # Filter by date range if provided
            if start_date or end_date:
                if isinstance(data, dict) and "data" in data:
                    if isinstance(data["data"], list):
                        filtered = []
                        for item in data["data"]:
                            item_date = item.get("date") or item.get("published_date") or item.get("publishedDate")
                            if item_date:
                                if start_date and item_date < start_date:
                                    continue
                                if end_date and item_date > end_date:
                                    continue
                            filtered.append(item)
                        data["data"] = filtered
            
            return {
                "tool_name": "get_news",
                "data": data
            }
        except Exception as e:
            return {"tool_name": "get_news", "error": str(e)}
    
    @mcp.tool(name="get_market_overview")
    def get_market_overview() -> Dict[str, Any]:
        """
        Get overall market overview/indices data.
        
        Returns:
            Dict with market overview data
        """
        try:
            # Get major indices
            result = obb.equity.market.indices()
            return {
                "tool_name": "get_market_overview",
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": "get_market_overview", "error": str(e)}

"""