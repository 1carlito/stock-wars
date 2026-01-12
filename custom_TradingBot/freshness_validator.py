"""
freshness_validator.py: Data freshness validation and staleness detection.

Validates that market data is recent enough for trading decisions.
Implements configurable tolerance levels per data type and automatic fallback strategies.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging

_logger = logging.getLogger(__name__)


class FreshnessValidator:
    """
    Validate data freshness for trading decisions.

    Tolerance levels:
      - Price data: 3 days (critical - trading depends on current prices)
      - Fundamental data: 30 days (important - quarterly earnings)
      - News data: 7 days (optional - context only)
    """

    # Tolerance levels in days (maximum acceptable staleness)
    TOLERANCE_DAYS = {
        "price": 3,           # Critical: fresh prices needed for entry/exit
        "fundamental": 30,    # Important: quarterly data
        "news": 7,           # Optional: context and sentiment
    }

    @staticmethod
    def validate_price_data(
        data: List[Dict[str, Any]],
        expected_date: str,
        tolerance_days: int = 3
    ) -> Dict[str, Any]:
        """
        Validate that price data is fresh enough.

        Args:
            data: List of OHLCV data points
            expected_date: Expected trading date (YYYY-MM-DD)
            tolerance_days: Maximum acceptable staleness in days

        Returns:
            Dict with freshness status, latest date, and staleness info
        """
        if not data:
            return {
                "fresh": False,
                "reason": "empty_data",
                "message": "No price data available",
                "latest_date": None,
                "expected_date": expected_date,
                "days_stale": None,
            }

        try:
            # Extract latest date from data
            if isinstance(data, list) and len(data) > 0:
                latest_item = data[-1]  # Assume sorted, last is newest
                if isinstance(latest_item, dict):
                    latest_date_str = latest_item.get("date")
                elif hasattr(latest_item, "date"):
                    latest_date_str = str(latest_item.date)
                else:
                    return {
                        "fresh": False,
                        "reason": "unparseable_date",
                        "message": "Cannot extract date from data",
                        "latest_date": None,
                        "expected_date": expected_date,
                        "days_stale": None,
                    }

                if not latest_date_str:
                    return {
                        "fresh": False,
                        "reason": "no_date_field",
                        "message": "Data missing date field",
                        "latest_date": None,
                        "expected_date": expected_date,
                        "days_stale": None,
                    }

                # Parse dates
                latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
                expected_dt = datetime.strptime(expected_date, "%Y-%m-%d")

                # Calculate staleness
                days_stale = (expected_dt - latest_dt).days

                # Determine freshness
                is_fresh = days_stale <= tolerance_days

                severity = "warning"
                if days_stale == 0:
                    severity = "fresh"
                elif days_stale <= 1:
                    severity = "slightly_stale"
                elif days_stale <= tolerance_days:
                    severity = "acceptable"
                else:
                    severity = "critical"

                return {
                    "fresh": is_fresh,
                    "reason": severity,
                    "message": f"Price data is {days_stale} days old (tolerance: {tolerance_days})",
                    "latest_date": latest_date_str,
                    "expected_date": expected_date,
                    "days_stale": days_stale,
                    "tolerance_days": tolerance_days,
                    "data_points": len(data),
                }

        except (ValueError, KeyError, AttributeError) as e:
            return {
                "fresh": False,
                "reason": "parse_error",
                "message": f"Error parsing price data: {str(e)}",
                "latest_date": None,
                "expected_date": expected_date,
                "days_stale": None,
            }

    @staticmethod
    def validate_fundamental_data(
        data: List[Dict[str, Any]],
        expected_date: str,
        tolerance_days: int = 30
    ) -> Dict[str, Any]:
        """
        Validate that fundamental data is recent enough.

        Earnings reports are quarterly, so 30-day tolerance is reasonable.

        Args:
            data: List of fundamental data points (income statement, balance sheet, etc.)
            expected_date: Expected trading date (YYYY-MM-DD)
            tolerance_days: Maximum acceptable staleness in days (default: 30 for quarterly)

        Returns:
            Dict with freshness status
        """
        if not data:
            return {
                "fresh": False,
                "reason": "empty_data",
                "message": "No fundamental data available",
                "latest_date": None,
                "expected_date": expected_date,
                "days_stale": None,
                "note": "Can proceed with older fundamental data if available",
            }

        try:
            # Extract latest date
            if isinstance(data, list) and len(data) > 0:
                latest_item = data[0]  # Assume first is newest for financial statements
                if isinstance(latest_item, dict):
                    latest_date_str = latest_item.get("date") or latest_item.get("fillingDate")
                elif hasattr(latest_item, "date"):
                    latest_date_str = str(latest_item.date)
                else:
                    return {
                        "fresh": False,
                        "reason": "unparseable_date",
                        "message": "Cannot extract date",
                        "latest_date": None,
                        "expected_date": expected_date,
                        "days_stale": None,
                    }

                if not latest_date_str:
                    return {
                        "fresh": False,
                        "reason": "no_date_field",
                        "message": "Data missing date field",
                        "latest_date": None,
                        "expected_date": expected_date,
                        "days_stale": None,
                    }

                latest_dt = datetime.strptime(latest_date_str[:10], "%Y-%m-%d")
                expected_dt = datetime.strptime(expected_date, "%Y-%m-%d")
                days_stale = (expected_dt - latest_dt).days

                is_fresh = days_stale <= tolerance_days

                return {
                    "fresh": is_fresh,
                    "reason": "fresh" if is_fresh else "stale",
                    "message": f"Fundamental data from {days_stale} days ago",
                    "latest_date": latest_date_str[:10],
                    "expected_date": expected_date,
                    "days_stale": days_stale,
                    "tolerance_days": tolerance_days,
                    "fallback": "Use latest available data if stale",
                }

        except (ValueError, KeyError, AttributeError, IndexError) as e:
            return {
                "fresh": False,
                "reason": "parse_error",
                "message": f"Error parsing fundamental data: {str(e)}",
                "latest_date": None,
                "expected_date": expected_date,
                "days_stale": None,
            }

    @staticmethod
    def validate_news_data(
        data: List[Dict[str, Any]],
        expected_date: str,
        tolerance_days: int = 7
    ) -> Dict[str, Any]:
        """
        Validate that news data is recent enough.

        News is optional context - older news is acceptable.

        Args:
            data: List of news articles
            expected_date: Expected trading date (YYYY-MM-DD)
            tolerance_days: Maximum acceptable staleness in days (default: 7)

        Returns:
            Dict with freshness status
        """
        if not data:
            return {
                "fresh": False,
                "reason": "no_data",
                "message": "No news data available",
                "latest_date": None,
                "expected_date": expected_date,
                "days_stale": None,
                "fallback": "Proceed without news - not critical",
            }

        try:
            if isinstance(data, list) and len(data) > 0:
                latest_item = data[0]  # First item is usually newest
                if isinstance(latest_item, dict):
                    latest_date_str = latest_item.get("publishedDate") or latest_item.get("date")
                else:
                    latest_date_str = str(getattr(latest_item, "publishedDate", None))

                if not latest_date_str:
                    return {
                        "fresh": False,
                        "reason": "no_date_field",
                        "message": "News missing date field",
                        "latest_date": None,
                        "expected_date": expected_date,
                        "days_stale": None,
                    }

                latest_dt = datetime.strptime(latest_date_str[:10], "%Y-%m-%d")
                expected_dt = datetime.strptime(expected_date, "%Y-%m-%d")
                days_stale = (expected_dt - latest_dt).days

                is_fresh = days_stale <= tolerance_days

                return {
                    "fresh": is_fresh,
                    "reason": "fresh" if is_fresh else "stale",
                    "message": f"Latest news from {days_stale} days ago",
                    "latest_date": latest_date_str[:10],
                    "expected_date": expected_date,
                    "days_stale": days_stale,
                    "tolerance_days": tolerance_days,
                    "fallback": "Proceed with older news if needed",
                    "article_count": len(data),
                }

        except (ValueError, KeyError, AttributeError, IndexError) as e:
            return {
                "fresh": False,
                "reason": "parse_error",
                "message": f"Error parsing news data: {str(e)}",
                "latest_date": None,
                "expected_date": expected_date,
                "days_stale": None,
            }

    @staticmethod
    def check_all_data_types(
        price_data: Optional[List[Dict[str, Any]]],
        fundamental_data: Optional[List[Dict[str, Any]]],
        news_data: Optional[List[Dict[str, Any]]],
        trade_date: str
    ) -> Dict[str, Any]:
        """
        Validate all data types and determine if stock is tradeable.

        Trading decision:
          - If price data is stale → SKIP (critical blocker)
          - If fundamental data is stale → USE (can proceed with old earnings)
          - If news is stale → PROCEED (not critical)

        Args:
            price_data: OHLCV price data
            fundamental_data: Income statement, balance sheet, etc.
            news_data: Company news articles
            trade_date: Trading date (YYYY-MM-DD)

        Returns:
            Dict with freshness status and trade decision
        """
        results = {
            "trade_date": trade_date,
            "can_trade": True,
            "skip_reason": None,
            "data_status": {},
            "summary": "",
        }

        # Check price data (critical)
        price_freshness = FreshnessValidator.validate_price_data(price_data, trade_date)
        results["data_status"]["price"] = price_freshness

        if not price_freshness["fresh"]:
            results["can_trade"] = False
            results["skip_reason"] = f"Stale price data: {price_freshness['reason']}"
            _logger.warning(f"⚠️  {results['skip_reason']}")

        # Check fundamental data (important but not critical)
        if fundamental_data:
            fundamental_freshness = FreshnessValidator.validate_fundamental_data(
                fundamental_data, trade_date
            )
            results["data_status"]["fundamental"] = fundamental_freshness

            if not fundamental_freshness["fresh"]:
                _logger.info(f"ℹ️  Fundamental data stale: {fundamental_freshness['reason']} "
                           f"({fundamental_freshness['days_stale']} days)")

        # Check news data (optional)
        if news_data:
            news_freshness = FreshnessValidator.validate_news_data(news_data, trade_date)
            results["data_status"]["news"] = news_freshness

            if not news_freshness["fresh"]:
                _logger.debug(f"ℹ️  News data stale: {news_freshness['reason']}")

        # Generate summary
        if results["can_trade"]:
            results["summary"] = "✅ All critical data fresh - PROCEED WITH TRADE"
        else:
            results["summary"] = f"❌ SKIP STOCK: {results['skip_reason']}"

        return results


class DataFreshnessContext:
    """
    Context manager for tracking data freshness across a trading session.

    Accumulates freshness checks and provides summary statistics.
    """

    def __init__(self, trade_date: str):
        """Initialize freshness context for a trading session."""
        self.trade_date = trade_date
        self.checks: Dict[str, Dict[str, Any]] = {}
        self.skipped_stocks: List[str] = []
        self.tradeable_stocks: List[str] = []

    def record_check(self, symbol: str, freshness_result: Dict[str, Any]) -> None:
        """
        Record a freshness check result.

        Args:
            symbol: Stock ticker symbol
            freshness_result: Result from check_all_data_types()
        """
        self.checks[symbol] = freshness_result

        if freshness_result["can_trade"]:
            self.tradeable_stocks.append(symbol)
        else:
            self.skipped_stocks.append(symbol)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all freshness checks."""
        total_checked = len(self.checks)
        total_tradeable = len(self.tradeable_stocks)
        total_skipped = len(self.skipped_stocks)

        skip_reasons = {}
        for symbol, result in self.checks.items():
            if not result["can_trade"] and result["skip_reason"]:
                reason = result["skip_reason"]
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

        return {
            "trade_date": self.trade_date,
            "total_checked": total_checked,
            "tradeable": total_tradeable,
            "skipped": total_skipped,
            "skip_percentage": round(total_skipped / total_checked * 100, 1) if total_checked > 0 else 0,
            "skipped_stocks": self.skipped_stocks,
            "skip_reasons": skip_reasons,
            "checks": self.checks,
        }

    def log_summary(self) -> None:
        """Log freshness check summary."""
        summary = self.get_summary()

        _logger.info(
            f"📊 Data Freshness Summary for {self.trade_date}: "
            f"{summary['tradeable']}/{summary['total_checked']} stocks tradeable"
        )

        if self.skipped_stocks:
            _logger.warning(
                f"⚠️  {summary['skipped']} stocks skipped due to stale data: "
                f"{', '.join(self.skipped_stocks)}"
            )

            for reason, count in summary["skip_reasons"].items():
                _logger.warning(f"  - {reason}: {count} stock(s)")
