#!/usr/bin/env python3
"""
OpenBB MCP Server (live_trade variant)
======================================

Lightly adapted copy of the project‑level OpenBB MCP server, scoped for the
`live_trade` package so we can tweak behaviour for live / paper trading
without affecting backtests.

Differences from the root version:
- .env is loaded from the project root (one directory up from this file).
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables from project‑root .env BEFORE importing OpenBB
# OpenBB SDK automatically reads API keys from environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=env_path)

# Check if API keys are loaded (OpenBB SDK reads from environment automatically)
import sys as _sys  # Import early for stderr output
if os.getenv("fmp_api_key"):
    print("✅ FMP API key loaded from project‑root .env", file=_sys.stderr)
else:
    print("⚠️  FMP API key not found in project‑root .env (check for fmp_api_key)", file=_sys.stderr)


try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("⚠️  MCP SDK not available. Install with: pip install mcp", file=_sys.stderr)

try:
    from openbb import obb
    OPENBB_AVAILABLE = True
except ImportError:
    OPENBB_AVAILABLE = False
    print("⚠️  OpenBB not available. Install with: pip install openbb", file=_sys.stderr)


# Create MCP server instance
if MCP_AVAILABLE:
    mcp = FastMCP("OpenBB Data Provider (live_trade)")
else:
    mcp = None


# Import helper function from utils module (project‑level)
import sys
# Ensure project root is in sys.path so we can import utils
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from utils import _convert_openbb_result  # type: ignore  # noqa: E402


# ============================================================================
# IMPORT TOOL MODULES
# ============================================================================

# Import tool registration functions
try:
    import sys
    import importlib.util

    # Get the absolute path to the Tools directory at project root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools_dir = os.path.join(base_dir, "Tools")

    # Use importlib to load modules from specific paths to avoid stale imports
    def load_module_from_path(module_name, file_path):
        """Load a module from a specific file path."""
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {module_name} from {file_path}")
        module = importlib.util.module_from_spec(spec)
        # Add parent directory to sys.path for utils import
        if base_dir not in sys.path:
            sys.path.insert(0, base_dir)
        spec.loader.exec_module(module)
        return module

    # Load modules from specific file paths
    # Fundamental Tools (FMP & OpenBB)
    fmp_fundamental_tools_path = os.path.join(tools_dir, "fmp_fundamental_tools.py")
    openbb_fundamental_tools_path = os.path.join(tools_dir, "openbb_fundamental_tools.py")
    
    # Technical Tools (FMP & OpenBB)
    fmp_technical_tools_path = os.path.join(tools_dir, "fmp_technical_tools.py")
    openbb_technical_tools_path = os.path.join(tools_dir, "openbb_technical_tools.py")
    
    # News Tools
    news_tools_path = os.path.join(tools_dir, "News_Tools.py")

    # Load Modules
    FMP_Fundamental_Tools = load_module_from_path("fmp_fundamental_tools", fmp_fundamental_tools_path)
    OpenBB_Fundamental_Tools = load_module_from_path("openbb_fundamental_tools", openbb_fundamental_tools_path)
    
    FMP_Technical_Tools = load_module_from_path("fmp_technical_tools", fmp_technical_tools_path)
    OpenBB_Technical_Tools = load_module_from_path("openbb_technical_tools", openbb_technical_tools_path)
    
    News_Tools = load_module_from_path("News_Tools", news_tools_path)

    # Get Register Functions
    register_fmp_fundamental_tools = FMP_Fundamental_Tools.register_fmp_fundamental_tools
    register_openbb_fundamental_tools = OpenBB_Fundamental_Tools.register_openbb_fundamental_tools
    
    register_fmp_technical_tools = FMP_Technical_Tools.register_fmp_technical_tools
    register_openbb_technical_tools = OpenBB_Technical_Tools.register_openbb_technical_tools
    
    register_news_tools = News_Tools.register_news_tools

except Exception as e:  # noqa: BLE001
    print(f"⚠️  Tool modules not available: {e}", file=_sys.stderr)
    register_fmp_fundamental_tools = None
    register_openbb_fundamental_tools = None
    register_fmp_technical_tools = None
    register_openbb_technical_tools = None
    register_news_tools = None


# ============================================================================
# TRADE EXECUTION TOOL
# ============================================================================

def execute_trade(
    symbol: str,
    decision: str,
    amount_usd: float,
    current_price: float,
    current_date: str,
    portfolio_state: Dict[str, Any],
    market_cap_bil: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Standalone function for executing trades (can be imported directly).

    This is the same logic as execute_trade_mcp but without MCP decorator.
    Used as a fallback when MCP is not available or for direct imports.
    """
    import math
    from datetime import datetime as _dt

    # Deep copy portfolio state to avoid mutating input
    updated_state = json.loads(json.dumps(portfolio_state))

    decision_upper = decision.upper()
    trade_executed = False
    trade_details = {
        "symbol": symbol,
        "decision": decision_upper,
        "amount_usd": amount_usd,
        "price": current_price,
        "date": current_date,
    }

    # Initialize missing fields
    if "positions" not in updated_state:
        updated_state["positions"] = {}
    if "short_positions" not in updated_state:
        updated_state["short_positions"] = {}
    if "last_prices" not in updated_state:
        updated_state["last_prices"] = {}
    if "market_caps" not in updated_state:
        updated_state["market_caps"] = {}
    if "realized_short_pnl" not in updated_state:
        updated_state["realized_short_pnl"] = 0.0

    # Update last price
    updated_state["last_prices"][symbol] = current_price

    # Calculate spread rate for shorts
    def _get_short_spread_rate(sym, market_caps, mc_bil):
        base_rate = 0.0006 + 0.0010
        mc_val = mc_bil or market_caps.get(sym)
        if mc_val and mc_val > 0:
            return base_rate + (1.0 / math.sqrt(mc_val))
        return base_rate

    # Update market cap if provided
    if market_cap_bil:
        updated_state["market_caps"][symbol] = market_cap_bil

    # --- 1. CLOSE/SELL/COVER (High Priority) ---
    if decision_upper in ("CLOSE", "COVER", "SELL"):
        # Check for Long Position to SELL
        if symbol in updated_state["positions"] and updated_state["positions"][symbol].get("shares", 0) > 0:
            shares_to_close = updated_state["positions"][symbol]["shares"]
            proceeds = shares_to_close * current_price
            updated_state["cash"] += proceeds

            trade_details.update(
                {
                    "action": "SELL",
                    "shares": shares_to_close,
                    "proceeds": proceeds,
                }
            )

            del updated_state["positions"][symbol]
            trade_executed = True

        # Check for Short Position to COVER
        elif symbol in updated_state["short_positions"] and updated_state["short_positions"][symbol].get("shares", 0) > 0:
            short_pos = updated_state["short_positions"][symbol]
            shares_to_cover = short_pos["shares"]
            entry_date = short_pos.get("entry_date", current_date)

            # Calculate days held
            try:
                entry_date_obj = _dt.strptime(entry_date, "%Y-%m-%d")
                current_date_obj = _dt.strptime(current_date, "%Y-%m-%d")
                days_held = max(0, (current_date_obj - entry_date_obj).days)
            except Exception:
                days_held = 0

            # CFD Model: Calculate fees and P&L
            entry_notional = short_pos["shares"] * short_pos["avg_price"]

            # Calculate exit spread fee
            spread_rate = _get_short_spread_rate(symbol, updated_state["market_caps"], market_cap_bil)
            exit_spread_fee = (shares_to_cover * current_price) * spread_rate

            # Profit/Loss from the short position
            pnl = (short_pos["avg_price"] - current_price) * shares_to_cover

            # Track as realized P&L
            updated_state["realized_short_pnl"] += pnl

            # Cash update for CFD: Add back entry notional + P&L, subtract exit spread fee
            updated_state["cash"] += entry_notional + pnl - exit_spread_fee

            trade_details.update(
                {
                    "action": "COVER",
                    "shares": shares_to_cover,
                    "entry_price": short_pos["avg_price"],
                    "pnl": pnl,
                    "exit_spread_fee": exit_spread_fee,
                    "days_held": days_held,
                }
            )

            del updated_state["short_positions"][symbol]
            trade_executed = True
        else:
            trade_details["action"] = "NO_POSITION"
            trade_details["message"] = "CLOSE proposed but no position found"

    # --- 2. SHORT (CFD Model) ---
    elif decision_upper == "SHORT" and amount_usd > 0:
        shares_requested = int(amount_usd / current_price)
        cost_or_value = shares_requested * current_price

        if shares_requested > 0:
            # Calculate entry spread fee
            spread_rate = _get_short_spread_rate(symbol, updated_state["market_caps"], market_cap_bil)
            entry_spread_fee = cost_or_value * spread_rate

            # For CFD shorts: Deduct notional + spread fee from cash
            total_cost = cost_or_value + entry_spread_fee

            if updated_state["cash"] >= total_cost:
                updated_state["cash"] -= total_cost

                # Update/Create Short Position
                current_short = updated_state["short_positions"].get(symbol, {"shares": 0, "avg_price": 0})

                # Calculate new average price
                new_total_shares = current_short["shares"] + shares_requested
                new_total_value = (current_short["shares"] * current_short["avg_price"]) + (shares_requested * current_price)
                new_avg_price = new_total_value / new_total_shares if new_total_shares > 0 else 0

                # Use existing entry_date if position already exists, otherwise use current date
                entry_date = current_short.get("entry_date", current_date)

                updated_state["short_positions"][symbol] = {
                    "shares": new_total_shares,
                    "avg_price": new_avg_price,
                    "entry_date": entry_date,
                    "short_date": current_date,
                }

                trade_details.update(
                    {
                        "action": "SHORT",
                        "shares": shares_requested,
                        "notional": cost_or_value,
                        "entry_spread_fee": entry_spread_fee,
                        "total_cost": total_cost,
                    }
                )

                trade_executed = True
            else:
                trade_details["action"] = "INSUFFICIENT_CASH"
                trade_details["message"] = f"Required ${total_cost:,.2f}, have ${updated_state['cash']:,.2f}"

    # --- 3. BUY ---
    elif decision_upper == "BUY" and amount_usd > 0:
        shares_requested = int(amount_usd / current_price)
        cost_or_value = shares_requested * current_price

        if shares_requested > 0 and updated_state["cash"] >= cost_or_value:
            # Update cash
            old_cash = updated_state["cash"]
            updated_state["cash"] -= cost_or_value
            print(f"DEBUG: Executing BUY. Cost: ${cost_or_value:,.2f}. Cash: ${old_cash:,.2f} -> ${updated_state['cash']:,.2f}")

            # Update/Create Long Position
            current_long = updated_state["positions"].get(symbol, {"shares": 0, "avg_price": 0})

            # Calculate new average price
            new_total_shares = current_long["shares"] + shares_requested
            new_total_value = (current_long["shares"] * current_long["avg_price"]) + (shares_requested * current_price)
            new_avg_price = new_total_value / new_total_shares if new_total_shares > 0 else 0

            updated_state["positions"][symbol] = {
                "shares": new_total_shares,
                "avg_price": new_avg_price,
                "buy_date": current_date,
            }

            trade_details.update(
                {
                    "action": "BUY",
                    "shares": shares_requested,
                    "cost": cost_or_value,
                }
            )

            trade_executed = True
        else:
            trade_details["action"] = "INSUFFICIENT_CASH" if updated_state["cash"] < cost_or_value else "INVALID_AMOUNT"
            trade_details["message"] = (
                f"Required ${cost_or_value:,.2f}, have ${updated_state['cash']:,.2f}"
                if updated_state["cash"] < cost_or_value
                else "Invalid amount"
            )
            

    # --- 4. NEUTRAL / MAINTAIN ---
    elif decision_upper in ("NEUTRAL", "MAINTAIN"):
        trade_details["action"] = "NO_ACTION"
        trade_details["message"] = f"{decision_upper} - no trade executed"

    return {
        "updated_portfolio_state": updated_state,
        "trade_executed": trade_executed,
        "trade_details": trade_details,
    }


