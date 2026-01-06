"""
News_Tools.py: News and headline tools using OpenBB SDK.

This module exposes small, purpose-built tools for fetching company-specific
and macro news, following the same MCP + OpenBB patterns as the other tools.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from functools import lru_cache
from openbb import obb

# Import helpers from utils module
import sys
import os

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import openbb_tool_wrapper  # noqa: E402


# ============================================================================
# CACHED UNDERLYING OPENBB CALLS
# ============================================================================


@lru_cache(maxsize=512)
def _cached_company_news(
    symbol: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> Any:
    """
    Cached wrapper around OpenBB company news endpoint.

    The upstream OpenBB API is expected to be something like:
      obb.news.company(symbol=..., start_date=..., end_date=..., limit=...)
    """
    return obb.news.company(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@lru_cache(maxsize=512)
def _cached_world_news(
    start_date: str,
    end_date: str,
    topics: Optional[List[str]],
    limit: int,
) -> Any:
    """
    Cached wrapper around OpenBB world / macro news endpoint.

    The upstream OpenBB API is expected to be something like:
      obb.news.world(start_date=..., end_date=..., topics=..., limit=...)
    """
    return obb.news.world(
        start_date=start_date,
        end_date=end_date,
        topics=topics,
        limit=limit,
    )


def register_news_tools(mcp):
    """Register all news tools with MCP server."""

    @mcp.tool(name="get_company_news")
    @openbb_tool_wrapper("get_company_news")
    def get_company_news(
        symbol: str,
        start_date: str,
        end_date: str,
        limit: int = 20,
    ) -> Any:
        """
        Get company-specific news headlines for a symbol over a date range.

        Args:
            symbol: Stock ticker symbol (required).
            start_date: Start date (YYYY-MM-DD), inclusive.
            end_date: End date (YYYY-MM-DD), inclusive.
            limit: Maximum number of articles to return (default: 20).

        Notes:
            - The ReasoningAgent will typically auto-fill and clamp the dates
              and limit for backtests to avoid lookahead and huge payloads.
            - This tool is intentionally symbol-scoped to keep the surface area
              targeted and easy for the LLM to reason about.
        """
        # Basic validation; agent does most clamping/guarding
        if not symbol:
            raise ValueError("get_company_news requires a non-empty symbol")

        # Ensure dates are in YYYY-MM-DD format; let OpenBB handle further checks
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")

        if limit <= 0:
            limit = 1

        return _cached_company_news(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    @mcp.tool(name="get_world_news")
    @openbb_tool_wrapper("get_world_news")
    def get_world_news(
        start_date: str,
        end_date: str,
        topics: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Any:
        """
        Get macro / world news headlines over a date range.

        Args:
            start_date: Start date (YYYY-MM-DD), inclusive.
            end_date: End date (YYYY-MM-DD), inclusive.
            topics: Optional list of topic filters (e.g. ["macro", "rates"]).
            limit: Maximum number of articles to return (default: 20).

        Notes:
            - This tool is intentionally symbol-agnostic and should be used
              primarily for macro context (e.g., rate decisions, CPI prints).
            - The ReasoningAgent will auto-fill and clamp dates + limit to
              keep payloads small and avoid lookahead in backtests.
        """
        # Ensure dates are in YYYY-MM-DD format; let OpenBB handle further checks
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")

        if limit <= 0:
            limit = 1

        # Normalize topics: allow single string or list of strings
        topics_param: Optional[List[str]]
        if topics is None:
            topics_param = None
        elif isinstance(topics, str):
            topics_param = [topics]
        else:
            topics_param = list(topics)

        return _cached_world_news(
            start_date=start_date,
            end_date=end_date,
            topics=topics_param,
            limit=limit,
        )


