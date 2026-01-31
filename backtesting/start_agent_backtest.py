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
import json
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
    symbol: str | list[str],
    start_date: str,
    end_date: str | None = None,
    starting_cash: float = 100000.0,
    selected_categories: list[str] | None = None,
    include_news: bool = False,
    allow_short_selling: bool = False,
) -> None:
    """
    Run a simple backtest loop over one or more dates.

    - If end_date is None, runs a single-day decision on start_date.
    - If end_date is provided, runs once per day from start_date to end_date (inclusive).
    """
    print("=" * 70)
    print("🧪 Backtest: ReasoningAgent → MCP → OpenBB → Trade")
    print("=" * 70)

    # Parse symbols
    if isinstance(symbol, str):
        symbols = [s.strip() for s in symbol.split(",") if s.strip()]
    else:
        symbols = symbol

    # ------------------------------------------------------------------
    # PATCH: Fix prompt generation for backtesting
    # Injects the symbol into the pre-computed tool templates.
    # Note: Currently prompt_passer only supports one symbol injection.
    # For multi-symbol, we might need to iterate or patch dynamically.
    # BUT, the reasoning agent will build its OWN prompt.
    # The patch only affects the "CATEGORY_TOOL_CALLS" used by `generate_precomputed_tool_calls`.
    # If we patch it with the *current* symbol before each decision, it handles it.
    # So we'll move the patch inside the loop.
    # ------------------------------------------------------------------
    try:
        from prompt_passer import patch_tool_registry_for_backtest
    except ImportError:
        print("⚠️  Warning: prompt_passer not found. Tool calls may lack 'symbol' argument.")
        patch_tool_registry_for_backtest = None

    # ------------------------------------------------------------------
    # FILTER: Remove FMP and News tools for backtesting (User Request)
    # This monkey-patches the tool_registry module in memory.
    # ------------------------------------------------------------------
    try:
        import tool_registry
        
        # 1. Remove FMP tools and News tools from main REGISTRY
        keys_to_remove = []
        for tool_name, metadata in tool_registry.TOOL_REGISTRY.items():
            is_fmp = metadata.get("provider") == "fmp" or tool_name.startswith("get_fmp_")
            is_news = metadata.get("category") in ["news", "sentiment"]
            
            if is_fmp or is_news:
                keys_to_remove.append(tool_name)
        
        for k in keys_to_remove:
            del tool_registry.TOOL_REGISTRY[k]
            
        print(f"🧹 Removed {len(keys_to_remove)} FMP/News tools from registry for backtesting.")

        # 2. Clean up CATEGORY_TOOL_CALLS to avoid referencing removed tools
        # and explicitly remove 'news'/'sentiment' categories
        categories_to_remove = ["news", "sentiment"]
        for cat in categories_to_remove:
            if cat in tool_registry.CATEGORY_TOOL_CALLS:
                del tool_registry.CATEGORY_TOOL_CALLS[cat]
        
        for cat, tools in tool_registry.CATEGORY_TOOL_CALLS.items():
            # Filter the list of dicts in place
            tool_registry.CATEGORY_TOOL_CALLS[cat] = [
                t for t in tools 
                if t["tool"] not in keys_to_remove
            ]
            
    except ImportError:
        print("⚠️  Could not import tool_registry for patching.")

    # Initialize agent (will connect to MCP server)
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_results")
    agent = ReasoningAgent(
        data_dir=".",
        use_mcp_client=True,  # Enable MCP client connection
    )
    # Override decision_save_dir to point to backtest_results
    agent.decision_save_dir = results_dir

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
        print(f"📅 Date: {current_date}")
        print(f"💰 Portfolio cash: ${portfolio_state.get('cash', 0):,.2f}")
        
        for symbol in symbols:
            print(f"   📊 Analyzing: {symbol}")
            
            # Patch registry for this symbol
            if patch_tool_registry_for_backtest:
                patch_tool_registry_for_backtest(symbol)

            # Prepare categories
            categories = selected_categories or ["technical_indicators", "fundamental"]
            # News category removed from backtesting per user request
            if "news" in categories:
                categories.remove("news")

            result = await agent._make_decision_async(
                symbol=symbol,
                current_date=current_date,
                portfolio_state=portfolio_state,
                execute_trade_after=True,  # Execute trade after decision
                current_price=None,  # Will be fetched if needed
                max_tool_iterations=10, # Increased to ensure all pre-computed tools run
                selected_categories=categories,  # Default tool categories for backtest
                technical_indicators_date_range=90,  # Fixed 90-day lookback for consistent backtest behavior
                allow_short_selling=allow_short_selling,
            )

            all_results.append(result)

            # Update portfolio state from trade execution (if trade was executed)
            if result.get("portfolio_state_updated"):
                portfolio_state = result["portfolio_state_updated"]
            
            # Calculate and update unrealized P&L
            portfolio_state['unrealized_pnl'] = calculate_unrealized_pnl(portfolio_state)

            # Save detailed logs
            results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_results")
            os.makedirs(results_dir, exist_ok=True)
            log_file = os.path.join(results_dir, f"backtest_{symbol}_{current_date}.json")
            try:
                with open(log_file, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"   📝 Log saved to: {os.path.basename(log_file)}")
            except Exception as e:
                print(f"   ⚠️  Failed to save log: {e}")

            print(f"   ✅ Decision for {symbol}: {result.get('decision', 'N/A')}")
            print(f"      Amount: ${result.get('amount_usd', 0):,.2f}")
            print(f"      Confidence: {result.get('confidence', 0):.2%}")
            print(f"      Tool Calls Made: {result.get('tool_calls_made', 0)}")

    print("\n" + "=" * 70)
    print("🏁 Backtest Complete")
    print("=" * 70)
    print("🏁 Backtest Complete")
    print("=" * 70)
    print(f"Symbols: {symbols}")
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

    parser.add_argument(
        "--news",
        action="store_true",
        help="Include news tools",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="Allow short selling",
    )
    parser.add_argument(
        "--tools",
        type=str,
        help="Comma-separated list of tool categories",
    )

    args = parser.parse_args()

    # If a single --date is provided, use that; otherwise use start/end
    if args.date:
        start = args.date
        end = None
    else:
        start = args.start_date
        end = args.end_date
    
    selected_categories = args.tools.split(",") if args.tools else None

    try:
        asyncio.run(
            run_backtest(
                symbols_input=args.symbol,
                start_date=start,
                end_date=end,
                starting_cash=args.cash,
                selected_categories=selected_categories,
                include_news=args.news,
                allow_short_selling=args.short,
            )
        )
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()

