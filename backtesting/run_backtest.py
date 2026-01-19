#!/usr/bin/env python3
"""
Backtesting entrypoint
======================

Thin wrapper around `custom_TradingBot.start_agent_backtest` so that all
backtest‑related scripts live under the `backtesting/` folder.

Design:
- Reuses the project‑level `ReasoningAgent` and `OpenBBMCPServer` for tools.
- Uses the strict no‑lookahead constraints implemented inside `ReasoningAgent`
  when building and executing MCP tool calls.
- Executes theoretical trades via the shared `execute_trade` function so that
  portfolio state (cash, positions, shorts, last_prices, P&L) is updated on
  each backtest step.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from custom_TradingBot.start_agent_backtest import run_backtest as _run_backtest


async def run_backtest(
    symbol: str,
    start_date: str,
    end_date: Optional[str] = None,
    starting_cash: float = 100_000.0,
) -> None:
    """
    Run a backtest using the shared ReasoningAgent + OpenBB MCP stack.

    This simply forwards to `custom_TradingBot.start_agent_backtest.run_backtest`
    so that all of the established no‑lookahead protections and trade execution
    behavior are preserved.
    """

    await _run_backtest(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        starting_cash=starting_cash,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ReasoningAgent backtest (backtesting package wrapper).")
    parser.add_argument("--symbol", type=str, default="AAPL", help="Ticker symbol")
    parser.add_argument(
        "--date",
        type=str,
        help="Single trading date (YYYY-MM-DD). If provided, overrides start/end.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2025-12-15",
        help="Start date for backtest (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for backtest (YYYY-MM-DD). If omitted, runs single day.",
    )
    parser.add_argument(
        "--cash",
        type=float,
        default=100_000.0,
        help="Starting cash for the portfolio",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # If a single --date is provided, use that; otherwise use start/end
    if args.date:
        start = args.date
        end = None
    else:
        start = args.start_date
        end = args.end_date

    try:
        asyncio.run(
            run_backtest(
                symbol=args.symbol,
                start_date=start,
                end_date=end,
                starting_cash=args.cash,
            )
        )
    except KeyboardInterrupt:
        print("\n⚠️  Backtest interrupted by user")
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ Backtest error: {e}")
        import traceback

        traceback.print_exc()


