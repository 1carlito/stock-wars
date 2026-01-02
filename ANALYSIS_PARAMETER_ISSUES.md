# Analysis: Parameter Issues and Execution Problems

## Summary

Based on the terminal output analysis, here are the key issues identified:

## 1. **What Was Able to Execute**

- ✅ **MCP Server Started**: Successfully connected to OpenBBMCPServer
- ✅ **Tool Discovery**: Only 1 tool discovered: `execute_trade`
- ❌ **Tool Calls**: All 24 tool calls failed due to parameter parsing issues

## 2. **Critical Issues Identified**

### Issue #1: Missing Tool Registration
**Problem**: The fundamental and technical analysis tools are **never registered** with the MCP server.

**Evidence**:
- Terminal shows: `✅ Discovered 1 MCP tools: execute_trade...`
- In `OpenBBMCPServer.py` lines 90-91, the registration functions are imported but **never called**:
  ```python
  register_fundamental_tools = Fundamental_Tools.register_fundamental_tools
  register_technical_tools = Technical_Tools.register_technical_tools
  ```
  These functions need to be called with `mcp` as argument: `register_fundamental_tools(mcp)`

**Impact**: The LLM only sees `execute_trade` as available, so it incorrectly tries to use it for data retrieval with a `function` parameter.

### Issue #2: Broken Parameter Parsing
**Problem**: The `_extract_tool_calls` method in `ReasoningAgent.py` (lines 670-708) uses simple comma-splitting that **cannot handle dictionaries or nested structures**.

**Evidence from Terminal**:
```
TOOL_CALL: execute_trade(symbol='AAPL', function='OVERVIEW', params={})
```
Gets parsed as:
```python
{'symbol': 'AAPL', 'function': 'OVERVIEW', 'params': '{}'}  # String, not dict!
```

For complex params like:
```
params={'period': 'annual', 'limit': 3}
```
Gets truncated to:
```python
{'params': "{'period': 'annual"}  # Incomplete!
```

**Root Cause**: The parser splits on commas without considering:
- Nested dictionaries `{}`
- Nested quotes within dictionaries
- Multi-line parameters

### Issue #3: Wrong Tool Usage
**Problem**: LLM is calling `execute_trade` with a `function` parameter, but `execute_trade` is **only for trade execution**, not data retrieval.

**What LLM Tried**:
```
execute_trade(symbol='AAPL', function='OVERVIEW', params={})
execute_trade(symbol='AAPL', function='EARNINGS', params={'period': 'annual', 'limit': 3})
execute_trade(symbol='AAPL', function='EMA', params={'time_period': 50, ...})
```

**What `execute_trade` Actually Requires**:
```python
execute_trade(
    symbol: str,
    decision: str,        # BUY/SELL/SHORT/HOLD
    amount_usd: float,
    current_price: float,  # ❌ Missing!
    current_date: str,
    portfolio_state: Dict[str, Any],  # ❌ Parsing fails!
    market_cap_bil: Optional[float] = None
)
```

### Issue #4: Missing Required Parameters
**Problem**: `current_price` and `portfolio_state` are required but not properly provided.

**Evidence**:
- Terminal shows: `⚠️  Cannot execute trade: current_price not provided and could not be fetched`
- LLM tried to pass `current_price=0` and `portfolio_state` as a string/dict, but parsing failed

