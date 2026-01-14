#!/usr/bin/env python3
"""Quick test to verify the PortfolioState.get() fix for MSFT and AAPL."""

import sys
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

# Add the custom_TradingBot to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_TradingBot'))

from custom_TradingBot.live_trade.portfolio_orchestrator import PortfolioOrchestrator

# Test that PortfolioOrchestrator can be initialized and handle PortfolioState correctly
def test_portfolio_state_conversion():
    """Test that portfolio_state is correctly converted to dict when passed to functions."""
    print("🧪 Testing PortfolioState conversion fix...")

    try:
        # Initialize orchestrator with multiple symbols
        orchestrator = PortfolioOrchestrator(
            symbols=['MSFT', 'AAPL'],
            starting_capital=50000.0,
            risk_level='medium',
            notes='Testing PortfolioState conversion',
            max_parallel=2
        )

        # Verify that portfolio_state is a PortfolioState object
        assert hasattr(orchestrator.portfolio_state, 'to_dict'), \
            f"Expected PortfolioState object, got {type(orchestrator.portfolio_state)}"

        # Test that it can be converted to dict
        state_dict = orchestrator.portfolio_state.to_dict()
        assert isinstance(state_dict, dict), "to_dict() should return a dict"
        assert 'cash' in state_dict, "Dict should have 'cash' key"
        assert 'positions' in state_dict, "Dict should have 'positions' key"

        print("✅ PortfolioState initialization: PASSED")
        print(f"   - cash: ${state_dict['cash']:,.2f}")
        print(f"   - positions: {len(state_dict['positions'])}")
        print(f"   - short_positions: {len(state_dict['short_positions'])}")

        # Test waterfall allocation with PortfolioState object
        test_decisions = [
            {
                'symbol': 'MSFT',
                'decision': 'BUY',
                'confidence': 0.8,
                'amount_usd': 5000,
                'sector_rank': 1,
            },
            {
                'symbol': 'AAPL',
                'decision': 'BUY',
                'confidence': 0.7,
                'amount_usd': 5000,
                'sector_rank': 1,
            }
        ]

        # This should not raise 'PortfolioState' object has no attribute 'get'
        final_decisions = orchestrator._apply_waterfall_allocation(
            test_decisions,
            orchestrator.portfolio_state
        )

        print("✅ Waterfall allocation: PASSED")
        print(f"   - Processed {len(final_decisions)} decisions")

        return True

    except AttributeError as e:
        if "'PortfolioState' object has no attribute 'get'" in str(e):
            print(f"❌ FAILED: The PortfolioState.get() bug still exists!")
            print(f"   Error: {e}")
            return False
        else:
            raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_portfolio_state_conversion()
    sys.exit(0 if success else 1)
