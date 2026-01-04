"""
ReasoningAgent.py: OpenBB-powered AI Agent for stock analysis and trading decisions.
Uses MCP client to connect to OpenBB MCP Server for tool execution.
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
# - Keys are tool names as seen by the LLM / MCP (and fallback names where applicable)
# - Values describe how trimming should behave for that tool
TOOL_DEFAULT_CONFIG: Dict[str, Any] = {
    "trim": True,
    "max_items": 60,  # default cap for list-like "data"
}

TOOL_CONFIG: Dict[str, Dict[str, Any]] = {
    # Price tools: never trim (we already control date ranges elsewhere)
    "get_price_history": {"trim": False},
    "get_current_price": {"trim": False},
    
    # Fundamental tools: keep a small number of most recent periods
    # Fallback names (direct call) and MCP-registered names where they differ
    "get_income_statement": {"trim": True, "max_items": 6},
    "get_balance_sheet": {"trim": True, "max_items": 6},
    "get_cash_flow": {"trim": True, "max_items": 6},
    "equity_fundamental_cash": {"trim": True, "max_items": 6},
    
    # Other tools (company profile, earnings calendar, technical indicators, news, etc.)
    # will use TOOL_DEFAULT_CONFIG unless explicitly overridden here.
}

# MCP Client imports
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_CLIENT_AVAILABLE = True
except ImportError:
    try:
        # Try alternative import path
        from mcp.client.stdio import stdio_client
        from mcp.types import StdioServerParameters
        MCP_CLIENT_AVAILABLE = True
    except ImportError:
        MCP_CLIENT_AVAILABLE = False
        print("⚠️  MCP client not available. Install with: pip install mcp")

# Import execute_trade function from OpenBBMCPServer (fallback)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from OpenBBMCPServer import execute_trade
    TRADE_EXECUTION_AVAILABLE = True
except ImportError:
    TRADE_EXECUTION_AVAILABLE = False
    print("⚠️  Trade execution not available. Install OpenBBMCPServer.")

class ReasoningAgent:
    def __init__(self, data_dir=".", api_key_override=None, use_mcp_client=True):
        self.data_dir = data_dir
        self.decision_save_dir = os.path.join(self.data_dir, "reasoning_decisions")
        self.model = MODEL_NAME
        self.api_key = api_key_override or DEFAULT_API_TOKEN
        self.use_mcp_client = use_mcp_client and MCP_CLIENT_AVAILABLE
        self.mcp_session = None
        self.available_tools = []
        
        if not self.api_key:
            raise ValueError("No API token provided. Set DEEPSEEK_API_KEY in environment.")
        
        # Initialize MCP client connection if available
        if self.use_mcp_client:
            self._init_mcp_client()
        else:
            print(f"⚠️  MCP client not available, using direct imports")
            
        print(f"✅ ReasoningAgent initialized with {self.model}")
    
    def _init_mcp_client(self):
        """Initialize MCP client connection to OpenBB MCP Server"""
        try:
            # Get path to OpenBBMCPServer.py
            server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OpenBBMCPServer.py")
            
            # Configure stdio server parameters
            self.server_params = StdioServerParameters(
                command="python",
                args=[server_path]
            )
            
            print(f"📡 MCP client configured (will connect on first use)")
        except Exception as e:
            print(f"⚠️  Failed to initialize MCP client: {e}")
            self.use_mcp_client = False
    
    async def _get_mcp_session(self):
        """Get or create MCP client session"""
        if not self.use_mcp_client:
            return None
        
        if self.mcp_session is None:
            try:
                # Use stdio_client as a context manager to properly handle initialization
                # This ensures the MCP protocol handshake completes before we use the session
                print("🔄 Starting MCP server subprocess...")
                print(f"   Server command: {self.server_params.command} {' '.join(self.server_params.args)}")
                stdio_context = stdio_client(self.server_params)
                read, write = await stdio_context.__aenter__()
                print("   ✅ Server subprocess started, streams connected")
                
                print("🔄 Creating MCP client session...")
                # Create ClientSession with the streams
                self.mcp_session = ClientSession(read, write)
                
                # Initialize the session - this sends the initialize request and waits for response
                # The MCP protocol requires: initialize request → server response → initialized notification
                print("🔄 Sending initialize request to MCP server...")
                try:
                    # Enter the session context (this handles the initialize handshake)
                    await self.mcp_session.__aenter__()
                    print("   ✅ Session context entered")
                    
                    # Explicitly call initialize to ensure handshake completes
                    # This sends the initialize request and waits for the response
                    await self.mcp_session.initialize()
                    print("   ✅ Initialize handshake complete")
                    
                    # Small delay to ensure server is fully ready
                    await asyncio.sleep(0.1)
                except Exception as init_error:
                    print(f"   ❌ Initialize failed: {init_error}")
                    print(f"   Error details: {type(init_error).__name__}: {str(init_error)}")
                    raise
                
                # Store context manager for cleanup
                self._stdio_context = stdio_context
                
                # Log that MCP client is ready
                print("✅ MCP client session initialized and ready")
                
                # Discover available tools (this will fail if initialization didn't complete)
                # Add retry logic in case of timing issues
                print("🔍 Discovering available MCP tools...")
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Wait a bit longer on first attempt to ensure server is ready
                        if attempt > 0:
                            wait_time = 0.2 * attempt
                            await asyncio.sleep(wait_time)
                        
                        tools_response = await self.mcp_session.list_tools()
                        self.available_tools = [tool.name for tool in tools_response.tools]
                        print(f"✅ Discovered {len(self.available_tools)} MCP tools: {', '.join(self.available_tools[:5])}...")
                        break
                    except Exception as tools_error:
                        if attempt < max_retries - 1:
                            wait_time = 0.3 * (attempt + 1)
                            print(f"   ⚠️  Tool discovery failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s...")
                            await asyncio.sleep(wait_time)
                        else:
                            print(f"   ❌ Tool discovery failed after {max_retries} attempts: {tools_error}")
                            raise
            except Exception as e:
                print(f"⚠️  Failed to create MCP session: {e}")
                print(f"   Error type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
                self.use_mcp_client = False
                return None
        
        return self.mcp_session
    
    async def _close_mcp_session(self):
        """Close MCP client session"""
        # Close in reverse order: session first, then stdio context
        if self.mcp_session:
            try:
                # Properly exit the session context
                await self.mcp_session.__aexit__(None, None, None)
            except Exception as e:
                # Ignore cleanup errors during shutdown
                pass
            finally:
                self.mcp_session = None
        
        # Close stdio context if it exists
        # Note: This may raise RuntimeError during event loop shutdown
        # but it's harmless - the context will be cleaned up by Python
        if hasattr(self, '_stdio_context'):
            try:
                # Try to close the stdio context
                # This might fail if we're in a different task context during shutdown
                await self._stdio_context.__aexit__(None, None, None)
            except (RuntimeError, asyncio.CancelledError) as e:
                # These errors are expected during event loop shutdown
                # The context manager will be cleaned up by Python's garbage collector
                pass
            except Exception as e:
                # Other errors - log but don't fail
                pass
            finally:
                # Always remove the reference
                if hasattr(self, '_stdio_context'):
                    delattr(self, '_stdio_context')

    def make_decision(
        self, 
        symbol: str, 
        current_date: str, 
        portfolio_state: Dict,
        execute_trade_after: bool = False,
        current_price: Optional[float] = None,
        max_tool_iterations: int = 5
    ) -> Dict:
        """
        Analyze a stock and make a trading decision using OpenBB tools via MCP.
        
        Args:
            symbol: Stock ticker symbol
            current_date: Current trading date (YYYY-MM-DD)
            portfolio_state: Current portfolio state (cash, positions, P&L)
            execute_trade_after: If True, automatically execute trade after decision
            current_price: Current stock price (required if execute_trade_after=True)
            max_tool_iterations: Maximum number of tool-calling iterations
        
        Returns:
            Dict with decision and optionally trade execution result
        """
        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, raise an error suggesting to use await
            raise RuntimeError(
                "make_decision() called from async context. "
                "Use 'await agent._make_decision_async(...)' instead, "
                "or call make_decision() from a non-async function."
            )
        except RuntimeError:
            # No running loop (RuntimeError raised by get_running_loop()), safe to use asyncio.run()
            return asyncio.run(self._make_decision_async(
                symbol, current_date, portfolio_state, execute_trade_after, 
                current_price, max_tool_iterations
            ))
    
    async def _make_decision_async(
        self,
        symbol: str,
        current_date: str,
        portfolio_state: Dict,
        execute_trade_after: bool,
        current_price: Optional[float],
        max_tool_iterations: int
    ) -> Dict:
        """Async version of make_decision with MCP tool calling"""
        try:
            # 1. Get MCP session (if using MCP client)
            mcp_session = await self._get_mcp_session() if self.use_mcp_client else None
            
            # 2. Build initial prompts
            system_prompt = self._build_system_prompt(mcp_session)
            user_prompt = self._build_user_prompt(symbol, current_date, portfolio_state)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # DEBUG: Print first stage input to LLM
            print("\n" + "="*80)
            print("🔵 FIRST STAGE REACT LOOP - INPUT TO LLM")
            print("="*80)
            print(f"\n📋 SYSTEM PROMPT ({len(system_prompt)} chars):")
            print("-"*80)
            print(system_prompt)
            print(f"\n📋 USER PROMPT ({len(user_prompt)} chars):")
            print("-"*80)
            print(user_prompt)
            print(f"\n📋 FULL MESSAGES (JSON):")
            print("-"*80)
            print(json.dumps(messages, indent=2))
            print("="*80 + "\n")
            
            # 3. Tool-calling loop (simple ReAct pattern)
            tool_results = []
            iteration = 0
            
            while iteration < max_tool_iterations:
                # Call LLM
                print(f"\n🔄 REACT ITERATION {iteration + 1}/{max_tool_iterations}")
                print(f"📤 Calling LLM with {len(messages)} messages (planning/analysis stage)...")
                response_text = self._call_chutes_api(messages)
                print(f"📥 LLM RESPONSE ({len(response_text)} chars):")
                print("-"*80)
                print(response_text)
                print("-"*80)
                
                # Check if LLM wants to call a tool
                tool_calls = self._extract_tool_calls(response_text)
                
                # Only break if DECISION is present in the correct format AND there are no tool calls to execute
                # Check for exact format: "DECISION: [BUY/SELL/SHORT]" (case-insensitive, at start of line or after whitespace)
                decision_pattern = re.compile(r'^\s*DECISION:\s*(BUY|SELL|SHORT|HOLD|CLOSE)', re.IGNORECASE | re.MULTILINE)
                has_decision = bool(decision_pattern.search(response_text))
                
                if has_decision and not tool_calls:
                    break 
                
                # Execute tool calls via MCP client (in parallel for efficiency)
                if mcp_session and tool_calls:
                    # Execute all tools in parallel with timeout
                    tool_tasks = [
                        self._execute_tool_via_mcp(mcp_session, tool_call, symbol, current_date)
                        for tool_call in tool_calls
                    ]
                    
                    try:
                        # Wait for all tools to complete with a timeout (30 seconds per tool)
                        timeout = 30 * len(tool_calls)  # Total timeout based on number of tools
                        tool_results_batch = await asyncio.wait_for(
                            asyncio.gather(*tool_tasks, return_exceptions=True),
                            timeout=timeout
                        )
                        
                        # Add the model response once before all tool results
                        messages.append({
                            "role": "assistant",
                            "content": response_text,
                        })
                        user_tool_messages: List[str] = []

                        # Process results and add to conversation
                        for i, (tool_call, tool_result) in enumerate(zip(tool_calls, tool_results_batch)):
                            if isinstance(tool_result, Exception):
                                print(f"⚠️  Tool '{tool_call['name']}' error: {tool_result}")
                                tool_result = {"error": str(tool_result), "tool": tool_call['name'], "tool_name": tool_call['name']}
                            
                            # Ensure tool_name is always set for tracking
                            if isinstance(tool_result, dict) and "tool_name" not in tool_result:
                                tool_result["tool_name"] = tool_call['name']
                            
                            # Trim tool result before saving & sending back to LLM
                            trimmed_result = self._trim_tool_result(tool_result)
                            tool_results.append(trimmed_result)
                            
                            # Add trimmed tool result to conversation (bounded size)
                            tool_result_str = json.dumps(trimmed_result, indent=2)
                            result_size = len(tool_result_str)
                            max_chars = 2000  # tighter cap per tool to keep prompts small
                            if result_size > max_chars:
                                print(f"  📊 Tool '{tool_call['name']}' result: {result_size} chars (will truncate for prompt)")
                                tool_result_str = tool_result_str[:max_chars] + f"\n... truncated tool '{tool_call['name']}' output to {max_chars} chars ..."
                            else:
                                print(f"  📊 Tool '{tool_call['name']}' result: {result_size} chars")

                            user_tool_messages.append(
                                f"Tool '{tool_call['name']}' result:\n{tool_result_str}"
                            )

                        # Send a single aggregated user message containing all tool results
                        if user_tool_messages:
                            messages.append({
                                "role": "user",
                                "content": "\n\n".join(user_tool_messages),
                            })

                    except asyncio.TimeoutError:
                        print(f"⚠️  Tool execution timed out after {timeout}s")
                        # Add timeout error for each tool
                        messages.append({
                            "role": "assistant",
                            "content": response_text,
                        })
                        timeout_msgs: List[str] = []
                        for tool_call in tool_calls:
                            tool_result = {"error": "Tool execution timed out", "tool": tool_call['name'], "tool_name": tool_call['name']}
                            tool_results.append(tool_result)
                            timeout_msgs.append(
                                f"Tool '{tool_call['name']}' timed out after {timeout}s"
                            )
                        messages.append({
                            "role": "user",
                            "content": "\n".join(timeout_msgs),
                        })
                    except Exception as e:
                        print(f"⚠️  Batch tool execution error: {e}")
                        # Fallback: add error message
                        for tool_call in tool_calls:
                            tool_result = {"error": str(e), "tool": tool_call['name'], "tool_name": tool_call['name']}
                            tool_results.append(tool_result)
                        messages.append({
                            "role": "assistant",
                            "content": response_text,
                        })
                        messages.append({
                            "role": "user",
                            "content": f"Tool execution failed: {str(e)}",
                        })
                
                iteration += 1
            
            # 4. Parse final decision from last response
            decision_result = self._parse_response(response_text, symbol, current_date)
            decision_result['tool_calls_made'] = len(tool_results)
            decision_result['tool_results'] = tool_results
            # Save raw prompt/messages that the LLM saw when making this decision
            try:
                self._save_raw_prompt(symbol, current_date, messages)
            except Exception as e:
                # Don't fail the whole run if logging the prompt fails
                print(f"⚠️  Failed to save raw LLM prompt: {e}")
            self._save_decision(decision_result)
            
            # 5. Optionally execute trade if requested
            if execute_trade_after and TRADE_EXECUTION_AVAILABLE:
                if not current_price:
                    # Try to extract price from tool results (get_current_price or get_price_history)
                    for tool_result in tool_results:
                        tool_name = tool_result.get('tool_name', '')
                        if tool_name == 'get_current_price':
                            data = tool_result.get('data', [])
                            if data and isinstance(data, list) and len(data) > 0:
                                entry = data[0]
                                # Try multiple price fields (close, price, last_price, prev_close)
                                current_price = entry.get('close') or entry.get('price') or entry.get('last_price') or entry.get('prev_close')
                                if current_price:
                                    break
                        elif tool_name == 'get_price_history':
                            # Get the close price for the current_date from history
                            data = tool_result.get('data', [])
                            if data and isinstance(data, list):
                                # Find entry for current_date (exact match)
                                for entry in reversed(data):  # Start from most recent
                                    entry_date = entry.get('date', '')
                                    if entry_date == current_date:
                                        price = entry.get('close')
                                        if price:
                                            current_price = price
                                            break
                                if current_price:
                                    break
                    
                    # If still missing, try to fetch it via MCP
                    if not current_price and mcp_session:
                        try:
                            print(f"🔍 Fetching current_price for {symbol} on {current_date}...")
                            price_tool_call = {
                                "name": "get_current_price",
                                "arguments": {
                                    "symbol": symbol,
                                    "current_date": current_date
                                }
                            }
                            price_result = await self._execute_tool_via_mcp(
                                mcp_session, price_tool_call, symbol, current_date
                            )
                            if 'error' not in price_result:
                                data = price_result.get('data', [])
                                if data and isinstance(data, list) and len(data) > 0:
                                    entry = data[0]
                                    current_price = entry.get('close') or entry.get('price') or entry.get('last_price') or entry.get('prev_close')
                                    if current_price:
                                        print(f"✅ Fetched current_price: ${current_price:.2f}")
                        except Exception as e:
                            print(f"⚠️  Failed to fetch current_price: {e}")
                    
                    # No fallback to portfolio state - must have current price from tools
                    if not current_price:
                        print(f"⚠️  Cannot execute trade: current_price not provided and could not be fetched")
                        print(f"   Tool results: {len(tool_results)} results")
                        return decision_result
                
                # Execute trade if decision is actionable
                decision = decision_result.get('decision', '').upper()
                if decision in ('BUY', 'SELL', 'SHORT', 'HOLD', 'CLOSE'):
                    amount_usd = decision_result.get('amount_usd', 0)
                    if decision == 'CLOSE' or amount_usd > 0:
                        try:
                            trade_result = execute_trade(
                                symbol=symbol,
                                decision=decision,
                                amount_usd=amount_usd,
                                current_price=current_price,
                                current_date=current_date,
                                portfolio_state=portfolio_state,
                                market_cap_bil=portfolio_state.get('market_caps', {}).get(symbol)
                            )
                            decision_result['trade_execution'] = trade_result
                            decision_result['portfolio_state_updated'] = trade_result.get('updated_portfolio_state')
                            print(f"✅ Trade executed: {decision} {symbol} - {trade_result.get('trade_details', {}).get('action', 'UNKNOWN')}")
                        except Exception as e:
                            print(f"❌ Trade execution failed: {e}")
                            decision_result['trade_execution_error'] = str(e)
            
            # Note: MCP session is NOT closed here to allow caching across backtest days.
            # The session will be closed by the caller (e.g., backtest script) when done.
            
            return decision_result

        except Exception as e:
            print(f"❌ Error for {symbol}: {e}")
            # Only close session on critical errors that require restart
            # For normal operation, keep session alive for caching across days
            # await self._close_mcp_session()  # Commented out to preserve cache
            return self._create_error_decision(symbol, current_date, str(e))

    def _build_system_prompt(self, mcp_session=None) -> str:
        """Build system prompt with available tools.
        
        Design:
        - First LLM call is a PLANNING call: choose specific tools and tightly bounded
          date ranges / limits. Do NOT make a final decision in the first call.
        - After tools have been executed and summarized, a later call makes a single
          final DECISION using the returned data.
        """
        if mcp_session and self.available_tools:
            # Use discovered tools from MCP
            tools_list = "You have access to the following tools via MCP:\n"
            tools_list += "\n".join([f"- {tool}" for tool in self.available_tools[:20]])  # Show first 20
            if len(self.available_tools) > 20:
                tools_list += f"\n... and {len(self.available_tools) - 20} more tools"
            tools_list += "\n\nTo use a tool, format your request as:\nTOOL_CALL: tool_name(param1=value1, param2=value2)"
        else:
            # Fallback: list predefined tools (note: actual tool schemas come from MCP discovery when available)
            tools_list = """You have access to the following analysis tools:
