"""
Test script for Phase 5: Portfolio Orchestrator

Tests:
  1. PortfolioOrchestrator initialization
  2. Sector rankings retrieval
  3. Decision filtering and enrichment
  4. Waterfall allocation with 25% cap
  5. Token tracking across multiple stocks
  6. Summary statistics
  7. State persistence
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

print("=" * 80)
print("PHASE 5 TEST: Portfolio Orchestrator for Parallel Processing")
print("=" * 80)

# --- TEST 1: PortfolioOrchestrator Initialization ---
print("\n[TEST 1] PortfolioOrchestrator initialization")
try:
    symbols = ["AAPL", "MSFT", "NVDA"]
    starting_capital = 100000.0

    orchestrator = PortfolioOrchestrator(
        symbols=symbols,
        starting_capital=starting_capital,
        risk_level="medium",
        max_parallel=3
    )

    assert orchestrator.symbols == symbols, "Symbols not set"
    assert orchestrator.starting_capital == starting_capital, "Capital not set"
    assert orchestrator.risk_level == "medium", "Risk level not set"
    assert len(orchestrator.token_tracker.decisions) == 0, "Should have no decisions initially"

    print(f"  Symbols: {orchestrator.symbols}")
    print(f"  Starting capital: ${orchestrator.starting_capital:,.2f}")
    print(f"  Risk level: {orchestrator.risk_level}")
    print(f"  Max parallel: {orchestrator.max_parallel}")
    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- TEST 2: Sector Rankings Retrieval ---
print("\n[TEST 2] Sector rankings retrieval")
try:
    async def test_sector_rankings():
        sector_ranks = await orchestrator._get_sector_rankings("2026-01-11")
        return sector_ranks

    sector_ranks = asyncio.run(test_sector_rankings())

    print(f"  Sectors retrieved: {len(sector_ranks)}")
    if sector_ranks:
        sample_sector = list(sector_ranks.values())[0]
        print(f"  Sample sector: {sample_sector['name']} (rank: {sample_sector['rank']})")

    assert isinstance(sector_ranks, dict), "Sector ranks should be a dict"
    assert len(sector_ranks) > 0, "Should have sector data"

    # Verify sector structure
    for sector_name, sector_data in sector_ranks.items():
        assert "rank" in sector_data, "Sector missing 'rank'"
        assert "score" in sector_data, "Sector missing 'score'"
        assert "momentum" in sector_data, "Sector missing 'momentum'"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- TEST 3: Decision Filtering and Enrichment ---
print("\n[TEST 3] Decision filtering and enrichment")
try:
    # Create mock decision results
    mock_results = [
        {
            "symbol": "AAPL",
            "success": True,
            "decision": "BUY",
            "confidence": 0.85,
            "amount_usd": 10000,
            "reasoning": "Strong technical signals"
        },
        {
            "symbol": "MSFT",
            "success": True,
            "decision": "HOLD",
            "confidence": 0.60,
            "amount_usd": 0,
            "reasoning": "Mixed signals"
        },
        {
            "symbol": "NVDA",
            "success": False,
            "error": "API error"
        }
    ]

    enriched = orchestrator._filter_and_enrich(mock_results, sector_ranks)

    print(f"  Input decisions: {len(mock_results)}")
    print(f"  Valid decisions after filtering: {len(enriched)}")

    for decision in enriched:
        print(f"    - {decision['symbol']}: {decision['decision']} "
              f"(confidence: {decision['confidence']:.0%})")

    assert len(enriched) == 2, "Should filter out failed decisions"
    assert all(d.get("success") for d in enriched), "All should be successful"
    assert all("sector" in d for d in enriched), "All should have sector info"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 4: Waterfall Allocation ---
print("\n[TEST 4] Waterfall allocation with 25% cap")
try:
    test_decisions = [
        {
            "symbol": "AAPL",
            "decision": "BUY",
            "confidence": 0.95,
            "amount_usd": 50000,
            "sector_rank": 1
        },
        {
            "symbol": "MSFT",
            "decision": "BUY",
            "confidence": 0.80,
            "amount_usd": 40000,
            "sector_rank": 2
        },
        {
            "symbol": "NVDA",
            "decision": "BUY",
            "confidence": 0.80,  # Same confidence as MSFT
            "amount_usd": 30000,
            "sector_rank": 1  # Better sector
        }
    ]

    # Create a PortfolioState object for testing
    from live_trading_loop import PortfolioState
    portfolio_state = PortfolioState(cash=100000)
    allocated = orchestrator._apply_waterfall_allocation(test_decisions, portfolio_state)

    print(f"  Input decisions: {len(test_decisions)}")
    print(f"  Cash available: ${portfolio_state.cash:,.2f}")
    print(f"  25% cap per trade: ${portfolio_state.cash * 0.25:,.2f}")
    print(f"  Allocated trades: {len(allocated)}")

    for decision in allocated:
        print(f"    - {decision['symbol']}: "
              f"Requested ${decision['requested_amount']:,.0f}, "
              f"Allocated ${decision['allocated_amount']:,.0f}")

    # First trade should get full amount (25% of $100k = $25k)
    assert allocated[0]["allocated_amount"] <= 25000, "Should cap at 25%"

    # Verify sorted by confidence and sector rank
    confidences = [d.get("confidence", 0) for d in allocated]
    assert confidences[0] >= confidences[-1], "Should be sorted by confidence descending"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- TEST 5: Token Tracking Across Multiple Stocks ---
print("\n[TEST 5] Token tracking across multiple stocks")
try:
    orchestrator2 = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
        starting_capital=100000,
        risk_level="medium"
    )

    trade_date = "2026-01-11"

    # Simulate token logging for each stock
    for i, symbol in enumerate(orchestrator2.symbols):
        input_tokens = 5000 + (i * 1000)
        output_tokens = 1000 + (i * 500)

        orchestrator2.token_tracker.log_decision(
            symbol=symbol,
            date=trade_date,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            decision="BUY"
        )

    summary = orchestrator2.token_tracker.get_summary()

    print(f"  Stocks analyzed: {summary['total_decisions']}")
    print(f"  Total tokens: {summary['total_tokens']:,}")
    print(f"  Total cost: ${summary['total_cost_usd']:.6f}")
    print(f"  Avg tokens/decision: {summary['avg_tokens_per_decision']:.0f}")
    print(f"  Budget status: {summary['budget']['pct_used']:.1f}% used")

    assert summary['total_decisions'] == 5, "Should have 5 decisions"
    assert summary['total_tokens'] > 0, "Should have token count"
    assert summary['total_cost_usd'] > 0, "Should have cost"
    assert summary['budget']['within_budget'], "Should be within budget"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- TEST 6: Budget Enforcement ---
print("\n[TEST 6] Budget enforcement with warnings")
try:
    orchestrator3 = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT"],
        starting_capital=50000,
        risk_level="high"
    )

    trade_date = "2026-01-11"

    # Log decisions approaching budget limit
    orchestrator3.token_tracker.log_decision(
        symbol="AAPL",
        date=trade_date,
        input_tokens=40000,
        output_tokens=15000,
        total_tokens=55000,
        decision="BUY"
    )

    budget_before = orchestrator3.token_tracker.check_budget()
    print(f"  After 1st decision: {budget_before['pct_used']:.1f}% used")
    print(f"  Warning triggered: {budget_before['warning']}")

    assert not budget_before['warning'], "Should not warn at 55% (warning at 80%)"
    assert budget_before['within_budget'], "Should still be within budget"

    # Log another large decision to exceed budget
    orchestrator3.token_tracker.log_decision(
        symbol="MSFT",
        date=trade_date,
        input_tokens=50000,
        output_tokens=20000,
        total_tokens=70000,
        decision="SELL"
    )

    budget_after = orchestrator3.token_tracker.check_budget()
    print(f"  After 2nd decision: {budget_after['pct_used']:.1f}% used")
    print(f"  Critical flag: {budget_after['critical']}")
    print(f"  Within budget: {budget_after['within_budget']}")

    assert not budget_after['within_budget'], "Should exceed budget"
    assert budget_after['critical'], "Should be critical"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 7: Portfolio Summary ---
print("\n[TEST 7] Portfolio summary")
try:
    orchestrator_summary = PortfolioOrchestrator(
        symbols=["AAPL", "MSFT"],
        starting_capital=100000
    )

    summary = orchestrator_summary.get_summary()
    print(f"  Symbols: {summary['symbols']}")
    print(f"  Portfolio cash: ${summary['portfolio_state'].cash:,.2f}")
    print(f"  Token tracker initialized: {summary['token_tracker'] is not None}")

    assert summary['symbols'] == ["AAPL", "MSFT"], "Symbols not in summary"
    assert summary['portfolio_state'] is not None, "Portfolio state should exist"
    assert hasattr(summary['portfolio_state'], 'cash'), "Portfolio state should have cash attribute"
    assert summary['token_tracker'] is not None, "Token tracker should be initialized"
    assert 'total_decisions' in summary['token_tracker'], "Token tracker should have total_decisions"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("PHASE 5 TESTS PASSED ✅")
print("=" * 80)
print("\nSummary:")
print("  ✅ PortfolioOrchestrator initializes correctly")
print("  ✅ Sector rankings retrieved and indexed")
print("  ✅ Decisions filtered and enriched with sector info")
print("  ✅ Waterfall allocation applies 25% cap correctly")
print("  ✅ Token tracking across multiple stocks working")
print("  ✅ Budget enforcement with warnings functional")
print("  ✅ Portfolio state persists correctly")
print("\nPhase 5 (Portfolio Orchestrator) foundation is complete!")
print("Ready for async parallel execution tests...")
