#!/usr/bin/env python3
"""
Live trading orchestrator
=========================

Runs the ReasoningAgent twice per trading day for intraday portfolio management:
- 15:00 GMT (3 PM GMT) - Midday analysis + portfolio rebalance
- 19:00 GMT (7 PM GMT) - Evening analysis + position management
Uses the OpenBB MCP server as a data + execution provider and persists portfolio state to disk.

Modes:
- Daemon mode (default): long‑running scheduler that waits until the next
  scheduled time (15:00 or 19:00 GMT) on a trading day, then runs the decision + trade flow.
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

# ANSI color codes for clean terminal output
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

_logger = logging.getLogger(__name__)


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
UTC_TZ = ZoneInfo("UTC")


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
        # Console handler (INFO level) with yellow color
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        # Yellow color formatter for console
        console_formatter = logging.Formatter(
            f"{Colors.YELLOW}%(asctime)s [%(levelname)s] %(message)s{Colors.RESET}",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)

        # File handler (DEBUG level) - no colors for file
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
    
    # Suppress rich library console output (file paths and line numbers)
    rich_logger = logging.getLogger("rich")
    rich_logger.setLevel(logging.WARNING)
    rich_logger.propagate = False

    # Suppress HTTPX and connection logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

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
    Enforces 30% cap for BUY positions and 25% cap for SHORT positions.
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

        # Calculate cap: 30% of remaining cash for BUY positions
        buy_cap = remaining_cash * 0.30

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
    current_price = trade_details.get("price") or decision_result.get("current_price")

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
            _logger.info(f"✅ Alpaca market {decision} submitted for {symbol}: id={order.id}")
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
            _logger.info(f"✅ Alpaca close position submitted for {symbol}: id={order.id}")
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
        initial_cash = starting_capital if starting_capital is not None else 10000.0
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


def _investment_only_results_dir() -> str:
    """Directory where investment‑only analysis results are stored."""
    return os.path.join(_get_live_trade_dir(), "investment_only_results")


def _display_decision_reasoning(decision_result):
    decision = decision_result.get("decision", "UNKNOWN")
    confidence = decision_result.get("confidence", 0.0)
    reasoning = decision_result.get("reasoning", "No reasoning provided")
    
    print(f"{Colors.YELLOW}\nDecision: {decision}{Colors.RESET}")
    print(f"{Colors.YELLOW}Confidence: {confidence}{Colors.RESET}")
    print(f"{Colors.YELLOW}Reasoning: {reasoning}{Colors.RESET}\n")


def _save_investment_only_result(
    symbol: str,
    trade_date: date,
    decision_result: Dict[str, Any],
    state: Optional[PortfolioState] = None,
) -> None:
    """
    Persist a single investment‑only analysis result to disk without creating
    any portfolio history files.

    Files are written under:
        live_trade/investment_only_results/{YYYY-MM-DD}_{SYMBOL}.json

    The payload captures:
        - symbol, trade_date
        - high‑level decision fields (decision, confidence, amount_usd)
        - optional thesis / reasoning if present
        - optional portfolio snapshot (in‑memory only)
        - full raw decision_result for deeper inspection
    """
    results_dir = _investment_only_results_dir()
    os.makedirs(results_dir, exist_ok=True)

    fname = f"{trade_date.isoformat()}_{symbol.upper()}.json"
    path = os.path.join(results_dir, fname)

    payload: Dict[str, Any] = {
        "symbol": symbol.upper(),
        "trade_date": trade_date.isoformat(),
        "decision": decision_result.get("decision"),
        "confidence": decision_result.get("confidence"),
        "amount_usd": decision_result.get("amount_usd"),
        "thesis": decision_result.get("thesis") or decision_result.get("reasoning"),
        "notes": decision_result.get("notes"),
        "portfolio_snapshot": state.to_dict() if state is not None else None,
        "raw_decision": decision_result,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    with open(path, "w") as f:
        json.dump(payload, f, indent=2)

    # Log with pink color for file path
    print(f"{Colors.MAGENTA}💾 Saved investment‑only result to {path}{Colors.RESET}")
    
    # Display decision reasoning
    _display_decision_reasoning(decision_result)


def get_next_run_time(
    now: datetime,
    scheduled_times_gmt: Optional[List[str]] = None,
    first_run_date: Optional[str] = None,
    first_day_entry_time_gmt: Optional[str] = None,
) -> datetime:
    """
    Compute the next scheduled run time for trading.

    Default (backward compatible):
    - 15:00 GMT (3 PM GMT) - Midday analysis + portfolio rebalance
    - 19:00 GMT (7 PM GMT) - Evening analysis + position management

    With config (NEW):
    - scheduled_times_gmt: List of times in HH:MM format (GMT), e.g., ["15:00", "19:00"]
      Default: ["15:00", "19:00"] (3 PM GMT, 7 PM GMT)
      Can specify a single time for once-daily runs, e.g., ["15:00"]
    - first_run_date: ISO date (YYYY-MM-DD) of first run - if today, use first_day_entry_time_gmt
    - first_day_entry_time_gmt: Time in HH:MM format (GMT) for first day only

    Returns the next upcoming scheduled time (whichever comes first).
    Weekends are skipped; holidays are not modeled here.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC_TZ)
    elif now.tzinfo != UTC_TZ:
        # Convert to UTC for consistent comparison
        now = now.astimezone(UTC_TZ)

    # Parse scheduled times
    if scheduled_times_gmt is None:
        scheduled_times_gmt = ["15:00", "19:00"]  # Default: 3 PM GMT, 7 PM GMT

    # Parse time strings to (hour, minute) tuples
    scheduled_hours_minutes = []
    for time_str in scheduled_times_gmt:
        try:
            h, m = map(int, time_str.split(":"))
            scheduled_hours_minutes.append((h, m))
        except (ValueError, AttributeError):
            _logger.warning(f"Invalid time format '{time_str}', skipping")
            continue

    if not scheduled_hours_minutes:
        # Fallback to default if all parsing failed
        scheduled_hours_minutes = [(15, 0), (19, 0)]

    # Sort times for consistent ordering
    scheduled_hours_minutes.sort()

    # Check if today is the first run day
    today_date = now.date()
    is_first_day = first_run_date and first_run_date == today_date.isoformat()

    # On first day, use entry time ONLY - not the scheduled times
    if is_first_day and first_day_entry_time_gmt:
        try:
            h, m = map(int, first_day_entry_time_gmt.split(":"))
            entry_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if now <= entry_time and now.weekday() < 5:
                # Before entry time on first day - return entry time
                return entry_time
            else:
                # Past entry time on first day - skip to next day's first scheduled time
                next_day = now + timedelta(days=1)
                while next_day.weekday() >= 5:  # Skip weekends
                    next_day += timedelta(days=1)
                first_hour, first_minute = scheduled_hours_minutes[0]
                _logger.info(f"First day entry time passed. Next run on {next_day.date()} at {first_hour:02d}:{first_minute:02d} GMT")
                return next_day.replace(hour=first_hour, minute=first_minute, second=0, microsecond=0)
        except (ValueError, AttributeError):
            _logger.warning(f"Invalid entry time format '{first_day_entry_time_gmt}'")
            # Fall through to normal logic if parsing fails

    # Check if it's a trading day (weekday) - for non-first-days or if first-day logic didn't trigger
    if now.weekday() < 5:  # 0-4 = Mon-Fri
        # Find the next upcoming time today
        for hour, minute in scheduled_hours_minutes:
            scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now <= scheduled_time:
                return scheduled_time

    # If past all times today, or if it's a weekend, move to next weekday
    next_day = now + timedelta(days=1)
    while next_day.weekday() >= 5:  # 5=Saturday, 6=Sunday
        next_day += timedelta(days=1)

    # Return first scheduled time on the next trading day
    first_hour, first_minute = scheduled_hours_minutes[0]
    return next_day.replace(hour=first_hour, minute=first_minute, second=0, microsecond=0)




