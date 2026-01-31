"""
Backtest Prompt Fixer
=====================

This module patches `custom_TradingBot.tool_registry.CATEGORY_TOOL_CALLS` 
to ensure that pre-computed tool call templates include the 'symbol' argument.

This allows the LLM to see:
  TOOL_CALL: calculate_rsi(symbol='AVGO', lookback_days=90, ...)
Instead of:
  TOOL_CALL: calculate_rsi(lookback_days=90, ...)
"""

import sys
import logging
from typing import List, Optional

# Ensure we can import from parent directory
# Ensure we can import from custom_TradingBot directory
import os
# We need to add custom_TradingBot to sys.path so we can import tool_registry directly
# This matches how ReasoningAgent imports it
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
custom_bot_dir = os.path.join(root_dir, "custom_TradingBot")
sys.path.insert(0, custom_bot_dir)

import tool_registry

_logger = logging.getLogger(__name__)

def patch_tool_registry_for_backtest(target_symbol: str):
    """
    Modifies tool_registry.CATEGORY_TOOL_CALLS in-place to inject the symbol argument.
    
    Args:
        target_symbol: The token symbol to inject (e.g. 'AAPL', 'NVO')
    """
    print(f"🔧 Patching tool registry for backtest symbol: {target_symbol}")
    
    # Iterate through all categories
    for category, tools in tool_registry.CATEGORY_TOOL_CALLS.items():
        # FILTER: Remove 'get_intraday_candles' from backtesting as it is not supported/needed
        # and causes errors in starter tier.
        if category == "technical_indicators":
            tools[:] = [t for t in tools if t["tool"] != "get_intraday_candles"]

        for tool_def in tools:
            params = tool_def.get("params", {})
            
            # If 'symbol' is missing, inject it
            # Always overwrite/inject 'symbol' to ensure the correct one is used for the current iteration
            new_params = {"symbol": target_symbol}
            # Add existing params (excluding 'symbol' if it was somehow already there)
            for k, v in params.items():
                if k != "symbol":
                    new_params[k] = v
            tool_def["params"] = new_params

    # Also force re-generation of any cached values if necessary 
    # (though generate_precomputed_tool_calls reads directly from CATEGORY_TOOL_CALLS each time)
    
    print("✅ Tool registry patched successfully.")
