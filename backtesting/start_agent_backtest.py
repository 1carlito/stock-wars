#!/usr/bin/env python3
"""
Test Full Workflow: ReasoningAgent → MCP Client → MCP Server → OpenBB → Trade Execution

This script demonstrates the complete workflow:
1. Start MCP server (OpenBBMCPServer.py) as subprocess
2. ReasoningAgent connects via MCP client
3. LLM makes tool calls (multiple API calls in a loop)
4. Tools execute via MCP → OpenBB → return JSON
5. LLM uses data to make final trade decision
6. Trade is executed (optional)
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from typing import Any
from dotenv import load_dotenv

# Load environment variables from .env file (for OpenBB API keys)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path)

# Add path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from custom_TradingBot.live_trade.ReasoningAgent import ReasoningAgent


def calculate_unrealized_pnl(portfolio_state: dict) -> float:
    """Calculate total unrealized P&L for all positions using last_prices."""
    unrealized_pnl = 0.0
    
    # Long positions: (current_price - avg_price) * shares
    positions = portfolio_state.get('positions', {})
    last_prices = portfolio_state.get('last_prices', {})
    
    for symbol, position in positions.items():
        shares = position.get('shares', 0)
        avg_price = position.get('avg_price', 0)
        # Only calculate P&L if we have a current price in last_prices
        if symbol not in last_prices:
            continue  # Skip if we don't have current price
        current_price = last_prices[symbol]
        if shares > 0 and avg_price > 0 and current_price > 0:
            unrealized_pnl += (current_price - avg_price) * shares
    
    # Short positions: (avg_price - current_price) * shares
    short_positions = portfolio_state.get('short_positions', {})
    for symbol, position in short_positions.items():
        shares = position.get('shares', 0)
        avg_price = position.get('avg_price', 0)
        # Only calculate P&L if we have a current price in last_prices
        if symbol not in last_prices:
            continue  # Skip if we don't have current price
        current_price = last_prices[symbol]
        if shares > 0 and avg_price > 0 and current_price > 0:
            unrealized_pnl += (avg_price - current_price) * shares
    
    return unrealized_pnl


async def run_backtest(
    symbol: str,
    start_date: str,
    end_date: str | None = None,
    starting_cash: float = 100000.0,
) -> None:
    """
    Run a simple backtest loop over one or more dates.

    - If end_date is None, runs a single-day decision on start_date.
    - If end_date is provided, runs once per day from start_date to end_date (inclusive).
    """
    print("=" * 70)
    print("🧪 Backtest: ReasoningAgent → MCP → OpenBB → Trade")
    print("=" * 70)

    # Initialize agent (will connect to MCP server)
    agent = ReasoningAgent(
        data_dir=".",
        use_mcp_client=True,  # Enable MCP client connection
    )

    # Build date list
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end_dt = start_dt

    dates: list[str] = []
    cur = start_dt
    while cur <= end_dt:
        dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)

    # Initial portfolio state
    portfolio_state: dict[str, Any] = {
        "cash": starting_cash,
        "positions": {},
        "short_positions": {},
        "last_prices": {},
        "market_caps": {},
        "realized_short_pnl": 0.0,
        "unrealized_pnl": 0.0,
    }

    all_results: list[dict[str, Any]] = []

    for current_date in dates:
        print("\n" + "-" * 70)
        print(f"📊 Analyzing: {symbol} on {current_date}")
        print(f"💰 Portfolio cash: ${portfolio_state.get('cash', 0):,.2f}")
        print("🔄 Starting ReAct loop for this date...")

        result = await agent._make_decision_async(
            symbol=symbol,
            current_date=current_date,
            portfolio_state=portfolio_state,
            execute_trade_after=True,  # Execute trade after decision
            current_price=None,  # Will be fetched if needed
            max_tool_iterations=5,
            selected_categories=["technical_indicators", "fundamental"],  # Default tool categories for backtest
            technical_indicators_date_range=90,  # Fixed 90-day lookback for consistent backtest behavior
        )

        all_results.append(result)

        # Update portfolio state from trade execution (if trade was executed)
        if result.get("portfolio_state_updated"):
            portfolio_state = result["portfolio_state_updated"]
        
        # Calculate and update unrealized P&L
        portfolio_state['unrealized_pnl'] = calculate_unrealized_pnl(portfolio_state)

        print(f"\n✅ Decision for {current_date}: {result.get('decision', 'N/A')}")
        print(f"   Amount: ${result.get('amount_usd', 0):,.2f}")
        print(f"   Confidence: {result.get('confidence', 0):.2%}")
        print(f"   Tool Calls Made: {result.get('tool_calls_made', 0)}")

    print("\n" + "=" * 70)
    print("🏁 Backtest Complete")
    print("=" * 70)
    print(f"Symbol: {symbol}")
    print(f"Date range: {dates[0]} → {dates[-1]}")
    print(f"Final cash: ${portfolio_state.get('cash', 0):,.2f}")
    print(f"Final positions: {portfolio_state.get('positions', {})}")
    print(f"Final short positions: {portfolio_state.get('short_positions', {})}")
    print(f"Last prices: {portfolio_state.get('last_prices', {})}")
    print(f"Unrealized P&L: ${portfolio_state.get('unrealized_pnl', 0):,.2f}")
    print(f"Realized short PnL: ${portfolio_state.get('realized_short_pnl', 0):,.2f}")
    
    # Debug: Show P&L calculation details
    positions = portfolio_state.get('positions', {})
    last_prices = portfolio_state.get('last_prices', {})
    for symbol, position in positions.items():
        shares = position.get('shares', 0)
        avg_price = position.get('avg_price', 0)
        current_price = last_prices.get(symbol)
        if current_price:
            pnl = (current_price - avg_price) * shares
            print(f"   {symbol}: {shares} shares @ ${avg_price:.2f} avg, current ${current_price:.2f} → P&L: ${pnl:,.2f}")
        else:
            print(f"   {symbol}: {shares} shares @ ${avg_price:.2f} avg, NO CURRENT PRICE in last_prices")

    # Explicitly close MCP session before event loop shuts down
    try:
        await agent._close_mcp_session()
        print("✅ MCP session closed cleanly")
    except Exception:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run ReasoningAgent backtest.")
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
        default=100000.0,
        help="Starting cash for the portfolio",
    )

    args = parser.parse_args()

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
        print("\n⚠️  Interrupted by user")
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()

