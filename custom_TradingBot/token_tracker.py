"""
token_tracker.py: Track API token usage and enforce daily budget limits.

Monitors usage from Chutes API (DeepSeek) and enforces 100K tokens/day limit
with warnings at 80% threshold. Tracks costs based on DeepSeek pricing.

Pricing (as of 2026-01-11):
  - Input tokens: $0.27 per 1M tokens
  - Output tokens: $1.10 per 1M tokens
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
from pathlib import Path


class TokenTracker:
    """
    Track token usage and enforce daily budget.

    Maintains per-decision token stats with daily aggregation.
    Includes cost calculation and budget enforcement.
    """

    # DeepSeek pricing in USD per 1M tokens
    PRICE_PER_1M_INPUT = 0.27
    PRICE_PER_1M_OUTPUT = 1.10

    def __init__(self, daily_limit: int = 100_000, log_file: Optional[str] = None):
        """
        Initialize token tracker.

        Args:
            daily_limit: Maximum tokens per day (default: 100K)
            log_file: Path to append daily summary logs (optional)
        """
        self.daily_limit = daily_limit
        self.log_file = log_file
        self.decisions: List[Dict[str, Any]] = []
        self.current_date: Optional[str] = None

    def reset_if_new_day(self, date: str) -> bool:
        """
        Reset token counter if date has changed (midnight ET).

        Args:
            date: Current date in YYYY-MM-DD format

        Returns:
            True if reset occurred, False if same day
        """
        if self.current_date != date:
            # Save previous day's summary
            if self.current_date and self.decisions:
                self._save_daily_summary()

            self.current_date = date
            self.decisions = []
            return True
        return False

    def log_decision(
        self,
        symbol: str,
        date: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        decision: Optional[str] = None
    ) -> None:
        """
        Log token usage for a trading decision.

        Args:
            symbol: Stock ticker symbol
            date: Trading date (YYYY-MM-DD)
            input_tokens: Number of prompt tokens used
            output_tokens: Number of completion tokens used
            total_tokens: Total tokens (input + output)
            decision: Trading decision made (BUY/SELL/HOLD/etc)
        """
        self.reset_if_new_day(date)

        cost_usd = self._calculate_cost(input_tokens, output_tokens)

        decision_log = {
            "symbol": symbol,
            "date": date,
            "decision": decision or "UNKNOWN",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": round(cost_usd, 6),
            "timestamp": datetime.now().isoformat(),
        }

        self.decisions.append(decision_log)

    def check_budget(self) -> Dict[str, Any]:
        """
        Check current token budget status.

        Returns:
            Dict with current usage, remaining budget, and warnings
        """
        total_tokens = sum(d["total_tokens"] for d in self.decisions)
        remaining = self.daily_limit - total_tokens
        pct_used = (total_tokens / self.daily_limit * 100) if self.daily_limit > 0 else 0

        return {
            "within_budget": remaining >= 0,
            "total_tokens": total_tokens,
            "remaining": max(0, remaining),
            "pct_used": round(pct_used, 1),
            "limit": self.daily_limit,
            "warning": pct_used >= 80,
            "critical": pct_used >= 95,
        }

    def get_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive summary of token usage.

        Returns:
            Dict with totals, averages, and financial metrics
        """
        if not self.decisions:
            return {
                "total_decisions": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_tokens_per_decision": 0,
                "date": self.current_date,
                "budget": self.check_budget(),
            }

        total_tokens = sum(d["total_tokens"] for d in self.decisions)
        total_input = sum(d["input_tokens"] for d in self.decisions)
        total_output = sum(d["output_tokens"] for d in self.decisions)
        total_cost = sum(d["cost_usd"] for d in self.decisions)

        return {
            "total_decisions": len(self.decisions),
            "total_tokens": total_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": round(total_cost, 6),
            "avg_tokens_per_decision": round(total_tokens / len(self.decisions), 0) if self.decisions else 0,
            "avg_cost_per_decision": round(total_cost / len(self.decisions), 6) if self.decisions else 0,
            "date": self.current_date,
            "budget": self.check_budget(),
        }

    def get_decision_logs(self) -> List[Dict[str, Any]]:
        """
        Get list of all logged decisions for the current day.

        Returns:
            List of decision dicts with token and cost data
        """
        return self.decisions.copy()

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost in USD based on DeepSeek pricing.

        Args:
            input_tokens: Number of prompt tokens
            output_tokens: Number of completion tokens

        Returns:
            Cost in USD (rounded to 6 decimal places)
        """
        input_cost = (input_tokens / 1_000_000) * self.PRICE_PER_1M_INPUT
        output_cost = (output_tokens / 1_000_000) * self.PRICE_PER_1M_OUTPUT
        return input_cost + output_cost

    def _save_daily_summary(self) -> None:
        """Save daily summary to log file if configured."""
        if not self.log_file or not self.current_date:
            return

        try:
            summary = self.get_summary()

            # Format summary line
            total = summary["total_tokens"]
            cost = summary["total_cost_usd"]
            decisions = summary["total_decisions"]
            pct_used = summary["budget"]["pct_used"]

            log_line = (
                f"[{self.current_date}] "
                f"{decisions} decisions | "
                f"{total:,} tokens ({pct_used:.1f}%) | "
                f"${cost:.4f}\n"
            )

            # Append to log file
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(log_line)

        except Exception:
            # Silently fail if logging fails
            pass

    def to_dict(self) -> Dict[str, Any]:
        """
        Export tracker state as dictionary.

        Useful for serialization and state persistence.

        Returns:
            Dict representation of tracker state
        """
        return {
            "daily_limit": self.daily_limit,
            "current_date": self.current_date,
            "decisions": self.decisions,
            "summary": self.get_summary(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenTracker":
        """
        Reconstruct tracker from dictionary.

        Args:
            data: Dict from to_dict()

        Returns:
            New TokenTracker instance with state restored
        """
        tracker = cls(daily_limit=data.get("daily_limit", 100_000))
        tracker.current_date = data.get("current_date")
        tracker.decisions = data.get("decisions", [])
        return tracker
