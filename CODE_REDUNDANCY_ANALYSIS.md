# Code Redundancy Analysis

## Summary

Found **5 major areas of redundancy** across the codebase that can be refactored to reduce duplication and improve maintainability.

---

## 1. **Repeated Import Pattern** ⚠️ HIGH REDUNDANCY

**Location**: `Fundamental_Tools.py` (lines 9-13) and `Technical_Tools.py` (lines 10-14)

**Redundant Code**:
```python
# Both files have identical import setup
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import _convert_openbb_result
```

**Impact**: 
- Duplicated in 2 files
- If import path changes, must update 2 places
- Same sys.path manipulation logic

**Recommendation**: 
- Move to a shared `Tools/__init__.py` or create a `Tools/utils.py`
- Or use relative imports if Python package structure allows

---

## 2. **Repeated Error Handling Pattern** ⚠️ VERY HIGH REDUNDANCY

**Location**: All tool functions in `Fundamental_Tools.py` and `Technical_Tools.py`

**Redundant Pattern** (repeated 16+ times):
```python
try:
    result = obb.equity...  # or obb.technical...
    return {
        "tool_name": "tool_name",
        "data": _convert_openbb_result(result)
    }
except Exception as e:
    return {"tool_name": "tool_name", "error": str(e)}
```

**Examples**:
- `get_income_statement` (lines 36-47)
- `get_balance_sheet` (lines 66-77)
- `get_cash_flow` (lines 96-107)
- `get_company_profile` (lines 122-129)
- `get_analyst_estimates` (lines 200-207)
- `calculate_rsi` (lines 54-69)
- `calculate_macd` (lines 96-113)
- ... and 8 more tools

**Impact**: 
- **16+ identical error handling blocks**
- If error format changes, must update 16+ places
- Hard to add consistent error logging/monitoring

**Recommendation**: 
Create a decorator or wrapper function:
```python
def openbb_tool_wrapper(tool_name: str):
    """Decorator to wrap OpenBB tool calls with consistent error handling"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return {
                    "tool_name": tool_name,
                    "data": _convert_openbb_result(result)
                }
            except Exception as e:
                return {"tool_name": tool_name, "error": str(e)}
        return wrapper
    return decorator
```

---

## 3. **Repeated Technical Indicator Pattern** ⚠️ HIGH REDUNDANCY

**Location**: `Technical_Tools.py` - 8 technical indicator tools

**Redundant Pattern** (repeated 8 times):
```python
try:
    # Fetch price data first
    price_data = _fetch_price_data(symbol, start_date, end_date)
    
    # Calculate indicator on the price data
    result = obb.technical.indicator_name(
        data=price_data,
        # ... indicator-specific params
    )
    return {
        "tool_name": "calculate_indicator",
        "data": _convert_openbb_result(result)
    }
except Exception as e:
    return {"tool_name": "calculate_indicator", "error": str(e)}
```

**Affected Tools**:
- `calculate_rsi` (lines 54-69)
- `calculate_macd` (lines 96-113)
- `calculate_bbands` (lines 138-154)
- `calculate_atr` (lines 175-189)
- `calculate_obv` (lines 208-221)
- `calculate_adx` (lines 242-256)
- `calculate_ema` (lines 279-294)
- `calculate_cci` (lines 315-329)

**Impact**: 
- **8 nearly identical function bodies**
- Only difference is the `obb.technical.*` call and parameters
- Hard to maintain consistency

**Recommendation**: 
Create a generic technical indicator wrapper:
```python
def register_technical_indicator(mcp, tool_name: str, indicator_func, **default_params):
    """Register a technical indicator tool with consistent pattern"""
    @mcp.tool(name=tool_name)
    def tool_func(symbol: str, start_date: str, end_date: str, **kwargs):
        try:
            price_data = _fetch_price_data(symbol, start_date, end_date)
            params = {**default_params, **kwargs}
            result = indicator_func(data=price_data, **params)
            return {
                "tool_name": tool_name,
                "data": _convert_openbb_result(result)
            }
        except Exception as e:
            return {"tool_name": tool_name, "error": str(e)}
    return tool_func
```

---

## 4. **Repeated Tool Registration Error Handling** ⚠️ MEDIUM REDUNDANCY

**Location**: `OpenBBMCPServer.py` (lines 367-379)