async def run_single_trading_cycle(
    symbol: str,
    trade_date: date,
    starting_capital: Optional[float] = None,
    notes: str = "",
    mode: str = "paper",
    force_reset: bool = False,
    current_price: Optional[float] = None,
) -> None:
    """
    Execute a single trading cycle (Analysis -> Decision -> Execution).

    1. Load/Initialize Portfolio State
    2. Setup Reasoning Agent
    3. Run Decision Logic (Agent)
    4. Execute Trades (if applicable)
    5. Update State & Persist
    """
    _logger.info("=" * 80)
    _logger.info(f"🚀 Trading Cycle: {symbol} | {trade_date} | Mode: {mode}")
    _logger.info("=" * 80)
    
    # Print clean output to console with colors
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}📊 {symbol} - {trade_date}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")

    # 1. Load Portfolio State
    #
    # In 'analysis' mode, we might want to start fresh each time (theoretical),
    # or continue a theoretical portfolio. The 'force_reset' flag controls this.
    try:
        state = load_portfolio_state(
            starting_capital=starting_capital,
            mode=mode,
            force_reset=force_reset
        )
    except Exception as e:
        _logger.error(f"❌ Failed to load portfolio state: {e}")
        return

    # If in 'alpaca_live' mode, we might want to sync positions manually if needed,
    # but load_portfolio_state should have already fetched them.
    # However, for hybrid paper/manual usage, let's respect manual overrides if any.
    if mode == "paper":
        # Optional: check if there's a manual override file to merge?
        # For now, just proceed.
        pass

    # For Analysis mode, if we didn't force reset, we just loaded the
    # existing theoretical portfolio.
    if mode == "analysis":
         _logger.info(f"📊 Analysis Mode: Cash=${state.cash:,.2f} (Theoretical)")

    # Check for manual portfolio overrides (e.g. user manually edited the JSON)
    # This is a bit advanced, but useful for debugging.
    # We'll skip complex merging logic for now to keep it robust.
    # But we will re-validate the state.
    validate_portfolio_state(state)
    
    # Print clean portfolio state with colors
    print(f"{Colors.GREEN}💰 Cash: ${state.cash:,.2f}{Colors.RESET} | {Colors.BLUE}Positions: {len(state.positions or {})}{Colors.RESET}")
    if state.positions:
        for sym, pos in state.positions.items():
            shares = pos.get('shares', 0)
            avg_price = pos.get('avg_price', 0)
            print(f"  • {Colors.BOLD}{sym}{Colors.RESET}: {shares} shares @ ${avg_price:.2f}")
    print(f"\n{Colors.YELLOW}🔍 Analyzing {symbol}...{Colors.RESET}\n")

    # 2. Initialize ReasoningAgent (MCP client connects lazily on first use)
    agent = ReasoningAgent(
        data_dir=_get_live_trade_dir(),
        use_mcp_client=True,
    )

    # 3. Build portfolio_state dict expected by ReasoningAgent
    portfolio_state_dict: Dict[str, Any] = state.to_dict()

    # 3.5 Load session config once (used for technical data and decision parameters)
    selected_categories = ["technical_indicators"]  # Default
    technical_indicators_date_range = None  # Optional optimization parameter
    allow_short_selling = False
    
    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_config.json")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config_data = json.load(f)
                if config_data.get("selected_tool_categories"):
                    selected_categories = config_data["selected_tool_categories"]
                if config_data.get("technical_indicators_date_range"):
                    technical_indicators_date_range = config_data["technical_indicators_date_range"]
                allow_short_selling = config_data.get("allow_short_selling", False)
    except Exception as e:
        _logger.debug(f"Could not load config: {e}")

    # 3.6 Fetch technical data based on user-selected tool categories

    technical_data_for_prompt = {}


    # For "analysis" mode (mode 1), disable trade execution entirely so that
    # this path becomes pure investment analysis with no theoretical trades.
    execute_trades = mode != "analysis"

    decision_result = await agent._make_decision_async(
        symbol=symbol,
        current_date=trade_date.isoformat(),
        portfolio_state=portfolio_state_dict,
        execute_trade_after=execute_trades,
        current_price=current_price,
        max_tool_iterations=5,
        notes=notes,
        technical_data=technical_data_for_prompt if technical_data_for_prompt else None,
        selected_categories=selected_categories,
        technical_indicators_date_range=technical_indicators_date_range,
        allow_short_selling=allow_short_selling,
    )

    # 5. Close MCP session cleanly
    try:
        await agent._close_mcp_session()
    except Exception:
        # Cleanup errors are non-fatal in this orchestrator
        pass

    # 6. Update portfolio state from decision_result
    if decision_result is None:
        _logger.error(f"❌ Decision result is None for {symbol} on {trade_date.isoformat()}. Cannot proceed.")
        _logger.error("   This usually indicates an error in the ReasoningAgent._make_decision_async() call.")
        return
    
    updated_state_dict = decision_result.get("portfolio_state_updated") or portfolio_state_dict
    updated_state = PortfolioState.from_dict(updated_state_dict)
    updated_state.last_run_date = trade_date.isoformat()

    if mode == "analysis":
        # Investment‑only mode:
        # - Do NOT persist portfolio JSON
        # - Do NOT append portfolio history
        # - Do NOT mirror to Alpaca
        #
        # Instead, save a lightweight investment‑only result snapshot that
        # captures the thesis/decision without creating a portfolio history.
        try:
            _save_investment_only_result(symbol, trade_date, decision_result, updated_state)
        except Exception as e:  # noqa: BLE001
            _logger.warning(f"⚠️  Failed to save investment‑only result for {symbol}: {e}")
    else:
        # Paper / Alpaca‑backed modes: persist updated portfolio + history and
        # optionally mirror trades to Alpaca.
        save_portfolio_state(updated_state, mode=mode)
        append_portfolio_history(updated_state, symbol, trade_date, decision_result)
        _maybe_execute_with_alpaca(symbol, trade_date, decision_result)

    _logger.info("=" * 80)
    _logger.info(
        f"✅ Trading cycle complete for {symbol} on {trade_date.isoformat()} | "
        f"decision={decision_result.get('decision')} "
        f"amount={decision_result.get('amount_usd')}"
    )
    _logger.info("=" * 80)


