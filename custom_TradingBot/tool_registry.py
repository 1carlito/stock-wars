"""
Tool Registry and Configuration
Defines all available tools, their metadata, tiers, and provider information.
"""

from typing import Dict, List, Any, Optional

# =============================================================================
# TOOL REGISTRY - All MCP-registered tools with metadata
# =============================================================================

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # PRICE TOOLS - Fast, always available (FREE)
    # =========================================================================
    "get_price_history": {
        "category": "price",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_price_history",
        "description": "Historical price data (OHLCV)"
    },
    "get_current_price": {
        "category": "price",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_current_price",
        "description": "Current price quote"
    },
    "get_current_price_yfinance": {
        "category": "price",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_current_price_yfinance",
        "description": "Current price via 5m intraday candle (FREE - yfinance)"
    },
    "get_real_time_quote": {
        "category": "price",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_real_time_quote",
        "description": "Real-time quote from FMP"
    },
    "get_4hour_chart": {
        "category": "price",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_4hour_chart",
        "description": "4-hour chart data"
    },
    "get_premarket_context": {
        "category": "price",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_premarket_context",
        "description": "Premarket trading data"
    },

    # =========================================================================
    # TECHNICAL INDICATORS - OpenBB versions (slower, fetch 200+ days)
    # FREE tier but prefer FMP versions if available
    # =========================================================================
    "calculate_rsi": {
        "category": "technical",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "calculate_rsi",
        "description": "RSI indicator (slow - fetches ~200 days)",
        "has_fast_alternative": True
    },
    "calculate_ema": {
        "category": "technical",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "calculate_ema",
        "description": "EMA indicator (slow - fetches ~200 days)",
        "has_fast_alternative": True
    },
    "calculate_adx": {
        "category": "technical",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "calculate_adx",
        "description": "ADX indicator (slow - fetches ~200 days)",
        "has_fast_alternative": False
    },
    "calculate_cci": {
        "category": "technical",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "calculate_cci",
        "description": "CCI indicator (slow - fetches ~200 days)",
        "has_fast_alternative": False
    },

    # =========================================================================
    # TECHNICAL INDICATORS - FMP versions (fast, precomputed)
    # Only available if has_fmp_access=true
    # =========================================================================
    "get_fmp_rsi": {
        "category": "technical",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_fmp_rsi",
        "description": "RSI indicator (fast - precomputed, instant response)",
        "requires": ["has_fmp_access"],
        "replaces": "calculate_rsi"  # Deduplication hint
    },
    "get_fmp_ema": {
        "category": "technical",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_fmp_ema",
        "description": "EMA indicator (fast - precomputed, instant response)",
        "requires": ["has_fmp_access"],
        "replaces": "calculate_ema"
    },
    "get_fmp_sma": {
        "category": "technical",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_fmp_sma",
        "description": "SMA indicator (fast - precomputed, instant response)",
        "requires": ["has_fmp_access"],
        "replaces": None  # No OpenBB equivalent in registry
    },
    "get_fmp_wma": {
        "category": "technical",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_fmp_wma",
        "description": "WMA indicator (fast - precomputed, instant response)",
        "requires": ["has_fmp_access"],
        "replaces": None
    },
    # =========================================================================
    # TECHNICAL INDICATORS - OpenBB intraday indicators (FREE)
    # Fetch historical data (60-200 days), calculate, return current values ONLY
    # No direct FMP equivalents available
    # =========================================================================
    "calculate_bbands": {
        "category": "technical",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_openbb_bbands",
        "description": "Bollinger Bands (requires history fetch, returns current values only)",
        "has_fast_alternative": True,
        "returns_indicator_only": True
    },
    "calculate_macd": {
        "category": "technical",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_openbb_macd",
        "description": "MACD (requires history fetch, returns current values only)",
        "has_fast_alternative": False,
        "returns_indicator_only": True
    },
    "calculate_obv": {
        "category": "technical",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_openbb_obv",
        "description": "On-Balance Volume (requires history fetch, returns current values only)",
        "has_fast_alternative": True,
        "returns_indicator_only": True
    },
    "get_openbb_vwap": {
        "category": "technical",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_openbb_vwap",
        "description": "Volume-Weighted Average Price intraday (current day only)",
        "has_fast_alternative": False,
        "returns_indicator_only": True
    },
    "get_intraday_candles": {
        "category": "technical",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_intraday_candles",
        "description": "Intraday price candles (30m/1h)",
        "requires": ["has_fmp_access"]
    },

    # =========================================================================
    # NEWS TOOLS
    # Note: Current get_company_news uses FMP API
    # Could add OpenBB variants in future
    # =========================================================================
    "get_company_news": {
        "category": "news",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_company_news",
        "description": "Company-specific news (FMP)"
    },
    "get_world_news": {
        "category": "news",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_world_news",
        "description": "Market and macro news (FMP)"
    },

    # =========================================================================
    # FUNDAMENTAL ANALYSIS - OpenBB (STARTER tier)
    # =========================================================================
    "get_income_statement": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "openbb",
        "mcp_name": "get_income_statement",
        "description": "Income statement financials"
    },
    "get_balance_sheet": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "openbb",
        "mcp_name": "get_balance_sheet",
        "description": "Balance sheet financials"
    },
    "get_cash_flow": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "openbb",
        "mcp_name": "get_cash_flow",
        "description": "Cash flow statement"
    },
    "get_company_profile": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "openbb",
        "mcp_name": "get_company_profile",
        "description": "Company profile and overview"
    },
    "get_earnings_calendar": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "openbb",
        "mcp_name": "get_earnings_calendar",
        "description": "Earnings calendar and dates"
    },
    "get_analyst_estimates": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "openbb",
        "mcp_name": "get_analyst_estimates",
        "description": "Analyst price targets and estimates"
    },
    "get_key_metrics": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "openbb",
        "mcp_name": "get_key_metrics",
        "description": "Key financial metrics and ratios"
    },
    
    # =========================================================================
    # FUNDAMENTAL - FMP DIRECT (New additions)
    # =========================================================================
    "get_fmp_income_statement": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "fmp",
        "mcp_name": "get_fmp_income_statement",
        "description": "Income statement (FMP direct)",
        "requires": ["has_fmp_access"]
    },
    "get_fmp_balance_sheet": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "fmp",
        "mcp_name": "get_fmp_balance_sheet",
        "description": "Balance sheet (FMP direct)",
        "requires": ["has_fmp_access"]
    },
    "get_fmp_key_metrics": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "fmp",
        "mcp_name": "get_fmp_key_metrics",
        "description": "Key metrics (FMP direct)",
        "requires": ["has_fmp_access"]
    },
    "get_fmp_ratings": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "fmp",
        "mcp_name": "get_fmp_ratings",
        "description": "Analyst ratings snapshot",
        "requires": ["has_fmp_access"]
    },
    "get_fmp_price_targets": {
        "category": "fundamental",
        "tier": "starter",
        "provider": "fmp",
        "mcp_name": "get_fmp_price_targets",
        "description": "Price target summary",
        "requires": ["has_fmp_access"]
    },

    # =========================================================================
    # SECTOR / MACRO ANALYSIS
    # =========================================================================
    "get_sector_rankings": {
        "category": "sector",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_sector_rankings",
        "description": "Sector performance rankings"
    },
    "get_sector_exposure": {
        "category": "sector",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_sector_exposure",
        "description": "Company sector exposure breakdown"
    },
    "get_company_sector": {
        "category": "sector",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "get_company_sector",
        "description": "Get company sector classification"
    },

    # =========================================================================
    # SPECIAL/TRADING TOOLS
    # =========================================================================
    "execute_trade": {
        "category": "execution",
        "tier": "free",
        "provider": "openbb",
        "mcp_name": "execute_trade",
        "description": "Execute a trade (BUY, SELL, SHORT, CLOSE)"
    },
}

