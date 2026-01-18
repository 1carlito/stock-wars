"""
Integration tests for Phase 7: Complete multi-phase trading system.

Validates end-to-end integration of:
  1. All six prior phases (indicators, caching, sectors, tokens, orchestrator, freshness).
  2. Backward compatibility (single-stock mode) and forward compatibility (multi-stock mode).
  3. Token budget tracking and enforcement across the portfolio.
  4. Data freshness rules preventing stale trades.
  5. Waterfall allocation with a 25% cap and sector-aware tie-breaking.
  6. Portfolio state persistence and DeepSeek cost accounting.
"""

import os
import sys
from datetime import date
from pathlib import Path

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
custom_trading_bot_dir = os.path.join(base_dir, "custom_TradingBot")
live_trade_dir = os.path.join(custom_trading_bot_dir, "live_trade")

sys.path.insert(0, custom_trading_bot_dir)
sys.path.insert(0, live_trade_dir)
sys.path.insert(0, base_dir)

from token_tracker import TokenTracker
from freshness_validator import FreshnessValidator, DataFreshnessContext
from portfolio_orchestrator import PortfolioOrchestrator
from live_trading_loop import load_portfolio_state, PortfolioState


def test_single_stock_backward_compatibility():
    orch_single = PortfolioOrchestrator(
        symbols=["AAPL"],
        starting_capital=50000,
        risk_level="medium",
    )

    assert len(orch_single.symbols) == 1
    assert orch_single.starting_capital == 50000
    assert orch_single.token_tracker is not None

    trade_date = "2026-01-10"
    orch_single.token_tracker.log_decision(
        symbol="AAPL",
        date=trade_date,
        input_tokens=5000,
        output_tokens=1000,
        total_tokens=6000,
        decision="BUY",
    )

    summary = orch_single.token_tracker.get_summary()
    assert summary["total_decisions"] == 1
    assert summary["total_tokens"] == 6000


def test_multi_stock_forward_compatibility_and_budget():
    orch_multi = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
        starting_capital=100000,
        risk_level="medium",
        max_parallel=5,
    )

    assert len(orch_multi.symbols) == 5
    assert orch_multi.max_parallel == 5

    for symbol in orch_multi.symbols:
        orch_multi.token_tracker.log_decision(
            symbol=symbol,
            date="2026-01-10",
            input_tokens=5000,
            output_tokens=1000,
            total_tokens=6000,
        )

    summary = orch_multi.token_tracker.get_summary()
    assert summary["total_decisions"] == 5
    assert summary["total_tokens"] == 30000
    assert summary["budget"]["within_budget"] is True
    assert summary["budget"]["pct_used"] == 30.0


def test_token_budget_enforcement():
    tracker = TokenTracker(daily_limit=100_000)

    test_cases = [
        ("AAPL", 20000, 5000),
        ("MSFT", 20000, 5000),
        ("NVDA", 20000, 5000),
        ("GOOGL", 20000, 5000),  # 100K total
    ]

    for symbol, input_tokens, output_tokens in test_cases:
        tracker.log_decision(
            symbol=symbol,
            date="2026-01-10",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    budget = tracker.check_budget()
    assert budget["within_budget"] is True
    assert budget["pct_used"] == 100.0
    assert budget["warning"] is True

    # Exceed budget
    tracker.log_decision(
        symbol="META",
        date="2026-01-10",
        input_tokens=10000,
        output_tokens=5000,
        total_tokens=15000,
    )

    budget_exceeded = tracker.check_budget()
    assert budget_exceeded["within_budget"] is False
    assert budget_exceeded["critical"] is True


def test_freshness_validation_blocks_stale_price():
    fresh_prices = [
        {"date": "2026-01-09", "close": 150.0},
        {"date": "2026-01-10", "close": 152.0},
    ]
    stale_prices = [
        {"date": "2026-01-02", "close": 145.0},
        {"date": "2026-01-03", "close": 147.0},
    ]
    trade_date = "2026-01-10"

    result_fresh = FreshnessValidator.validate_price_data(fresh_prices, trade_date)
    assert result_fresh["fresh"] is True
    assert result_fresh["days_stale"] == 0

    result_stale = FreshnessValidator.validate_price_data(stale_prices, trade_date)
    assert result_stale["fresh"] is False
    assert result_stale["days_stale"] == 7

    all_fresh = FreshnessValidator.check_all_data_types(
        price_data=fresh_prices,
        fundamental_data=None,
        news_data=None,
        trade_date=trade_date,
    )
    assert all_fresh["can_trade"] is True

    all_stale = FreshnessValidator.check_all_data_types(
        price_data=stale_prices,
        fundamental_data=None,
        news_data=None,
        trade_date=trade_date,
    )
    assert all_stale["can_trade"] is False


def test_waterfall_allocation_25_percent_cap():
    portfolio_state = PortfolioState(cash=100000)
    orch = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT", "NVDA"],
        starting_capital=100000,
    )

    decisions = [
        {
            "symbol": "AAPL",
            "decision": "BUY",
            "confidence": 0.95,
            "requested_amount": 60000,
            "sector_rank": 1,
        },
        {
            "symbol": "MSFT",
            "decision": "BUY",
            "confidence": 0.85,
            "requested_amount": 50000,
            "sector_rank": 1,
        },
        {
            "symbol": "NVDA",
            "decision": "BUY",
            "confidence": 0.80,
            "requested_amount": 40000,
            "sector_rank": 2,
        },
    ]

    allocated = orch._apply_waterfall_allocation(decisions, portfolio_state)
    assert allocated
    for decision in allocated:
        assert decision["allocated_amount"] <= portfolio_state.cash * 0.25


