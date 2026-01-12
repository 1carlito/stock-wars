#!/usr/bin/env python3
"""Quick test of live trading with fixed MCP tools"""
import asyncio
from datetime import date
from custom_TradingBot.live_trade.portfolio_orchestrator import PortfolioOrchestrator

async def test_single_stock():
    """Test single stock analysis (backward compatible)"""
    print("🚀 Testing single stock mode (backward compatible)...")
    orch = PortfolioOrchestrator(
        symbols=["AAPL"],
        starting_capital=50000,
        risk_level="medium"
    )
    
    try:
        result = await orch.process_portfolio(date.today())
        print(f"✅ Single stock analysis complete")
        print(f"   Trades executed: {len(result['trades'])}")
        print(f"   Token usage: {result['token_summary']['total_tokens']:,} tokens")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_single_stock())
    exit(0 if success else 1)
