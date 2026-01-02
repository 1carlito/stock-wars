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
from dotenv import load_dotenv

# Load environment variables from .env file (for OpenBB API keys)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path)

# Add path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ReasoningAgent import ReasoningAgent

async def test_workflow():
    """
    Test the full workflow for a single stock decision.
    
    Flow:
    1. Initialize ReasoningAgent (connects to MCP server)
    2. Set up portfolio state
    3. Call make_decision_async() which:
       a. Calls LLM with prompt + available tools
       b. LLM responds with tool call (e.g., "I'll call calculate_rsi")
       c. Agent parses tool call, executes via MCP client
       d. Tool result is fed back to LLM
       e. LLM may call more tools OR make final decision
       f. Loop continues until decision is made
    4. Trade is executed (if requested)
    """
    
    print("=" * 70)
    print("🧪 Testing Full Workflow: ReasoningAgent → MCP → OpenBB → Trade")
    print("=" * 70)
    
    # Initialize agent (will connect to MCP server)
    agent = ReasoningAgent(
        data_dir=".",
        use_mcp_client=True  # Enable MCP client connection
    )
    
    # Test stock
    symbol = "AAPL"
    current_date = "2025-12-15"
    
    # Initial portfolio state
    portfolio_state = {
        "cash": 100000.0,  # $100k starting capital
        "positions": {},  # No long positions
        "short_positions": {},  # No short positions
        "last_prices": {},
        "market_caps": {},
        "realized_short_pnl": 0.0
    }
    
    print(f"\n📊 Analyzing: {symbol} on {current_date}")
    print(f"💰 Portfolio: ${portfolio_state['cash']:,.2f} cash")
    print(f"\n🔄 Starting ReAct loop...")
    print("-" * 70)
    print("\n💡 This will make MULTIPLE LLM API calls in a loop:")
    print("   1. LLM sees prompt → decides to call a tool")
    print("   2. Tool executes → returns JSON result")
    print("   3. LLM sees result → may call another tool OR make decision")
    print("   4. Loop continues until decision is made\n")
    print("-" * 70)
    
    # Make decision (this triggers the ReAct loop)
    result = await agent._make_decision_async(
        symbol=symbol,
        current_date=current_date,
        portfolio_state=portfolio_state,
        execute_trade_after=True,  # Execute trade after decision
        current_price=None,  # Will be fetched if needed
        max_tool_iterations=5  # Max 5 tool calls before forcing decision
    )
    
    # Update portfolio state from trade execution (if trade was executed)
    if result.get('portfolio_state_updated'):
        portfolio_state = result['portfolio_state_updated']
    
    print("\n" + "=" * 70)
    print("✅ Decision Complete!")
    print("=" * 70)
    print(f"\n📋 Decision: {result.get('decision', 'N/A')}")
    print(f"💵 Amount: ${result.get('amount_usd', 0):,.2f}")
    print(f"📈 Confidence: {result.get('confidence', 0):.2%}")
    print(f"🔧 Tool Calls Made: {result.get('tool_calls_made', 0)}")
    
    if result.get('trade_execution'):
        trade_exec = result['trade_execution']
        trade_details = trade_exec.get('trade_details', {})
        print(f"\n💼 Trade Execution:")
        print(f"   Action: {trade_details.get('action', 'N/A')}")
        if 'shares' in trade_details:
            print(f"   Shares: {trade_details['shares']}")
        if 'cost' in trade_details:
            print(f"   Cost: ${trade_details['cost']:,.2f}")
        if 'proceeds' in trade_details:
            print(f"   Proceeds: ${trade_details['proceeds']:,.2f}")
    
    if result.get('tool_results'):
        print(f"\n🔍 Tools Used:")
        for i, tool_result in enumerate(result['tool_results'], 1):
            tool_name = tool_result.get('tool_name', 'unknown')
            print(f"   {i}. {tool_name}")
            if 'error' in tool_result:
                print(f"      ⚠️  Error: {tool_result['error']}")
    
    print("\n" + "=" * 70)
    
    # Explicitly close MCP session before event loop shuts down
    # This prevents cleanup errors during asyncio.run() shutdown
    try:
        await agent._close_mcp_session()
        print("✅ MCP session closed cleanly")
    except Exception as e:
        # Ignore cleanup errors during shutdown
        pass
    
    return result


if __name__ == "__main__":
  
    
    # Run the test
    try:
        asyncio.run(test_workflow())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