# Register as MCP tool (requires MCP to be available)
if mcp:

    @mcp.tool(name="execute_trade")
    def execute_trade_mcp(
        symbol: str,
        decision: str,
        amount_usd: float,
        current_price: float,
        current_date: str,
        portfolio_state: Dict[str, Any],
        market_cap_bil: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute a single trade and update portfolio state (MCP tool wrapper).

        This is a wrapper around the standalone execute_trade function for MCP.
        Handles BUY, SELL, SHORT, and CLOSE operations with proper fee calculations.
        Returns updated portfolio state and trade execution details.
        """
        # Call the standalone execute_trade function
        return execute_trade(
            symbol=symbol,
            decision=decision,
            amount_usd=amount_usd,
            current_price=current_price,
            current_date=current_date,
            portfolio_state=portfolio_state,
            market_cap_bil=market_cap_bil,
        )

    def _register_tool_module(register_func, module_name: str) -> None:
        """Register a tool module with consistent error handling."""
        if not register_func:
            return
        try:
            register_func(mcp)
            print(f"✅ Registered {module_name}", file=_sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Failed to register {module_name}: {e}", file=_sys.stderr)

    # Register fundamental, technical, and news tools
    _register_tool_module(register_fmp_fundamental_tools, "FMP fundamental tools")
    _register_tool_module(register_openbb_fundamental_tools, "OpenBB fundamental tools")
    
    _register_tool_module(register_fmp_technical_tools, "FMP technical tools")
    _register_tool_module(register_openbb_technical_tools, "OpenBB technical tools")
    
    _register_tool_module(register_news_tools, "news tools")


if __name__ == "__main__":
    import sys
    if mcp:
        # Use stderr for startup messages - stdout is reserved for JSON-RPC
        print("🚀 Starting OpenBB MCP Server (live_trade)...", file=sys.stderr)
        print("📊 Available tools:", file=sys.stderr)
        print("   - Fundamental tools (income, balance, cash flow, profile)", file=sys.stderr)
        print("   - Valuation tools (price history, current price)", file=sys.stderr)
        print("   - Technical indicators (RSI, MACD, SMA, volatility)", file=sys.stderr)
        print("   - News tools (company and world headlines)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("✅ Direct OpenBB SDK calls", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        mcp.run()
    else:
        print("❌ MCP SDK not available. Install with: pip install mcp", file=sys.stderr)