def run_daemon(
    symbols: Optional[List[str]] = None,
    symbol: Optional[str] = None,
    starting_capital: Optional[float] = None,
    notes: str = "",
    mode: str = "paper",
    scheduled_times_gmt: Optional[List[str]] = None,
    first_run_date: Optional[str] = None,
    first_day_entry_time_gmt: Optional[str] = None,
) -> None:
    """
    Long‑running scheduler:
    - Computes next trading time based on GMT schedule (default: 1 PM GMT, 7 PM GMT).
    - First day: if specified, runs at first_day_entry_time_gmt.
    - After first day: uses scheduled_times_gmt times.
    - Sleeps until then.
    - Runs trading cycles for all symbols (uses PortfolioOrchestrator for multi-stock).
    - Repeats indefinitely.

    Args:
        symbols: List of ticker symbols to trade (multi-stock mode)
        symbol: Single ticker symbol (backward compatibility)
        starting_capital: Initial capital
        notes: Additional notes
        mode: "paper" or "alpaca_live" (NOT "analysis" - analysis is one-shot only)
        scheduled_times_gmt: List of times in HH:MM format (GMT), e.g., ["15:00", "19:00"]
                            Can specify a single time for once-daily runs, e.g., ["15:00"]
        first_run_date: ISO date string (YYYY-MM-DD) of first run
        first_day_entry_time_gmt: Time in HH:MM format (GMT) for first day only
    """
    if mode == "analysis":
        _logger.error("❌ Analysis mode only supports one-shot runs, not daemon mode")
        return

    # Determine which symbols to trade
    symbols_to_trade = symbols if symbols else ([symbol] if symbol else ["AAPL"])

    # If Alpaca mode, fetch current portfolio holdings and merge with user-specified symbols
    # This ensures we analyze ALL current holdings, not just the symbols from config
    if mode == "alpaca_live":
        try:
            _logger.info("🦙 Fetching Alpaca portfolio to include current holdings...")
            alpaca_portfolio = _fetch_alpaca_portfolio()
            alpaca_symbols = list(alpaca_portfolio.positions.keys())
            
            if alpaca_symbols:
                _logger.info(f"🦙 Found {len(alpaca_symbols)} holdings in Alpaca portfolio: {', '.join(alpaca_symbols)}")
                # Merge Alpaca holdings with user-specified symbols (remove duplicates)
                original_symbols = set(symbols_to_trade)
                all_symbols = list(set(symbols_to_trade + alpaca_symbols))
                symbols_to_trade = all_symbols
                
                # Log what was added
                added_symbols = set(all_symbols) - original_symbols
                if added_symbols:
                    _logger.info(f"🦙 Added {len(added_symbols)} holdings from Alpaca: {', '.join(sorted(added_symbols))}")
            else:
                _logger.info("🦙 No current holdings in Alpaca portfolio")
        except Exception as e:
            _logger.warning(f"⚠️  Could not fetch Alpaca portfolio holdings: {e}")
            _logger.warning("   Continuing with user-specified symbols only")

    # Default to 3 PM GMT and 7 PM GMT if not specified
    if scheduled_times_gmt is None:
        scheduled_times_gmt = ["15:00", "19:00"]

    _logger.info(f"📡 Live trading daemon starting for symbols={symbols_to_trade} (mode={mode})")
    _logger.info(f"   Schedule (GMT): {', '.join(scheduled_times_gmt)}")
    if first_run_date and first_day_entry_time_gmt:
        _logger.info(f"   First day ({first_run_date}): entry at {first_day_entry_time_gmt} GMT")

    while True:
        now = datetime.now(tz=UTC_TZ)
        next_run = get_next_run_time(
            now,
            scheduled_times_gmt=scheduled_times_gmt,
            first_run_date=first_run_date,
            first_day_entry_time_gmt=first_day_entry_time_gmt,
        )
        seconds_until = (next_run - now).total_seconds()

        now_ny = now.astimezone(NY_TZ)
        _logger.info(
            f"⏰ Current time: {now.isoformat(timespec='seconds')} GMT / {now_ny.isoformat(timespec='seconds')} ET, "
            f"next run at: {next_run.isoformat(timespec='seconds')} GMT "
            f"({seconds_until:.0f}s from now)"
        )

        # Single long sleep – for a production setup you might prefer shorter
        # sleeps with health checks; here we keep it simple.
        if seconds_until > 0:
            time.sleep(seconds_until)

        # At/after scheduled time, run trading cycle for "today"
        # Use NY timezone for trade date to match market days
        trade_date = datetime.now(tz=NY_TZ).date()

        # Use PortfolioOrchestrator for multi-stock mode (same as run_once)
        if len(symbols_to_trade) > 1:
            _logger.info(
                f"🔄 Running multi-stock portfolio cycle for "
                f"{', '.join(symbols_to_trade)} on {trade_date.isoformat()}"
            )
            from portfolio_orchestrator import PortfolioOrchestrator
            
            orchestrator = PortfolioOrchestrator(
                symbols=symbols_to_trade,
                starting_capital=starting_capital or 50000,
                notes=notes,
                data_dir=_get_live_trade_dir(), # Explicitly set data_dir to live_trade
                mode=mode,
                force_reset=False,
                max_parallel=min(5, len(symbols_to_trade))
            )
            asyncio.run(orchestrator.process_portfolio(trade_date))
        else:
            # Single-stock mode: use run_single_trading_cycle
            single_symbol = symbols_to_trade[0]
            _logger.info(f"🔄 Processing {single_symbol} in daemon cycle...")
            
            # Fetch fresh current price before running trading cycle
            fresh_price = None
            if mode in ("paper", "alpaca_live"):
                try:
                    from openbb import obb
                    price_data = obb.equity.price.historical(
                        symbol=single_symbol,
                        start_date=trade_date.isoformat(),
                        end_date=trade_date.isoformat(),
                        interval="5m",
                        provider="yfinance",
                        extended_hours=True,
                    )
                    if price_data and price_data.results:
                        latest = price_data.results[-1]
                        latest_dict = latest.model_dump() if hasattr(latest, "model_dump") else latest.dict() if hasattr(latest, "dict") else latest
                        fresh_price = latest_dict.get("close")
                        _logger.info(f"💰 Pre-cycle price fetch: {single_symbol} = ${fresh_price:.2f}")
                except Exception as e:  # noqa: BLE001
                    _logger.warning(f"⚠️  Could not fetch current price for {single_symbol}: {e}")

            asyncio.run(run_single_trading_cycle(single_symbol, trade_date, starting_capital, notes, mode=mode, current_price=fresh_price))


