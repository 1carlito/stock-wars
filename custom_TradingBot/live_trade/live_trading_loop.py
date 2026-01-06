#!/usr/bin/env python3
"""
Live trading orchestrator
=========================

Runs the ReasoningAgent once per trading day, 1 hour before US market close
(15:00 America/New_York), using the OpenBB MCP server as a data + execution
provider and persisting portfolio state to disk.

Modes:
- Daemon mode (default): long‑running scheduler that waits until the next
  15:00 ET on a trading day, then runs the decision + trade flow.
- One‑shot mode (--once): run the flow immediately for "today" and exit;
  useful for cron or manual testing.
"""

import os
import sys
import json
import time
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional

from dotenv import load_dotenv

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - older Python fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore


# Ensure project root (custom_TradingBot) is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Load environment variables (for Alpaca keys, etc.)
load_dotenv()

# Use the live_trade-specific ReasoningAgent copy
try:
    from .ReasoningAgent import ReasoningAgent  # noqa: E402
except ImportError:
    # Fallback for direct execution
    _live_trade_dir = os.path.dirname(os.path.abspath(__file__))
    if _live_trade_dir not in sys.path:
        sys.path.insert(0, _live_trade_dir)
    from ReasoningAgent import ReasoningAgent  # noqa: E402


# Optional Alpaca integration (paper trading by default)
try:  # pragma: no cover - optional dependency
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    ALPACA_AVAILABLE = True
except Exception:  # pragma: no cover - if alpaca-py is not installed
    TradingClient = None  # type: ignore[assignment]
    MarketOrderRequest = None  # type: ignore[assignment]
    OrderSide = None  # type: ignore[assignment]
    TimeInForce = None  # type: ignore[assignment]
    ALPACA_AVAILABLE = False


NY_TZ = ZoneInfo("America/New_York")


