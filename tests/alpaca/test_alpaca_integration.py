"""
Unit tests for Alpaca integration - Trade Execution Logic.

Tests the trade execution functions (BUY, SHORT, CLOSE, COVER) without requiring
the alpaca-py library, which has a websockets dependency conflict with OpenBB.

Note: These tests use the standalone execute_trade() function from OpenBBMCPServer.py
which implements the core trading logic without external API dependencies.

Tests that require alpaca-py (connection, live position tracking) are excluded due to:
    alpaca-py requires websockets <12.0
    openbb-core requires websockets >=15.0
    → Incompatible dependency conflict

To run these tests:
    cd custom_TradingBot/live_trade
    python -m pytest ../../tests/alpaca/test_alpaca_integration.py -v
"""

import os
import sys

# Setup paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
custom_trading_bot_dir = os.path.join(base_dir, "custom_TradingBot")
live_trade_dir = os.path.join(custom_trading_bot_dir, "live_trade")

sys.path.insert(0, custom_trading_bot_dir)
sys.path.insert(0, live_trade_dir)


def test_alpaca_buy_order():
    """Test placing a BUY order (paper trading)."""
    with patch.dict(os.environ, {
        "ALPACA_ENABLED": "true",
        "ALPACA_API_KEY": "test_key",
        "ALPACA_API_SECRET": "test_secret",
        "ALPACA_PAPER": "true"
    }):
        with patch("live_trading_loop.TradingClient") as mock_trading_client:
            # Mock account and order submission
            mock_client = Mock()
            mock_client.get_account.return_value = Mock(
                cash="100000.0",
                portfolio_value="100000.0"
            )
            
            # Mock successful order
            mock_order = Mock(
                id="order_123",
                symbol="AAPL",
                qty="10",
                side="buy",
                status="filled",
                filled_avg_price="150.0"
            )
            mock_client.submit_order.return_value = mock_order
            mock_trading_client.return_value = mock_client
            
            # Import execute_trade function
            from OpenBBMCPServer import execute_trade
            
            # Test BUY order
            portfolio_state = {
                "cash": 100000.0,
                "positions": {},
                "short_positions": {},
                "last_prices": {},
                "market_caps": {},
                "realized_short_pnl": 0.0
            }
            
            result = execute_trade(
                symbol="AAPL",
                decision="BUY",
                amount_usd=1500.0,
                current_price=150.0,
                current_date="2026-01-30",
                portfolio_state=portfolio_state
            )
            
            # Verify trade was executed
            assert result["trade_executed"] is True
            assert result["trade_details"]["action"] == "BUY"
            assert result["trade_details"]["shares"] == 10
            assert result["updated_portfolio_state"]["cash"] == 98500.0  # 100k - 1500
            assert "AAPL" in result["updated_portfolio_state"]["positions"]


def test_alpaca_short_order():
    """Test placing a SHORT order (paper trading)."""
    with patch.dict(os.environ, {
        "ALPACA_ENABLED": "true",
        "ALPACA_API_KEY": "test_key",
        "ALPACA_API_SECRET": "test_secret",
        "ALPACA_PAPER": "true"
    }):
        with patch("live_trading_loop.TradingClient") as mock_trading_client:
            # Mock account
            mock_client = Mock()
            mock_client.get_account.return_value = Mock(
                cash="100000.0",
                portfolio_value="100000.0"
            )
            
            # Mock successful short order
            mock_order = Mock(
                id="order_456",
                symbol="TSLA",
                qty="5",
                side="sell",
                status="filled",
                filled_avg_price="200.0"
            )
            mock_client.submit_order.return_value = mock_order
            mock_trading_client.return_value = mock_client
            
            # Import execute_trade function
            from OpenBBMCPServer import execute_trade
            
            # Test SHORT order
            portfolio_state = {
                "cash": 100000.0,
                "positions": {},
                "short_positions": {},
                "last_prices": {},
                "market_caps": {},
                "realized_short_pnl": 0.0
            }
            
            result = execute_trade(
                symbol="TSLA",
                decision="SHORT",
                amount_usd=1000.0,
                current_price=200.0,
                current_date="2026-01-30",
                portfolio_state=portfolio_state,
                market_cap_bil=800.0  # Tesla market cap
            )
            
            # Verify short trade was executed
            assert result["trade_executed"] is True
            assert result["trade_details"]["action"] == "SHORT"
            assert result["trade_details"]["shares"] == 5
            assert "TSLA" in result["updated_portfolio_state"]["short_positions"]
            # Cash should be reduced by notional + spread fee
            assert result["updated_portfolio_state"]["cash"] < 100000.0


