"""
News_Tools.py: News and headline tools using FMP (Financial Modeling Prep) and Polygon.

Implements small, purpose-built tools for fetching company-specific
and macro news, exposed via MCP. We call the FMP REST API directly:
see FMP docs for news endpoints:
https://site.financialmodelingprep.com/developer/docs#general-news

Also includes Polygon-based news tools via OpenBB as a free alternative.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from functools import lru_cache
import os
import sys
import requests

# Import helpers from utils module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import format_tool_result  # noqa: E402

FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_API_KEY = os.getenv("fmp_api_key")


def _fmp_get(path: str, params: Dict[str, Any]) -> Any:
    """Thin wrapper around FMP GET requests."""
    if not FMP_API_KEY:
        raise RuntimeError("fmp_api_key not set in environment for FMP news tools")
    q = dict(params)
    q["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE_URL}{path}"
    resp = requests.get(url, params=q, timeout=30)
    resp.raise_for_status()
    return resp.json()


@lru_cache(maxsize=512)
def _cached_company_news(
    symbol: str,
    start_date: str,
    end_date: str,
    limit: int,
    page: int,
) -> Any:
    """Cached wrapper around FMP stock news search endpoint."""
    params: Dict[str, Any] = {
        "symbols": symbol,
        "from": start_date,
        "to": end_date,
        "page": page,
        "limit": limit,
    }
    return _fmp_get("/news/stock", params)


@lru_cache(maxsize=512)
def _cached_world_news(
    start_date: str,
    end_date: str,
    limit: int,
    page: int,
) -> Any:
    """Cached wrapper around FMP general news endpoint."""
    params: Dict[str, Any] = {
        "from": start_date,
        "to": end_date,
        "page": page,
        "limit": limit,
    }
    return _fmp_get("/news/general-latest", params)


# ============================================================================
# Polygon News Tools (Free Alternative - requires Polygon API key)
# ============================================================================

POLYGON_API_KEY = os.getenv("POLYGON")


def _get_polygon_key() -> str:
    """Get Polygon API key from environment, loading from .env if needed."""
    global POLYGON_API_KEY
    if POLYGON_API_KEY and POLYGON_API_KEY.strip():
        return POLYGON_API_KEY.strip()
    
    # Try getting from env first
    env_key = os.getenv("POLYGON")
    if env_key and env_key.strip():
        POLYGON_API_KEY = env_key.strip()
        return POLYGON_API_KEY

    # Try finding .env in project root (Tools/../.env) or custom_TradingBot/.env
    try:
        from dotenv import load_dotenv
        # Check custom_TradingBot/.env
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        possible_paths = [
            os.path.join(root_dir, ".env"),
            os.path.join(os.path.dirname(root_dir), ".env"), # Parent of custom_TradingBot
        ]
        
        for env_path in possible_paths:
            if os.path.exists(env_path):
                load_dotenv(env_path)
                break
    except Exception:
        pass
        
    POLYGON_API_KEY = os.getenv("POLYGON")
    if not POLYGON_API_KEY or not POLYGON_API_KEY.strip():
        raise RuntimeError(
            "POLYGON API key not set in environment or is empty. "
            "Please add POLYGON=your_api_key to your .env file in custom_TradingBot/"
        )
    
    POLYGON_API_KEY = POLYGON_API_KEY.strip()
    return POLYGON_API_KEY


def _polygon_get(params: Dict[str, Any]) -> Any:
    """Helper to call Polygon News API."""
    api_key = _get_polygon_key()
    
    # Use apiKey param as requested (safest method)
    params["apiKey"] = api_key
    
    # Filter out None values
    clean_params = {k: v for k, v in params.items() if v is not None}
    
    # Polygon News Endpoint (Standard Reference API)
    url = "https://api.polygon.io/v2/reference/news"
    
    # No Auth header needed when using apiKey param
    resp = requests.get(url, params=clean_params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@lru_cache(maxsize=512)
def _cached_company_news_polygon(
    symbol: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> Any:
    """Cached wrapper around Polygon company news API."""
    params = {
        'ticker': symbol,                    # Polygon v2 uses 'ticker' (singular)
        'published_utc.gte': start_date,     # date filtering via published_utc modifiers
        'published_utc.lte': end_date,
        'limit': limit,
        'sort': 'published_utc',             # Polygon v2 uses 'sort' not 'sortBy'
        'order': 'desc',
    }
    return _polygon_get(params)


@lru_cache(maxsize=512)
def _cached_world_news_polygon(
    start_date: str,
    end_date: str,
    limit: int,
) -> Any:
    """Cached wrapper around Polygon world news API (general market news)."""
    params = {
        'published_utc.gte': start_date,
        'published_utc.lte': end_date,
        'limit': limit,
        'sort': 'published_utc',
        'order': 'desc',
    }
    return _polygon_get(params)



def register_news_tools(mcp):
    """Register all news tools with MCP server."""

    @mcp.tool(name="get_company_news")
    def get_company_news(
        symbol: str,
        start_date: str,
        end_date: str,
        limit: int = 20,
        page: int = 0,
    ) -> Dict[str, Any]:
        """
        Get company-specific news headlines for a symbol over a date range.

        Args:
            symbol: Stock ticker symbol (required).
            start_date: Start date (YYYY-MM-DD), inclusive.
            end_date: End date (YYYY-MM-DD), inclusive.
            limit: Maximum number of articles to return (default: 20).

        Notes:
            - The ReasoningAgent will typically auto-fill and clamp the dates,
              limit, and lookback window to avoid lookahead and huge payloads.
            - FMP news search endpoints may only support relatively short
              lookback windows; if a much larger span is requested we
              automatically clamp to the last 12 days ending at end_date.
            - This tool is intentionally symbol-scoped to keep the surface area
              targeted and easy for the LLM to reason about.
        """
        tool_name = "get_company_news"
        try:
            if not symbol:
                raise ValueError("get_company_news requires a non-empty symbol")

            # Validate / normalize dates
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            if end_dt < start_dt:
                start_dt, end_dt = end_dt, start_dt

            # Clamp to a max 12-day window to match FMP behaviour
            if (end_dt - start_dt).days > 12:
                start_dt = end_dt - timedelta(days=12)

            if limit <= 0:
                limit = 1
            if limit > 250:
                limit = 250
            if page < 0:
                page = 0

            data = _cached_company_news(
                symbol=symbol.upper(),
                start_date=start_dt.strftime("%Y-%m-%d"),
                end_date=end_dt.strftime("%Y-%m-%d"),
                limit=limit,
                page=page,
            )
            # FMP returns a list; wrap in our standard schema
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_world_news")
    def get_world_news(
        start_date: str,
        end_date: str,
        limit: int = 20,
        page: int = 0,
        topics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get macro / world news headlines over a date range.

        Args:
            start_date: Start date (YYYY-MM-DD), inclusive.
            end_date: End date (YYYY-MM-DD), inclusive.
            limit: Maximum number of articles to return (default: 20).
            page: Result page index for FMP pagination.
            topics: Optional list of simple topic filters; we apply these as a
                best-effort filter on the returned headlines (case-insensitive
                substring match on the title and text fields).

        Notes:
            - This tool is intentionally symbol-agnostic and should be used
              primarily for macro context (e.g., rate decisions, CPI prints).
            - The ReasoningAgent will auto-fill and clamp dates + limit to
              keep payloads small and avoid lookahead in backtests.
        """
        tool_name = "get_world_news"
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            if end_dt < start_dt:
                start_dt, end_dt = end_dt, start_dt

            # Clamp to max 12-day window to match FMP behaviour
            if (end_dt - start_dt).days > 12:
                start_dt = end_dt - timedelta(days=12)

            if limit <= 0:
                limit = 1
            if limit > 250:
                limit = 250
            if page < 0:
                page = 0

            raw = _cached_world_news(
                start_date=start_dt.strftime("%Y-%m-%d"),
                end_date=end_dt.strftime("%Y-%m-%d"),
                limit=limit,
                page=page,
            )

            # Optional topic filtering on title/text
            data = raw
            if topics:
                if isinstance(topics, str):
                    topics_list: List[str] = [topics]
                else:
                    topics_list = list(topics)
                lowered = [t.lower() for t in topics_list]
                filtered: List[Dict[str, Any]] = []
                for item in raw or []:
                    if not isinstance(item, dict):
                        continue
                    text = (
                        f"{item.get('title','')} {item.get('text','')}".lower()
                    )
                    if any(tok in text for tok in lowered):
                        filtered.append(item)
                data = filtered

            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    # ========================================================================
    # Polygon News Tools (OpenBB-based, free alternative to FMP)
    # ========================================================================

    @mcp.tool(name="get_openbb_company_news")
    def get_openbb_company_news(
        symbol: str,
        start_date: str,
        end_date: str,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Get company-specific news headlines for a symbol over a date range using OpenBB/Polygon.

        Args:
            symbol: Stock ticker symbol (required).
            start_date: Start date (YYYY-MM-DD), inclusive.
            end_date: End date (YYYY-MM-DD), inclusive.
            limit: Maximum number of articles to return (default: 20).

        Notes:
            - Uses Polygon as the free data provider (requires Polygon API key).
            - The ReasoningAgent will typically auto-fill and clamp the dates
              and limit to avoid lookahead and huge payloads.
        """
        tool_name = "get_openbb_company_news"
        try:
            if not symbol:
                raise ValueError("get_openbb_company_news requires a non-empty symbol")

            # Validate / normalize dates
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            if end_dt < start_dt:
                start_dt, end_dt = end_dt, start_dt

            # Clamp limit
            if limit <= 0:
                limit = 1
            if limit > 250:
                limit = 250

            # Call cached OpenBB function
            data = _cached_company_news_polygon(
                symbol=symbol.upper(),
                start_date=start_dt.strftime("%Y-%m-%d"),
                end_date=end_dt.strftime("%Y-%m-%d"),
                limit=limit,
            )
            
            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)

    @mcp.tool(name="get_openbb_world_news")
    def get_openbb_world_news(
        start_date: str,
        end_date: str,
        limit: int = 20,
        topics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get macro / world news headlines over a date range using OpenBB/Polygon.

        Args:
            start_date: Start date (YYYY-MM-DD), inclusive.
            end_date: End date (YYYY-MM-DD), inclusive.
            limit: Maximum number of articles to return (default: 20).
            topics: Optional list of simple topic filters; we apply these as a
                best-effort filter on the returned headlines (case-insensitive
                substring match on the title and text fields).

        Notes:
            - Uses Polygon as the free data provider (requires Polygon API key).
            - This tool is intentionally symbol-agnostic and should be used
                primarily for macro context (e.g., rate decisions, CPI prints).
        """
        tool_name = "get_openbb_world_news"
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            if end_dt < start_dt:
                start_dt, end_dt = end_dt, start_dt

            # Clamp limit
            if limit <= 0:
                limit = 1
            if limit > 250:
                limit = 250

            # Call cached OpenBB function
            raw = _cached_world_news_polygon(
                start_date=start_dt.strftime("%Y-%m-%d"),
                end_date=end_dt.strftime("%Y-%m-%d"),
                limit=limit,
            )

            # Optional topic filtering on title/text
            data = raw
            
            if topics:
                if isinstance(topics, str):
                    topics_list: List[str] = [topics]
                else:
                    topics_list = list(topics)
                lowered = [t.lower() for t in topics_list]
                filtered: List[Dict[str, Any]] = []
                
                for item in raw or []:
                    if not isinstance(item, dict):
                        continue
                    text = (
                        f"{item.get('title','')} {item.get('text','')}".lower()
                    )
                    if any(tok in text for tok in lowered):
                        filtered.append(item)
                data = filtered

            return format_tool_result(tool_name, data=data)
        except Exception as e:  # noqa: BLE001
            return format_tool_result(tool_name, error=e)
