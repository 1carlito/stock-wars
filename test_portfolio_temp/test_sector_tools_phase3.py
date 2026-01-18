"""
Unit tests for Phase 3: Sector Ranking System (`Sector_Tools`).

Verifies:
  1. `get_sector_rankings` returns a static S&P 500 sector list with valid fields.
  2. Sector scores and ranks are well-formed and sequential.
  3. Momentum values use the expected enum set.
  4. Sector weights sum to approximately 1.0 for allocation.
  5. `get_company_sector` behaves gracefully on Starter tier (may return an error).
"""

import os
import sys
from datetime import datetime

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
custom_trading_bot_dir = os.path.join(base_dir, "custom_TradingBot")
sys.path.insert(0, custom_trading_bot_dir)
sys.path.insert(0, base_dir)

from Tools.Sector_Tools import register_sector_tools
from utils import format_tool_result


class SimpleMCP:
    """Minimal MCP-style container used to capture registered tools in tests."""

    def tool(self, name):
        def decorator(func):
            setattr(SimpleMCP, f"_func_{name}", func)
            return func

        return decorator


def _get_sector_rankings_tool():
    mcp = SimpleMCP()
    register_sector_tools(mcp)
    return getattr(SimpleMCP, "_func_get_sector_rankings")


def _get_company_sector_tool():
    mcp = SimpleMCP()
    register_sector_tools(mcp)
    return getattr(SimpleMCP, "_func_get_company_sector")


def test_sector_rankings_basic_structure():
    get_sector_rankings = _get_sector_rankings_tool()
    test_date = "2026-01-11"
    result = get_sector_rankings(test_date)

    assert isinstance(result, dict)
    assert "data" in result

    data = result["data"]
    assert "sectors" in data
    sectors = data["sectors"]

    assert isinstance(sectors, list)
    assert len(sectors) == 11  # S&P 500 sectors


def test_sector_data_fields_and_ranges():
    get_sector_rankings = _get_sector_rankings_tool()
    result = get_sector_rankings("2026-01-11")
    sectors = result["data"]["sectors"]

    required_fields = ["name", "score", "rank", "momentum", "weight"]
    for sector in sectors:
        for field in required_fields:
            assert field in sector

        score = sector["score"]
        assert 0 <= score <= 100

    ranks = sorted(s["rank"] for s in sectors)
    assert ranks == list(range(1, len(sectors) + 1))

    valid_momentum = ["strong", "moderate", "neutral", "weak", "very_weak"]
    for sector in sectors:
        assert sector["momentum"] in valid_momentum


def test_sector_ranking_order_and_weights():
    get_sector_rankings = _get_sector_rankings_tool()
    result = get_sector_rankings("2026-01-11")
    sectors = result["data"]["sectors"]

    sectors_by_rank = sorted(sectors, key=lambda s: s["rank"])
    scores = [s["score"] for s in sectors_by_rank]
    assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))

    weights = [s["weight"] for s in sectors]
    total_weight = sum(weights)
    assert 0.99 <= total_weight <= 1.01


def test_company_sector_lookup_is_resilient():
    """`get_company_sector` should not raise even if FMP is unavailable."""
    get_company_sector = _get_company_sector_tool()
    result = get_company_sector("AAPL")

    assert isinstance(result, dict)
    # Either we have an error (e.g., Starter tier / no key) or data with sector info
    if "error" in result:
        # Error is acceptable for environments without FMP access
        assert isinstance(result["error"], str)
    elif "data" in result:
        data = result["data"]
        assert "sector" in data
        assert "industry" in data


