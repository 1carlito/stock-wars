"""
Unit tests for Phase 5: `PortfolioOrchestrator` for parallel portfolio processing.

Verifies:
  1. `PortfolioOrchestrator` initialization and basic attributes.
  2. Sector rankings retrieval via the sector tools (static ranking).
  3. Decision filtering and enrichment with sector metadata.
  4. Waterfall allocation with a 25% cash cap per trade.
  5. Token tracking behavior across multiple symbols.
  6. Budget enforcement behavior.
  7. Portfolio summary helper structure.
"""

import os
import sys
import asyncio
from datetime import datetime, date
from pathlib import Path

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
custom_trading_bot_dir = os.path.join(base_dir, "custom_TradingBot")
live_trade_dir = os.path.join(custom_trading_bot_dir, "live_trade")

sys.path.insert(0, custom_trading_bot_dir)
sys.path.insert(0, live_trade_dir)
sys.path.insert(0, base_dir)

from portfolio_orchestrator import PortfolioOrchestrator
from token_tracker import TokenTracker


def test_portfolio_orchestrator_initialization():
    symbols = ["AAPL", "MSFT", "NVDA"]
    starting_capital = 100000.0

    orchestrator = PortfolioOrchestrator(
        symbols=symbols,
        starting_capital=starting_capital,
        max_parallel=3,
    )

    assert orchestrator.symbols == symbols
    assert orchestrator.starting_capital == starting_capital
    assert isinstance(orchestrator.token_tracker, TokenTracker)
    assert len(orchestrator.token_tracker.decisions) == 0


def test_sector_rankings_retrieval():
    """Static sector rankings should be returned with valid structure."""
    orchestrator = PortfolioOrchestrator(
        symbols=["AAPL"],
        starting_capital=100000.0,
        max_parallel=1,
    )

    async def _run():
        return await orchestrator._get_sector_rankings("2026-01-11")

    sector_ranks = asyncio.run(_run())

    assert isinstance(sector_ranks, dict)
    assert len(sector_ranks) > 0

    sample_sector = next(iter(sector_ranks.values()))
    for field in ["rank", "score", "momentum"]:
        assert field in sample_sector


def test_decision_filter_and_enrich():
    """Filtering removes failed decisions and enriches with sector info."""
    orchestrator = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT", "NVDA"],
        starting_capital=100000.0,
        max_parallel=3,
    )

    # Simple static sector ranks (Technology only)
    sector_ranks = {
        "Technology": {"rank": 1, "score": 95, "momentum": "strong"},
    }

    mock_results = [
        {
            "symbol": "AAPL",
            "success": True,
            "decision": "BUY",
            "confidence": 0.85,
            "amount_usd": 10000,
            "reasoning": "Strong technical signals",
        },
        {
            "symbol": "MSFT",
            "success": True,
            "decision": "HOLD",
            "confidence": 0.60,
            "amount_usd": 0,
            "reasoning": "Mixed signals",
        },
        {
            "symbol": "NVDA",
            "success": False,
            "error": "API error",
        },
    ]

    enriched = orchestrator._filter_and_enrich(mock_results, sector_ranks)

    assert len(enriched) == 2
    assert all(d.get("success") for d in enriched)
    assert all("sector" in d for d in enriched)


def test_waterfall_allocation_with_25_percent_cap():
    """Waterfall allocation caps per-trade allocation at 25% of cash."""
    orchestrator = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT", "NVDA"],
        starting_capital=100000.0,
        max_parallel=3,
    )

    from live_trading_loop import PortfolioState

    test_decisions = [
        {
            "symbol": "AAPL",
            "decision": "BUY",
            "confidence": 0.95,
            "amount_usd": 50000,
            "sector_rank": 1,
        },
        {
            "symbol": "MSFT",
            "decision": "BUY",
            "confidence": 0.80,
            "amount_usd": 40000,
            "sector_rank": 2,
        },
        {
            "symbol": "NVDA",
            "decision": "BUY",
            "confidence": 0.80,
            "amount_usd": 30000,
            "sector_rank": 1,
        },
    ]

    portfolio_state = PortfolioState(cash=100000)
    allocated = orchestrator._apply_waterfall_allocation(test_decisions, portfolio_state)

    assert allocated
    first_alloc = allocated[0]["allocated_amount"]
    assert first_alloc <= 25000  # 25% of 100k

    confidences = [d.get("confidence", 0) for d in allocated]
    assert confidences[0] >= confidences[-1]


def test_token_tracking_multi_stock():
    """Token tracker aggregates usage across multiple symbols."""
    orchestrator = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
        starting_capital=100000,
    )

    trade_date = "2026-01-11"

    for i, symbol in enumerate(orchestrator.symbols):
        input_tokens = 5000 + (i * 1000)
        output_tokens = 1000 + (i * 500)
        orchestrator.token_tracker.log_decision(
            symbol=symbol,
            date=trade_date,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            decision="BUY",
        )

    summary = orchestrator.token_tracker.get_summary()
    assert summary["total_decisions"] == 5
    assert summary["total_tokens"] > 0
    assert summary["total_cost_usd"] > 0
    assert summary["budget"]["within_budget"] is True


def test_budget_enforcement_behavior():
    """Budget goes to critical state when over limit."""
    orchestrator = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT"],
        starting_capital=50000,
    )

    trade_date = "2026-01-11"

    orchestrator.token_tracker.log_decision(
        symbol="AAPL",
        date=trade_date,
        input_tokens=40000,
        output_tokens=15000,
        total_tokens=55000,
        decision="BUY",
    )
    budget_before = orchestrator.token_tracker.check_budget()
    assert budget_before["within_budget"] is True
    assert budget_before["warning"] is False

    orchestrator.token_tracker.log_decision(
        symbol="MSFT",
        date=trade_date,
        input_tokens=50000,
        output_tokens=20000,
        total_tokens=70000,
        decision="SELL",
    )
    budget_after = orchestrator.token_tracker.check_budget()
    assert budget_after["within_budget"] is False
    assert budget_after["critical"] is True


def test_portfolio_summary_structure():
    """`get_summary` should expose basic portfolio and token-tracker state."""
    orchestrator = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT"],
        starting_capital=100000,
    )

    summary = orchestrator.get_summary()

    assert summary["symbols"] == ["AAPL", "MSFT"]
    assert summary["portfolio_state"] is not None
    assert hasattr(summary["portfolio_state"], "cash")
    assert "total_decisions" in summary["token_tracker"]



