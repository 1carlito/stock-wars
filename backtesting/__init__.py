"""
Backtesting module for the Stock Agent.

This module provides backtesting functionality for the ReasoningAgent,
allowing historical simulation of trading decisions.
"""

from backtesting.run_backtest import run_backtest
from backtesting.start_agent_backtest import run_backtest as run_agent_backtest

__all__ = ["run_backtest", "run_agent_backtest"]