# =============================================================================
# TIER DEFINITIONS - What tools are available at each tier
# =============================================================================

# Free tier tools (base set)
_FREE_TOOLS = [
    # Price
    "get_price_history",
    "get_current_price",
    "get_current_price_yfinance",
    "get_real_time_quote",
    "get_4hour_chart",
    "get_premarket_context",
    # Technical (OpenBB versions - slower but always available)
    "calculate_rsi",
    "calculate_ema",
    "calculate_adx",
    "calculate_cci",
    # Technical (OpenBB intraday - new indicators)
    "get_openbb_bbands",
    "get_openbb_macd",
    "get_openbb_obv",
    "get_openbb_vwap",
    # News
    "get_company_news",
    "get_world_news",
    # Sector
    "get_sector_rankings",
    "get_sector_exposure",
    "get_company_sector",
    # Trading
    "execute_trade",
]

# Starter tier = free + fundamentals
_STARTER_TOOLS = _FREE_TOOLS + [
    "get_income_statement",
    "get_balance_sheet",
    "get_cash_flow",
    "get_company_profile",
    "get_earnings_calendar",
    "get_analyst_estimates",
    "get_key_metrics",
]

TIER_DEFINITIONS: Dict[str, List[str]] = {
    "free": _FREE_TOOLS,
    "starter": _STARTER_TOOLS,
    "premium": list(TOOL_REGISTRY.keys()),
}

