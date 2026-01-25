"""
Unit tests for Phase 4: Token Usage Tracking via `TokenTracker`.

Verifies:
  1. Initialization and basic decision logging with DeepSeek pricing.
  2. Daily budget reset-on-date-change behavior.
  3. Budget status, warnings, and critical over-budget flags.
  4. Summary statistics (totals and averages).
  5. Exact cost calculation for large token counts.
  6. Serialization/deserialization via `to_dict` / `from_dict`.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
custom_trading_bot_dir = os.path.join(base_dir, "custom_TradingBot")
sys.path.insert(0, custom_trading_bot_dir)
sys.path.insert(0, base_dir)

from token_tracker import TokenTracker


def test_initialization():
    tracker = TokenTracker(daily_limit=100_000)
    assert tracker.daily_limit == 100_000
    assert tracker.decisions == []
    assert tracker.current_date is None


def test_log_single_decision_and_cost():
    """Single decision should compute DeepSeek cost correctly."""
    tracker = TokenTracker(daily_limit=100_000)
    test_date = "2026-01-11"

    tracker.log_decision(
        symbol="AAPL",
        date=test_date,
        input_tokens=8000,
        output_tokens=2000,
        total_tokens=10000,
        decision="BUY",
    )

    assert len(tracker.decisions) == 1
    assert tracker.current_date == test_date

    decision = tracker.decisions[0]
    expected_cost = (8000 * 0.27 / 1_000_000) + (2000 * 1.10 / 1_000_000)
    assert abs(decision["cost_usd"] - expected_cost) < 1e-6


def test_daily_reset():
    """Decisions reset when the trading date changes."""
    tracker = TokenTracker(daily_limit=100_000)

    # Day 1
    tracker.log_decision("AAPL", "2026-01-11", 5000, 1000, 6000, "BUY")
    tracker.log_decision("MSFT", "2026-01-11", 5000, 1000, 6000, "SELL")
    assert len(tracker.decisions) == 2

    # New day -> should reset
    assert tracker.reset_if_new_day("2026-01-12") is True
    assert len(tracker.decisions) == 0
    assert tracker.current_date == "2026-01-12"

    tracker.log_decision("NVDA", "2026-01-12", 4000, 1000, 5000, "HOLD")
    assert len(tracker.decisions) == 1

    # Same day -> no reset
    assert tracker.reset_if_new_day("2026-01-12") is False
    assert len(tracker.decisions) == 1


def test_budget_status_and_warning():
    """Budget warning should trigger at >=80% of daily limit."""
    tracker = TokenTracker(daily_limit=100_000)

    decisions_data = [
        ("AAPL", 20000, 5000),
        ("MSFT", 20000, 5000),
        ("NVDA", 20000, 5000),
        ("GOOGL", 15000, 4000),  # Total ~89K tokens
    ]

    for symbol, input_tokens, output_tokens in decisions_data:
        tracker.log_decision(
            symbol=symbol,
            date="2026-01-11",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    budget = tracker.check_budget()
    assert budget["within_budget"] is True
    assert budget["warning"] is True
    assert budget["pct_used"] >= 80


def test_budget_exceeded_and_critical():
    """When over the limit, remaining should be 0 and critical flag true."""
    tracker = TokenTracker(daily_limit=100_000)

    tracker.log_decision("AAPL", "2026-01-11", 50000, 15000, 65000)
    tracker.log_decision("MSFT", "2026-01-11", 40000, 10000, 50000)  # 115K total

    budget = tracker.check_budget()
    assert budget["within_budget"] is False
    assert budget["remaining"] == 0
    assert budget["critical"] is True


def test_summary_statistics():
    """Summary should aggregate totals and averages correctly."""
    tracker = TokenTracker(daily_limit=100_000)
    tracker.log_decision("AAPL", "2026-01-11", 10000, 2000, 12000, "BUY")
    tracker.log_decision("MSFT", "2026-01-11", 8000, 2000, 10000, "SELL")
    tracker.log_decision("NVDA", "2026-01-11", 12000, 3000, 15000, "BUY")

    summary = tracker.get_summary()
    assert summary["total_decisions"] == 3
    assert summary["total_tokens"] == 37000
    assert summary["total_cost_usd"] > 0
    assert summary["avg_tokens_per_decision"] > 0


def test_deepseek_cost_accuracy():
    """1M/1M input/output tokens should cost ~$1.37 using DeepSeek pricing."""
    tracker = TokenTracker(daily_limit=100_000)
    tracker.log_decision("TEST", "2026-01-11", 1_000_000, 1_000_000, 2_000_000)

    decision = tracker.decisions[0]
    expected_cost = 0.27 + 1.10  # 1M input + 1M output
    assert abs(decision["cost_usd"] - expected_cost) < 0.01


def test_serialization_roundtrip():
    """`to_dict` and `from_dict` should preserve tracker state."""
    tracker = TokenTracker(daily_limit=100_000)
    tracker.log_decision("AAPL", "2026-01-11", 5000, 1000, 6000, "BUY")
    tracker.log_decision("MSFT", "2026-01-11", 4000, 1000, 5000, "SELL")

    state_dict = tracker.to_dict()
    restored = TokenTracker.from_dict(state_dict)

    assert restored.daily_limit == 100_000
    assert restored.current_date == "2026-01-11"
    assert len(restored.decisions) == 2