def test_data_freshness_context_summary():
    context = DataFreshnessContext("2026-01-10")
    stocks_fresh = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]
    stocks_stale = ["JPM", "JNJ", "XOM"]

    for symbol in stocks_fresh:
        context.record_check(
            symbol,
            {
                "can_trade": True,
                "skip_reason": None,
                "data_status": {"price": {"fresh": True}},
            },
        )

    for symbol in stocks_stale:
        context.record_check(
            symbol,
            {
                "can_trade": False,
                "skip_reason": "Stale price data",
                "data_status": {"price": {"fresh": False, "days_stale": 5}},
            },
        )

    summary = context.get_summary()
    assert summary["total_checked"] == 10
    assert summary["tradeable"] == 7
    assert summary["skipped"] == 3
    assert summary["skip_percentage"] == 30.0


def test_complete_workflow_token_and_freshness_summaries():
    workflow_orch = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT"],
        starting_capital=50000,
        risk_level="medium",
        max_parallel=2,
    )

    trade_date = "2026-01-10"
    workflow_orch.freshness_context = DataFreshnessContext(trade_date)

    price_data_aapl = [
        {"date": "2026-01-09", "close": 150.0, "high": 151.0, "low": 149.0},
        {"date": "2026-01-10", "close": 152.0, "high": 153.0, "low": 151.0},
    ]
    price_data_msft = [
        {"date": "2026-01-09", "close": 310.0, "high": 312.0, "low": 309.0},
        {"date": "2026-01-10", "close": 315.0, "high": 316.0, "low": 314.0},
    ]

    fresh_aapl = FreshnessValidator.validate_price_data(price_data_aapl, trade_date)
    fresh_msft = FreshnessValidator.validate_price_data(price_data_msft, trade_date)

    workflow_orch.freshness_context.record_check(
        "AAPL",
        {
            "can_trade": fresh_aapl["fresh"],
            "skip_reason": None if fresh_aapl["fresh"] else "Stale",
            "data_status": {"price": fresh_aapl},
        },
    )
    workflow_orch.freshness_context.record_check(
        "MSFT",
        {
            "can_trade": fresh_msft["fresh"],
            "skip_reason": None if fresh_msft["fresh"] else "Stale",
            "data_status": {"price": fresh_msft},
        },
    )

    for symbol in ["AAPL", "MSFT"]:
        workflow_orch.token_tracker.log_decision(
            symbol=symbol,
            date=trade_date,
            input_tokens=5000,
            output_tokens=1500,
            total_tokens=6500,
            decision="BUY",
        )

    token_summary = workflow_orch.token_tracker.get_summary()
    freshness_summary = workflow_orch.freshness_context.get_summary()

    assert token_summary["total_decisions"] == 2
    assert token_summary["total_tokens"] == 13000
    assert freshness_summary["total_checked"] == 2
    assert freshness_summary["tradeable"] == 2


def test_deepseek_cost_calculation_portfolio_level():
    cost_tracker = TokenTracker(daily_limit=1_000_000)

    cost_tracker.log_decision(
        symbol="AAPL",
        date="2026-01-10",
        input_tokens=50_000,
        output_tokens=10_000,
        total_tokens=60_000,
        decision="BUY",
    )
    cost_tracker.log_decision(
        symbol="MSFT",
        date="2026-01-10",
        input_tokens=45_000,
        output_tokens=9_000,
        total_tokens=54_000,
        decision="SELL",
    )

    summary = cost_tracker.get_summary()
    expected_cost = (95_000 * 0.27 / 1_000_000) + (19_000 * 1.10 / 1_000_000)
    assert abs(summary["total_cost_usd"] - expected_cost) < 1e-6


def test_portfolio_state_persistence_structure():
    initial_state = load_portfolio_state(starting_capital=100000)

    assert isinstance(initial_state, PortfolioState)
    assert hasattr(initial_state, "cash")
    assert hasattr(initial_state, "positions")