@dataclass
class PortfolioState:
    """
    Persistent portfolio state for live / paper trading.

    Currencies are nominal (we'll use the same float numbers regardless of GBP/USD),
    starting with 50.0 as requested, which is enough to verify that the workflow
    is wired correctly before scaling up.
    """

    cash: float = 50.0
    positions: Dict[str, Dict[str, Any]] = None
    short_positions: Dict[str, Dict[str, Any]] = None
    last_prices: Dict[str, float] = None
    market_caps: Dict[str, float] = None
    realized_short_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_run_date: Optional[str] = None  # YYYY-MM-DD in America/New_York

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Normalize None -> empty dicts for JSON consumers
        d["positions"] = d["positions"] or {}
        d["short_positions"] = d["short_positions"] or {}
        d["last_prices"] = d["last_prices"] or {}
        d["market_caps"] = d["market_caps"] or {}
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PortfolioState":
        return cls(
            cash=float(data.get("cash", 50.0)),
            positions=data.get("positions") or {},
            short_positions=data.get("short_positions") or {},
            last_prices=data.get("last_prices") or {},
            market_caps=data.get("market_caps") or {},
            realized_short_pnl=float(data.get("realized_short_pnl", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            last_run_date=data.get("last_run_date"),
        )


_ALPACA_CLIENT: Optional["TradingClient"] = None


def _get_alpaca_client() -> Optional["TradingClient"]:
    """
    Return a shared Alpaca TradingClient if:
    - alpaca-py is installed
    - ALPACA_ENABLED env var is truthy ("1", "true", "yes", "on")
    - ALPACA_API_KEY / ALPACA_API_SECRET are present

    This is intentionally minimal and geared for paper trading.
    """
    global _ALPACA_CLIENT

    if not ALPACA_AVAILABLE:
        return None

    enabled = os.getenv("ALPACA_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None

    if _ALPACA_CLIENT is not None:
        return _ALPACA_CLIENT

    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")

    if not api_key or not api_secret:
        print("⚠️  ALPACA_ENABLED is true but ALPACA_API_KEY / ALPACA_API_SECRET are missing; skipping Alpaca execution.")
        return None
    
    # Check if user accidentally put the base URL in ALPACA_API_KEY
    if api_key.startswith("http://") or api_key.startswith("https://"):
        print("⚠️  ALPACA_API_KEY appears to be a URL, not an API key token.")
        print("   ALPACA_API_KEY should be your actual API key (token string), not the base URL.")
        print("   The base URL is automatically set based on ALPACA_PAPER setting.")
        print("   Skipping Alpaca execution.")
        return None

    # Default to paper trading unless explicitly set to a live-like value
    paper_flag = os.getenv("ALPACA_PAPER", "true").lower()
    paper = paper_flag not in {"0", "false", "no", "live"}

    try:
        _ALPACA_CLIENT = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)
        mode = "paper" if paper else "live"
        
        # Test the connection by fetching account info
        try:
            account = _ALPACA_CLIENT.get_account()
            print(f"🦙 Alpaca client initialised ({mode} mode).")
            print(f"   Account: {account.account_number} | Buying Power: ${float(account.buying_power):,.2f}")
        except Exception as auth_exc:  # noqa: BLE001
            print(f"❌ Alpaca authentication failed: {auth_exc}")
            print(f"   Please verify your API keys are correct for {mode} trading.")
            print(f"   Paper trading keys are different from live trading keys.")
            print(f"   Get your keys from: https://app.alpaca.markets/paper/dashboard/overview")
            _ALPACA_CLIENT = None
            return None
            
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Failed to create Alpaca TradingClient: {exc}")
        _ALPACA_CLIENT = None

    return _ALPACA_CLIENT


def _maybe_execute_with_alpaca(
    symbol: str,
    trade_date: date,
    decision_result: Dict[str, Any],
) -> None:
    """
    Optionally mirror the simulated trade to Alpaca (paper account).

    Design:
    - No changes to internal PortfolioState – this is a side-effect for real
      (paper) trading only.
    - Kept deliberately small:
      * BUY / SHORT → market order sized by AMOUNT_USD and simulated price
      * SELL / CLOSE → delegate to Alpaca's close_position
    - Controlled entirely by env vars so it's easy to turn off:
      * ALPACA_ENABLED=true to activate
      * ALPACA_PAPER=true (default) to ensure paper trading
    """
    client = _get_alpaca_client()
    if client is None:
        return

    decision = (decision_result.get("decision") or "").upper()
    amount_usd = float(decision_result.get("amount_usd") or 0.0)

    if decision not in {"BUY", "SELL", "SHORT", "CLOSE"}:
        return

    # Pull the price the ReasoningAgent used, if available
    trade_exec = decision_result.get("trade_execution") or {}
    trade_details = trade_exec.get("trade_details") or {}
    current_price = trade_details.get("price")

    print(
        f"🦙 Alpaca hook | date={trade_date.isoformat()} symbol={symbol} "
        f"decision={decision} amount_usd={amount_usd} price={current_price}"
    )

    # BUY / SHORT: simple market order, sized by amount_usd
    if decision in {"BUY", "SHORT"}:
        if amount_usd <= 0 or not current_price or current_price <= 0:
            print("⚠️  Alpaca: missing amount or price for BUY/SHORT; skipping broker order.")
            return

        qty = int(amount_usd // float(current_price))
        if qty <= 0:
            print("⚠️  Alpaca: computed quantity is 0; skipping broker order.")
            return

        side = OrderSide.BUY if decision == "BUY" else OrderSide.SELL

        try:
            order_req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,
            )
            order = client.submit_order(order_data=order_req)
            print(f"✅ Alpaca market {decision} submitted: {order}")
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            print(f"❌ Alpaca {decision} order failed: {error_msg}")
            if "401" in error_msg or "not authorized" in error_msg.lower():
                print("   ⚠️  Authentication error - please verify your API keys are correct.")
                print("   ⚠️  Make sure you're using PAPER trading keys (not live trading keys).")
                print("   ⚠️  Get paper keys from: https://app.alpaca.markets/paper/dashboard/overview")
        return

    # SELL / CLOSE: let Alpaca work out the size by closing the position
    if decision in {"SELL", "CLOSE"}:
        try:
            order = client.close_position(symbol)
            print(f"✅ Alpaca close position submitted for {symbol}: {order}")
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Alpaca close_position failed for {symbol}: {exc}")
        return


def _get_live_trade_dir() -> str:
    """Directory where live trading state + logs are stored."""
    return os.path.dirname(os.path.abspath(__file__))


def _portfolio_state_path() -> str:
    return os.path.join(_get_live_trade_dir(), "portfolio_state.json")


def _portfolio_history_path() -> str:
    return os.path.join(_get_live_trade_dir(), "portfolio_history.jsonl")


def load_portfolio_state(starting_capital: Optional[float] = None) -> PortfolioState:
    path = _portfolio_state_path()
    if not os.path.exists(path):
        # First run: start with provided starting_capital or default
        initial_cash = starting_capital if starting_capital is not None else 50.0
        state = PortfolioState(cash=initial_cash)
        print(f"📁 No existing portfolio_state.json found. Initializing new state with cash={state.cash}.")
        save_portfolio_state(state)
        return state

    with open(path, "r") as f:
        data = json.load(f)
    state = PortfolioState.from_dict(data)
    
    # If starting_capital provided and current cash is default (50.0), update it
    if starting_capital is not None and state.cash == 50.0 and not state.positions and not state.short_positions:
        state.cash = starting_capital
        save_portfolio_state(state)
        print(f"📁 Updated portfolio_state.json with starting_capital={starting_capital:.2f}")
    
    print(
        f"📁 Loaded portfolio_state.json | cash={state.cash:.2f}, "
        f"positions={len(state.positions)}, shorts={len(state.short_positions)}"
    )
    return state


def save_portfolio_state(state: PortfolioState) -> None:
    path = _portfolio_state_path()
    with open(path, "w") as f:
        json.dump(state.to_dict(), f, indent=2)
    print(f"💾 Saved portfolio_state.json | cash={state.cash:.2f}")


def compute_portfolio_equity(state: PortfolioState) -> float:
    """
    Approximate total equity:
    - cash
    - plus value of long positions (shares * last_price)
    - plus unrealized P&L on shorts (based on avg_price vs last_price)

    This is intentionally conservative and simple; the main goal is to have a
    stable, inspectable equity time series rather than perfect CFD accounting.
    """
    equity = state.cash

    # Long positions
    for symbol, pos in (state.positions or {}).items():
        shares = float(pos.get("shares", 0.0))
        last_price = float((state.last_prices or {}).get(symbol, pos.get("avg_price", 0.0)))
        equity += shares * last_price

    # Short positions (unrealized P&L only; realized P&L is reflected in cash)
    for symbol, pos in (state.short_positions or {}).items():
        shares = float(pos.get("shares", 0.0))
        avg_price = float(pos.get("avg_price", 0.0))
        last_price = float((state.last_prices or {}).get(symbol, avg_price))
        # Short P&L: profit when price falls
        unrealized = (avg_price - last_price) * shares
        equity += unrealized

    state.unrealized_pnl = equity - state.cash
    return equity


def append_portfolio_history(
    state: PortfolioState,
    symbol: str,
    trade_date: date,
    decision_result: Dict[str, Any],
) -> None:
    """Append a single JSONL record with snapshot of equity and decision metadata."""
    path = _portfolio_history_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    equity = compute_portfolio_equity(state)
    record = {
        "timestamp_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "trade_date": trade_date.isoformat(),
        "symbol": symbol,
        "total_equity": equity,
        "cash": state.cash,
        "positions": state.positions,
        "short_positions": state.short_positions,
        "realized_short_pnl": state.realized_short_pnl,
        "unrealized_pnl": state.unrealized_pnl,
        "decision": decision_result.get("decision"),
        "confidence": decision_result.get("confidence"),
        "amount_usd": decision_result.get("amount_usd"),
        "tool_calls_made": decision_result.get("tool_calls_made"),
    }

    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")

    print(
        f"📈 Logged portfolio history for {symbol} on {trade_date} | "
        f"equity={equity:.2f}, cash={state.cash:.2f}"
    )


def get_next_run_time(now: datetime) -> datetime:
    """
    Compute the next scheduled run time at 15:00 America/New_York on a
    weekday (Mon–Fri). Weekends are skipped; holidays are not modeled here.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=NY_TZ)

    # Start from "today" at 15:00
    run_today = now.replace(hour=15, minute=0, second=0, microsecond=0)

    if now <= run_today and now.weekday() < 5:
        return run_today

    # Otherwise, move to the next weekday at 15:00
    next_day = now + timedelta(days=1)
    while next_day.weekday() >= 5:  # 5=Saturday, 6=Sunday
        next_day += timedelta(days=1)

    return next_day.replace(hour=15, minute=0, second=0, microsecond=0)


async def run_single_trading_cycle(
    symbol: str,
    trade_date: date,
    starting_capital: Optional[float] = None,
    risk_level: str = "medium",
    notes: str = "",
) -> None:
    """
    Execute one full decision + trade cycle for a single symbol on a given date.
    """
    print("=" * 80)
    print(f"🚀 Live trading cycle for {symbol} on {trade_date.isoformat()}")
    print("=" * 80)

    # 1. Load portfolio state (initialize with starting_capital if provided)
    state = load_portfolio_state(starting_capital=starting_capital)

    # 2. Initialize ReasoningAgent (MCP client connects lazily on first use)
    agent = ReasoningAgent(
        data_dir=os.path.dirname(BASE_DIR),  # project root for reasoning_decisions
        use_mcp_client=True,
    )

    # 3. Build portfolio_state dict expected by ReasoningAgent
    portfolio_state_dict: Dict[str, Any] = state.to_dict()

    # 4. Run decision with trade execution enabled, passing risk_level and notes
    decision_result = await agent._make_decision_async(
        symbol=symbol,
        current_date=trade_date.isoformat(),
        portfolio_state=portfolio_state_dict,
        execute_trade_after=True,
        current_price=None,
        max_tool_iterations=5,
    )

    # 5. Close MCP session cleanly
    try:
        await agent._close_mcp_session()
    except Exception:
        # Cleanup errors are non-fatal in this orchestrator
        pass

    # 6. Update portfolio state from decision_result
    updated_state_dict = decision_result.get("portfolio_state_updated") or portfolio_state_dict
    updated_state = PortfolioState.from_dict(updated_state_dict)
    updated_state.last_run_date = trade_date.isoformat()
    save_portfolio_state(updated_state)

    # 7. Append portfolio history record
    append_portfolio_history(updated_state, symbol, trade_date, decision_result)

    # 8. Optionally mirror the trade to Alpaca (paper account)
    _maybe_execute_with_alpaca(symbol, trade_date, decision_result)

    print("=" * 80)
    print(
        f"✅ Trading cycle complete for {symbol} on {trade_date.isoformat()} | "
        f"decision={decision_result.get('decision')} "
        f"amount={decision_result.get('amount_usd')}"
    )
    print("=" * 80)


def run_daemon(
    symbol: str,
    starting_capital: Optional[float] = None,
    risk_level: str = "medium",
    notes: str = "",
) -> None:
    """
    Long‑running scheduler:
    - Computes next 15:00 ET trading time.
    - Sleeps until then.
    - Runs one trading cycle.
    - Repeats indefinitely.
    """
    print(f"📡 Live trading daemon starting for symbol={symbol}")
    print("   Schedule: once per trading day at 15:00 America/New_York (1 hour before US close)")
    while True:
        now = datetime.now(tz=NY_TZ)
        next_run = get_next_run_time(now)
        seconds_until = (next_run - now).total_seconds()

        print(
            f"⏰ Current NY time: {now.isoformat(timespec='seconds')}, "
            f"next run at: {next_run.isoformat(timespec='seconds')} "
            f"({seconds_until:.0f}s from now)"
        )

        # Single long sleep – for a production setup you might prefer shorter
        # sleeps with health checks; here we keep it simple.
        if seconds_until > 0:
            time.sleep(seconds_until)

        # At/after scheduled time, run trading cycle for "today" in NY
        trade_date = datetime.now(tz=NY_TZ).date()
        asyncio.run(run_single_trading_cycle(symbol, trade_date, starting_capital, risk_level, notes))


def run_once(
    symbol: str,
    starting_capital: Optional[float] = None,
    risk_level: str = "medium",
    notes: str = "",
) -> None:
    """
    Run a single trading cycle "now" for today's NY date.

    Useful for cron or manual testing. Does not check the clock, it just
    uses the current America/New_York calendar date.
    """
    trade_date = datetime.now(tz=NY_TZ).date()
    print(
        f"🏁 One‑shot mode: running trading cycle for {symbol} on "
        f"{trade_date.isoformat()} (NY date)"
    )
    asyncio.run(run_single_trading_cycle(symbol, trade_date, starting_capital, risk_level, notes))


def _parse_args(argv: Optional[list] = None):
    import argparse

    parser = argparse.ArgumentParser(description="Live trading orchestrator")
    parser.add_argument(
        "--symbol",
        type=str,
        default=os.getenv("LIVE_SYMBOL", "AAPL"),
        help="Ticker symbol to trade (default from LIVE_SYMBOL env or 'AAPL').",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single trading cycle for today's NY date and exit.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    if args.once:
        run_once(args.symbol.upper())
    else:
        run_daemon(args.symbol.upper())


