"""
Test script for Phase 6: Data Freshness Validation

Tests:
  1. Price data freshness validation
  2. Fundamental data freshness validation
  3. News data freshness validation
  4. Combined data type checking
  5. Stale data detection and skip logic
  6. DataFreshnessContext tracking
  7. Summary statistics
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
custom_trading_bot_dir = os.path.join(base_dir, "custom_TradingBot")
sys.path.insert(0, custom_trading_bot_dir)
sys.path.insert(0, base_dir)

from freshness_validator import FreshnessValidator, DataFreshnessContext

print("=" * 80)
print("PHASE 6 TEST: Data Freshness Validation")
print("=" * 80)

# --- TEST 1: Fresh Price Data ---
print("\n[TEST 1] Fresh price data validation")
try:
    fresh_price_data = [
        {"date": "2026-01-08", "close": 150.0, "volume": 100000},
        {"date": "2026-01-09", "close": 151.0, "volume": 110000},
        {"date": "2026-01-10", "close": 152.0, "volume": 120000},
    ]

    result = FreshnessValidator.validate_price_data(
        fresh_price_data,
        expected_date="2026-01-10"
    )

    print(f"  Latest date: {result['latest_date']}")
    print(f"  Expected date: {result['expected_date']}")
    print(f"  Days stale: {result['days_stale']}")
    print(f"  Fresh: {result['fresh']}")
    print(f"  Reason: {result['reason']}")

    assert result["fresh"], "Should be fresh"
    assert result["days_stale"] == 0, "Should be 0 days stale"
    assert result["reason"] == "fresh", "Should indicate fresh"
    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 2: Slightly Stale Price Data ---
print("\n[TEST 2] Slightly stale price data (1-3 days)")
try:
    slightly_stale_data = [
        {"date": "2026-01-07", "close": 150.0, "volume": 100000},
        {"date": "2026-01-08", "close": 151.0, "volume": 110000},
    ]

    result = FreshnessValidator.validate_price_data(
        slightly_stale_data,
        expected_date="2026-01-10"
    )

    print(f"  Latest date: {result['latest_date']}")
    print(f"  Days stale: {result['days_stale']}")
    print(f"  Fresh: {result['fresh']}")
    print(f"  Reason: {result['reason']}")

    assert result["fresh"], "Should still be acceptable (within 3-day tolerance)"
    assert result["days_stale"] == 2, "Should be 2 days stale"
    assert result["reason"] in ["slightly_stale", "acceptable"], "Should indicate staleness"
    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 3: Very Stale Price Data ---
print("\n[TEST 3] Very stale price data (>3 days)")
try:
    very_stale_data = [
        {"date": "2026-01-01", "close": 148.0, "volume": 90000},
        {"date": "2026-01-05", "close": 149.0, "volume": 95000},
    ]

    result = FreshnessValidator.validate_price_data(
        very_stale_data,
        expected_date="2026-01-10"
    )

    print(f"  Latest date: {result['latest_date']}")
    print(f"  Days stale: {result['days_stale']}")
    print(f"  Fresh: {result['fresh']}")
    print(f"  Reason: {result['reason']}")

    assert not result["fresh"], "Should NOT be fresh"
    assert result["days_stale"] == 5, "Should be 5 days stale"
    assert result["reason"] == "critical", "Should indicate critical staleness"
    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 4: Empty Price Data ---
print("\n[TEST 4] Empty price data handling")
try:
    result = FreshnessValidator.validate_price_data(
        [],
        expected_date="2026-01-10"
    )

    print(f"  Fresh: {result['fresh']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Message: {result['message']}")

    assert not result["fresh"], "Should NOT be fresh"
    assert result["reason"] == "empty_data", "Should indicate empty data"
    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 5: Fundamental Data Validation ---
print("\n[TEST 5] Fundamental data validation (quarterly earnings)")
try:
    fundamental_data = [
        {"date": "2025-10-15", "revenue": 100000000, "earnings": 25000000},
    ]

    # Check fresh (within 30 days)
    result_fresh = FreshnessValidator.validate_fundamental_data(
        fundamental_data,
        expected_date="2025-11-10"
    )

    print(f"  Recent fundamentals (within 30 days):")
    print(f"    Latest date: {result_fresh['latest_date']}")
    print(f"    Days stale: {result_fresh['days_stale']}")
    print(f"    Fresh: {result_fresh['fresh']}")

    assert result_fresh["fresh"], "Should be fresh"

    # Check stale (>30 days)
    result_stale = FreshnessValidator.validate_fundamental_data(
        fundamental_data,
        expected_date="2026-01-10"  # Much later
    )

    print(f"  Old fundamentals (>30 days):")
    print(f"    Days stale: {result_stale['days_stale']}")
    print(f"    Fresh: {result_stale['fresh']}")

    assert not result_stale["fresh"], "Should be stale"
    assert result_stale["days_stale"] > 30, "Should be >30 days old"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 6: News Data Validation ---
print("\n[TEST 6] News data validation (optional, 7-day tolerance)")
try:
    news_data = [
        {"publishedDate": "2026-01-08", "headline": "Stock up on earnings"},
        {"publishedDate": "2026-01-07", "headline": "Analyst upgrade"},
    ]

    # Fresh news
    result_fresh = FreshnessValidator.validate_news_data(
        news_data,
        expected_date="2026-01-10"
    )

    print(f"  Recent news (2 days old):")
    print(f"    Days stale: {result_fresh['days_stale']}")
    print(f"    Fresh: {result_fresh['fresh']}")

    assert result_fresh["fresh"], "Should be fresh"
    assert result_fresh["days_stale"] == 2, "Should be 2 days old"

    # Stale news
    old_news = [
        {"publishedDate": "2026-01-01", "headline": "Old news"},
    ]

    result_stale = FreshnessValidator.validate_news_data(
        old_news,
        expected_date="2026-01-10"
    )

    print(f"  Old news (9 days old):")
    print(f"    Days stale: {result_stale['days_stale']}")
    print(f"    Fresh: {result_stale['fresh']}")

    assert not result_stale["fresh"], "Should be stale"
    assert result_stale["article_count"] == 1, "Should have 1 article"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 7: Combined Data Type Checking ---
print("\n[TEST 7] Combined data type checking (trade decision)")
try:
    trade_date = "2026-01-10"

    # Case 1: All fresh data → CAN TRADE
    fresh_price = [{"date": "2026-01-10", "close": 152.0}]
    fresh_fundamental = [{"date": "2025-12-15", "revenue": 100000000}]
    fresh_news = [{"publishedDate": "2026-01-09", "headline": "News"}]

    result_all_fresh = FreshnessValidator.check_all_data_types(
        fresh_price, fresh_fundamental, fresh_news, trade_date
    )

    print(f"  Case 1: All fresh data")
    print(f"    Can trade: {result_all_fresh['can_trade']}")
    print(f"    Summary: {result_all_fresh['summary']}")

    assert result_all_fresh["can_trade"], "Should allow trading"

    # Case 2: Stale price data → SKIP
    stale_price = [{"date": "2026-01-05", "close": 150.0}]

    result_stale_price = FreshnessValidator.check_all_data_types(
        stale_price, fresh_fundamental, fresh_news, trade_date
    )

    print(f"  Case 2: Stale price data")
    print(f"    Can trade: {result_stale_price['can_trade']}")
    print(f"    Skip reason: {result_stale_price['skip_reason']}")

    assert not result_stale_price["can_trade"], "Should skip due to stale price"

    # Case 3: Stale fundamentals but fresh price → CAN TRADE
    stale_fundamental = [{"date": "2025-11-01", "revenue": 100000000}]

    result_stale_fundamental = FreshnessValidator.check_all_data_types(
        fresh_price, stale_fundamental, fresh_news, trade_date
    )

    print(f"  Case 3: Stale fundamentals, fresh price")
    print(f"    Can trade: {result_stale_fundamental['can_trade']}")

    # Should still be able to trade (fundamental is not critical)
    assert result_stale_fundamental["can_trade"], "Should allow trading with stale fundamentals"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- TEST 8: DataFreshnessContext Tracking ---
print("\n[TEST 8] DataFreshnessContext tracking and summary")
try:
    trade_date = "2026-01-10"
    context = DataFreshnessContext(trade_date)

    # Simulate checking 5 stocks
    stocks_to_check = [
        ("AAPL", True, None),        # Tradeable
        ("MSFT", True, None),        # Tradeable
        ("NVDA", False, "Stale price data"),  # Skip
        ("GOOGL", False, "Stale price data"), # Skip
        ("AMZN", True, None),        # Tradeable
    ]

    for symbol, can_trade, skip_reason in stocks_to_check:
        result = {
            "can_trade": can_trade,
            "skip_reason": skip_reason,
            "data_status": {},
            "summary": "✅" if can_trade else "❌",
        }
        context.record_check(symbol, result)

    summary = context.get_summary()

    print(f"  Total checked: {summary['total_checked']}")
    print(f"  Tradeable: {summary['tradeable']}")
    print(f"  Skipped: {summary['skipped']}")
    print(f"  Skip percentage: {summary['skip_percentage']}%")
    print(f"  Skipped stocks: {summary['skipped_stocks']}")

    assert summary["total_checked"] == 5, "Should have 5 checks"
    assert summary["tradeable"] == 3, "Should have 3 tradeable"
    assert summary["skipped"] == 2, "Should have 2 skipped"
    assert summary["skip_percentage"] == 40.0, "Should be 40% skipped"
    assert "NVDA" in summary["skipped_stocks"], "NVDA should be skipped"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 9: Tolerance Configuration ---
print("\n[TEST 9] Configurable tolerance levels")
try:
    # Test with custom tolerance
    three_day_stale = [
        {"date": "2026-01-07", "close": 150.0},  # 3 days old on 2026-01-10
    ]

    # With default 3-day tolerance → FRESH
    result_default = FreshnessValidator.validate_price_data(
        three_day_stale,
        expected_date="2026-01-10",
        tolerance_days=3
    )

    print(f"  With 3-day tolerance: Fresh={result_default['fresh']}")
    assert result_default["fresh"], "Should be fresh with 3-day tolerance"

    # With stricter 2-day tolerance → STALE
    result_strict = FreshnessValidator.validate_price_data(
        three_day_stale,
        expected_date="2026-01-10",
        tolerance_days=2
    )

    print(f"  With 2-day tolerance: Fresh={result_strict['fresh']}")
    assert not result_strict["fresh"], "Should be stale with 2-day tolerance"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 10: Error Handling ---
print("\n[TEST 10] Malformed data handling")
try:
    # Missing date field
    bad_data = [{"close": 150.0}]  # No date!

    result_no_date = FreshnessValidator.validate_price_data(
        bad_data,
        expected_date="2026-01-10"
    )

    print(f"  Missing date field:")
    print(f"    Fresh: {result_no_date['fresh']}")
    print(f"    Reason: {result_no_date['reason']}")

    assert not result_no_date["fresh"], "Should detect missing date"

    # Invalid date format
    bad_format = [{"date": "01-10-2026"}]  # Wrong format

    result_bad_format = FreshnessValidator.validate_price_data(
        bad_format,
        expected_date="2026-01-10"
    )

    print(f"  Invalid date format:")
    print(f"    Fresh: {result_bad_format['fresh']}")
    print(f"    Reason: {result_bad_format['reason']}")

    assert not result_bad_format["fresh"], "Should detect invalid format"

    print("  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL PHASE 6 TESTS PASSED ✅")
print("=" * 80)
print("\nSummary:")
print("  ✅ Fresh price data detection working")
print("  ✅ Stale price data detection working (>3 day tolerance)")
print("  ✅ Fundamental data validation (30-day tolerance)")
print("  ✅ News data validation (7-day tolerance)")
print("  ✅ Combined data type checking")
print("  ✅ Stale price data blocks trading (SKIP)")
print("  ✅ Stale fundamental data allows trading (CONTINUE)")
print("  ✅ DataFreshnessContext tracking with summary stats")
print("  ✅ Configurable tolerance levels")
print("  ✅ Error handling for malformed data")
print("\nPhase 6 (Data Freshness Validator) is complete and verified!")