# =============================================================================
# DEDUPLICATION PAIRS - Tools to prefer when both are available
# Format: (slow_openbb_tool, fast_fmp_tool)
# When both tools are available, prefer the FMP (fast) version
# =============================================================================

DEDUPLICATION_PAIRS: List[tuple] = [
    ("calculate_rsi", "get_fmp_rsi"),           # Prefer FMP (faster, precomputed)
    ("calculate_ema", "get_fmp_ema"),           # Prefer FMP (faster, precomputed)
    ("get_income_statement", "get_fmp_income_statement"),
    ("get_balance_sheet", "get_fmp_balance_sheet"),
    ("get_key_metrics", "get_fmp_key_metrics"),
    # Note: BBands, MACD, OBV, VWAP have no FMP equivalents (not in FMP free tier docs)
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def resolve_enabled_tools(
    user_tier: str = "free",
    has_fmp_access: bool = False,
    explicit_enabled: Optional[List[str]] = None
) -> set:
    """
    Resolve which tools are enabled for a user based on tier and FMP access.

    Args:
        user_tier: "free", "starter", or "premium"
        has_fmp_access: Whether user has FMP API access
        explicit_enabled: Optional list to override default tier tools

    Returns:
        Set of enabled tool names (MCP tool names)
    """
    # Start with explicit override, or use tier defaults
    if explicit_enabled is not None:
        enabled = set(explicit_enabled)
    else:
        # Tier 1: free, Tier 2: starter, default to free for safety
        if user_tier not in TIER_DEFINITIONS:
            user_tier = "free"
        enabled = set(TIER_DEFINITIONS[user_tier])

    # Add FMP tools if user has access
    if has_fmp_access:
        for tool_name, metadata in TOOL_REGISTRY.items():
            requires = metadata.get("requires", [])
            if "has_fmp_access" in requires:
                enabled.add(tool_name)

    return enabled


def get_dedup_preference(fast_tool: str, slow_tool: str) -> str:
    """
    Given a fast and slow tool pair, return which to prefer.
    Always returns the fast one.

    Args:
        fast_tool: FMP tool name (e.g., "get_fmp_rsi")
        slow_tool: OpenBB tool name (e.g., "calculate_rsi")

    Returns:
        Preferred tool name
    """
    return fast_tool


def deduplicate_tools(enabled_tools: set) -> set:
    """
    Remove redundant tools when both slow and fast versions are available.
    Prefers FMP (fast) versions.

    Args:
        enabled_tools: Set of tool names

    Returns:
        Deduplicated set with only preferred versions
    """
    result = set(enabled_tools)

    for slow_tool, fast_tool in DEDUPLICATION_PAIRS:
        # If both exist, remove the slow one
        if fast_tool in result and slow_tool in result:
            result.discard(slow_tool)

    return result


def validate_tool_name(tool_name: str) -> bool:
    """Check if a tool name exists in the registry."""
    return tool_name in TOOL_REGISTRY


def get_tool_metadata(tool_name: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a tool by name."""
    return TOOL_REGISTRY.get(tool_name)


def get_tools_by_category(category: str) -> List[str]:
    """Get all tool names in a category."""
    return [
        name for name, meta in TOOL_REGISTRY.items()
        if meta.get("category") == category
    ]


def get_tools_by_provider(provider: str) -> List[str]:
    """Get all tool names from a specific provider."""
    return [
        name for name, meta in TOOL_REGISTRY.items()
        if meta.get("provider") == provider
    ]


# =============================================================================
# TOOL CATEGORIES FOR USER SELECTION (Live Trading & Backtesting)
# =============================================================================
# User selects which tool categories to use, and the system only shows
# those tools in the system prompt. The agent uses only tools from
# selected categories.

TOOL_CATEGORIES: Dict[str, Dict[str, List[str]]] = {
    "technical_indicators": {
        "description": "Technical analysis tools (RSI, EMA, MACD, etc.) + intraday candles",
        "tools": [
            "get_intraday_candles",  # NEW - latest 30m/1h candle for today
            "calculate_rsi",
            "calculate_ema",
            "calculate_macd",
            "calculate_bbands",
            "calculate_atr",
            "calculate_adx",
            "calculate_obv",
            "calculate_cci",
            "get_fmp_rsi",
            "get_fmp_ema",
        ]
    },
    "fundamental": {
        "description": "Fundamental analysis (financials, earnings, analyst estimates)",
        "tools": [
            "get_company_profile",
            "get_income_statement",
            "get_balance_sheet",
            "get_cash_flow",
            "get_analyst_estimates",
            "get_earnings_calendar",
            "get_fmp_income_statement",
            "get_fmp_balance_sheet",
            "get_fmp_key_metrics",
            "get_fmp_ratings",
            "get_fmp_price_targets",
        ]
    },
    "sentiment": {
        "description": "News and sentiment analysis",
        "tools": [
            "get_company_news",
            "get_world_news",
        ]
    }
}


def get_tools_for_categories(categories: List[str]) -> List[str]:
    """Get all tools for selected categories.

    Args:
        categories: List of category names (e.g., ["technical_indicators", "fundamental"])

    Returns:
        List of tool names to include in system prompt
    """
    tools = []
    for category in categories:
        if category in TOOL_CATEGORIES:
            tools.extend(TOOL_CATEGORIES[category]["tools"])
    return tools


CATEGORY_TOOL_CALLS: Dict[str, List[Dict[str, Any]]] = {
    "technical_indicators": [
        {"tool": "get_intraday_candles", "params": {"lookback_days": None}},
        {"tool": "calculate_rsi", "params": {"lookback_days": None, "period": 14}},
        {"tool": "calculate_ema", "params": {"lookback_days": None, "period": 20}},
        {"tool": "calculate_macd", "params": {"lookback_days": None}},
        {"tool": "calculate_bbands", "params": {"lookback_days": None, "period": 20}},
        {"tool": "calculate_atr", "params": {"lookback_days": None, "period": 14}},
        {"tool": "calculate_adx", "params": {"lookback_days": None, "period": 14}},
        {"tool": "calculate_obv", "params": {"lookback_days": None}},
        {"tool": "calculate_cci", "params": {"lookback_days": None, "period": 20}},
        {"tool": "get_fmp_rsi", "params": {"lookback_days": None}},
        {"tool": "get_fmp_ema", "params": {"lookback_days": None}},
    ],
    "fundamental": [
        {"tool": "get_company_profile", "params": {}},
        {"tool": "get_income_statement", "params": {"limit": 4}},
        {"tool": "get_balance_sheet", "params": {"limit": 4}},
        {"tool": "get_cash_flow", "params": {"limit": 4}},
        {"tool": "get_analyst_estimates", "params": {}},
        {"tool": "get_earnings_calendar", "params": {}},
    ],
    "sentiment": [
        {"tool": "get_company_news", "params": {"limit": 5}},
        {"tool": "get_world_news", "params": {"limit": 5}},
    ]
}


def generate_precomputed_tool_calls(
    selected_categories: List[str],
    technical_indicators_date_range: Optional[int] = None,
) -> str:
    """Generate pre-computed tool calls when user specifies date range.

    Args:
        selected_categories: Tool categories to include (e.g., ["technical_indicators", "fundamental"])
        technical_indicators_date_range: Number of days to lookback (applies to all indicators)

    Returns:
        Pre-formatted tool calls string ready for agent
    """
    if not technical_indicators_date_range:
        return ""  # Return empty if no date range specified

    tool_calls = []

    for category in selected_categories:
        if category not in CATEGORY_TOOL_CALLS:
            continue

        for tool_def in CATEGORY_TOOL_CALLS[category]:
            tool_name = tool_def["tool"]
            params = tool_def["params"].copy()

            # Apply user's date range to all indicators
            if "lookback_days" in params and params["lookback_days"] is None:
                params["lookback_days"] = technical_indicators_date_range

            # Format as tool call string
            param_strs = [f"{k}={v}" for k, v in params.items() if v is not None]
            tool_call_str = f"TOOL_CALL: {tool_name}({', '.join(param_strs)})"
            tool_calls.append(tool_call_str)

    if not tool_calls:
        return ""

    return "PRE-COMPUTED TOOL CALLS:\n" + "\n".join(tool_calls) + "\n"