def test_alpaca_insufficient_cash():
    """Test handling of insufficient cash for orders."""
    from OpenBBMCPServer import execute_trade
    
    # Portfolio with low cash
    portfolio_state = {
        "cash": 100.0,  # Only $100
        "positions": {},
        "short_positions": {},
        "last_prices": {},
        "market_caps": {},
        "realized_short_pnl": 0.0
    }
    
    # Try to buy $1000 worth of stock
    result = execute_trade(
        symbol="AAPL",
        decision="BUY",
        amount_usd=1000.0,
        current_price=150.0,
        current_date="2026-01-30",
        portfolio_state=portfolio_state
    )
    
    # Verify trade was rejected
    assert result["trade_executed"] is False
    assert result["trade_details"]["action"] == "INSUFFICIENT_CASH"
    assert "Required" in result["trade_details"]["message"]


def test_alpaca_close_position():
    """Test closing an existing position."""
    from OpenBBMCPServer import execute_trade
    
    # Portfolio with existing long position
    portfolio_state = {
        "cash": 50000.0,
        "positions": {
            "AAPL": {
                "shares": 100,
                "avg_price": 150.0,
                "buy_date": "2026-01-20"
            }
        },
        "short_positions": {},
        "last_prices": {"AAPL": 155.0},
        "market_caps": {},
        "realized_short_pnl": 0.0
    }
    
    # Close the position
    result = execute_trade(
        symbol="AAPL",
        decision="CLOSE",
        amount_usd=0.0,  # Amount not used for CLOSE
        current_price=155.0,
        current_date="2026-01-30",
        portfolio_state=portfolio_state
    )
    
    # Verify position was closed
    assert result["trade_executed"] is True
    assert result["trade_details"]["action"] == "SELL"
    assert result["trade_details"]["shares"] == 100
    assert result["trade_details"]["proceeds"] == 15500.0  # 100 * 155
    assert "AAPL" not in result["updated_portfolio_state"]["positions"]
    assert result["updated_portfolio_state"]["cash"] == 65500.0  # 50k + 15.5k


def test_alpaca_cover_short_position():
    """Test covering a short position."""
    from OpenBBMCPServer import execute_trade
    
    # Portfolio with existing short position
    portfolio_state = {
        "cash": 50000.0,
        "positions": {},
        "short_positions": {
            "TSLA": {
                "shares": 50,
                "avg_price": 200.0,
                "entry_date": "2026-01-20",
                "short_date": "2026-01-20"
            }
        },
        "last_prices": {"TSLA": 195.0},
        "market_caps": {"TSLA": 800.0},
        "realized_short_pnl": 0.0
    }
    
    # Cover the short position (price dropped, profit)
    result = execute_trade(
        symbol="TSLA",
        decision="COVER",
        amount_usd=0.0,
        current_price=195.0,
        current_date="2026-01-30",
        portfolio_state=portfolio_state,
        market_cap_bil=800.0
    )
    
    # Verify short was covered
    assert result["trade_executed"] is True
    assert result["trade_details"]["action"] == "COVER"
    assert result["trade_details"]["shares"] == 50
    assert result["trade_details"]["pnl"] > 0  # Profit from price drop
    assert "TSLA" not in result["updated_portfolio_state"]["short_positions"]
    # Cash should increase by entry notional + P&L - exit spread fee
    assert result["updated_portfolio_state"]["cash"] > 50000.0
