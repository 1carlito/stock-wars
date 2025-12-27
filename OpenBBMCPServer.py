#!/usr/bin/env python3
"""
OpenBB MCP Server
=================

MCP server that exposes OpenBB tools using Model Context Protocol.
Direct OpenBB SDK calls - no provider layer needed.
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing OpenBB
# OpenBB SDK automatically reads API keys from environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path)

# Check if API keys are loaded (OpenBB SDK reads from environment automatically)
if os.getenv("fmp_api_key"):
    print(f"✅ FMP API key loaded from .env")
else:
    print(f"⚠️  FMP API key not found in .env (check for fmp_api_key)")



try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("⚠️  MCP SDK not available. Install with: pip install mcp")

try:
    from openbb import obb
    OPENBB_AVAILABLE = True
except ImportError:
    OPENBB_AVAILABLE = False
    print("⚠️  OpenBB not available. Install with: pip install openbb")


# Create MCP server instance
if MCP_AVAILABLE:
    mcp = FastMCP("OpenBB Data Provider")
else:
    mcp = None


# Helper function to convert OpenBB OBBject results to dict
def _convert_openbb_result(result):
    """Convert OpenBB OBBject result to dictionary format"""
    if hasattr(result, 'results'):
        # OBBject has .results attribute
        if hasattr(result.results, 'to_dict'):
            return result.results.to_dict()
        elif hasattr(result.results, 'to_dataframe'):
            # For DataFrame results
            df = result.results.to_dataframe()
            return df.to_dict('records')
        elif isinstance(result.results, list):
            # List of Data objects
            return [item.model_dump() if hasattr(item, 'model_dump') else dict(item) for item in result.results]
        elif isinstance(result.results, dict):
            return result.results
        else:
            return {"data": str(result.results)}
    elif hasattr(result, 'to_dict'):
        return result.to_dict()
    elif hasattr(result, 'to_dataframe'):
        df = result.to_dataframe()
        return df.to_dict('records')
    elif isinstance(result, dict):
        return result
    else:
        return {"data": str(result)}


# ============================================================================
# IMPORT TOOL MODULES
# ============================================================================

# Import tool registration functions
try:
    import sys
    import os
    # Add Tools directory to path
    tools_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    
    from Fundamental_Tools import register_fundamental_tools
    from Technical_Tools import register_technical_tools
    from News_Tools import register_news_tools
    TOOLS_AVAILABLE = True
except ImportError as e:
    TOOLS_AVAILABLE = False
    print(f"⚠️  Tool modules not available: {e}")

# Register all tools with MCP server
if mcp and TOOLS_AVAILABLE:
    register_fundamental_tools(mcp)
    register_technical_tools(mcp)
    register_news_tools(mcp)


# ============================================================================
# TRADE EXECUTION TOOL - Extracted from ParallelOrchestrator
# MCP tool for executing trades and updating portfolio state
# ============================================================================

# ============================================================================
# TRADE EXECUTION TOOL - Extracted from ParallelOrchestrator
# MCP tool for executing trades and updating portfolio state
# ============================================================================

def execute_trade(
    symbol: str,
    decision: str,
    amount_usd: float,
    current_price: float,
    current_date: str,
    portfolio_state: Dict[str, Any],
    market_cap_bil: Optional[float] = None
) -> Dict[str, Any]:
    """
    Standalone function for executing trades (can be imported directly).
    
    This is the same logic as execute_trade_mcp but without MCP decorator.
    Used as a fallback when MCP is not available or for direct imports.
    """
    import math
    from datetime import datetime
    
    # Deep copy portfolio state to avoid mutating input
    updated_state = json.loads(json.dumps(portfolio_state))
    
    decision_upper = decision.upper()
    trade_executed = False
    trade_details = {
        "symbol": symbol,
        "decision": decision_upper,
        "amount_usd": amount_usd,
        "price": current_price,
        "date": current_date
    }
    
    # Initialize missing fields
    if 'positions' not in updated_state:
        updated_state['positions'] = {}
    if 'short_positions' not in updated_state:
        updated_state['short_positions'] = {}
    if 'last_prices' not in updated_state:
        updated_state['last_prices'] = {}
    if 'market_caps' not in updated_state:
        updated_state['market_caps'] = {}
    if 'realized_short_pnl' not in updated_state:
        updated_state['realized_short_pnl'] = 0.0
    
    # Update last price
    updated_state['last_prices'][symbol] = current_price
    
    # Calculate spread rate for shorts
    def _get_short_spread_rate(symbol, market_caps, market_cap_bil):
        base_rate = 0.0006 + 0.0010
        mc_bil = market_cap_bil or market_caps.get(symbol)
        if mc_bil and mc_bil > 0:
            return base_rate + (1.0 / math.sqrt(mc_bil))
        return base_rate
    
    # Update market cap if provided
    if market_cap_bil:
        updated_state['market_caps'][symbol] = market_cap_bil
    
    # --- 1. CLOSE/SELL/COVER (High Priority) ---
    if decision_upper in ('CLOSE', 'COVER', 'SELL'):
        # Check for Long Position to SELL
        if symbol in updated_state['positions'] and updated_state['positions'][symbol].get('shares', 0) > 0:
            shares_to_close = updated_state['positions'][symbol]['shares']
            proceeds = shares_to_close * current_price
            updated_state['cash'] += proceeds
            
            trade_details.update({
                "action": "SELL",
                "shares": shares_to_close,
                "proceeds": proceeds
            })
            
            del updated_state['positions'][symbol]
            trade_executed = True
            
        # Check for Short Position to COVER
        elif symbol in updated_state['short_positions'] and updated_state['short_positions'][symbol].get('shares', 0) > 0:
            short_pos = updated_state['short_positions'][symbol]
            shares_to_cover = short_pos['shares']
            entry_date = short_pos.get('entry_date', current_date)
            
            # Calculate days held
            try:
                entry_date_obj = datetime.strptime(entry_date, '%Y-%m-%d')
                current_date_obj = datetime.strptime(current_date, '%Y-%m-%d')
                days_held = max(0, (current_date_obj - entry_date_obj).days)
            except:
                days_held = 0
            
            # CFD Model: Calculate fees and P&L
            entry_notional = short_pos['shares'] * short_pos['avg_price']
            
            # Calculate exit spread fee
            spread_rate = _get_short_spread_rate(symbol, updated_state['market_caps'], market_cap_bil)
            exit_spread_fee = (shares_to_cover * current_price) * spread_rate
            
            # Profit/Loss from the short position
            pnl = (short_pos['avg_price'] - current_price) * shares_to_cover
            
            # Track as realized P&L
            updated_state['realized_short_pnl'] += pnl
            
            # Cash update for CFD: Add back entry notional + P&L, subtract exit spread fee
            updated_state['cash'] += entry_notional + pnl - exit_spread_fee
            
            trade_details.update({
                "action": "COVER",
                "shares": shares_to_cover,
                "entry_price": short_pos['avg_price'],
                "pnl": pnl,
                "exit_spread_fee": exit_spread_fee,
                "days_held": days_held
            })
            
            del updated_state['short_positions'][symbol]
            trade_executed = True
        else:
            trade_details["action"] = "NO_POSITION"
            trade_details["message"] = "CLOSE proposed but no position found"
    
    # --- 2. SHORT (CFD Model) ---
    elif decision_upper == 'SHORT' and amount_usd > 0:
        shares_requested = int(amount_usd / current_price)
        cost_or_value = shares_requested * current_price
        
        if shares_requested > 0:
            # Calculate entry spread fee
            spread_rate = _get_short_spread_rate(symbol, updated_state['market_caps'], market_cap_bil)
            entry_spread_fee = cost_or_value * spread_rate
            
            # For CFD shorts: Deduct notional + spread fee from cash
            total_cost = cost_or_value + entry_spread_fee
            
            if updated_state['cash'] >= total_cost:
                updated_state['cash'] -= total_cost
                
                # Update/Create Short Position
                current_short = updated_state['short_positions'].get(symbol, {'shares': 0, 'avg_price': 0})
                
                # Calculate new average price
                new_total_shares = current_short['shares'] + shares_requested
                new_total_value = (current_short['shares'] * current_short['avg_price']) + (shares_requested * current_price)
                new_avg_price = new_total_value / new_total_shares if new_total_shares > 0 else 0
                
                # Use existing entry_date if position already exists, otherwise use current date
                entry_date = current_short.get('entry_date', current_date)
                
                updated_state['short_positions'][symbol] = {
                    'shares': new_total_shares,
                    'avg_price': new_avg_price,
                    'entry_date': entry_date,
                    'short_date': current_date
                }
                
                trade_details.update({
                    "action": "SHORT",
                    "shares": shares_requested,
                    "notional": cost_or_value,
                    "entry_spread_fee": entry_spread_fee,
                    "total_cost": total_cost
                })
                
                trade_executed = True
            else:
                trade_details["action"] = "INSUFFICIENT_CASH"
                trade_details["message"] = f"Required ${total_cost:,.2f}, have ${updated_state['cash']:,.2f}"
    
    # --- 3. BUY ---
    elif decision_upper == 'BUY' and amount_usd > 0:
        shares_requested = int(amount_usd / current_price)
        cost_or_value = shares_requested * current_price
        
        if shares_requested > 0 and updated_state['cash'] >= cost_or_value:
            # Update cash
            updated_state['cash'] -= cost_or_value
            
            # Update/Create Long Position
            current_long = updated_state['positions'].get(symbol, {'shares': 0, 'avg_price': 0})
            
            # Calculate new average price
            new_total_shares = current_long['shares'] + shares_requested
            new_total_value = (current_long['shares'] * current_long['avg_price']) + (shares_requested * current_price)
            new_avg_price = new_total_value / new_total_shares if new_total_shares > 0 else 0
            
            updated_state['positions'][symbol] = {
                'shares': new_total_shares,
                'avg_price': new_avg_price,
                'buy_date': current_date
            }
            
            trade_details.update({
                "action": "BUY",
                "shares": shares_requested,
                "cost": cost_or_value
            })
            
            trade_executed = True
        else:
            trade_details["action"] = "INSUFFICIENT_CASH" if updated_state['cash'] < cost_or_value else "INVALID_AMOUNT"
            trade_details["message"] = f"Required ${cost_or_value:,.2f}, have ${updated_state['cash']:,.2f}" if updated_state['cash'] < cost_or_value else "Invalid amount"
    
    # --- 4. NEUTRAL / MAINTAIN ---
    elif decision_upper in ('NEUTRAL', 'MAINTAIN'):
        trade_details["action"] = "NO_ACTION"
        trade_details["message"] = f"{decision_upper} - no trade executed"
    
    return {
        "updated_portfolio_state": updated_state,
        "trade_executed": trade_executed,
        "trade_details": trade_details
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
        market_cap_bil: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute a single trade and update portfolio state (MCP tool wrapper).
        
        This is a wrapper around the standalone execute_trade function for MCP.
        Handles BUY, SELL, SHORT, and CLOSE operations with proper fee calculations.
        Returns updated portfolio state and trade execution details.
        
        Args:
            symbol: Stock ticker symbol
            decision: Trade decision - 'BUY', 'SELL', 'SHORT', or 'CLOSE'
            amount_usd: Dollar amount for the trade (0 for CLOSE means close full position)
            current_price: Current stock price
            current_date: Trading date (YYYY-MM-DD)
            portfolio_state: Current portfolio state dict with:
                - cash: float
                - positions: dict of long positions
                - short_positions: dict of short positions
                - last_prices: dict of last known prices
                - market_caps: dict of market caps
                - realized_short_pnl: float
            market_cap_bil: Market cap in billions (for spread calculation)
        
        Returns:
            Dict with:
                - updated_portfolio_state: Updated portfolio state
                - trade_executed: bool
                - trade_details: Dict with execution details
        """
        # Call the standalone execute_trade function
        return execute_trade(
            symbol=symbol,
            decision=decision,
            amount_usd=amount_usd,
            current_price=current_price,
            current_date=current_date,
            portfolio_state=portfolio_state,
            market_cap_bil=market_cap_bil
        )


if __name__ == "__main__":
    if mcp:
        print("🚀 Starting OpenBB MCP Server...")
        print("📊 Available tools:")
        print("   - Fundamental tools (income, balance, cash flow, profile)")
        print("   - Valuation tools (price history, current price)")
        print("   - Technical indicators (RSI, MACD, SMA, volatility)")
        print("=" * 60)
        print("✅ Direct OpenBB SDK calls")
        print("=" * 60)
        mcp.run()
    else:
        print("❌ MCP SDK not available. Install with: pip install mcp")