- get_price_history(symbol, start_date, end_date)
- calculate_rsi(symbol, start_date, end_date, length=14, target='close')
- calculate_macd(symbol, start_date, end_date, fast=12, slow=26, signal=9, target='close')
- calculate_bbands(symbol, start_date, end_date, length=20, std=2.0, target='close')
- calculate_atr(symbol, start_date, end_date, length=14)
- calculate_obv(symbol, start_date, end_date)
- calculate_adx(symbol, start_date, end_date, length=14)
- calculate_ema(symbol, start_date, end_date, length=50, target='close')
- calculate_cci(symbol, start_date, end_date, length=20)
- get_current_price(symbol, current_date=None)
- get_earnings_calendar(start_date, end_date, symbol=None, current_date=None)
- get_analyst_estimates(symbol)
- get_company_profile(symbol)
- get_income_statement(symbol, period='annual', limit=5)
- get_balance_sheet(symbol, period='annual', limit=5)
- get_cash_flow(symbol, period='annual', limit=5)"""
        
        return f"""You are an expert autonomous trading agent powered by OpenBB data.
Your goal is to analyze stocks and make profitable trading decisions (BUY, SELL, SHORT, HOLD).

{tools_list}

You operate in TWO CLEAR STAGES:

STAGE 1 - PLANNING (FIRST RESPONSE ONLY):
- Carefully decide which tools you need and with what parameters.
- For technical indicators: Use date ranges of 60-90 days for fetching price history. You can still use long indicator periods (e.g., 200-day EMA, 50-day EMA) - the period parameter is separate from the data range.
- For fundamentals, request only as much history as you truly need (for example: period='annual', limit=3).
- Output ONLY tool calls in this format (no decision yet):
  TOOL_CALL: tool_name(param1=value1, param2=value2)
  You may emit multiple TOOL_CALL lines if needed.

