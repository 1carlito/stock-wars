"""
Technical Indicator Store

Persists daily technical indicators so they can be reused for next day's premarket analysis.
Stores: RSI, EMA, ADX, CCI values for each symbol/date.
"""

import os
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path


class TechnicalIndicatorStore:
    """Persist and retrieve daily technical indicator values."""

    def __init__(self, store_dir: Optional[str] = None):
        """
        Initialize the store.

        Args:
            store_dir: Directory to store indicator JSON files.
                      Defaults to ~/.cache/stock_agent/indicators/
        """
        if store_dir is None:
            store_dir = os.path.expanduser("~/.cache/stock_agent/indicators")

        self.store_dir = store_dir
        Path(self.store_dir).mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, symbol: str, date_str: str) -> str:
        """Get file path for symbol's daily indicators."""
        # Format: indicators/AAPL/2026-01-20.json
        symbol_dir = os.path.join(self.store_dir, symbol.upper())
        Path(symbol_dir).mkdir(parents=True, exist_ok=True)
        return os.path.join(symbol_dir, f"{date_str}.json")

    def save_daily_indicators(self, symbol: str, date_str: str, indicators: Dict[str, Any]) -> bool:
        """
        Save daily technical indicators for a symbol/date.

        Args:
            symbol: Stock ticker symbol
            date_str: Date string (YYYY-MM-DD)
            indicators: Dict with RSI, EMA, ADX, CCI, close price, etc.

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            file_path = self._get_file_path(symbol, date_str)

            # Add metadata
            data = {
                "symbol": symbol.upper(),
                "date": date_str,
                "saved_at": datetime.now().isoformat(),
                "indicators": indicators,
            }

            with open(file_path, "w") as f:
                json.dump(data, f, indent=2, default=str)

            return True
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Failed to save indicators for {symbol}/{date_str}: {e}")
            return False

    def load_daily_indicators(
        self, symbol: str, date_str: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load daily technical indicators for a symbol/date.

        Args:
            symbol: Stock ticker symbol
            date_str: Date string (YYYY-MM-DD)

        Returns:
            Dict with indicators, or None if not found/error
        """
        try:
            file_path = self._get_file_path(symbol, date_str)

            if not os.path.exists(file_path):
                return None

            with open(file_path, "r") as f:
                data = json.load(f)

            return data.get("indicators")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Failed to load indicators for {symbol}/{date_str}: {e}")
            return None

    def load_yesterday_indicators(self, symbol: str, today: str) -> Optional[Dict[str, Any]]:
        """
        Load yesterday's indicators for premarket analysis.

        Args:
            symbol: Stock ticker symbol
            today: Today's date string (YYYY-MM-DD)

        Returns:
            Dict with yesterday's indicators, or None if not found
        """
        from datetime import datetime as dt

        try:
            today_obj = dt.strptime(today, "%Y-%m-%d")
            yesterday_obj = today_obj - timedelta(days=1)
            yesterday_str = yesterday_obj.strftime("%Y-%m-%d")

            return self.load_daily_indicators(symbol, yesterday_str)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Failed to load yesterday's indicators: {e}")
            return None

    def cleanup_old_indicators(self, symbol: str, keep_days: int = 30) -> int:
        """
        Remove old indicator files older than keep_days.

        Args:
            symbol: Stock ticker symbol
            keep_days: Number of days of indicators to keep

        Returns:
            Number of files deleted
        """
        try:
            symbol_dir = os.path.join(self.store_dir, symbol.upper())
            if not os.path.exists(symbol_dir):
                return 0

            cutoff_date = datetime.now() - timedelta(days=keep_days)
            deleted = 0

            for filename in os.listdir(symbol_dir):
                file_path = os.path.join(symbol_dir, filename)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))

                if file_mtime < cutoff_date:
                    os.remove(file_path)
                    deleted += 1

            return deleted
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Failed to cleanup indicators: {e}")
            return 0


# Global instance
_indicator_store = TechnicalIndicatorStore()


def save_daily_indicators(symbol: str, date_str: str, indicators: Dict[str, Any]) -> bool:
    """Module-level helper to save daily indicators."""
    return _indicator_store.save_daily_indicators(symbol, date_str, indicators)


def load_daily_indicators(symbol: str, date_str: str) -> Optional[Dict[str, Any]]:
    """Module-level helper to load daily indicators."""
    return _indicator_store.load_daily_indicators(symbol, date_str)


def load_yesterday_indicators(symbol: str, today: str) -> Optional[Dict[str, Any]]:
    """Module-level helper to load yesterday's indicators."""
    return _indicator_store.load_yesterday_indicators(symbol, today)
