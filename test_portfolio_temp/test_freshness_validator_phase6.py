"""
Unit tests for Phase 6: Data Freshness Validation.

Verifies:
  1. Price data freshness classification (fresh, slightly stale, very stale).
  2. Handling of empty and malformed price data.
  3. Fundamental and news data freshness rules.
  4. Combined data-type freshness decisions via `check_all_data_types`.
  5. `DataFreshnessContext` tracking and summary statistics.
  6. Configurable tolerance levels.
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


def test_fresh_price_data():
    """Fresh price data should be marked fresh with 0 days stale."""
    fresh_price_data = [
        {"date": "2026-01-08", "close": 150.0, "volume": 100000},
        {"date": "2026-01-09", "close": 151.0, "volume": 110000},
        {"date": "2026-01-10", "close": 152.0, "volume": 120000},
    ]

    result = FreshnessValidator.validate_price_data(
        fresh_price_data,
        expected_date="2026-01-10",
    )

    assert result["fresh"] is True
    assert result["days_stale"] == 0
    assert result["reason"] == "fresh"


def test_slightly_stale_price_data():
    """Price data within tolerance (<=3 days) is still acceptable."""
    slightly_stale_data = [
        {"date": "2026-01-07", "close": 150.0, "volume": 100000},
        {"date": "2026-01-08", "close": 151.0, "volume": 110000},
    ]

    result = FreshnessValidator.validate_price_data(
        slightly_stale_data,
        expected_date="2026-01-10",
    )

    assert result["fresh"] is True
    assert result["days_stale"] == 2
    assert result["reason"] in ["slightly_stale", "acceptable"]


def test_very_stale_price_data():
    """Price data beyond tolerance (>3 days) should be critical/stale."""
    very_stale_data = [
        {"date": "2026-01-01", "close": 148.0, "volume": 90000},
        {"date": "2026-01-05", "close": 149.0, "volume": 95000},
    ]

    result = FreshnessValidator.validate_price_data(
        very_stale_data,
        expected_date="2026-01-10",
    )

    assert result["fresh"] is False
    assert result["days_stale"] == 5
    assert result["reason"] == "critical"


def test_empty_price_data():
    """Empty price series should be treated as not fresh with explicit reason."""
    result = FreshnessValidator.validate_price_data(
        [],
        expected_date="2026-01-10",
    )

    assert result["fresh"] is False
    assert result["reason"] == "empty_data"


def test_fundamental_data_validation():
    """Fundamental data is fresh within 30 days and stale beyond that."""
    fundamental_data = [
        {"date": "2025-10-15", "revenue": 100000000, "earnings": 25000000},
    ]

    # Fresh (within 30 days)
    result_fresh = FreshnessValidator.validate_fundamental_data(
        fundamental_data,
        expected_date="2025-11-10",
    )
    assert result_fresh["fresh"] is True

    # Stale (>30 days)
    result_stale = FreshnessValidator.validate_fundamental_data(
        fundamental_data,
        expected_date="2026-01-10",
    )
    assert result_stale["fresh"] is False
    assert result_stale["days_stale"] > 30


def test_news_data_validation():
    """News data uses a 7-day tolerance and reports article counts."""
    news_data = [
        {"publishedDate": "2026-01-08", "headline": "Stock up on earnings"},
        {"publishedDate": "2026-01-07", "headline": "Analyst upgrade"},
    ]

    result_fresh = FreshnessValidator.validate_news_data(
        news_data,
        expected_date="2026-01-10",
    )
    assert result_fresh["fresh"] is True
    assert result_fresh["days_stale"] == 2

    old_news = [
        {"publishedDate": "2026-01-01", "headline": "Old news"},
    ]
    result_stale = FreshnessValidator.validate_news_data(
        old_news,
        expected_date="2026-01-10",
    )
    assert result_stale["fresh"] is False
    assert result_stale["article_count"] == 1


def test_combined_data_type_checking():
    """Combined freshness checks gate trading based on price freshness."""
    trade_date = "2026-01-10"

    fresh_price = [{"date": "2026-01-10", "close": 152.0}]
    fresh_fundamental = [{"date": "2025-12-15", "revenue": 100000000}]
    fresh_news = [{"publishedDate": "2026-01-09", "headline": "News"}]

    result_all_fresh = FreshnessValidator.check_all_data_types(
        fresh_price, fresh_fundamental, fresh_news, trade_date
    )
    assert result_all_fresh["can_trade"] is True

    stale_price = [{"date": "2026-01-05", "close": 150.0}]
    result_stale_price = FreshnessValidator.check_all_data_types(
        stale_price, fresh_fundamental, fresh_news, trade_date
    )
    assert result_stale_price["can_trade"] is False

    stale_fundamental = [{"date": "2025-11-01", "revenue": 100000000}]
    result_stale_fundamental = FreshnessValidator.check_all_data_types(
        fresh_price, stale_fundamental, fresh_news, trade_date
    )
    # Stale fundamentals alone do not block trading
    assert result_stale_fundamental["can_trade"] is True


def test_data_freshness_context_summary():
    """DataFreshnessContext aggregates tradeable vs skipped symbols correctly."""
    trade_date = "2026-01-10"
    context = DataFreshnessContext(trade_date)

    stocks_to_check = [
        ("AAPL", True, None),
        ("MSFT", True, None),
        ("NVDA", False, "Stale price data"),
        ("GOOGL", False, "Stale price data"),
        ("AMZN", True, None),
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
    assert summary["total_checked"] == 5
    assert summary["tradeable"] == 3
    assert summary["skipped"] == 2
    assert summary["skip_percentage"] == 40.0
    assert "NVDA" in summary["skipped_stocks"]


def test_tolerance_configuration():
    """Custom tolerance_days changes freshness classification."""
    three_day_stale = [
        {"date": "2026-01-07", "close": 150.0},  # 3 days old on 2026-01-10
    ]

    # With default 3-day tolerance → FRESH
    result_default = FreshnessValidator.validate_price_data(
        three_day_stale,
        expected_date="2026-01-10",
        tolerance_days=3,
    )
    assert result_default["fresh"] is True

    # With stricter 2-day tolerance → STALE
    result_strict = FreshnessValidator.validate_price_data(
        three_day_stale,
        expected_date="2026-01-10",
        tolerance_days=2,
    )
    assert result_strict["fresh"] is False


def test_malformed_price_data():
    """Malformed price rows (missing or bad date) are treated as not fresh."""
    bad_data = [{"close": 150.0}]  # No date!
    result_no_date = FreshnessValidator.validate_price_data(
        bad_data,
        expected_date="2026-01-10",
    )
    assert result_no_date["fresh"] is False

    bad_format = [{"date": "01-10-2026"}]  # Wrong format
    result_bad_format = FreshnessValidator.validate_price_data(
        bad_format,
        expected_date="2026-01-10",
    )
    assert result_bad_format["fresh"] is False