STAGE 2 - ANALYSIS AND DECISION (AFTER YOU SEE TOOL RESULTS):
- When tool results are provided, use them to form a single, final trading decision.
- Now you MUST output your answer in the format below.

Make sure to check for:
1. Trend (EMA, ADX)
2. Momentum (RSI, MACD, CCI)
3. Volatility (BBands, ATR)
4. Volume (OBV)
5. Fundamental events (Earnings) and health.

Once you have receiced the data from the tool calls, then you can provide your final output in this format:
DECISION: [BUY/SELL/SHORT/HOLD]
CONFIDENCE: [0.0-1.0]
AMOUNT_USD: [Optional - dollar amount for the trade, based on confidence and portfolio size]
REASONING: [Detailed analysis]

Note: If you decide to execute a trade, specify the AMOUNT_USD based on your confidence level and available cash.
"""

    def _build_user_prompt(self, symbol, current_date, portfolio_state) -> str:
        return f"""Analyze {symbol} for trading date {current_date}.

Portfolio State:
- Cash: ${portfolio_state.get('cash', 0):,.2f}
- Long Positions: {portfolio_state.get('positions', {})}
- Short Positions: {portfolio_state.get('short_positions', {})}
- Unrealized P&L: ${portfolio_state.get('unrealized_pnl', 0):,.2f}