def run_once(
    symbol: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    starting_capital: Optional[float] = None,
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
        notes: Additional notes
        mode: "paper", "analysis", or "alpaca_live"
        force_reset: Force reset portfolio (analysis mode only)

    Useful for cron or manual testing. Does not check the clock, it just
    uses the current America/New_York calendar date.
    """
    from portfolio_orchestrator import PortfolioOrchestrator

    trade_date = datetime.now(tz=NY_TZ).date()

    # Determine which symbols to trade
    if mode == "alpaca_live" and (not symbols or len(symbols) == 0):
        # For Alpaca-backed modes (paper or live), allow CLI to signal
        # "trade all open portfolio positions" by passing an empty list.
        try:
            state = load_portfolio_state(starting_capital=starting_capital, mode=mode, force_reset=force_reset)
            portfolio_symbols = list((state.positions or {}).keys())
            symbols_to_trade = portfolio_symbols if portfolio_symbols else ([symbol] if symbol else ["AAPL"])
        except Exception as e:
            _logger.error(f"❌ Failed to load Alpaca portfolio symbols: {e}")
            symbols_to_trade = ([symbol] if symbol else ["AAPL"])
    else:
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
            notes=notes,
            data_dir=_get_live_trade_dir(), # Explicitly set data_dir to live_trade
            mode=mode,
            force_reset=force_reset,
            max_parallel=min(1, len(symbols_to_trade))
        )
        asyncio.run(orchestrator.process_portfolio(trade_date))
    else:
        # Single-stock mode: backward compatible
        single_symbol = symbols_to_trade[0]
        _logger.info(
            f"🏁 Running trading cycle for {single_symbol} on "
            f"{trade_date.isoformat()} (NY date)"
        )
        asyncio.run(run_single_trading_cycle(single_symbol, trade_date, starting_capital, notes, mode=mode, force_reset=force_reset))


def _load_session_config() -> Optional[Dict[str, Any]]:
    """Load session configuration from session_config.json if it exists."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_config.json")
    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        _logger.warning(f"⚠️  Failed to load session_config.json: {e}")
        return None


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

    # Try to load session config
    session_config = _load_session_config()

    if args.once:
        if session_config:
            # Use config if available
            symbols = session_config.get("symbols", [args.symbol.upper()])
            starting_capital = session_config.get("starting_capital")
            notes = session_config.get("notes", "")
            # Map trade_mode to actual mode
            trade_mode = session_config.get("trade_mode", "paper")
            mode = "alpaca_live" if trade_mode == "live" else "paper"

            run_once(
                symbols=symbols,
                starting_capital=starting_capital,
                notes=notes,
                mode=mode,
                force_reset=session_config.get("force_reset_portfolio", False),
            )
        else:
            run_once(args.symbol.upper())
    else:
        if session_config:
            # Use config if available
            symbols = session_config.get("symbols", [args.symbol.upper()])
            starting_capital = session_config.get("starting_capital")
            notes = session_config.get("notes", "")
            # Map trade_mode to actual mode
            trade_mode = session_config.get("trade_mode", "paper")
            mode = "alpaca_live" if trade_mode == "live" else "paper"

            # Extract scheduling parameters
            scheduled_times_gmt = session_config.get("scheduled_times_gmt")
            first_run_date = session_config.get("first_run_date")
            first_day_entry_time_gmt = session_config.get("first_day_entry_time_gmt")

            _logger.info(f"📋 Loaded config: symbols={symbols}, mode={mode}, first_day={first_run_date}")

            run_daemon(
                symbols=symbols,
                starting_capital=starting_capital,
                notes=notes,
                mode=mode,
                scheduled_times_gmt=scheduled_times_gmt,
                first_run_date=first_run_date,
                first_day_entry_time_gmt=first_day_entry_time_gmt,
            )
        else:
            run_daemon(symbol=args.symbol.upper())


