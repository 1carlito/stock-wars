"""
ReasoningAgent (live_trade variant)
===================================

Copy of the project‑level ReasoningAgent, colocated with the live OpenBB
server so we can evolve live‑trading behaviour independently of backtests.
"""

import os
import sys
import json
import time
import asyncio
import re
import inspect
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Default configuration
DEFAULT_API_TOKEN = os.getenv("DEEPSEEK_API_KEY_1") or os.getenv("DEEPSEEK_API_KEY")
MODEL_NAME = "deepseek-ai/DeepSeek-V3.1-Terminus"
CHUTES_API_URL = os.getenv("CHUTES_API_URL", "https://llm.chutes.ai/v1/chat/completions")

# Tool behavior configuration
TOOL_DEFAULT_CONFIG: Dict[str, Any] = {
    "trim": True,
    "max_items": 60,
}

TOOL_CONFIG: Dict[str, Dict[str, Any]] = {
    "get_price_history": {"trim": False},
    "get_current_price": {"trim": False},
    "get_income_statement": {"trim": True, "max_items": 6},
    "get_balance_sheet": {"trim": True, "max_items": 6},
    "get_cash_flow": {"trim": True, "max_items": 6},
    "equity_fundamental_cash": {"trim": True, "max_items": 6},
    "get_company_news": {"trim": True, "max_items": 20},
    "get_world_news": {"trim": True, "max_items": 20},
}

# MCP Client imports
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_CLIENT_AVAILABLE = True
except ImportError:
    try:
        from mcp.client.stdio import stdio_client
        from mcp.types import StdioServerParameters
        MCP_CLIENT_AVAILABLE = True
    except ImportError:
        MCP_CLIENT_AVAILABLE = False
        print("⚠️  MCP client not available. Install with: pip install mcp")

# Import execute_trade function from live_trade OpenBBMCPServer
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from OpenBBMCPServer import execute_trade  # type: ignore
    TRADE_EXECUTION_AVAILABLE = True
except ImportError:
    TRADE_EXECUTION_AVAILABLE = False
    print("⚠️  Trade execution not available. Install OpenBBMCPServer in live_trade.")