Please use the available tools to gather data and make a decision.
Avoid lookahead bias: do not use data from after {current_date}.
"""

    def _call_chutes_api(self, messages: List[Dict]) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": 4096,
            "temperature": 0.1
        }
        
        # Calculate total input size
        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        print(f"  📤 API Request: {len(messages)} messages, {total_chars:,} total chars")
        
        response = requests.post(CHUTES_API_URL, headers=headers, json=body, timeout=120)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _parse_response(self, text: str, symbol: str, date: str) -> Dict:
        # Parse decision, confidence, amount, and reasoning
        import re
        
        decision = "HOLD"
        confidence = 0.0
        amount_usd = 0.0
        reasoning = text
        
        # Extract decision
        decision_match = re.search(r"DECISION:\s*(\w+)", text, re.IGNORECASE)
        if decision_match:
            decision = decision_match.group(1).upper()
            if decision not in ('BUY', 'SELL', 'SHORT', 'HOLD', 'CLOSE'):
                decision = ""
        
        # Extract confidence
        confidence_match = re.search(r"CONFIDENCE:\s*(\d+\.?\d*)", text, re.IGNORECASE)
        if confidence_match:
            confidence = float(confidence_match.group(1))
            # Normalize to 0-1 range if > 1
            if confidence > 1.0:
                confidence = confidence / 100.0
        
        # Extract amount_usd (optional)
        amount_match = re.search(r"AMOUNT_USD:\s*\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
        if amount_match:
            amount_usd = float(amount_match.group(1).replace(',', ''))
        
        # Extract reasoning
        reasoning_match = re.search(r"REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)", text, re.DOTALL | re.IGNORECASE)
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()
            
        return {
            "symbol": symbol,
            "date": date,
            "decision": decision,
            "confidence": confidence,
            "amount_usd": amount_usd,
            "reasoning": reasoning,
            "raw_response": text
        }

    def _save_decision(self, decision: Dict):
        os.makedirs(self.decision_save_dir, exist_ok=True)
        filename = f"{decision['symbol']}_{decision['date']}_decision.json"
        with open(os.path.join(self.decision_save_dir, filename), 'w') as f:
            json.dump(decision, f, indent=2)

    def _save_raw_prompt(self, symbol: str, date: str, messages: List[Dict[str, Any]]) -> None:
        """Append a copy of the raw data (messages) seen by the LLM when making a decision.

        Saved alongside decisions, using a `.w` extension for easy identification.
        Each run is appended with a separator so multiple decisions for the same
        symbol/date can coexist in a single file.
        """
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
        """
        Reduce size of tool results before they are sent back to the LLM and saved.
        
        Goals:
        - Avoid flooding the prompt with huge raw JSON (especially fundamentals).
        - Keep enough recent data for the model to make an accurate decision.
        - Do NOT trim price history when configured not to, since we may need all requested dates.
        """
        if not isinstance(tool_result, dict):
            return tool_result
        
        result = dict(tool_result)
        tool_name = result.get("tool_name") or result.get("tool") or ""
        data = result.get("data")
        
        # Only operate on list-like "data"
        if not isinstance(data, list) or not data:
            return result
        
        # Look up trimming behavior for this tool
        config = TOOL_CONFIG.get(tool_name, TOOL_DEFAULT_CONFIG)
        if not config.get("trim", True):
            # This tool is configured to never be trimmed
            return result
        
        # Determine how many items to keep
        max_items = int(config.get("max_items", TOOL_DEFAULT_CONFIG["max_items"]))
        
        if len(data) > max_items:
            # Keep the most recent entries (assuming results are in chronological order)
            result["data"] = data[-max_items:]
            result["truncated"] = True
            result["truncated_note"] = f"Trimmed data to last {max_items} items out of {len(data)}"
        
        return result

    def _extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Extract tool calls from LLM response text with proper handling of dictionaries and nested structures"""
        import ast
        
        tool_calls = []
        
        # Pattern: TOOL_CALL: tool_name(param1=value1, param2=value2)
        pattern = r'TOOL_CALL:\s*(\w+)\s*\(([^)]*)\)'
        matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            tool_name = match.group(1)
            params_str = match.group(2).strip()
            
            params = {}
            if params_str:
                # Use a smarter parser that handles nested structures
                # Split parameters while respecting nested brackets and quotes
                param_parts = []
                current_part = ""
                depth = 0  # Track nesting depth for {}, [], ()
                in_string = False
                string_char = None
                i = 0
                
                while i < len(params_str):
                    char = params_str[i]
                    
                    # Handle string literals
                    if char in ('"', "'") and (i == 0 or params_str[i-1] != '\\'):
                        if not in_string:
                            in_string = True
                            string_char = char
                        elif char == string_char:
                            in_string = False
                            string_char = None
                        current_part += char
                    elif in_string:
                        current_part += char
                    # Handle brackets
                    elif char in ('{', '[', '('):
                        depth += 1
                        current_part += char
                    elif char in ('}', ']', ')'):
                        depth -= 1
                        current_part += char
                    # Handle parameter separator (comma at top level)
                    elif char == ',' and depth == 0:
                        if current_part.strip():
                            param_parts.append(current_part.strip())
                        current_part = ""
                    else:
                        current_part += char
                    i += 1
                
                # Add the last parameter
                if current_part.strip():
                    param_parts.append(current_part.strip())
                
                # Parse each parameter
                for param in param_parts:
                    if '=' not in param:
                        continue
                    
                    # Split on first '=' only
                    key, value_str = param.split('=', 1)
                    key = key.strip()
                    value_str = value_str.strip()
                    
                    # Try to parse as Python literal (handles dicts, lists, numbers, bools, None)
                    try:
                        # Use ast.literal_eval for safe evaluation of Python literals
                        params[key] = ast.literal_eval(value_str)
                    except (ValueError, SyntaxError):
                        # Fallback: try to parse as string, number, or bool
                        # Remove surrounding quotes if present
                        if (value_str.startswith('"') and value_str.endswith('"')) or \
                           (value_str.startswith("'") and value_str.endswith("'")):
                            params[key] = value_str[1:-1]
                        elif value_str.lower() in ('true', 'false'):
                            params[key] = value_str.lower() == 'true'
                        elif value_str.lower() == 'none':
                            params[key] = None
                        else:
                            # Try to parse as number
                            try:
                                if '.' in value_str:
                                    params[key] = float(value_str)
                                else:
                                    params[key] = int(value_str)
                            except ValueError:
                                # Keep as string
                                params[key] = value_str
            
            tool_calls.append({
                "name": tool_name,
                "arguments": params
            })
        
        return tool_calls
    
    async def _execute_tool_via_mcp(
        self, 
        mcp_session: ClientSession, 
        tool_call: Dict[str, Any],
        symbol: str,
        current_date: str
    ) -> Dict[str, Any]:
        """Execute a tool call via MCP client"""
        tool_name = tool_call["name"]
        arguments = tool_call["arguments"]

        # Parse current_date once for reuse in clamps
        current_date_dt = None
        try:
            current_date_dt = datetime.strptime(current_date, "%Y-%m-%d")
        except Exception:
            # If current_date is invalid, we simply skip clamping – the tools may still handle it
            pass
        
        # Fill in common parameters
        # Note: earnings_calendar now accepts optional symbol parameter for filtering
        if tool_name in ["get_earnings_calendar", "fundamental_earnings_calendar"]:
            # Always ensure symbol + current_date are present to avoid lookahead
            arguments.setdefault("symbol", symbol)
            if "current_date" not in arguments and current_date:
                arguments["current_date"] = current_date
        else:
            if "symbol" not in arguments:
                arguments["symbol"] = symbol
        
        # Add current_date to get_current_price to prevent lookahead bias   
        if tool_name == "get_current_price" and "current_date" not in arguments:
            arguments["current_date"] = current_date
        
        # Handle date parameters for tools that need them
        # NOTE: get_price_history requires explicit dates - don't auto-fill (returns raw data, can be huge)
        # Technical indicators can auto-fill because they return calculated summaries, not raw data
        technical_indicators_needing_dates = [
            "calculate_rsi", "calculate_macd", 
            "calculate_bbands", "calculate_atr", "calculate_obv",
            "calculate_adx", "calculate_ema", "calculate_cci",
            "calculate_moving_averages", "calculate_volatility"
        ]
        
        # For technical indicators, auto-fill dates if not provided (they return summaries, not raw data)
        # Technical indicators now REQUIRE start_date and end_date, so ensure both are always present
        # Technical indicators need longer lookbacks (e.g., 200-day MA needs 200+ days) but return small calculated values
        if tool_name in technical_indicators_needing_dates:
            # Always ensure both dates are provided since they're required parameters
            if "start_date" not in arguments or "end_date" not in arguments:
                lookback_days = arguments.get("lookback_days", 200)  # Default 200 days for indicators like 200-day MA
                # Allow up to 252 days (1 trading year) for technical calculations - they return summaries, not raw data
                if lookback_days > 252:
                    lookback_days = 252  # Cap at 1 trading year
                end_date = current_date
                if current_date_dt:
                    start_dt = current_date_dt - timedelta(days=lookback_days)
                    start_date = start_dt.strftime("%Y-%m-%d")
                else:
                    start_date = current_date
                arguments["start_date"] = start_date
                arguments["end_date"] = end_date
                # Remove lookback_days if present (not a real parameter)
                arguments.pop("lookback_days", None)

        # Clamp any provided end_date to current_date to avoid lookahead where applicable
        if current_date_dt and "end_date" in arguments:
            try:
                end_dt = datetime.strptime(str(arguments["end_date"]), "%Y-%m-%d")
                if end_dt > current_date_dt:
                    arguments["end_date"] = current_date
            except Exception:
                # If parsing fails, leave as-is and let the tool handle it
                pass
        
        # For get_price_history, require explicit dates - return error if missing
        if tool_name == "get_price_history":
            if "start_date" not in arguments or "end_date" not in arguments:
                return {
                    "error": "get_price_history requires explicit start_date and end_date parameters. "
                            "Please specify dates to avoid returning too much data. "
                            "Example: TOOL_CALL: get_price_history(symbol=AAPL, start_date=2025-11-15, end_date=2025-12-15)",
                    "tool_name": tool_name
                }
            # Ensure no lookahead for price history
            try:
                if current_date_dt:
                    end = datetime.strptime(arguments["end_date"], "%Y-%m-%d")
                    if end > current_date_dt:
                        end = current_date_dt
                        arguments["end_date"] = current_date

                # Limit to max 90 days of data to prevent prompt flooding
                start = datetime.strptime(arguments["start_date"], "%Y-%m-%d")
                end = datetime.strptime(arguments["end_date"], "%Y-%m-%d")
                days_diff = (end - start).days
                if days_diff > 90:
                    # Auto-limit to last 90 days
                    arguments["start_date"] = (end - timedelta(days=90)).strftime("%Y-%m-%d")
                    print(f"⚠️  Limited get_price_history to 90 days (requested {days_diff} days)")
            except (ValueError, KeyError):
                pass  # Let the tool handle invalid dates
        
        # Call tool via MCP with timeout
        try:
            # Add timeout per tool call (30 seconds should be enough for most OpenBB calls)
            result = await asyncio.wait_for(
                mcp_session.call_tool(tool_name, arguments),
                timeout=30.0
            )
            # MCP returns CallToolResult with content array
            if hasattr(result, 'content') and result.content:
                # Extract text from content
                content_text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                # Try to parse as JSON, otherwise return as text
                try:
                    parsed_result = json.loads(content_text)
                    # Ensure tool_name is always included
                    if isinstance(parsed_result, dict) and "tool_name" not in parsed_result:
                        parsed_result["tool_name"] = tool_name

                    # Extra safety: strip out any records dated AFTER current_date to
                    # prevent subtle lookahead if the data provider returns a later bar.
                    if current_date_dt and isinstance(parsed_result, dict):
                        data = parsed_result.get("data")
                        if isinstance(data, list) and data:
                            filtered = []
                            for item in data:
                                if not isinstance(item, dict):
                                    filtered.append(item)
                                    continue
                                item_date = item.get("date")
                                if not item_date:
                                    filtered.append(item)
                                    continue
                                try:
                                    item_dt = datetime.strptime(str(item_date), "%Y-%m-%d")
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
            return {"error": "Tool execution timed out after 30s", "tool": tool_name, "tool_name": tool_name}
        except Exception as e:
            return {"error": str(e), "tool": tool_name, "tool_name": tool_name}
    
    def _create_error_decision(self, symbol, date, error) -> Dict:
        return {
            "symbol": symbol,
            "date": date,
            "decision": "HOLD",
            "confidence": 0.0,
            "reasoning": f"Error: {error}"
        
        }
    
    def __del__(self):
        """Cleanup MCP session on destruction"""
        # Don't try to cleanup in __del__ - it causes asyncio issues
        # Cleanup should be done explicitly via _close_mcp_session() in the async context
        pass
