"""
Test script for Phase 4: Token Usage Tracking

Tests:
  1. Token tracking initialization
  2. Daily budget reset
  3. Cost calculation (DeepSeek pricing)
  4. Budget enforcement and warnings
  5. Summary statistics
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

print("=" * 80)
print("PHASE 4 TEST: Token Usage Tracking")
print("=" * 80)

# --- TEST 1: Initialize TokenTracker ---
print("\n[TEST 1] TokenTracker initialization")
try:
    tracker = TokenTracker(daily_limit=100_000)
    assert tracker.daily_limit == 100_000, "Daily limit not set"
    assert tracker.decisions == [], "Decisions should be empty"
    assert tracker.current_date is None, "Current date should be None"
    print(f"  Daily limit: {tracker.daily_limit:,} tokens")
    print(f"  Decisions: {len(tracker.decisions)}")
    print("  ✅ PASS")
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 2: Log Single Decision ---
print("\n[TEST 2] Log single decision with token usage")
try:
    test_date = "2026-01-11"
    tracker.log_decision(
        symbol="AAPL",
        date=test_date,
        input_tokens=8000,
        output_tokens=2000,
        total_tokens=10000,
        decision="BUY"
    )

    assert len(tracker.decisions) == 1, "Decision not logged"
    assert tracker.current_date == test_date, "Date not set"

    decision = tracker.decisions[0]
    print(f"  Symbol: {decision['symbol']}")
    print(f"  Tokens: {decision['total_tokens']:,}")
    print(f"  Decision: {decision['decision']}")
    print(f"  Cost: ${decision['cost_usd']:.6f}")

    # Verify cost calculation
    # Input: 8000 * (0.27 / 1M) = 0.00216
    # Output: 2000 * (1.10 / 1M) = 0.0022
    # Total: 0.00436
    expected_cost = (8000 * 0.27 / 1_000_000) + (2000 * 1.10 / 1_000_000)
    assert abs(decision['cost_usd'] - expected_cost) < 0.000001, "Cost calculation wrong"
    print(f"  Expected cost: ${expected_cost:.6f} ✓")
    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- TEST 3: Daily Reset ---
print("\n[TEST 3] Daily reset on date change")
try:
    tracker2 = TokenTracker(daily_limit=100_000)

    # Day 1
    tracker2.log_decision("AAPL", "2026-01-11", 5000, 1000, 6000, "BUY")
    tracker2.log_decision("MSFT", "2026-01-11", 5000, 1000, 6000, "SELL")
    print(f"  Day 1 decisions: {len(tracker2.decisions)}")
    assert len(tracker2.decisions) == 2, "Should have 2 decisions"

    # Day 2 - should reset
    day2_reset = tracker2.reset_if_new_day("2026-01-12")
    print(f"  Day 2 reset: {day2_reset}")
    assert day2_reset is True, "Reset should occur on new day"
    assert len(tracker2.decisions) == 0, "Decisions not cleared"
    assert tracker2.current_date == "2026-01-12", "Date not updated"

    tracker2.log_decision("NVDA", "2026-01-12", 4000, 1000, 5000, "HOLD")
    print(f"  Day 2 decisions: {len(tracker2.decisions)}")
    assert len(tracker2.decisions) == 1, "Should have 1 decision"

    # Same day - no reset
    same_day_reset = tracker2.reset_if_new_day("2026-01-12")
    print(f"  Same day reset: {same_day_reset}")
    assert same_day_reset is False, "No reset should occur on same day"
    assert len(tracker2.decisions) == 1, "Decisions should not be cleared"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 4: Budget Status Checking ---
print("\n[TEST 4] Budget status and warnings")
try:
    tracker3 = TokenTracker(daily_limit=100_000)

    # Log several decisions to accumulate tokens
    decisions_data = [
        ("AAPL", 20000, 5000),
        ("MSFT", 20000, 5000),
        ("NVDA", 20000, 5000),
        ("GOOGL", 15000, 4000),  # Total: ~89K tokens (89% of budget)
    ]

    for symbol, input_tokens, output_tokens in decisions_data:
        tracker3.log_decision(
            symbol=symbol,
            date="2026-01-11",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens
        )

    budget = tracker3.check_budget()
    print(f"  Total tokens: {budget['total_tokens']:,}")
    print(f"  Remaining: {budget['remaining']:,}")
    print(f"  % Used: {budget['pct_used']:.1f}%")
    print(f"  Within budget: {budget['within_budget']}")
    print(f"  Warning (80%+): {budget['warning']}")

    assert budget['within_budget'] is True, "Should be within budget"
    assert budget['warning'] is True, "Should have warning at 80%+"
    assert budget['pct_used'] >= 80, "Should be at 80%+"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 5: Budget Exceeded ---
print("\n[TEST 5] Budget exceeded detection")
try:
    tracker4 = TokenTracker(daily_limit=100_000)

    # Log decisions that exceed budget
    tracker4.log_decision("AAPL", "2026-01-11", 50000, 15000, 65000)  # 65K
    tracker4.log_decision("MSFT", "2026-01-11", 40000, 10000, 50000)  # 115K total

    budget = tracker4.check_budget()
    print(f"  Total tokens: {budget['total_tokens']:,}")
    print(f"  Remaining: {budget['remaining']:,}")
    print(f"  Within budget: {budget['within_budget']}")
    print(f"  Critical (95%+): {budget['critical']}")

    assert budget['within_budget'] is False, "Should be over budget"
    assert budget['remaining'] == 0, "Remaining should be 0"
    assert budget['critical'] is True, "Should be critical at 95%+"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 6: Summary Statistics ---
print("\n[TEST 6] Summary statistics")
try:
    tracker5 = TokenTracker(daily_limit=100_000)
    tracker5.log_decision("AAPL", "2026-01-11", 10000, 2000, 12000, "BUY")
    tracker5.log_decision("MSFT", "2026-01-11", 8000, 2000, 10000, "SELL")
    tracker5.log_decision("NVDA", "2026-01-11", 12000, 3000, 15000, "BUY")

    summary = tracker5.get_summary()
    print(f"  Total decisions: {summary['total_decisions']}")
    print(f"  Total tokens: {summary['total_tokens']:,}")
    print(f"  Total cost: ${summary['total_cost_usd']:.6f}")
    print(f"  Avg tokens/decision: {summary['avg_tokens_per_decision']:.0f}")
    print(f"  Avg cost/decision: ${summary['avg_cost_per_decision']:.6f}")

    assert summary['total_decisions'] == 3, "Should have 3 decisions"
    assert summary['total_tokens'] == 37000, "Should have 37000 total tokens"
    assert summary['total_cost_usd'] > 0, "Cost should be > 0"
    assert summary['avg_tokens_per_decision'] > 0, "Avg tokens should be > 0"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- TEST 7: Cost Calculation Accuracy ---
print("\n[TEST 7] DeepSeek cost calculation accuracy")
try:
    tracker6 = TokenTracker(daily_limit=100_000)

    # Test specific token amounts
    # 1M input tokens should cost $0.27
    # 1M output tokens should cost $1.10
    tracker6.log_decision("TEST", "2026-01-11", 1_000_000, 1_000_000, 2_000_000)

    decision = tracker6.decisions[0]
    # Expected: 0.27 + 1.10 = 1.37
    expected_cost = 0.27 + 1.10
    actual_cost = decision['cost_usd']

    print(f"  1M input + 1M output cost:")
    print(f"  Expected: ${expected_cost:.2f}")
    print(f"  Actual: ${actual_cost:.2f}")

    assert abs(actual_cost - expected_cost) < 0.01, f"Cost mismatch: expected {expected_cost}, got {actual_cost}"
    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 8: Serialization ---
print("\n[TEST 8] Tracker serialization and deserialization")
try:
    tracker7 = TokenTracker(daily_limit=100_000)
    tracker7.log_decision("AAPL", "2026-01-11", 5000, 1000, 6000, "BUY")
    tracker7.log_decision("MSFT", "2026-01-11", 4000, 1000, 5000, "SELL")

    # Serialize
    state_dict = tracker7.to_dict()
    print(f"  Serialized state keys: {list(state_dict.keys())}")

    # Deserialize
    tracker8 = TokenTracker.from_dict(state_dict)
    print(f"  Restored decisions: {len(tracker8.decisions)}")
    print(f"  Restored date: {tracker8.current_date}")

    assert tracker8.daily_limit == 100_000, "Limit not restored"
    assert tracker8.current_date == "2026-01-11", "Date not restored"
    assert len(tracker8.decisions) == 2, "Decisions not restored"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL PHASE 4 TESTS PASSED ✅")
print("=" * 80)
print("\nSummary:")
print("  ✅ TokenTracker initializes correctly")
print("  ✅ Decision logging with cost tracking")
print("  ✅ Daily reset on date change")
print("  ✅ Budget status checking with warnings")
print("  ✅ Budget exceeded detection")
print("  ✅ Summary statistics accurate")
print("  ✅ DeepSeek cost calculation correct")
print("  ✅ Serialization/deserialization working")
print("\nPhase 4 (Token Usage Tracking) foundation is complete!")
print("Next: Integrate with ReasoningAgent to extract actual token usage from API responses")