class ReasoningAgent:
    def __init__(self, data_dir=".", api_key_override=None, use_mcp_client=True):
        self.data_dir = data_dir
        self.decision_save_dir = os.path.join(self.data_dir, "reasoning_decisions")
        self.model = MODEL_NAME
        self.api_key = api_key_override or DEFAULT_API_TOKEN
        self.use_mcp_client = use_mcp_client and MCP_CLIENT_AVAILABLE
        self.mcp_session = None
        self.available_tools: List[str] = []

        if not self.api_key:
            raise ValueError("No API token provided. Set DEEPSEEK_API_KEY in environment.")

        if self.use_mcp_client:
            self._init_mcp_client()
        else:
            print("⚠️  MCP client not available, using direct imports")

        print(f"✅ ReasoningAgent (live_trade) initialized with {self.model}")

    def _init_mcp_client(self):
        """Initialize MCP client connection to live_trade OpenBB MCP Server."""
        try:
            server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OpenBBMCPServer.py")
            self.server_params = StdioServerParameters(
                command="python",
                args=[server_path],
            )
            print("📡 MCP client (live_trade) configured (will connect on first use)")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Failed to initialize MCP client: {e}")
            self.use_mcp_client = False

    async def _get_mcp_session(self):
        """Get or create MCP client session."""
        if not self.use_mcp_client:
            return None

        if self.mcp_session is None:
            try:
                print("🔄 Starting MCP server subprocess (live_trade)...")
                print(f"   Server command: {self.server_params.command} {' '.join(self.server_params.args)}")
                stdio_context = stdio_client(self.server_params)
                read, write = await stdio_context.__aenter__()
                print("   ✅ Server subprocess started, streams connected")

                print("🔄 Creating MCP client session...")
                self.mcp_session = ClientSession(read, write)

                print("🔄 Sending initialize request to MCP server...")
                try:
                    await self.mcp_session.__aenter__()
                    print("   ✅ Session context entered")
                    await self.mcp_session.initialize()
                    print("   ✅ Initialize handshake complete")
                    await asyncio.sleep(0.1)
                except Exception as init_error:  # noqa: BLE001
                    print(f"   ❌ Initialize failed: {init_error}")
                    raise

                self._stdio_context = stdio_context

                print("✅ MCP client session initialized and ready")

                print("🔍 Discovering available MCP tools...")
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        if attempt > 0:
                            wait_time = 0.2 * attempt
                            await asyncio.sleep(wait_time)

                        tools_response = await self.mcp_session.list_tools()
                        self.available_tools = [tool.name for tool in tools_response.tools]
                        print(
                            f"✅ Discovered {len(self.available_tools)} MCP tools: "
                            f"{', '.join(self.available_tools[:5])}..."
                        )
                        break
                    except Exception as tools_error:  # noqa: BLE001
                        if attempt < max_retries - 1:
                            wait_time = 0.3 * (attempt + 1)
                            print(
                                f"   ⚠️  Tool discovery failed (attempt {attempt + 1}/{max_retries}), "
                                f"retrying in {wait_time:.1f}s..."
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            print(f"   ❌ Tool discovery failed after {max_retries} attempts: {tools_error}")
                            raise
            except Exception as e:  # noqa: BLE001
                print(f"⚠️  Failed to create MCP session: {e}")
                import traceback

                traceback.print_exc()
                self.use_mcp_client = False
                return None

        return self.mcp_session

    async def _close_mcp_session(self):
        """Close MCP client session."""
        if self.mcp_session:
            try:
                await self.mcp_session.__aexit__(None, None, None)
            except Exception:
                pass
            finally:
                self.mcp_session = None

        if hasattr(self, "_stdio_context"):
            try:
                await self._stdio_context.__aexit__(None, None, None)
            except (RuntimeError, asyncio.CancelledError):
                pass
            except Exception:
                pass
            finally:
                if hasattr(self, "_stdio_context"):
                    delattr(self, "_stdio_context")

    def make_decision(
        self,
        symbol: str,
        current_date: str,
        portfolio_state: Dict,
        execute_trade_after: bool = False,
        current_price: Optional[float] = None,
        max_tool_iterations: int = 5,
    ) -> Dict:
        try:
            _ = asyncio.get_running_loop()
            raise RuntimeError(
                "make_decision() called from async context. "
                "Use 'await agent._make_decision_async(...)' instead, "
                "or call make_decision() from a non-async function."
            )
        except RuntimeError:
            return asyncio.run(
                self._make_decision_async(
                    symbol,
                    current_date,
                    portfolio_state,
                    execute_trade_after,
                    current_price,
                    max_tool_iterations,
                )
            )

    async def _make_decision_async(
        self,
        symbol: str,
        current_date: str,
        portfolio_state: Dict,
        execute_trade_after: bool,
        current_price: Optional[float],
        max_tool_iterations: int,
        risk_level: str = "medium",
        notes: str = "",
    ) -> Dict:
        try:
            try:
                mcp_session = await self._get_mcp_session() if self.use_mcp_client else None

                system_prompt = self._build_system_prompt(mcp_session, risk_level=risk_level)
                user_prompt = self._build_user_prompt(symbol, current_date, portfolio_state, notes=notes)

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]

                print("\n" + "=" * 80)
                print("🔵 FIRST STAGE REACT LOOP - INPUT TO LLM (live_trade)")
                print("=" * 80)
                print(f"\n📋 SYSTEM PROMPT ({len(system_prompt)} chars):")
                print("-" * 80)
                print(system_prompt)
                print(f"\n📋 USER PROMPT ({len(user_prompt)} chars):")
                print("-" * 80)
                print(user_prompt)
                print(f"\n📋 FULL MESSAGES (JSON):")
                print("-" * 80)
                print(json.dumps(messages, indent=2))
                print("=" * 80 + "\n")

                tool_results: List[Dict[str, Any]] = []
                iteration = 0

                while iteration < max_tool_iterations:
                    print(f"\n🔄 REACT ITERATION {iteration + 1}/{max_tool_iterations}")
                    print(f"📤 Calling LLM with {len(messages)} messages (planning/analysis stage)...")
                    response_text = self._call_chutes_api(messages)
                    print(f"📥 LLM RESPONSE ({len(response_text)} chars):")
                    print("-" * 80)
                    print(response_text)
                    print("-" * 80)

                    tool_calls = self._extract_tool_calls(response_text)

                    decision_pattern = re.compile(
                        r"^\s*DECISION:\s*(BUY|SELL|SHORT|HOLD|CLOSE)",
                        re.IGNORECASE | re.MULTILINE,
                    )
                    has_decision = bool(decision_pattern.search(response_text))

                    if has_decision and not tool_calls:
                        break

                    if mcp_session and tool_calls:
                        tool_tasks = [
                            self._execute_tool_via_mcp(mcp_session, tool_call, symbol, current_date)
                            for tool_call in tool_calls
                        ]

                        try:
                            timeout = 30 * len(tool_calls)
                            tool_results_batch = await asyncio.wait_for(
                                asyncio.gather(*tool_tasks, return_exceptions=True),
                                timeout=timeout,
                            )

                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": response_text,
                                }
                            )
                            user_tool_messages: List[str] = []

                            for tool_call, tool_result in zip(tool_calls, tool_results_batch):
                                if isinstance(tool_result, Exception):
                                    print(f"⚠️  Tool '{tool_call['name']}' error: {tool_result}")
                                    tool_result = {
                                        "error": str(tool_result),
                                        "tool": tool_call["name"],
                                        "tool_name": tool_call["name"],
                                    }

                                if isinstance(tool_result, dict) and "tool_name" not in tool_result:
                                    tool_result["tool_name"] = tool_call["name"]

                                trimmed_result = self._trim_tool_result(tool_result)
                                tool_results.append(trimmed_result)

                                tool_result_str = json.dumps(trimmed_result, indent=2)
                                result_size = len(tool_result_str)
                                max_chars = 2000
                                if result_size > max_chars:
                                    print(
                                        f"  📊 Tool '{tool_call['name']}' result: {result_size} chars "
                                        f"(will truncate for prompt)"
                                    )
                                    tool_result_str = (
                                        tool_result_str[:max_chars]
                                        + f"\n... truncated tool '{tool_call['name']}' output to {max_chars} chars ..."
                                    )
                                else:
                                    print(f"  📊 Tool '{tool_call['name']}' result: {result_size} chars")

                                user_tool_messages.append(
                                    f"Tool '{tool_call['name']}' result:\n{tool_result_str}"
                                )

                            if user_tool_messages:
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": "\n\n".join(user_tool_messages),
                                    }
                                )

                        except asyncio.TimeoutError:
                            print(f"⚠️  Tool execution timed out after {timeout}s")
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": response_text,
                                }
                            )
                            timeout_msgs: List[str] = []
                            for tool_call in tool_calls:
                                tool_result = {
                                    "error": "Tool execution timed out",
                                    "tool": tool_call["name"],
                                    "tool_name": tool_call["name"],
                                }
                                tool_results.append(tool_result)
                                timeout_msgs.append(
                                    f"Tool '{tool_call['name']}' timed out after {timeout}s"
                                )
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "\n".join(timeout_msgs),
                                }
                            )
                        except Exception as e:  # noqa: BLE001
                            print(f"⚠️  Batch tool execution error: {e}")
                            for tool_call in tool_calls:
                                tool_result = {
                                    "error": str(e),
                                    "tool": tool_call["name"],
                                    "tool_name": tool_call["name"],
                                }
                                tool_results.append(tool_result)
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": response_text,
                                }
                            )
                            messages.append(
                                {
                                    "role": "user",
                                    "content": f"Tool execution failed: {str(e)}",
                                }
                            )

                    iteration += 1

                decision_result = self._parse_response(response_text, symbol, current_date)
                decision_result["tool_calls_made"] = len(tool_results)
                decision_result["tool_results"] = tool_results
                try:
                    self._save_raw_prompt(symbol, current_date, messages)
                except Exception as e:  # noqa: BLE001
                    print(f"⚠️  Failed to save raw LLM prompt: {e}")
                self._save_decision(decision_result)

                if not current_price:
                    # Try to recover a usable current_price from any available tool data.
                    # Strategy:
                    #   1) Prefer explicit get_current_price results
                    #   2) Next, look for a bar on current_date from get_price_history
                    #   3) Finally, fall back to the latest available close on/before current_date
                    #      from ANY tool that returns OHLC data (e.g. OBV price history)
                    price_history_entries: list[dict] = []

                    for tool_result in tool_results:
                        if tool_result.get("error"):
                            continue

                        tool_name = tool_result.get("tool_name", "")
                        data = tool_result.get("data", [])

                        # 1) Direct get_current_price result (historical or quote)
                        if tool_name == "get_current_price":
                            if data and isinstance(data, list):
                                entry = data[0]
                                current_price = (
                                    entry.get("close")
                                    or entry.get("price")
                                    or entry.get("last_price")
                                    or entry.get("prev_close")
                                )
                                if current_price:
                                    break
                            continue

                        # 2) Collect any OHLC-style history (date + close) we can find
                        candidates = []
                        if isinstance(data, list):
                            candidates = data
                        elif isinstance(data, dict) and isinstance(data.get("data"), list):
                            candidates = data.get("data", [])

                        for entry in candidates:
                            if isinstance(entry, dict) and "date" in entry and "close" in entry:
                                price_history_entries.append(entry)

                    # 3) Prefer a bar exactly on current_date if present
                    if not current_price and price_history_entries:
                        same_day = [
                            e for e in price_history_entries
                            if e.get("date") == current_date and e.get("close")
                        ]
                        if same_day:
                            # Use the last bar for the current_date
                            current_price = same_day[-1].get("close")

                    # 4) If still nothing, fall back to the latest close on/before current_date
                    if not current_price and price_history_entries:
                        # Sort by date string (YYYY-MM-DD) just in case entries are unordered
                        price_history_entries.sort(key=lambda e: e.get("date", ""))
                        for entry in reversed(price_history_entries):
                            entry_date = entry.get("date", "")
                            if entry_date and entry_date <= current_date:
                                price = entry.get("close")
                                if price:
                                    current_price = price
                                    break

                if current_price:
                    # Log and expose the resolved current price so downstream
                    # orchestrators can reuse it for execution and portfolio
                    # state updates.
                    print(f"📊 Current price today is ${float(current_price):.2f}")
                    try:
                        decision_result["current_price"] = float(current_price)
                    except Exception:
                        # If casting fails, don't let it break the flow
                        pass

                if execute_trade_after and TRADE_EXECUTION_AVAILABLE:
                    if not current_price and mcp_session:
                        try:
                            print(f"🔍 Fetching current_price for {symbol} on {current_date}...")
                            price_tool_call = {
                                "name": "get_current_price",
                                "arguments": {
                                    "symbol": symbol,
                                    "current_date": current_date,
                                },
                            }
                            price_result = await self._execute_tool_via_mcp(
                                mcp_session, price_tool_call, symbol, current_date
                            )
                            if "error" not in price_result:
                                data = price_result.get("data", [])
                                if data and isinstance(data, list):
                                    entry = data[0]
                                    current_price = (
                                        entry.get("close")
                                        or entry.get("price")
                                        or entry.get("last_price")
                                        or entry.get("prev_close")
                                    )
                                    if current_price:
                                        print(f"✅ Fetched current_price: ${float(current_price):.2f}")
                                        print(f"📊 Current price today is ${float(current_price):.2f}")
                        except Exception as e:  # noqa: BLE001
                            print(f"⚠️  Failed to fetch current_price: {e}")

                    if not current_price:
                        print(
                            "⚠️  Cannot execute trade: current_price not provided "
                            "and could not be fetched"
                        )
                        print(f"   Tool results: {len(tool_results)} results")
                        decision = decision_result.get("decision", "").upper()
                        if decision in ("BUY", "SELL", "SHORT", "CLOSE"):
                            amount_usd = decision_result.get("amount_usd", 0)
                            if decision == "CLOSE" or amount_usd > 0:
                                return decision_result

                    decision = decision_result.get("decision", "").upper()
                    if decision in ("BUY", "SELL", "SHORT", "HOLD", "CLOSE"):
                        amount_usd = decision_result.get("amount_usd", 0)
                        if decision == "CLOSE" or amount_usd > 0:
                            try:
                                trade_result = execute_trade(
                                    symbol=symbol,
                                    decision=decision,
                                    amount_usd=amount_usd,
                                    current_price=float(current_price),
                                    current_date=current_date,
                                    portfolio_state=portfolio_state,
                                    market_cap_bil=portfolio_state.get("market_caps", {}).get(symbol),
                                )
                                decision_result["trade_execution"] = trade_result
                                decision_result["portfolio_state_updated"] = trade_result.get(
                                    "updated_portfolio_state"
                                )
                                print(
                                    f"✅ Trade executed: {decision} {symbol} - "
                                    f"{trade_result.get('trade_details', {}).get('action', 'UNKNOWN')}"
                                )
                            except Exception as e:  # noqa: BLE001
                                print(f"❌ Trade execution failed: {e}")
                                decision_result["trade_execution_error"] = str(e)

                    if current_price and not decision_result.get("portfolio_state_updated"):
                        updated_state = json.loads(json.dumps(portfolio_state))
                        if "last_prices" not in updated_state:
                            updated_state["last_prices"] = {}
                        updated_state["last_prices"][symbol] = float(current_price)
                        decision_result["portfolio_state_updated"] = updated_state
                else:
                    if current_price and not decision_result.get("portfolio_state_updated"):
                        updated_state = json.loads(json.dumps(portfolio_state))
                        if "last_prices" not in updated_state:
                            updated_state["last_prices"] = {}
                        updated_state["last_prices"][symbol] = float(current_price)
                        decision_result["portfolio_state_updated"] = updated_state

                return decision_result

            except Exception as e:  # noqa: BLE001
                print(f"❌ Error for {symbol}: {e}")
                return self._create_error_decision(symbol, current_date, str(e))
        finally:
            if self.use_mcp_client:
                try:
                    await self._close_mcp_session()
                except Exception:
                    # Cleanup failures should not crash the calling flow
                    pass

    def _build_system_prompt(self, mcp_session=None, risk_level: str = "medium") -> str:
        if mcp_session and self.available_tools:
            tools_list = "You have access to the following tools via MCP:\n"
            tools_list += "\n".join([f"- {tool}" for tool in self.available_tools[:20]])
            if len(self.available_tools) > 20:
                tools_list += f"\n... and {len(self.available_tools) - 20} more tools"
            tools_list += "\n\nKey FMP technical tools (when available):\n- get_fmp_rsi\n- get_fmp_ema"
            tools_list += "\n\nKey news tools (when available):\n- get_company_news\n- get_world_news"
            tools_list += "\n\nTo use a tool, format your request as:\nTOOL_CALL: tool_name(param1=value1, param2=value2)"
        else:
            tools_list = """You have access to the following analysis tools:
- get_price_history(symbol, start_date, end_date)
- calculate_rsi(symbol, start_date, end_date, length=14, target='close')
- get_fmp_rsi(symbol, start_date, end_date, period_length=14, timeframe='1day')
- calculate_bbands(symbol, start_date, end_date, length=20, std=2.0, target='close')
- calculate_atr(symbol, start_date, end_date, length=14)
- calculate_obv(symbol, start_date, end_date)
- calculate_adx(symbol, start_date, end_date, length=14)
- calculate_ema(symbol, start_date, end_date, length=50, target='close')
- get_fmp_ema(symbol, start_date, end_date, period_length=50, timeframe='1day')
- calculate_cci(symbol, start_date, end_date, length=20)
- get_current_price(symbol, current_date=None)
- get_earnings_calendar(start_date, end_date, symbol=None, current_date=None)
- get_analyst_estimates(symbol)
- get_company_profile(symbol)
- get_income_statement(symbol, period='annual', limit=5)
- get_balance_sheet(symbol, period='annual', limit=5)
- get_cash_flow(symbol, period='annual', limit=5)
- get_company_news(symbol, start_date, end_date, limit)
- get_world_news(start_date, end_date, topics=None, limit)"""

        # Risk level guidance for position sizing
        risk_guidance = {
            "low": "Capital preservation focus: Use small position sizes (5-10% of available cash per trade), prioritize stop-losses, avoid high volatility stocks.",
            "medium": "Balanced approach: Use moderate position sizes (10-20% of available cash per trade), balanced risk/reward, standard stop-losses.",
            "high": "Aggressive strategy: Use larger position sizes (25-30% of available cash per trade), higher drawdown tolerance, can take on more volatility.",
        }.get(risk_level.lower(), "Balanced approach: Use moderate position sizes (10-20% of available cash per trade), balanced risk/reward, standard stop-losses.")

        return f"""You are an expert autonomous portfolio trading agent powered by OpenBB data.
Your goal is to analyze stocks and make profitable PORTFOLIO-AWARE trading decisions.

DECISION FRAMEWORK (Portfolio-Aware):
=====================================

1. BUY
   - Stock is undervalued OR has strong positive signals (momentum, breakout, fundamental)
   - Apply to: ANY stock (new position or add to existing)
   - Position sizing: Based on confidence, available cash, and risk level

2. SELL
   - Stock is overvalued OR has strong negative signals (breakdown, deterioration, valuation)
   - Behavior depends on portfolio position:
     * IF stock is OWNED (long position): Close/reduce the long position
     * IF stock is NOT OWNED: Convert to SHORT action (short-sell opportunity)
   - Example: SELL on AAPL when you own it = close position
   - Example: SELL on AAPL when you don't own it = open short position

3. NEUTRAL
   - Signals are truly mixed or neutral - no clear edge found
   - Behavior depends on portfolio position:
     * IF stock is OWNED: Consider closing position if better opportunities exist
     * IF stock is NOT OWNED: Ignore (no action taken)

4. MAINTAIN
   - Thesis is still intact (positive OR negative signals remain unchanged)
   - Behavior depends on portfolio position:
     * IF stock is OWNED: Keep position as-is, do NOT add more shares
     * IF stock is NOT OWNED: Ignore (no action taken)

PORTFOLIO CONTEXT MATTERS:
- Long positions: Use SELL to exit or reduce when signals turn negative
- Short positions: Similar logic applies (exit when signals improve)
- Cash: Use BUY decisions to deploy capital when strong signals appear
- Risk level: {risk_level.upper()} → {risk_guidance}

{tools_list}

You operate in TWO CLEAR STAGES:

STAGE 1 - PLANNING (FIRST RESPONSE ONLY):
- Carefully decide which tools you need and with what parameters.
- For technical indicators: Use compact date ranges of ~60-90 days. These tools return pre-calculated indicator series (and may internally use longer price windows), so avoid redundant raw price-history calls unless you specifically need candles.
- For intraday 4-hour trading: Use 4-hour historical chart API when available
- For fundamentals, request only as much history as you truly need.
- For news, use short date windows and small limits.
- Output ONLY tool calls in this format (no decision yet):
  TOOL_CALL: tool_name(param1=value1, param2=value2)

STAGE 2 - ANALYSIS AND DECISION (AFTER YOU SEE TOOL RESULTS):
- When tool results are provided, use them to form a single, final trading decision.
- Check portfolio state: Are we ALREADY holding this stock? This changes SELL behavior!
- Consider the risk level when sizing positions (AMOUNT_USD).
- For SELL decisions: If not owned, this becomes a SHORT opportunity

Once you have received the data from the tool calls, output:
DECISION: [BUY/SELL/NEUTRAL/MAINTAIN]
CONFIDENCE: [0.0-1.0]
AMOUNT_USD: [Dollar amount for the trade, based on confidence, portfolio size, and risk level]
REASONING: [Detailed analysis explaining: signals found, portfolio impact, position sizing logic]
"""

    def _build_user_prompt(self, symbol, current_date, portfolio_state, notes: str = "") -> str:
        notes_section = f"\n\nAdditional Instructions:\n{notes}" if notes else ""

        # Build summary-only portfolio context (minimal tokens)
        portfolio_context = f"Portfolio State:\n- Cash: ${portfolio_state.get('cash', 0):,.2f}\n"

        # Long positions summary (symbol: shares @ avg_price)
        positions = portfolio_state.get('positions', {})
        if positions:
            portfolio_context += "- Long Positions:\n"
            for pos_symbol, pos_data in positions.items():
                shares = pos_data.get('shares', 0)
                avg_price = pos_data.get('avg_price', 0)
                portfolio_context += f"  * {pos_symbol}: {shares} shares @ ${avg_price:.2f} avg\n"
        else:
            portfolio_context += "- Long Positions: None\n"

        # Short positions summary
        short_positions = portfolio_state.get('short_positions', {})
        if short_positions:
            portfolio_context += "- Short Positions:\n"
            for pos_symbol, pos_data in short_positions.items():
                shares = pos_data.get('shares', 0)
                avg_price = pos_data.get('avg_price', 0)
                portfolio_context += f"  * {pos_symbol}: {shares} shares @ ${avg_price:.2f} avg\n"
        else:
            portfolio_context += "- Short Positions: None\n"

        portfolio_context += f"- Unrealized P&L: ${portfolio_state.get('unrealized_pnl', 0):,.2f}"

        return f"""Analyze {symbol} for trading date {current_date}.

{portfolio_context}
{notes_section}

Please use the available tools to gather data and make a decision.
Avoid lookahead bias: do not use data from after {current_date}.
"""

    def _call_chutes_api(self, messages: List[Dict]) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": 4096,
            "temperature": 0.1,
        }

        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        print(f"  📤 API Request: {len(messages)} messages, {total_chars:,} total chars")

        response = requests.post(CHUTES_API_URL, headers=headers, json=body, timeout=120)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _parse_response(self, text: str, symbol: str, date: str) -> Dict:
        decision = "NEUTRAL"  # Changed default from HOLD to NEUTRAL (portfolio-aware)
        confidence = 0.0
        amount_usd = 0.0
        reasoning = text

        decision_match = re.search(r"DECISION:\s*(\w+)", text, re.IGNORECASE)
        if decision_match:
            decision = decision_match.group(1).upper()
            # Updated valid decisions to include NEUTRAL and MAINTAIN
            if decision not in ("BUY", "SELL", "NEUTRAL", "MAINTAIN", "SHORT", "HOLD", "CLOSE"):
                decision = ""

        confidence_match = re.search(r"CONFIDENCE:\s*(\d+\.?\d*)", text, re.IGNORECASE)
        if confidence_match:
            confidence = float(confidence_match.group(1))
            if confidence > 1.0:
                confidence = confidence / 100.0

        amount_match = re.search(r"AMOUNT_USD:\s*\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
        if amount_match:
            amount_usd = float(amount_match.group(1).replace(",", ""))

        reasoning_match = re.search(
            r"REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()

        return {
            "symbol": symbol,
            "date": date,
            "decision": decision,
            "confidence": confidence,
            "amount_usd": amount_usd,
            "reasoning": reasoning,
            "raw_response": text,
        }

    def _save_decision(self, decision: Dict):
        os.makedirs(self.decision_save_dir, exist_ok=True)
        filename = f"{decision['symbol']}_{decision['date']}_decision.json"
        with open(os.path.join(self.decision_save_dir, filename), "w") as f:
            json.dump(decision, f, indent=2)

        # Extract and save news findings separately
        if "tool_results" in decision:
            self._save_news_findings(decision["symbol"], decision["date"], decision["tool_results"])

    def _extract_news_results(self, tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract only news tool results."""
        news_tools = ["get_company_news", "get_world_news"]
        return [r for r in tool_results if r.get("tool_name") in news_tools]

    def _save_news_findings(self, symbol: str, date: str, tool_results: List[Dict[str, Any]]) -> None:
        """Save raw news findings to dedicated folder."""
        news_results = self._extract_news_results(tool_results)
        if not news_results:
            return  # No news to save

        news_dir = os.path.join(self.data_dir, "news_decisions")
        os.makedirs(news_dir, exist_ok=True)

        filename = f"{symbol}_{date}_news.json"
        filepath = os.path.join(news_dir, filename)

        news_data = {
            "symbol": symbol,
            "date": date,
            "news_findings": news_results,
            "timestamp_utc": datetime.now().isoformat(),
        }

        with open(filepath, "w") as f:
            json.dump(news_data, f, indent=2)

    def _save_raw_prompt(self, symbol: str, date: str, messages: List[Dict[str, Any]]) -> None:
        os.makedirs(self.decision_save_dir, exist_ok=True)
        filename = f"{symbol}_{date}_prompt.w"
        path = os.path.join(self.decision_save_dir, filename)

        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        record = {
            "symbol": symbol,
            "date": date,
            "total_messages": len(messages),
            "total_chars": total_chars,
            "messages": messages,
        }

        with open(path, "a") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"RAW LLM PROMPT SNAPSHOT - {symbol} {date}\n")
            f.write(f"Total messages: {len(messages)}, total chars: {total_chars}\n")
            f.write("=" * 80 + "\n")
            json.dump(record, f, indent=2)
            f.write("\n")

    def _trim_tool_result(self, tool_result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(tool_result, dict):
            return tool_result

        result = dict(tool_result)
        tool_name = result.get("tool_name") or result.get("tool") or ""
        data = result.get("data")

        if not isinstance(data, list) or not data:
            return result

        config = TOOL_CONFIG.get(tool_name, TOOL_DEFAULT_CONFIG)
        if not config.get("trim", True):
            return result

        max_items = int(config.get("max_items", TOOL_DEFAULT_CONFIG["max_items"]))

        if len(data) > max_items:
            result["data"] = data[-max_items:]
            result["truncated"] = True
            result["truncated_note"] = f"Trimmed data to last {max_items} items out of {len(data)}"

        return result

    def _extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        import ast

        tool_calls: List[Dict[str, Any]] = []
        pattern = r"TOOL_CALL:\s*(\w+)\s*\(([^)]*)\)"
        matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)

        for match in matches:
            tool_name = match.group(1)
            params_str = match.group(2).strip()

            params: Dict[str, Any] = {}
            if params_str:
                param_parts: List[str] = []
                current_part = ""
                depth = 0
                in_string = False
                string_char = None
                i = 0

                while i < len(params_str):
                    char = params_str[i]
                    if char in ('"', "'") and (i == 0 or params_str[i - 1] != "\\"):
                        if not in_string:
                            in_string = True
                            string_char = char
                        elif char == string_char:
                            in_string = False
                            string_char = None
                        current_part += char
                    elif in_string:
                        current_part += char
                    elif char in ("{", "[", "("):
                        depth += 1
                        current_part += char
                    elif char in ("}", "]", ")"):
                        depth -= 1
                        current_part += char
                    elif char == "," and depth == 0:
                        if current_part.strip():
                            param_parts.append(current_part.strip())
                        current_part = ""
                    else:
                        current_part += char
                    i += 1

                if current_part.strip():
                    param_parts.append(current_part.strip())

                for param in param_parts:
                    if "=" not in param:
                        continue
                    key, value_str = param.split("=", 1)
                    key = key.strip()
                    value_str = value_str.strip()

                    try:
                        params[key] = ast.literal_eval(value_str)
                    except (ValueError, SyntaxError):
                        if (value_str.startswith('"') and value_str.endswith('"')) or (
                            value_str.startswith("'") and value_str.endswith("'")
                        ):
                            params[key] = value_str[1:-1]
                        elif value_str.lower() in ("true", "false"):
                            params[key] = value_str.lower() == "true"
                        elif value_str.lower() == "none":
                            params[key] = None
                        else:
                            try:
                                if "." in value_str:
                                    params[key] = float(value_str)
                                else:
                                    params[key] = int(value_str)
                            except ValueError:
                                params[key] = value_str

            tool_calls.append(
                {
                    "name": tool_name,
                    "arguments": params,
                }
            )

        return tool_calls

    async def _execute_tool_via_mcp(
        self,
        mcp_session: "ClientSession",
        tool_call: Dict[str, Any],
        symbol: str,
        current_date: str,
    ) -> Dict[str, Any]:
        tool_name = tool_call["name"]
        arguments = tool_call["arguments"]

        current_date_dt = None
        try:
            current_date_dt = datetime.strptime(current_date, "%Y-%m-%d")
        except Exception:
            pass

        tools_default_symbol = {
            "calculate_rsi",
            "calculate_bbands",
            "calculate_atr",
            "calculate_obv",
            "calculate_adx",
            "calculate_ema",
            "calculate_cci",
            "calculate_moving_averages",
            "calculate_volatility",
            "get_fmp_rsi",
            "get_fmp_ema",
            "get_price_history",
            "get_current_price",
            "get_income_statement",
            "get_balance_sheet",
            "get_cash_flow",
            "get_company_profile",
            "get_analyst_estimates",
            "get_company_news",
        }

        if tool_name in ["get_earnings_calendar", "fundamental_earnings_calendar"]:
            arguments.setdefault("symbol", symbol)
            if "current_date" not in arguments and current_date:
                arguments["current_date"] = current_date
        else:
            if tool_name in tools_default_symbol and "symbol" not in arguments:
                arguments["symbol"] = symbol

        if tool_name == "get_current_price" and "current_date" not in arguments:
            arguments["current_date"] = current_date

        technical_indicators_needing_dates = [
            "calculate_rsi",
            "calculate_bbands",
            "calculate_atr",
            "calculate_obv",
            "calculate_adx",
            "calculate_ema",
            "calculate_cci",
            "calculate_moving_averages",
            "calculate_volatility",
            "get_fmp_rsi",
            "get_fmp_ema",
        ]

        if tool_name in technical_indicators_needing_dates:
            if "start_date" not in arguments or "end_date" not in arguments:
                lookback_days = arguments.get("lookback_days", 200)
                if lookback_days > 252:
                    lookback_days = 252
                end_date = current_date
                if current_date_dt:
                    start_dt = current_date_dt - timedelta(days=lookback_days)
                    start_date = start_dt.strftime("%Y-%m-%d")
                else:
                    start_date = current_date
                arguments["start_date"] = start_date
                arguments["end_date"] = end_date
                arguments.pop("lookback_days", None)

        if tool_name in ["get_company_news", "get_world_news"]:
            if "start_date" not in arguments or "end_date" not in arguments:
                lookback_days = int(arguments.get("lookback_days", 3))
                if lookback_days < 1:
                    lookback_days = 1
                if lookback_days > 7:
                    lookback_days = 7
                end_date = current_date
                if current_date_dt:
                    start_dt = current_date_dt - timedelta(days=lookback_days)
                    start_date = start_dt.strftime("%Y-%m-%d")
                else:
                    start_date = current_date
                arguments["start_date"] = start_date
                arguments["end_date"] = end_date
                arguments.pop("lookback_days", None)

            try:
                limit = int(arguments.get("limit", 20))
            except (TypeError, ValueError):
                limit = 20
            if limit <= 0:
                limit = 1
            if limit > 50:
                limit = 50
            arguments["limit"] = limit

            # Clamp excessively wide ranges to the last 12 days ending at end_date
            if "start_date" in arguments and "end_date" in arguments:
                try:
                    sd = datetime.strptime(str(arguments["start_date"]), "%Y-%m-%d")
                    ed = datetime.strptime(str(arguments["end_date"]), "%Y-%m-%d")
                    if ed < sd:
                        sd, ed = ed, sd
                    if (ed - sd).days > 12:
                        sd = ed - timedelta(days=12)
                        arguments["start_date"] = sd.strftime("%Y-%m-%d")
                        arguments["end_date"] = ed.strftime("%Y-%m-%d")
                except Exception:
                    pass

        if current_date_dt and "end_date" in arguments:
            try:
                end_dt = datetime.strptime(str(arguments["end_date"]), "%Y-%m-%d")
                if end_dt > current_date_dt:
                    arguments["end_date"] = current_date
            except Exception:
                pass

        if tool_name == "get_price_history":
            if "start_date" not in arguments or "end_date" not in arguments:
                return {
                    "error": (
                        "get_price_history requires explicit start_date and end_date parameters. "
                        "Please specify dates to avoid returning too much data."
                    ),
                    "tool_name": tool_name,
                }
            try:
                if current_date_dt:
                    end = datetime.strptime(arguments["end_date"], "%Y-%m-%d")
                    if end > current_date_dt:
                        end = current_date_dt
                        arguments["end_date"] = current_date

                start = datetime.strptime(arguments["start_date"], "%Y-%m-%d")
                end = datetime.strptime(arguments["end_date"], "%Y-%m-%d")
                days_diff = (end - start).days
                if days_diff > 90:
                    arguments["start_date"] = (end - timedelta(days=90)).strftime("%Y-%m-%d")
                    print(f"⚠️  Limited get_price_history to 90 days (requested {days_diff} days)")
            except (ValueError, KeyError):
                pass

        try:
            result = await asyncio.wait_for(
                mcp_session.call_tool(tool_name, arguments),
                timeout=30.0,
            )
            if hasattr(result, "content") and result.content:
                content_text = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
                try:
                    parsed_result = json.loads(content_text)
                    if isinstance(parsed_result, dict) and "tool_name" not in parsed_result:
                        parsed_result["tool_name"] = tool_name

                    if current_date_dt and isinstance(parsed_result, dict):
                        data = parsed_result.get("data")
                        if isinstance(data, list) and data:
                            filtered = []
                            for item in data:
                                if not isinstance(item, dict):
                                    filtered.append(item)
                                    continue
                                raw_date = None
                                for key in ("date", "published_at", "publishedDate", "datetime"):
                                    value = item.get(key)
                                    if value:
                                        raw_date = str(value)[:10]
                                        break
                                if not raw_date:
                                    filtered.append(item)
                                    continue
                                try:
                                    item_dt = datetime.strptime(raw_date, "%Y-%m-%d")
                                except Exception:
                                    filtered.append(item)
                                    continue
                                if item_dt <= current_date_dt:
                                    filtered.append(item)
                            parsed_result["data"] = filtered

                    return parsed_result
                except json.JSONDecodeError:
                    return {"result": content_text, "tool_name": tool_name}
            return {"result": str(result), "tool_name": tool_name}
        except asyncio.TimeoutError:
            return {
                "error": "Tool execution timed out after 30s",
                "tool": tool_name,
                "tool_name": tool_name,
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e), "tool": tool_name, "tool_name": tool_name}

    def _create_error_decision(self, symbol, date, error) -> Dict:
        return {
            "symbol": symbol,
            "date": date,
            "decision": "HOLD",
            "confidence": 0.0,
            "reasoning": f"Error: {error}",
        }

    def __del__(self):
        # Cleanup is handled explicitly via _close_mcp_session in async context.
        pass