**Redundant Pattern**:
```python
if register_fundamental_tools:
    try:
        register_fundamental_tools(mcp)
        print("✅ Registered fundamental analysis tools")
    except Exception as e:
        print(f"⚠️  Failed to register fundamental tools: {e}")

if register_technical_tools:
    try:
        register_technical_tools(mcp)
        print("✅ Registered technical analysis tools")
    except Exception as e:
        print(f"⚠️  Failed to register technical tools: {e}")
```

**Impact**: 
- Duplicated try/except pattern
- If registration logic changes, must update 2 places

**Recommendation**: 
Create a helper function:
```python
def register_tool_module(mcp, register_func, module_name: str):
    """Register a tool module with consistent error handling"""
    if register_func:
        try:
            register_func(mcp)
            print(f"✅ Registered {module_name}")
        except Exception as e:
            print(f"⚠️  Failed to register {module_name}: {e}")

# Usage:
register_tool_module(mcp, register_fundamental_tools, "fundamental analysis tools")
register_tool_module(mcp, register_technical_tools, "technical analysis tools")
```

---

## 5. **Premium Error Handling** ⚠️ LOW-MEDIUM REDUNDANCY

**Location**: `Fundamental_Tools.py` - `get_earnings_calendar` (lines 175-185)

**Current Pattern**:
```python
except Exception as e:
    error_str = str(e)
    # Check if it's a premium endpoint error
    if "Premium" in error_str or "402" in error_str or "subscription" in error_str.lower():
        return {
            "tool_name": "get_earnings_calendar",
            "data": [],
            "message": "Earnings calendar data requires a premium FMP subscription...",
            "premium_required": True
        }
    return {"tool_name": "get_earnings_calendar", "error": str(e)}
```

**Impact**: 
- If other tools need premium error handling, this pattern will be duplicated
- Premium error detection logic is tool-specific

**Recommendation**: 
Create a helper function for premium error detection:
```python
def handle_premium_error(tool_name: str, error: Exception, fallback_message: str = None):
    """Handle premium endpoint errors consistently"""
    error_str = str(error)
    if "Premium" in error_str or "402" in error_str or "subscription" in error_str.lower():
        return {
            "tool_name": tool_name,
            "data": [],
            "message": fallback_message or f"{tool_name} requires a premium subscription.",
            "premium_required": True
        }
    return {"tool_name": tool_name, "error": error_str}
```

---

## 6. **Repeated Return Format** ⚠️ VERY HIGH REDUNDANCY

**Location**: All tools return the same format

**Pattern**: Every tool returns:
```python
{
    "tool_name": "...",
    "data": ...  # or "error": ...
}
```

**Impact**: 
- Consistent format is good, but enforced manually
- No validation that format is correct
- Easy to make mistakes (typo in "tool_name", missing field, etc.)

**Recommendation**: 
Create a helper function to ensure consistent format:
```python
def format_tool_result(tool_name: str, data=None, error=None, **kwargs):
    """Format tool result with consistent structure"""
    result = {"tool_name": tool_name}
    if error:
        result["error"] = str(error)
    else:
        result["data"] = data if data is not None else []
    result.update(kwargs)  # Allow additional fields (e.g., premium_required)
    return result
```

---

## Summary Statistics

| Redundancy Type | Frequency | Severity | Files Affected |
|----------------|-----------|----------|----------------|
| Error handling pattern | 16+ times | Very High | Fundamental_Tools.py, Technical_Tools.py |
| Technical indicator pattern | 8 times | High | Technical_Tools.py |
| Import pattern | 2 times | High | Fundamental_Tools.py, Technical_Tools.py |
| Tool registration pattern | 2 times | Medium | OpenBBMCPServer.py |
| Premium error handling | 1 time (potential for more) | Low-Medium | Fundamental_Tools.py |
| Return format | 16+ times | Very High | All tool files |

---

## Recommended Refactoring Priority

1. **HIGH PRIORITY**: Create error handling wrapper/decorator (affects 16+ functions)
2. **HIGH PRIORITY**: Create technical indicator registration helper (affects 8 functions)
3. **MEDIUM PRIORITY**: Consolidate import pattern (affects 2 files)
4. **MEDIUM PRIORITY**: Create tool registration helper (affects 2 registrations)
5. **LOW PRIORITY**: Create premium error handler (future-proofing)

---

## Estimated Code Reduction

- **Current**: ~800+ lines across tool files
- **After refactoring**: ~400-500 lines (estimated 40-50% reduction)
- **Maintainability**: Significantly improved (single source of truth for patterns)

