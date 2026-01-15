"""
portfolio_orchestrator.py: Multi-stock portfolio orchestrator with parallel processing.

Manages analysis of multiple stocks in parallel using async tasks.
Coordinates token tracking, waterfall allocation, and trade execution.
"""

import asyncio
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Import portfolio state management
from live_trading_loop import load_portfolio_state, save_portfolio_state, PortfolioState

# Import ReasoningAgent for stock analysis
from ReasoningAgent import ReasoningAgent

# Import TokenTracker and FreshnessValidator from parent directory
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from token_tracker import TokenTracker
from freshness_validator import FreshnessValidator, DataFreshnessContext
from Tools.Sector_Tools import register_sector_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
_logger = logging.getLogger(__name__)


class PortfolioOrchestrator:
    """
    Orchestrate multi-stock portfolio analysis with parallel processing.

    Responsibilities:
      1. Manage multiple stock analyses in parallel
      2. Track token usage across all decisions
      3. Enforce portfolio-level constraints (25% per trade cap)
      4. Apply waterfall allocation algorithm
      5. Execute trades and update portfolio state
      6. Persist results and logs
    """

    def __init__(
        self,
        symbols: List[str],
        starting_capital: float,
        risk_level: str = "medium",
        notes: str = "",
        data_dir: str = ".",
        mode: str = "paper",
        force_reset: bool = False,
        max_parallel: int = 5,
    ):
        """
        Initialize portfolio orchestrator.

        Args:
            symbols: List of stock ticker symbols to analyze
            starting_capital: Starting capital for portfolio
            risk_level: Risk level for all stocks (low/medium/high)
            notes: Additional notes for context
            data_dir: Directory for saving state and logs
            mode: "paper", "analysis", or "alpaca_live"
            force_reset: Force reset portfolio (analysis mode only)
            max_parallel: Maximum parallel stock analyses (default: 5)
        """
        self.symbols = symbols
        self.starting_capital = starting_capital
        self.risk_level = risk_level
        self.notes = notes
        self.data_dir = Path(data_dir)
        self.mode = mode
        self.force_reset = force_reset
        self.max_parallel = max_parallel

        # Load or initialize portfolio state
        self.portfolio_state = load_portfolio_state(starting_capital, mode=mode, force_reset=force_reset)

        # Initialize token tracker with 100K daily limit
        self.token_tracker = TokenTracker(daily_limit=100_000)

        # Initialize freshness validator context (will be set per cycle)
        self.freshness_context: Optional[DataFreshnessContext] = None

        # Per-stock data storage
        self.stock_decisions: Dict[str, Dict[str, Any]] = {}
        self.stock_errors: Dict[str, str] = {}

        _logger.info(f"🚀 PortfolioOrchestrator initialized for {len(symbols)} stocks")

    async def process_portfolio(self, trade_date: date) -> Dict[str, Any]:
        """
        Execute complete portfolio analysis and trading cycle.

        Process flow:
          1. Check daily token budget
          2. Fetch sector rankings (shared)
          3. Analyze each stock in parallel
          4. Filter errors and add sector context
          5. Apply waterfall allocation
          6. Execute trades
          7. Save state and logs

        Args:
            trade_date: Trading date for all decisions (YYYY-MM-DD if str)

        Returns:
            Dict with decisions, trades executed, and token summary
        """
        trade_date_str = trade_date.isoformat() if isinstance(trade_date, date) else str(trade_date)

        # Initialize freshness context for this cycle
        self.freshness_context = DataFreshnessContext(trade_date_str)

        _logger.info(f"📊 Starting portfolio cycle for {len(self.symbols)} stocks on {trade_date_str}")

        # --- PHASE 0: Check token budget ---
        budget_status = self.token_tracker.check_budget()
        if not budget_status["within_budget"]:
            _logger.error(
                f"🚫 Daily token budget exceeded: "
                f"{budget_status['total_tokens']}/{budget_status['limit']} tokens used"
            )
            return {
                "error": "Daily token budget exceeded",
                "budget_status": budget_status,
                "decisions": [],
                "trades": [],
            }

        if budget_status["warning"]:
            _logger.warning(
                f"⚠️  Token budget warning: {budget_status['pct_used']:.1f}% used "
                f"({budget_status['remaining']:,} tokens remaining)"
            )

        # --- PHASE 1: Fetch sector rankings (shared) ---
        sector_ranks = await self._get_sector_rankings(trade_date_str)

        # --- PHASE 2: Parallel stock analysis ---
        _logger.info(f"🔄 Analyzing {len(self.symbols)} stocks in parallel...")
        stock_analysis_tasks = [
            self._analyze_stock(symbol, trade_date_str, sector_ranks)
            for symbol in self.symbols
        ]

        # Run with semaphore to limit parallelism
        semaphore = asyncio.Semaphore(self.max_parallel)

        async def bounded_task(task):
            async with semaphore:
                return await task

        all_results = await asyncio.gather(
            *[bounded_task(task) for task in stock_analysis_tasks],
            return_exceptions=True
        )

        # --- PHASE 3: Filter errors, validate freshness, and add sector ranks ---
        valid_decisions = self._filter_and_enrich(all_results, sector_ranks, trade_date_str)
        _logger.info(f"✅ Valid decisions: {len(valid_decisions)}/{len(self.symbols)}")

        # Log all stock results (including HOLD)
        for result in all_results:
            if isinstance(result, Exception):
                _logger.warning(f"  ⚠️  {result}")
            elif result.get("success"):
                symbol = result.get("symbol")
                decision = result.get("decision", "HOLD")
                confidence = result.get("confidence", 0.0)
                _logger.info(f"  📊 {symbol}: {decision} (confidence: {confidence:.0%})")
            else:
                symbol = result.get("symbol", "UNKNOWN")
                error = result.get("error", "Unknown error")
                _logger.warning(f"  ❌ {symbol}: {error}")

        # --- PHASE 4: Apply portfolio constraints & waterfall allocation ---
        final_decisions = self._apply_waterfall_allocation(
            valid_decisions,
            self.portfolio_state
        )
        _logger.info(f"📋 Final trade decisions: {len(final_decisions)}")

        # --- PHASE 5: Execute trades ---
        trades_executed = await self._execute_trades(final_decisions, trade_date_str)
        _logger.info(f"💰 Trades executed: {len(trades_executed)}")

        # --- PHASE 6: Save state and logs ---
        self._save_results(final_decisions, trades_executed, trade_date_str)

        # Log freshness summary
        if self.freshness_context:
            self.freshness_context.log_summary()
            freshness_summary = self.freshness_context.get_summary()
        else:
            freshness_summary = None

        return {
            "date": trade_date_str,
            "symbols_analyzed": len(self.symbols),
            "symbols_tradeable": len(self.freshness_context.tradeable_stocks) if self.freshness_context else 0,
            "symbols_skipped": len(self.freshness_context.skipped_stocks) if self.freshness_context else 0,
            "decisions": final_decisions,
            "trades": trades_executed,
            "token_summary": self.token_tracker.get_summary(),
            "freshness_summary": freshness_summary,
            "portfolio_state": self.portfolio_state,
            "errors": self.stock_errors if self.stock_errors else None,
        }

    async def _analyze_stock(
        self,
        symbol: str,
        trade_date: str,
        sector_ranks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze single stock in parallel (runs in a separate task).

        Args:
            symbol: Stock ticker symbol
            trade_date: Trading date (YYYY-MM-DD)
            sector_ranks: Sector rankings for context

        Returns:
            Dict with decision, confidence, and token usage
        """
        try:
            _logger.info(f"  📈 Analyzing {symbol}...")

            agent = ReasoningAgent(
                data_dir=str(self.data_dir),
                use_mcp_client=True
            )

            # Make decision without executing trade yet
            result = await agent._make_decision_async(
                symbol=symbol,
                current_date=trade_date,
                portfolio_state=self.portfolio_state.to_dict() if hasattr(self.portfolio_state, 'to_dict') else self.portfolio_state,
                execute_trade_after=False,
                current_price=None,
                max_tool_iterations=5,
                risk_level=self.risk_level,
                notes=self.notes,
            )

            # Extract token usage from response (if available)
            # For now, estimate tokens from response length
            token_usage = self._estimate_tokens(result)

            # Log to token tracker
            self.token_tracker.log_decision(
                symbol=symbol,
                date=trade_date,
                input_tokens=token_usage.get("input_tokens", 5000),
                output_tokens=token_usage.get("output_tokens", 2000),
                total_tokens=token_usage.get("total_tokens", 7000),
                decision=result.get("decision", "HOLD")
            )

            return {
                "symbol": symbol,
                "success": True,
                "decision": result.get("decision", "HOLD"),
                "confidence": result.get("confidence", 0.0),
                "amount_usd": result.get("amount_usd", 0.0),
                "reasoning": result.get("reasoning", ""),
                "token_usage": token_usage,
            }

        except Exception as e:
            error_msg = f"Stock analysis failed: {str(e)}"
            _logger.error(f"  ❌ {symbol}: {error_msg}")
            self.stock_errors[symbol] = error_msg

            # Log token usage for failed attempt
            self.token_tracker.log_decision(
                symbol=symbol,
                date=trade_date,
                input_tokens=2000,
                output_tokens=500,
                total_tokens=2500,
                decision="ERROR"
            )

            return {
                "symbol": symbol,
                "success": False,
                "error": error_msg,
            }

    async def _get_sector_rankings(self, trade_date: str) -> Dict[str, Any]:
        """
        Get sector rankings (runs once, shared across all stocks).

        Args:
            trade_date: Current trading date

        Returns:
            Dict with sector data indexed by sector name
        """
        try:
            from Tools.Sector_Tools import register_sector_tools

            # Create mock MCP to register and call sector tool
            class MockMCP:
                def tool(self, name):
                    def decorator(func):
                        setattr(MockMCP, f"_func_{name}", func)
                        return func
                    return decorator

            mcp = MockMCP()
            register_sector_tools(mcp)

            get_sector_rankings_fn = getattr(MockMCP, "_func_get_sector_rankings")
            result = get_sector_rankings_fn(trade_date)

            if "data" in result:
                sectors = result["data"].get("sectors", [])
                # Index by sector name for quick lookup
                return {s["name"]: s for s in sectors}

            return {}

        except Exception as e:
            _logger.warning(f"⚠️  Could not fetch sector rankings: {e}")
            return {}

    def _validate_data_freshness(
        self,
        symbol: str,
        trade_date: str,
        price_data: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Validate data freshness for a stock.

        Args:
            symbol: Stock ticker symbol
            trade_date: Trading date (YYYY-MM-DD)
            price_data: Optional price data to validate

        Returns:
            Dict with freshness status and trade decision
        """
        # For now, perform basic price data freshness check
        # In a real system, would fetch actual data from tool results
        freshness_result = FreshnessValidator.check_all_data_types(
            price_data=price_data,
            fundamental_data=None,  # Would fetch from tool results
            news_data=None,         # Would fetch from tool results
            trade_date=trade_date
        )

        # Record in freshness context
        if self.freshness_context:
            self.freshness_context.record_check(symbol, freshness_result)

        return freshness_result

    def _filter_and_enrich(
        self,
        results: List[Dict[str, Any]],
        sector_ranks: Dict[str, Any],
        trade_date: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Filter successful decisions, check freshness, and add sector context.

        Args:
            results: List of decision results from parallel analysis
            sector_ranks: Sector rankings dict
            trade_date: Trading date for freshness validation

        Returns:
            List of enriched valid decisions (skips stale data)
        """
        valid = []

        for result in results:
            if isinstance(result, Exception):
                _logger.warning(f"Task failed with exception: {result}")
                continue

            if not result.get("success", False):
                continue

            symbol = result.get("symbol", "UNKNOWN")

            # Check data freshness (skip if stale)
            # For demo, simulate freshness check
            freshness_result = {
                "can_trade": True,
                "skip_reason": None,
                "data_status": {}
            }

            if self.freshness_context:
                self.freshness_context.record_check(symbol, freshness_result)

            # If data is stale, skip this stock
            if not freshness_result["can_trade"]:
                _logger.warning(
                    f"⚠️  Skipping {symbol}: {freshness_result['skip_reason']}"
                )
                continue

            # Add sector context (for now, assume Technology sector as default)
            # In a real system, would look up symbol's actual sector
            sector_name = "Technology"  # Default
            sector_info = sector_ranks.get(sector_name, {})

            enriched = {
                **result,
                "sector": sector_name,
                "sector_rank": sector_info.get("rank", 99),
            }

            valid.append(enriched)

        return valid

    def _apply_waterfall_allocation(
        self,
        decisions: List[Dict[str, Any]],
        portfolio_state: Any
    ) -> List[Dict[str, Any]]:
        """
        Apply waterfall allocation: sort by confidence, cap trades at 25% of cash.

        Args:
            decisions: List of stock decisions
            portfolio_state: Current portfolio state (PortfolioState object)

        Returns:
            List of decisions in execution order with allocation amounts
        """
        # Sort by confidence (descending), then sector rank (ascending)
        sorted_decisions = sorted(
            decisions,
            key=lambda d: (-d.get("confidence", 0), d.get("sector_rank", 99))
        )

        # Handle both PortfolioState objects and dicts
        if hasattr(portfolio_state, 'cash'):
            remaining_cash = portfolio_state.cash
        else:
            remaining_cash = portfolio_state.get("cash", 0)

        max_per_trade = remaining_cash * 0.25  # 25% cap
        final_decisions = []

        for decision in sorted_decisions:
            if decision.get("decision") in ("HOLD", "ERROR"):
                continue

            # Calculate allocation
            requested_amount = decision.get("amount_usd", 0)
            allocated_amount = min(requested_amount, max_per_trade)

            if allocated_amount > 0:
                final_decisions.append({
                    **decision,
                    "allocated_amount": allocated_amount,
                    "requested_amount": requested_amount,
                })

                # Deduct from remaining cash (simplified)
                remaining_cash -= allocated_amount

            if remaining_cash <= 0:
                break

        return final_decisions

    async def _execute_trades(
        self,
        decisions: List[Dict[str, Any]],
        trade_date: str
    ) -> List[Dict[str, Any]]:
        """
        Execute trades and update portfolio state.
        Also mirrors trades to Alpaca paper account if enabled.

        Args:
            decisions: List of decisions to execute
            trade_date: Trading date

        Returns:
            List of executed trade details
        """
        from OpenBBMCPServer import execute_trade
        from live_trading_loop import _maybe_execute_with_alpaca

        executed_trades = []

        for decision in decisions:
            symbol = decision.get("symbol")
            decision_type = decision.get("decision")
            amount_usd = decision.get("allocated_amount", 0)

            # Derive a reasonable current price for execution:
            #  1) Prefer last_prices from portfolio_state
            #  2) Fallback to avg_price from an existing position (if any)
            #  3) If still unavailable or non-positive, skip trade to avoid
            #     divide-by-zero errors in downstream logic.
            current_price = 0.0
            state_dict = self.portfolio_state.to_dict() if hasattr(self.portfolio_state, 'to_dict') else self.portfolio_state
            last_prices = state_dict.get("last_prices") or {}
            positions = state_dict.get("positions") or {}

            if symbol in last_prices and last_prices[symbol] and last_prices[symbol] > 0:
                current_price = float(last_prices[symbol])
            elif symbol in positions:
                avg_price = positions[symbol].get("avg_price") or 0.0
                if avg_price and avg_price > 0:
                    current_price = float(avg_price)

            if current_price <= 0:
                _logger.error(
                    f"  ❌ Trade execution skipped for {symbol}: "
                    f"no valid current price available (would cause division by zero)."
                )
                executed_trades.append({
                    "symbol": symbol,
                    "decision": decision_type,
                    "amount": amount_usd,
                    "executed": False,
                    "error": "no valid current price available",
                })
                continue

            try:
                result = execute_trade(
                    symbol=symbol,
                    decision=decision_type,
                    amount_usd=amount_usd,
                    current_price=current_price,
                    current_date=trade_date,
                    portfolio_state=state_dict,
                )

                # Update portfolio state if trade executed
                if result.get("trade_executed"):
                    updated_dict = result.get("updated_portfolio_state", self.portfolio_state.to_dict() if hasattr(self.portfolio_state, 'to_dict') else self.portfolio_state)
                    # Convert back to PortfolioState object if needed
                    if isinstance(updated_dict, dict):
                        self.portfolio_state = PortfolioState.from_dict(updated_dict)
                    else:
                        self.portfolio_state = updated_dict

                    # Mirror trade to Alpaca if enabled
                    try:
                        _maybe_execute_with_alpaca(
                            symbol=symbol,
                            trade_date=__import__('datetime').datetime.strptime(trade_date, '%Y-%m-%d').date(),
                            decision_result={
                                "decision": decision_type,
                                "amount_usd": amount_usd,
                                "current_price": 0.0,
                            }
                        )
                    except Exception as alpaca_error:
                        _logger.warning(f"  ⚠️  Alpaca execution failed for {symbol}: {alpaca_error}")

                executed_trades.append({
                    "symbol": symbol,
                    "decision": decision_type,
                    "amount": amount_usd,
                    "executed": result.get("trade_executed", False),
                    "details": result.get("trade_details", {}),
                })

                _logger.info(
                    f"  💾 {symbol}: {decision_type} "
                    f"${amount_usd:,.2f} - "
                    f"{'✅ Executed' if result.get('trade_executed') else '⏭️  Skipped'}"
                )

            except Exception as e:
                _logger.error(f"  ❌ Trade execution failed for {symbol}: {e}")
                executed_trades.append({
                    "symbol": symbol,
                    "decision": decision_type,
                    "amount": amount_usd,
                    "executed": False,
                    "error": str(e),
                })

        return executed_trades

    def _save_results(
        self,
        decisions: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
        trade_date: str
    ) -> None:
        """
        Save portfolio state, decisions, and logs.

        Args:
            decisions: Final trading decisions
            trades: Executed trades
            trade_date: Trading date
        """
        # Save updated portfolio state
        save_portfolio_state(self.portfolio_state, mode=self.mode)

        # Save decisions to JSON
        decisions_file = self.data_dir / "portfolio_decisions" / f"decisions_{trade_date}.json"
        decisions_file.parent.mkdir(parents=True, exist_ok=True)

        with open(decisions_file, "w") as f:
            json.dump({
                "date": trade_date,
                "decisions": decisions,
                "trades": trades,
                "token_summary": self.token_tracker.get_summary(),
            }, f, indent=2)

        _logger.info(f"  💾 Saved decisions to {decisions_file}")

    def _estimate_tokens(self, response: Dict[str, Any]) -> Dict[str, int]:
        """
        Estimate token usage from response (placeholder).

        In a real implementation, would extract from API response usage field.

        Args:
            response: Decision response dict

        Returns:
            Dict with input_tokens, output_tokens, total_tokens
        """
        # Rough estimation based on response size
        reasoning_len = len(response.get("reasoning", ""))
        decision_len = len(str(response.get("decision", "")))

        # Assume ~4 chars per token for estimation
        output_tokens = max(100, (reasoning_len + decision_len) // 4)
        input_tokens = max(5000, output_tokens * 2)  # Rough estimate

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary."""
        return {
            "symbols": self.symbols,
            "portfolio_state": self.portfolio_state,
            "token_tracker": self.token_tracker.get_summary(),
            "errors": self.stock_errors if self.stock_errors else None,
        }
