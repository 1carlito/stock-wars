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
    "get_fmp_bbands": {
        "category": "technical",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_fmp_bbands",
        "description": "Bollinger Bands (fast - precomputed, instant response)",
        "requires": ["has_fmp_access"],
        "replaces": None
    },
    "get_fmp_obv": {
        "category": "technical",
        "tier": "free",
        "provider": "fmp",
        "mcp_name": "get_fmp_obv",
        "description": "OBV indicator (fast - precomputed, instant response)",
        "requires": ["has_fmp_access"],
        "replaces": None
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

TIER_DEFINITIONS: Dict[str, List[str]] = {
    "free": [
        # Price
        "get_price_history",
        "get_current_price",
        "get_real_time_quote",
        "get_4hour_chart",
        "get_premarket_context",
        # Technical (OpenBB versions - slower but always available)
        "calculate_rsi",
        "calculate_ema",
        "calculate_adx",
        "calculate_cci",
        # News
        "get_company_news",
        "get_world_news",
        # Sector
        "get_sector_rankings",
        "get_sector_exposure",
        "get_company_sector",
        # Trading
        "execute_trade",
    ],
    "starter": [
        # All free tier tools
        *[tool for tool in TIER_DEFINITIONS.get("free", [])],
        # Plus all fundamentals
        "get_income_statement",
        "get_balance_sheet",
        "get_cash_flow",
        "get_company_profile",
        "get_earnings_calendar",
        "get_analyst_estimates",
        "get_key_metrics",
    ],
    "premium": [
        # All tools (would add more premium-only tools here in future)
        *list(TOOL_REGISTRY.keys()),
    ],
}

# Fix tier_definitions forward reference
TIER_DEFINITIONS["starter"] = [
    # All free tier tools
    "get_price_history",
    "get_current_price",
    "get_real_time_quote",
    "get_4hour_chart",
    "get_premarket_context",
    "calculate_rsi",
    "calculate_ema",
    "calculate_adx",
    "calculate_cci",
    "get_company_news",
    "get_world_news",
    "get_sector_rankings",
    "get_sector_exposure",
    "get_company_sector",
    "execute_trade",
    # Plus fundamentals
    "get_income_statement",
    "get_balance_sheet",
    "get_cash_flow",
    "get_company_profile",
    "get_earnings_calendar",
    "get_analyst_estimates",
    "get_key_metrics",
]

# =============================================================================
# DEDUPLICATION PAIRS - Tools to prefer when both are available
# Format: (slow_openbb_tool, fast_fmp_tool)
# =============================================================================

DEDUPLICATION_PAIRS: List[tuple] = [
    ("calculate_rsi", "get_fmp_rsi"),      # Prefer FMP (faster)
    ("calculate_ema", "get_fmp_ema"),      # Prefer FMP (faster)
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