**What Should Happen**:
1. `current_price` should be fetched using `get_current_price` tool (but it's not registered!)
2. `portfolio_state` should be passed as a proper Python dict, not a string

### Issue #5: Portfolio State Format Issues
**Problem**: When LLM tries to pass `portfolio_state` as a dictionary, the parser fails.

**LLM Attempts**:
```
portfolio_state={'cash': 100000, 'long_positions': {}, 'short_positions': {}, 'unrealized_pnl': 0}
portfolio_state={"cash": 100000, "long_positions": {}, "short_positions": {}, "unrealized_pnl": 0}
```

**What Gets Parsed** (from terminal output):
```python
# Iteration 1:
{'symbol': 'AAPL', 'function': 'OVERVIEW', 'params': '{}'}  # params is string, not dict

# Iteration 2:
{'symbol': 'AAPL', 'function': 'OVERVIEW', 'params': '{}', 'decision': 'HOLD', 
 'amount_usd': 0, 'current_price': 0, 'current_date': '2025-12-15', 
 'portfolio_state': "{'cash': 100000"}  # Truncated at first comma!

# Iteration 3:
{'symbol': 'AAPL', 'function': 'OVERVIEW', 'params': '{}', 'decision': 'HOLD',
 'amount_usd': 0, 'current_price': 0, 'current_date': '2025-12-15',
 'portfolio_state': '{"cash": 100000'}  # Still truncated!
```

**Root Cause**: The parser in `_extract_tool_calls()` (line 685) splits on commas:
```python
for param in params_str.split(','):  # ❌ Splits on commas inside dict!
```

This breaks when dictionaries contain commas, as seen in the terminal output.

## 3. **Tool Results Analysis**

All 8 tool calls in each iteration returned **336 chars** of error messages, indicating:
- Parameter validation failed at the MCP server level
- FastMCP framework validates parameters against function signature before execution
- Error messages were consistent across all calls (likely "missing required parameter" or "invalid parameter type")
- The errors are returned as JSON from `mcp_session.call_tool()` and parsed in `_execute_tool_via_mcp()` (lines 820-833)

**Likely Error Content** (based on FastMCP validation):
- Missing required parameter: `current_price` (required float, got 0 or missing)
- Invalid parameter type: `portfolio_state` (required Dict, got string)
- Unknown parameter: `function` (not in function signature)
- Unknown parameter: `params` (not in function signature)

## 4. **Root Causes Summary**

1. **Missing Tool Registration**: Fundamental and technical tools not registered → LLM only sees `execute_trade`
2. **Inadequate Parameter Parser**: Simple regex/comma-split can't handle complex structures
3. **Tool Confusion**: LLM thinks `execute_trade` can retrieve data via `function` parameter
4. **Missing Data Tools**: No way to get `current_price` or other data needed for analysis

## 5. **Recommended Fixes**

### Fix #1: Register All Tools
In `OpenBBMCPServer.py`, add after line 364:
```python
# Register fundamental and technical tools
if mcp and register_fundamental_tools:
    register_fundamental_tools(mcp)
if mcp and register_technical_tools:
    register_technical_tools(mcp)
```

### Fix #2: Improve Parameter Parser
Replace `_extract_tool_calls` in `ReasoningAgent.py` with a proper parser that:
- Handles nested dictionaries using `ast.literal_eval()` or `json.loads()`
- Properly parses quoted strings
- Handles multi-line parameters

### Fix #3: Update System Prompt
The system prompt should list all available tools, not just `execute_trade`:
- Data retrieval tools: `get_company_overview`, `get_earnings_calendar`, `calculate_rsi`, etc.
- Trade execution tool: `execute_trade` (only for executing trades after analysis)

### Fix #4: Add Price Fetching Logic
Before calling `execute_trade`, ensure `current_price` is fetched if not provided:
```python
if current_price is None or current_price == 0:
    price_result = await mcp_session.call_tool("get_current_price", {"symbol": symbol, "current_date": current_date})
    current_price = extract_price_from_result(price_result)
```

## 6. **Expected Behavior After Fixes**

1. LLM sees all available tools (fundamental, technical, price, trade execution)
2. LLM calls data retrieval tools first (e.g., `calculate_rsi`, `get_company_overview`)
3. After analysis, LLM calls `execute_trade` with proper parameters
4. Parameters are correctly parsed as Python objects (dicts, lists, etc.)
5. `current_price` is automatically fetched if missing
6. `portfolio_state` is passed as a proper dict structure

