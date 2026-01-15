#!/usr/bin/env python3
"""
Live trading orchestrator
=========================

Runs the ReasoningAgent twice per trading day for intraday portfolio management:
- 10:00 ET (10 AM) - Gap analysis + morning cycle
- 15:00 ET (3 PM) - Afternoon cycle (5 hours separation)
Uses the OpenBB MCP server as a data + execution provider and persists portfolio state to disk.

Modes:
- Daemon mode (default): long‑running scheduler that waits until the next
  scheduled time (10:00 or 15:00 ET) on a trading day, then runs the decision + trade flow.
- One‑shot mode (--once): run the flow immediately for "today" and exit;
  useful for cron or manual testing.
"""

import os
import sys
import json
import time
import asyncio
import math
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, Optional, List

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


# ============================================================================
# STRUCTURED LOGGING SETUP
# ============================================================================

def _setup_logging(log_dir: Optional[str] = None) -> logging.Logger:
    """
    Initialize structured logging for live trading.
    Logs to both console and a rotating daily log file.
    Also suppresses non-fatal MCP shutdown errors during asyncio cleanup.
    """
    if log_dir is None:
        log_dir = os.path.dirname(os.path.abspath(__file__))

    os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger_obj = logging.getLogger("live_trading")
    logger_obj.setLevel(logging.DEBUG)

    # Only add handlers if they don't already exist (prevent duplicates)
    if not logger_obj.handlers:
        # Console handler (INFO level)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)

        # File handler (DEBUG level)
        log_file = os.path.join(log_dir, "live_trading.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)

        logger_obj.addHandler(console_handler)
        logger_obj.addHandler(file_handler)

    # Suppress non-fatal MCP shutdown error logging
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.addFilter(_MCPShutdownFilter())

    return logger_obj


# Suppress MCP shutdown errors (non-fatal asyncio task context issues)
import contextlib

class _MCPShutdownFilter(logging.Filter):
    """Filter to suppress non-fatal MCP shutdown errors"""
    def filter(self, record):
        """Suppress known MCP shutdown error messages"""
        msg = record.getMessage()
        # Suppress these specific asyncio task group shutdown errors from MCP
        if ("unhandled exception during asyncio.run() shutdown" in msg or
            "Attempted to exit cancel scope in a different task" in msg):
            return False  # Don't log this
        return True  # Log everything else


@contextlib.contextmanager
def _suppress_mcp_shutdown_errors():
    """
    Context manager to suppress MCP shutdown errors during asyncio.run() cleanup.

    The MCP client may raise RuntimeError about cancel scope task context mismatch
    during event loop shutdown. This is non-fatal - the cleanup happens anyway.
    We suppress these by filtering the asyncio logger.
    """
    # Get the asyncio logger and add our filter
    asyncio_logger = logging.getLogger("asyncio")
    filter_obj = _MCPShutdownFilter()
    asyncio_logger.addFilter(filter_obj)

    try:
        yield
    finally:
        asyncio_logger.removeFilter(filter_obj)


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


# ============================================================================
# RETRY DECORATOR FOR API CALLS
# ============================================================================

def _retry_on_exception(max_retries: int = 3, wait_seconds: float = 2.0, backoff: float = 2.0):
    """
    Decorator for retrying failed API calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        wait_seconds: Initial wait time between retries (in seconds)
        backoff: Multiplier for wait time each retry (e.g., 2.0 = exponential backoff)
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            wait_time = wait_seconds

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        _logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: {e}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        await asyncio.sleep(wait_time)
                        wait_time *= backoff
                    else:
                        _logger.error(f"All {max_retries} attempts failed for {func.__name__}: {e}")

            raise last_exception

        def sync_wrapper(*args, **kwargs):
            last_exception = None
            wait_time = wait_seconds

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        _logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: {e}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        wait_time *= backoff
                    else:
                        _logger.error(f"All {max_retries} attempts failed for {func.__name__}: {e}")

            raise last_exception

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# WATERFALL ALLOCATION (for multi-stock portfolio management)
# ============================================================================

def _waterfall_allocation(
    decisions_list: List[Dict[str, Any]],
    portfolio_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Waterfall allocation: Process decisions sequentially, updating cash after each trade.
    Enforces strict 25% of remaining cash cap per trade.
    Blocks new SHORT positions when cash < 25% of initial value.

    Args:
        decisions_list: List of trade decisions (each with symbol, action, amount_usd, etc.)
        portfolio_state: Current portfolio state dict with cash, positions, last_prices, market_caps, etc.

    Returns:
        List of adjusted decisions with capped amounts and waterfall reasoning
    """
    available_cash = portfolio_state.get('cash', 0)
    initial_value = portfolio_state.get('initial_value', 100000)
    last_prices = portfolio_state.get('last_prices', {}) or {}
    max_short_per_stock_pct = portfolio_state.get('max_short_per_stock_pct', 25)
    short_cap_pct = min(0.25, (max_short_per_stock_pct or 25) / 100.0)

    # Calculate 25% of initial value threshold
    cash_threshold = initial_value * 0.25

    # Separate decisions by action type for priority processing
    close_decisions = [d for d in decisions_list if d.get('action', '').upper() in ('CLOSE', 'COVER', 'SELL')]
    short_decisions = [d for d in decisions_list if d.get('action', '').upper() == 'SHORT']
    buy_decisions = [d for d in decisions_list if d.get('action', '').upper() == 'BUY']
    other_decisions = [d for d in decisions_list if d.get('action', '').upper() not in ('CLOSE', 'COVER', 'SELL', 'SHORT', 'BUY')]

    # Build confidence map from decisions
    confidence_map = {d.get('symbol'): d.get('confidence', 0.5) for d in decisions_list}
    short_confidence_map = {d.get('symbol'): d.get('short_confidence', d.get('confidence', 0.5)) for d in decisions_list}

    # Sort BUY and SHORT by confidence (higher first) - highest conviction trades first
    buy_decisions.sort(key=lambda x: confidence_map.get(x.get('symbol'), 0.5), reverse=True)
    short_decisions.sort(key=lambda x: short_confidence_map.get(x.get('symbol'), 0.5), reverse=True)

    remaining_cash = available_cash
    final_decisions = []

    # Process CLOSE/COVER/SELL first (these generate cash)
    for decision in close_decisions:
        final_decisions.append(decision)

    # Process SHORT decisions
    if available_cash < cash_threshold:
        # Block all SHORT decisions when cash is below threshold
        for decision in short_decisions:
            decision['amount_usd'] = 0
            decision['reasoning'] = f"{decision.get('reasoning', '')} (blocked: cash ${available_cash:,.2f} < 25% of initial ${cash_threshold:,.2f})"
            decision['action'] = 'NEUTRAL'
        final_decisions.extend(short_decisions)
    else:
        # Normal SHORT processing with waterfall capping
        for decision in short_decisions:
            symbol = decision.get('symbol')
            requested_amount = abs(float(decision.get('amount_usd', 0) or 0))
            price = last_prices.get(symbol, 0)

            if price <= 0:
                continue

            # Calculate cap: 25% of remaining cash (further limited by max_short_per_stock_pct)
            cap = min(remaining_cash * 0.25, remaining_cash * short_cap_pct)
            capped_amount = min(requested_amount, cap)

            if capped_amount < price:
                continue  # Skip if can't afford 1 share

            shares = int(capped_amount // price)
            if shares < 1:
                continue

            final_amount = shares * price

            # Calculate spread fee (matching execute_trade formula)
            market_cap_bil = 10  # fallback
            mcaps = portfolio_state.get('market_caps', {})
            if symbol in mcaps:
                try:
                    mcval = float(mcaps[symbol])
                    if mcval > 0:
                        market_cap_bil = mcval
                except Exception:
                    pass

            # Spread rate: 0.0006 + 0.0010 + (1.0 / sqrt(market_cap_bil))
            base_rate = 0.0006 + 0.0010
            spread_rate = base_rate + (1.0 / math.sqrt(market_cap_bil))
            spread_fee = final_amount * spread_rate

            # If trade would cause overspend, reduce or skip
            if final_amount + spread_fee > remaining_cash:
                shares = int(remaining_cash // (price * (1 + spread_rate)))
                if shares < 1:
                    continue
                final_amount = shares * price
                spread_fee = final_amount * spread_rate

            decision['amount_usd'] = final_amount
            decision['reasoning'] = f"{decision.get('reasoning', '')} (waterfall: ${final_amount:,.2f}, {shares} shares, spread_fee: ${spread_fee:,.2f})"
            final_decisions.append(decision)

            # Deduct from remaining cash
            remaining_cash -= (final_amount + spread_fee)

    # Process BUY decisions
    for decision in buy_decisions:
        symbol = decision.get('symbol')
        requested_amount = abs(float(decision.get('amount_usd', 0) or 0))
        price = last_prices.get(symbol, 0)

        if price <= 0:
            continue

        # Calculate cap: 25% of remaining cash
        buy_cap = remaining_cash * 0.25

        # Cap the requested amount
        capped_amount = min(requested_amount, buy_cap)

        # Ensure at least 1 share
        if capped_amount < price:
            continue  # Skip if can't afford 1 share

        # Round down to whole shares
        shares = int(capped_amount // price)
        if shares < 1:
            continue

        final_amount = shares * price

        # Update remaining cash
        remaining_cash -= final_amount

        decision['amount_usd'] = final_amount
        decision['reasoning'] = f"{decision.get('reasoning', '')} (waterfall: ${final_amount:,.2f}, {shares} shares)"
        final_decisions.append(decision)

    # Add other decisions (NEUTRAL, MAINTAIN, etc.)
    final_decisions.extend(other_decisions)

    return final_decisions


# Initialize global logger
_logger = _setup_logging()


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
        _logger.warning("⚠️  ALPACA_ENABLED is true but ALPACA_API_KEY / ALPACA_API_SECRET are missing; skipping Alpaca execution.")
        return None

    # Check if user accidentally put the base URL in ALPACA_API_KEY
    if api_key.startswith("http://") or api_key.startswith("https://"):
        _logger.warning("⚠️  ALPACA_API_KEY appears to be a URL, not an API key token.")
        _logger.warning("   ALPACA_API_KEY should be your actual API key (token string), not the base URL.")
        _logger.warning("   The base URL is automatically set based on ALPACA_PAPER setting.")
        _logger.warning("   Skipping Alpaca execution.")
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
            _logger.info(f"🦙 Alpaca client initialised ({mode} mode).")
            _logger.info(f"   Account: {account.account_number} | Buying Power: ${float(account.buying_power):,.2f}")
        except Exception as auth_exc:  # noqa: BLE001
            _logger.error(f"❌ Alpaca authentication failed: {auth_exc}")
            _logger.error(f"   Please verify your API keys are correct for {mode} trading.")
            _logger.error(f"   Paper trading keys are different from live trading keys.")
            _logger.error(f"   Get your keys from: https://app.alpaca.markets/paper/dashboard/overview")
            _ALPACA_CLIENT = None
            return None

    except Exception as exc:  # noqa: BLE001
        _logger.error(f"❌ Failed to create Alpaca TradingClient: {exc}")
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

    _logger.info(
        f"🦙 Alpaca hook | date={trade_date.isoformat()} symbol={symbol} "
        f"decision={decision} amount_usd={amount_usd} price={current_price}"
    )

    # BUY / SHORT: simple market order, sized by amount_usd
    if decision in {"BUY", "SHORT"}:
        if amount_usd <= 0 or not current_price or current_price <= 0:
            _logger.warning("⚠️  Alpaca: missing amount or price for BUY/SHORT; skipping broker order.")
            return

        qty = int(amount_usd // float(current_price))
        if qty <= 0:
            _logger.warning("⚠️  Alpaca: computed quantity is 0; skipping broker order.")
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
            _logger.info(f"✅ Alpaca market {decision} submitted: {order}")
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            _logger.error(f"❌ Alpaca {decision} order failed: {error_msg}")
            if "401" in error_msg or "not authorized" in error_msg.lower():
                _logger.error("   ⚠️  Authentication error - please verify your API keys are correct.")
                _logger.error("   ⚠️  Make sure you're using PAPER trading keys (not live trading keys).")
                _logger.error("   ⚠️  Get paper keys from: https://app.alpaca.markets/paper/dashboard/overview")
        return

    # SELL / CLOSE: let Alpaca work out the size by closing the position
    if decision in {"SELL", "CLOSE"}:
        try:
            order = client.close_position(symbol)
            _logger.info(f"✅ Alpaca close position submitted for {symbol}: {order}")
        except Exception as exc:  # noqa: BLE001
            _logger.error(f"❌ Alpaca close_position failed for {symbol}: {exc}")
        return


def _get_live_trade_dir() -> str:
    """Directory where live trading state + logs are stored."""
    return os.path.dirname(os.path.abspath(__file__))


def _portfolio_state_path(mode: str = "paper") -> str:
    """
    Get portfolio state file path based on mode.

    File layout (for user clarity):
      - analysis / "Investment Analysis Only" mode:
          theoretical_portfolio.json  -> theoretical / investment-only portfolio
      - paper trading mode:
          portfolio_state.json       -> paper trading portfolio state
      - alpaca_live:
          no local JSON file (state comes from Alpaca account)
    """
    live_trade_dir = _get_live_trade_dir()
    if mode == "analysis":
        return os.path.join(live_trade_dir, "theoretical_portfolio.json")
    elif mode == "alpaca_live":
        # Alpaca mode doesn't use a file
        return None
    else:  # paper
        return os.path.join(live_trade_dir, "portfolio_state.json")


def _portfolio_history_path() -> str:
    return os.path.join(_get_live_trade_dir(), "portfolio_history.jsonl")


def validate_portfolio_state(state: PortfolioState) -> None:
    """
    Validate portfolio state and log warnings for suspicious states.

    Args:
        state: Portfolio state to validate
    """
    if state.cash < 0:
        _logger.warning(f"⚠️  Portfolio has negative cash: ${state.cash:,.2f}")

    # Validate positions have required fields
    for symbol, pos in (state.positions or {}).items():
        if "shares" not in pos or "avg_price" not in pos:
            _logger.warning(f"⚠️  Position {symbol} missing required fields: {pos}")

    for symbol, pos in (state.short_positions or {}).items():
        if "shares" not in pos or "avg_price" not in pos:
            _logger.warning(f"⚠️  Short position {symbol} missing required fields: {pos}")

    # Check last_prices exist for positions
    for symbol in (state.positions or {}):
        if symbol not in (state.last_prices or {}):
            _logger.warning(f"⚠️  Position {symbol} missing last_price")


def _fetch_alpaca_portfolio() -> PortfolioState:
    """
    Fetch live portfolio state from Alpaca account.

    Returns:
        PortfolioState object with current Alpaca positions

    Raises:
        Exception if Alpaca credentials not configured or API call fails
    """
    client = _get_alpaca_client()
    if client is None:
        raise ValueError("Alpaca client not available. Check ALPACA_ENABLED and credentials.")

    _logger.info("🦙 Fetching portfolio from Alpaca...")

    # Get account info for cash
    account = client.get_account()
    cash = float(account.cash)

    # Get all positions
    positions_data = client.get_all_positions()

    positions = {}
    last_prices = {}
    market_caps = {}

    for pos in positions_data:
        symbol = pos.symbol
        shares = float(pos.qty)
        avg_price = float(pos.avg_entry_price)
        current_price = float(pos.current_price)

        if shares > 0:
            # Long position
            positions[symbol] = {
                "shares": shares,
                "avg_price": avg_price,
                "entry_date": pos.created_at.isoformat() if hasattr(pos, 'created_at') else None
            }
        elif shares < 0:
            # Short position (if supported)
            positions[symbol] = {
                "shares": abs(shares),
                "avg_price": avg_price,
                "entry_date": pos.created_at.isoformat() if hasattr(pos, 'created_at') else None,
                "is_short": True
            }

        last_prices[symbol] = current_price

    state = PortfolioState(
        cash=cash,
        positions=positions,
        short_positions={},  # Alpaca positions are in positions dict
        last_prices=last_prices,
        market_caps=market_caps
    )

    _logger.info(f"🦙 Synced Alpaca portfolio: cash=${cash:,.2f}, positions={len(positions)}")
    return state


@_retry_on_exception(max_retries=3, wait_seconds=1.0)
def load_portfolio_state(
    starting_capital: Optional[float] = None,
    mode: str = "paper",
    force_reset: bool = False
) -> PortfolioState:
    """
    Load portfolio state based on mode.

    Args:
        starting_capital: Initial capital amount
        mode: "paper" (portfolio_state.json), "analysis" (theoretical_portfolio.json),
              or "alpaca_live" (fetch from Alpaca API)
        force_reset: Force reset to starting_capital (analysis mode only)

    Returns:
        PortfolioState object
    """
    # If Alpaca mode, always fetch from API (no file)
    if mode == "alpaca_live":
        try:
            return _fetch_alpaca_portfolio()
        except Exception as e:
            _logger.error(f"❌ Failed to fetch portfolio from Alpaca: {e}")
            raise

    # Get appropriate file path
    path = _portfolio_state_path(mode)

    # Handle force reset for local JSON-backed modes (analysis & paper)
    if force_reset and mode in {"analysis", "paper"}:
        if path and os.path.exists(path):
            timestamp = datetime.now(tz=NY_TZ).strftime("%Y%m%d_%H%M%S")
            backup_path = path.replace(".json", f"_backup_{timestamp}.json")
            import shutil
            shutil.copy(path, backup_path)
            mode_label = "theoretical" if mode == "analysis" else "paper"
            _logger.info(f"📁 Backed up {mode_label} portfolio to {backup_path}")

        # Initialise fresh state with requested starting capital (or sensible default)
        initial_cash = starting_capital or 10000.0
        state = PortfolioState(cash=initial_cash)
        save_portfolio_state(state, mode=mode)
        mode_label = "theoretical" if mode == "analysis" else "paper"
        _logger.info(f"📁 Reset {mode_label} portfolio with cash=${state.cash:,.2f}")
        return state

    # Load existing or create new
    if not os.path.exists(path):
        initial_cash = starting_capital if starting_capital is not None else 50.0
        state = PortfolioState(cash=initial_cash)
        _logger.info(f"📁 No existing portfolio found. Initializing new state with cash=${state.cash:,.2f}.")
        save_portfolio_state(state, mode=mode)
        return state

    # Load and validate existing state
    with open(path, "r") as f:
        data = json.load(f)
    state = PortfolioState.from_dict(data)
    validate_portfolio_state(state)

    _logger.info(
        f"📁 Loaded portfolio | cash=${state.cash:,.2f}, "
        f"positions={len(state.positions)}, shorts={len(state.short_positions)}"
    )
    return state


@_retry_on_exception(max_retries=3, wait_seconds=1.0)
def save_portfolio_state(state: PortfolioState, mode: str = "paper") -> None:
    """
    Atomically save portfolio state to disk using a temporary file + rename pattern.
    This prevents data corruption if the process crashes mid-write.

    Args:
        state: Portfolio state to save
        mode: "paper" or "analysis" (alpaca_live doesn't use files)
    """
    # Alpaca mode doesn't save to file
    if mode == "alpaca_live":
        _logger.debug("🦙 Alpaca mode - not saving to file")
        return

    path = _portfolio_state_path(mode)
    if path is None:
        return

    temp_path = f"{path}.tmp"

    try:
        # Write to temporary file first
        with open(temp_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2)

        # Atomic rename (works on all platforms)
        import shutil
        shutil.move(temp_path, path)

        mode_label = "theoretical" if mode == "analysis" else "paper"
        _logger.info(f"💾 Saved {mode_label} portfolio | cash=${state.cash:.2f}")
    except Exception as e:
        mode_label = "theoretical" if mode == "analysis" else "paper"
        _logger.error(f"❌ Failed to save {mode_label} portfolio: {e}")
        # Clean up temp file if it exists
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        raise


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
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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

    _logger.info(
        f"📈 Logged portfolio history for {symbol} on {trade_date} | "
        f"equity={equity:.2f}, cash={state.cash:.2f}"
    )


def get_next_run_time(now: datetime) -> datetime:
    """
    Compute the next scheduled run time for twice-daily trading:
    - 10:00 (10 AM) America/New_York - Gap analysis + morning cycle
    - 15:00 (3 PM) America/New_York - Afternoon cycle (5 hours after morning)

    Returns the next upcoming scheduled time (whichever comes first).
    Weekends are skipped; holidays are not modeled here.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=NY_TZ)

    # Define the two trading times each day
    morning_time = now.replace(hour=10, minute=0, second=0, microsecond=0)  # 10 AM
    afternoon_time = now.replace(hour=15, minute=0, second=0, microsecond=0)   # 3 PM

    # Check if it's a trading day (weekday)
    if now.weekday() < 5:  # 0-4 = Mon-Fri
        # Return the next upcoming time (morning or afternoon)
        if now <= morning_time:
            return morning_time
        elif now <= afternoon_time:
            return afternoon_time

    # If past both times today, or if it's a weekend, move to next weekday
    next_day = now + timedelta(days=1)
    while next_day.weekday() >= 5:  # 5=Saturday, 6=Sunday
        next_day += timedelta(days=1)

    # Return morning time on the next trading day
    return next_day.replace(hour=10, minute=0, second=0, microsecond=0)


async def run_single_trading_cycle(
    symbol: str,
    trade_date: date,
    starting_capital: Optional[float] = None,
    risk_level: str = "medium",
    notes: str = "",
    mode: str = "paper",
    force_reset: bool = False,
) -> None:
    """
    Execute one full decision + trade cycle for a single symbol on a given date.

    Args:
        symbol: Ticker symbol
        trade_date: Date for trading
        starting_capital: Initial capital
        risk_level: "low", "medium", or "high"
        notes: Additional notes
        mode: "paper", "analysis", or "alpaca_live"
        force_reset: Force reset portfolio (analysis mode only)
    """
    _logger.info("=" * 80)
    _logger.info(f"🚀 Live trading cycle for {symbol} on {trade_date.isoformat()}")
    _logger.info("=" * 80)

    # 1. Load portfolio state (initialize with starting_capital if provided)
    state = load_portfolio_state(starting_capital=starting_capital, mode=mode, force_reset=force_reset)

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
        risk_level=risk_level,
        notes=notes,
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
    save_portfolio_state(updated_state, mode=mode)

    # 7. Append portfolio history record
    append_portfolio_history(updated_state, symbol, trade_date, decision_result)

    # 8. Optionally mirror the trade to Alpaca (paper account)
    _maybe_execute_with_alpaca(symbol, trade_date, decision_result)

    _logger.info("=" * 80)
    _logger.info(
        f"✅ Trading cycle complete for {symbol} on {trade_date.isoformat()} | "
        f"decision={decision_result.get('decision')} "
        f"amount={decision_result.get('amount_usd')}"
    )
    _logger.info("=" * 80)


def run_daemon(
    symbol: str,
    starting_capital: Optional[float] = None,
    risk_level: str = "medium",
    notes: str = "",
    mode: str = "paper",
) -> None:
    """
    Long‑running scheduler:
    - Computes next trading time (10:00 or 15:00 ET).
    - Sleeps until then.
    - Runs one trading cycle.
    - Repeats indefinitely.

    Args:
        symbol: Ticker symbol
        starting_capital: Initial capital
        risk_level: "low", "medium", or "high"
        notes: Additional notes
        mode: "paper" or "alpaca_live" (NOT "analysis" - analysis is one-shot only)
    """
    if mode == "analysis":
        _logger.error("❌ Analysis mode only supports one-shot runs, not daemon mode")
        return

    _logger.info(f"📡 Live trading daemon starting for symbol={symbol} (mode={mode})")
    _logger.info("   Schedule: twice per trading day at 10:00 (10 AM) and 15:00 (3 PM) America/New_York")
    while True:
        now = datetime.now(tz=NY_TZ)
        next_run = get_next_run_time(now)
        seconds_until = (next_run - now).total_seconds()

        _logger.info(
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
        asyncio.run(run_single_trading_cycle(symbol, trade_date, starting_capital, risk_level, notes, mode=mode))


def run_once(
    symbol: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    starting_capital: Optional[float] = None,
    risk_level: str = "medium",
    notes: str = "",
    mode: str = "paper",
    force_reset: bool = False,
) -> None:
    """
    Run a single trading cycle "now" for today's NY date.

    Supports both single-stock (backward compatible) and multi-stock modes.
    - If symbols list provided, uses PortfolioOrchestrator for parallel processing
    - If single symbol provided, uses single-stock trading cycle

    Args:
        symbol: Single symbol (backward compatible)
        symbols: List of symbols for multi-stock mode
        starting_capital: Initial capital
        risk_level: "low", "medium", or "high"
        notes: Additional notes
        mode: "paper", "analysis", or "alpaca_live"
        force_reset: Force reset portfolio (analysis mode only)

    Useful for cron or manual testing. Does not check the clock, it just
    uses the current America/New_York calendar date.
    """
    from portfolio_orchestrator import PortfolioOrchestrator

    trade_date = datetime.now(tz=NY_TZ).date()

    # Determine which symbols to trade
    symbols_to_trade = symbols if symbols else ([symbol] if symbol else ["AAPL"])

    _logger.info(f"🏁 One‑shot mode: mode={mode}, force_reset={force_reset}")

    if len(symbols_to_trade) > 1:
        # Multi-stock mode: use PortfolioOrchestrator
        _logger.info(
            f"🏁 Running multi-stock portfolio cycle for "
            f"{', '.join(symbols_to_trade)} on {trade_date.isoformat()} (NY date)"
        )
        orchestrator = PortfolioOrchestrator(
            symbols=symbols_to_trade,
            starting_capital=starting_capital or 50000,
            risk_level=risk_level,
            notes=notes,
            mode=mode,
            force_reset=force_reset,
            max_parallel=min(5, len(symbols_to_trade))
        )
        asyncio.run(orchestrator.process_portfolio(trade_date))
    else:
        # Single-stock mode: backward compatible
        single_symbol = symbols_to_trade[0]
        _logger.info(
            f"🏁 Running trading cycle for {single_symbol} on "
            f"{trade_date.isoformat()} (NY date)"
        )
        asyncio.run(run_single_trading_cycle(single_symbol, trade_date, starting_capital, risk_level, notes, mode=mode, force_reset=force_reset))


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


