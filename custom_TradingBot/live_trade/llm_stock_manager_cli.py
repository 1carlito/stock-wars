#!/usr/bin/env python3
"""
LLM STOCK MANAGER - Interactive CLI
===================================

A polished, self‑contained command line interface for configuring the live
trading agent.

This CLI is **purely front-end**:
- It does NOT connect to the live trading backend yet.
- It focuses on gathering all the key inputs in a pleasant terminal UI.

Inspired by the Dexter terminal experience (`https://github.com/virattt/dexter`),
but tailored for this project.
"""

from __future__ import annotations

import os
import sys
import json
import time
import threading
import contextlib
import subprocess
import asyncio
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from typing import List, Literal, Dict, Any
from pathlib import Path

from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text
from rich.progress import track, Progress, SpinnerColumn, TextColumn


console = Console()

# Wire in the live_trade module for accessing functions
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_AGENT_DIR = PROJECT_ROOT / "custom_TradingBot"
LIVE_TRADE_DIR = CORE_AGENT_DIR / "live_trade"

# Ensure core paths are importable
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CORE_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_AGENT_DIR))
if str(LIVE_TRADE_DIR) not in sys.path:
    sys.path.insert(0, str(LIVE_TRADE_DIR))

try:
    from ReasoningAgent import ReasoningAgent  # type: ignore
except Exception as import_exc:  # pragma: no cover - defensive import
    ReasoningAgent = None  # type: ignore[assignment]

try:
    from live_trading_loop import run_once, run_daemon  # type: ignore
    LIVE_TRADING_AVAILABLE = True
except Exception:  # pragma: no cover
    LIVE_TRADING_AVAILABLE = False
    run_once = None  # type: ignore[assignment]
    run_daemon = None  # type: ignore[assignment]

# Optional backtesting integration (via backtesting/run_backtest.py)
try:  # pragma: no cover - optional dependency
    from backtesting.run_backtest import run_backtest as RUN_BACKTEST  # type: ignore
    BACKTESTING_AVAILABLE = True
except Exception:
    RUN_BACKTEST = None  # type: ignore[assignment]
    BACKTESTING_AVAILABLE = False



TradeMode = Literal["paper", "live"]
RunMode = Literal["once", "daemon"]
PortfolioMode = Literal["new", "current"]
AnalysisMode = Literal["analysis", "paper", "alpaca_live"]
EngineMode = Literal["live", "backtest"]


@dataclass
class PortfolioPosition:
    """Represents a single stock position in the portfolio."""
    ticker: str
    avg_price: float
    shares: float  # or total_value if value-based
    holding_period_days: int = 0
    current_price: float = 0.0
    current_value: float = 0.0

    def calculate_return(self) -> Dict[str, float]:
        """Calculate P&L and return % for this position."""
        if self.current_price == 0:
            self.current_price = self.avg_price  # fallback
        if self.current_value == 0:
            self.current_value = self.shares * self.current_price

        cost_basis = self.shares * self.avg_price
        unrealized_pnl = self.current_value - cost_basis
        return_pct = (unrealized_pnl / cost_basis * 100) if cost_basis != 0 else 0.0

        return {
            "ticker": self.ticker,
            "cost_basis": cost_basis,
            "current_value": self.current_value,
            "unrealized_pnl": unrealized_pnl,
            "return_pct": return_pct,
        }


@dataclass
class PortfolioSnapshot:
    """Complete portfolio snapshot with positions and aggregated metrics."""
    portfolio_value: float
    num_stocks: int
    positions: List[PortfolioPosition]
    created_at: str = ""  # ISO datetime

    def calculate_total_return(self) -> Dict[str, Any]:
        """Calculate total portfolio return from individual positions."""
        total_cost_basis = 0.0
        total_current_value = 0.0
        total_pnl = 0.0
        position_returns = []

        for pos in self.positions:
            ret = pos.calculate_return()
            position_returns.append(ret)
            total_cost_basis += ret["cost_basis"]
            total_current_value += ret["current_value"]
            total_pnl += ret["unrealized_pnl"]

        total_return_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis != 0 else 0.0

        return {
            "total_cost_basis": total_cost_basis,
            "total_current_value": total_current_value,
            "total_unrealized_pnl": total_pnl,
            "total_return_pct": total_return_pct,
            "position_returns": position_returns,
        }


@dataclass
class SessionConfig:
    symbols: List[str]
    starting_capital: float
    trade_mode: TradeMode
    run_mode: RunMode
    analysis_mode: AnalysisMode = "paper"
    portfolio_mode: PortfolioMode = "new"
    portfolio: PortfolioSnapshot | None = None
    notes: str = ""
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_paper_trading: bool = True
    force_reset_portfolio: bool = False
    has_fmp_access: bool = False
    # Scheduling (times in GMT)
    first_run_date: str | None = None  # ISO format date string (YYYY-MM-DD)
    scheduled_times_gmt: List[str] | None = field(default=None)  # List of HH:MM format times in GMT (e.g., ["13:00", "19:00"])
    first_day_entry_time_gmt: str | None = None  # HH:MM format time in GMT for first day only
    # Tool Selection
    user_tier: str = "starter"  # Default to starter to ensure fundamental tools are available
    selected_tool_categories: List[str] = field(default_factory=list)  # e.g., ["technical_indicators", "fundamental"]
    include_news: bool = False  # Toggle for news/sentiment tools
    technical_indicators_date_range: int | None = None  # Days of history for technical indicators (None = agent decides)
    allow_short_selling: bool = False  # If True, agent can SHORT and COVER. If False, LONG and CLOSE only.


def _render_header() -> Panel:
    # Render "LLM STOCK MANAGER" in Star Wars‑style ASCII art and append the image.
    try:
        from pyfiglet import Figlet  # type: ignore[import]

        # Prefer Star Wars‑style fonts, fall back to a big block font.
        star_wars_fonts = ["starwars", "epic", "isometric1", "big"]
        fig = None
        for font_name in star_wars_fonts:
            try:
                fig = Figlet(font=font_name, width=120)
                break
            except Exception:  # noqa: BLE001
                continue
        if fig is None:
            fig = Figlet(font="big", width=110)

        # Slight spacing tweak so STOCK and MANAGER feel balanced.
        ascii_art = fig.renderText("STOCK WARS")

        # Apply a dark‑yellow gradient across the ASCII banner.
        title = Text()
        for line in ascii_art.split("\n"):
            for i, ch in enumerate(line):
                style = "bold yellow" if i % 2 == 0 else "bold bright_yellow"
                title.append(ch, style=style)
            title.append("\n")

        # Append the provided image (e.g. General Grievous trader motif).
        grievous_art = """
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⠤⠒⠒⠉⠉⠉⠛⠳⢦⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⣷⡆⠀⠀⠀⠀⢀⡴⠋⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⡈⠙⢦⡀⠀⠀⠀⣶⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⢧⠀⠀⠀⢀⣿⠀⠀⣰⠀⠀⠀⠀⠀⠀⠀⠀⠀⣷⠀⠀⢹⠀⠀⠀⡿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⣠⠏⠸⡄⠀⣰⢺⡟⠀⠀⢿⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⠁⠀⢸⣆⠀⢀⡇⠘⢆⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⢀⡤⠚⠁⠀⠀⡇⠀⣳⣼⠀⠀⠀⣾⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡆⠀⠀⣿⡀⢸⡇⠀⠀⠙⠦⡀⠀⠀⠀⠀⠀
⠀⠀⠀⢠⠖⠁⠀⠀⠀⠀⢀⣷⣴⣿⠏⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⡇⠀⠀⠘⣷⣾⣀⠀⠀⠀⠀⠈⠳⡄⠀⠀⠀
⠀⠀⠀⢸⣤⣀⠀⢀⣴⡾⢏⠀⢀⠏⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡇⠀⠀⠀⠹⡄⠈⣿⣦⡀⠀⠀⣀⡇⠀⠀⠀
⠀⠀⠀⠈⡇⣀⡉⡛⠇⠀⠈⣧⡎⢀⣀⣀⣀⣀⣿⠐⢦⡀⠀⠀⠀⢀⡠⠔⢀⣧⣀⣀⣀⣀⠹⣤⠁⡇⢹⠊⠁⢀⡇⠀⠀⠀
⠀⠀⠀⠀⢹⠀⣀⣡⢸⠀⠀⢻⠀⡏⢫⡹⡿⡙⠻⡝⢲⡽⠂⠀⠀⠁⠰⣯⣿⡟⠉⢉⡽⠉⣧⡿⠀⢰⢸⠋⠉⢹⠁⠀⠀⠀
⠀⠀⠀⠀⠘⡍⠁⠈⢾⣇⠀⢸⡇⢇⠀⠙⠓⢒⣫⡷⠋⠀⠀⠀⠀⠀⠀⠈⢫⣏⠛⠉⠀⢠⢿⡇⠀⣮⡎⠉⠉⣹⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠻⡌⠁⠀⠙⢆⣸⣷⠈⠓⣒⡿⠟⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠛⠶⣖⡉⣸⣃⡼⠟⠉⠉⡩⠋⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠈⢦⠀⠀⠀⠉⠻⢷⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⡼⠛⠁⠀⠀⢀⠞⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠑⣄⠀⠀⠀⠸⡄⠈⠓⢆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⠖⠉⢸⠁⠀⠀⠀⣠⠋⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢣⡀⠀⠀⢷⣤⠤⢼⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣾⠢⣤⣌⠀⠀⢀⡼⠁⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⣷⡀⠀⠸⣟⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⡏⠀⢀⣞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⣠⢴⣵⠏⠀⣻⣆⠀⣿⣿⠉⡇⠀⢰⣦⢠⡆⢴⡀⢶⠀⢠⣿⣿⣿⠃⢠⣏⠈⠳⡀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⣠⣾⡿⢋⡏⠀⣰⠃⠻⣄⢹⡇⠀⢃⠀⣾⢿⡏⣥⣦⣧⠀⣇⢸⠁⠉⡿⢀⡇⠈⢣⠀⢹⣶⣄⠀⠀⠀⠀⠀⠀
⠀⠀⠀⢀⡴⣿⠏⠀⢸⡇⠀⣯⣠⣾⠿⣆⣇⢠⣧⣴⣿⣼⡇⣿⣿⣿⠀⣿⣬⣧⠀⣇⡼⢷⣄⠈⡇⠀⡿⢍⢷⣄⠀⠀⠀⠀
⠀⠀⢀⡞⡼⠁⠀⠀⠸⡇⠀⠸⡟⠁⠀⢹⡼⠘⠁⢸⠸⡏⢹⡿⢿⣿⣾⣿⠀⡇⠀⡿⠃⠀⠻⣿⠃⢠⠇⠀⠳⡙⢦⡀⠀⠀
⠀⠀⡞⢠⠁⠀⠀⠀⠀⢻⡄⠀⠱⣄⡤⠤⢧⠀⠀⢸⢀⣡⣾⣷⢦⣄⡉⣿⠀⡇⣸⠉⠑⠲⣴⠃⢠⡎⠀⠀⠀⠹⡄⢳⡀⠀
⠀⢰⠃⢸⠀⠀⠀⢀⣠⣼⠿⣄⠀⠱⡄⠀⠸⡄⡄⢸⠿⡟⠛⠉⠉⠛⡿⡟⠀⣇⠇⠀⢠⠞⠁⢠⢿⣷⣤⡀⠀⠀⢻⠘⣇⠀
⢀⡇⠀⢸⠀⢀⠖⠋⣿⡏⠀⠙⣦⠀⠙⣦⡀⣇⠸⡶⠀⢿⠀⠀⠀⢰⠃⢷⠎⡟⠀⡰⠋⠀⡰⠋⠀⣿⡌⠻⡆⠀⢸⠀⢻⡀
⢸⠀⠀⠈⢧⠎⠀⠘⣟⢧⣀⠀⠈⠳⣄⠈⠻⣾⡀⢱⠀⠈⡇⣀⣠⡏⢀⠏⣀⡷⠚⢀⡴⠏⠀⢀⣠⢿⠇⠀⢳⣠⠃⠀⠘⡇
⠀⠀⠀⠀⠈⠳⡀⠀⠈⠙⠒⠭⠭⢷⣚⣳⣄⠈⣹⣾⠓⢻⡉⠀⠀⢹⠛⢿⣅⢀⣴⢿⣵⣒⣯⠥⠚⠉⠀⣠⡿⠁⠀⠀⠀⠁
⠀⠀⠀⠀⠀⠀⠈⠒⢤⣀⡀⠀⠀⠀⠀⠈⣹⠟⠉⢹⠀⠈⠳⣄⣠⠞⠀⢸⠏⠻⡉⠉⠁⠀⠀⠀⢀⣤⠞⠋⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠁⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⠀⢀⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀
"""
        title.append(grievous_art, style="yellow")

    except Exception:  # noqa: BLE001
        # Fallback: simple text title if pyfiglet or the font is unavailable.
        title = Text("LLM STOCK MANAGER", style="bold magenta")

    subtitle = Text("Autonomous Live Trade Orchestrator", style="dim")

    text = Text()
    text.append(title)
    text.append("\n")
    text.append(subtitle)

    return Panel(
        Align.center(text, vertical="middle"),
        border_style="bright_magenta",
        padding=(1, 4),
    )


def _render_footer() -> Panel:
    footer_text = Text()
    footer_text.append("Status: ", style="bold cyan")
    if LIVE_TRADING_AVAILABLE:
        footer_text.append(
            "Connected to live trading backend. Settings will feed directly into the live agent.",
            style="dim green",
        )
    else:
        footer_text.append(
            "Live trading backend not available. Analysis mode only.",
            style="dim yellow",
        )
    return Panel(footer_text, border_style="grey42")


def _prompt_trading_strategy() -> bool:
    """
    Prompt for trading capability: Long Only vs. Long + Short.
    
    Returns:
        bool: True if short selling is allowed, False otherwise.
    """
    prompt_text = (
        "Select your **trading capabilities**:\n\n"
        "[bold]1.[/bold] [bold green]Long Only[/bold green]\n"
        "   • Buy stocks and close long positions\n"
        "   • Safer, traditional investing approach\n\n"
        "[bold]2.[/bold] [bold magenta]Long & Short[/bold magenta]\n"
        "   • Buy, Sell, Short, and Cover capabilities\n"
        "   • Allows profiting from downtrends (higher risk)\n"
    )
    console.print(Panel(prompt_text, title="Step 2 • Trading Strategy", border_style="cyan"))

    while True:
        choice = Prompt.ask(
            "Select strategy [1=Long Only, 2=Long & Short]",
            choices=["1", "2"],
            default="1",
            show_choices=False,
        ).strip()

        if choice == "1":
            return False  # Short selling disabled
        if choice == "2":
            return True   # Short selling allowed


def _banner() -> None:
    # Simpler banner: just header + footer, no extra empty body box.
    console.print(_render_header())
    console.print(_render_footer())
    console.print()  # Single blank line before prompts


def _prompt_symbols_analysis() -> List[str]:
    """Prompt for symbols when running in analysis-only mode."""
    prompt_text = (
        "Enter the ticker **symbol or symbols** you want the agent to analyze.\n"
        "[dim]Examples: AAPL, MSFT, NVDA[/dim]"
    )
    console.print(Panel(prompt_text, title="Step 5 • Symbols", border_style="cyan"))

    while True:
        raw = Prompt.ask("Symbols (comma‑separated)", default="AAPL")
        symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        if symbols:
            return symbols
        console.print("[red]Please enter at least one symbol.[/red]")


def _prompt_symbols_for_alpaca() -> List[str]:
    """
    Prompt for symbols when running against an Alpaca account (paper or live).

    Users can:
      - Press Enter with no input to trade all symbols currently held
        in their Alpaca portfolio, or
      - Provide a comma-separated subset of tickers to focus on.
    """
    prompt_text = (
        "Select which symbols to manage from your Alpaca account.\n\n"
        "- Leave blank to trade **all symbols currently held** in your Alpaca portfolio.\n"
        "- Or enter a comma-separated list to focus on a subset "
        "(e.g. APLD, MSFT, ASML)."
    )
    console.print(Panel(prompt_text, title="Step 5 • Symbols (Alpaca)", border_style="cyan"))

    raw = Prompt.ask("Symbols (comma‑separated, blank = all Alpaca positions)", default="").strip()
    if not raw:
        # Empty list signals 'use all Alpaca portfolio positions'
        return []

    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
    return symbols




def _prompt_starting_capital() -> float:
    prompt_text = (
        "Specify the **notional capital** you want the agent to reason about.\n"
        "This does not connect to a broker yet; it's used for sizing logic."
    )
    console.print(
        Panel(prompt_text, title="Step 3 • Capital", border_style="cyan"),
    )

    while True:
        amount_str = Prompt.ask("Starting capital (USD)", default="10000")
        try:
            value = float(amount_str)
            if value <= 0:
                raise ValueError
            return value
        except ValueError:
            console.print("[red]Please enter a positive number (e.g. 5000, 10000).[/red]")


def _prompt_trade_mode() -> TradeMode:
    prompt_text = (
        "Choose whether this configuration is intended for **paper** or **live** trading.\n"
        "Right now this is informational only, but it will guide safety checks later."
    )
    console.print(Panel(prompt_text, title="Step 5 • Mode", border_style="cyan"))

    choice = Prompt.ask(
        "Trading mode",
        choices=["paper", "live"],
        default="paper",
        show_choices=True,
    )
    return choice  # type: ignore[return-value]


def _prompt_run_mode() -> RunMode:
    prompt_text = (
        "How should the agent run?\n"
        "- [bold]once[/bold]: run a single decision cycle and exit\n"
        "- [bold]daemon[/bold]: schedule one run per trading day (15:00 NY time)"
    )
    console.print(Panel(prompt_text, title="Step 6 • Schedule", border_style="cyan"))

    choice = Prompt.ask(
        "Run mode",
        choices=["once", "daemon"],
        default="once",
        show_choices=True,
    )
    return choice  # type: ignore[return-value]


def _is_within_nyse_hours(times: List[str]) -> tuple[bool, List[str]]:
    """
    Check if all times fall within NYSE extended trading hours (GMT).

    NYSE Trading Hours (GMT - approximate):
    - Pre-market: 08:00 GMT (4 AM ET)
    - Regular: 13:30-21:00 GMT (9:30 AM - 4 PM ET)
    - After-hours: 21:00-23:00 GMT (4-8 PM ET)

    Recommended window: 08:00-23:00 GMT

    Returns: (is_within_hours, list_of_outside_times)
    """
    nyse_min_hour = 8      # 08:00 GMT (premarket start)
    nyse_max_hour = 23     # 23:00 GMT (after-hours end)

    outside_times = []
    for time_str in times:
        try:
            h, m = map(int, time_str.split(":"))
            if not (nyse_min_hour <= h <= nyse_max_hour):
                outside_times.append(time_str)
        except (ValueError, AttributeError):
            pass

    return len(outside_times) == 0, outside_times


def _prompt_notes() -> str:
    console.print(
        Panel(
            "Optional: add any [bold]verified news or events[/bold] you want the agent to consider "
            "(e.g. 'earnings report today', 'FDA approval announced', 'macro headwinds expected').\n\n"
            "[dim]Since we may not have real-time news, you can inject your own verified information.[/dim]",
            title="Step 8 • Verified News (Optional)",
            border_style="cyan",
        )
    )
    return Prompt.ask("Verified news to consider", default="")


def _prompt_scheduled_times_gmt() -> List[str] | None:
    """Prompt for custom trading schedule times in GMT."""
    console.print(
        Panel(
            "[bold]Customize Your Trading Schedule (Optional)[/bold]\n\n"
            "Default: [bold]13:00 GMT (1 PM GMT)[/bold] and [bold]19:00 GMT (7 PM GMT)[/bold]\n"
            "Times should be in HH:MM format (24-hour), e.g., 13:00, 19:00\n\n"
            "[dim]Recommended: 08:00-23:00 GMT (covers premarket to after-hours)[/dim]\n"
            "[dim]Note: GMT times will be converted to your local timezone for display[/dim]",
            title="Step 8a • Scheduled Times (Optional)",
            border_style="cyan",
        )
    )

    customize = Confirm.ask("Would you like to customize the schedule times?", default=False)
    if not customize:
        return None

    while True:
        times_input = Prompt.ask(
            "Enter scheduled times in GMT (comma-separated, e.g., '13:00,19:00')",
            default="13:00,19:00"
        ).strip()

        try:
            times = [t.strip() for t in times_input.split(",")]
            # Validate each time format
            for t in times:
                parts = t.split(":")
                if len(parts) != 2:
                    raise ValueError(f"Invalid format: {t}")
                h, m = int(parts[0]), int(parts[1])
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError(f"Invalid time: {t}")

            # Check if times fall within NYSE trading hours
            is_within_hours, outside_times = _is_within_nyse_hours(times)

            if not is_within_hours:
                console.print()
                console.print(
                    Panel(
                        "[bold yellow]⚠️  Warning: Times Outside NYSE Trading Hours[/bold yellow]\n\n"
                        f"These times fall outside recommended hours (08:00-23:00 GMT):\n"
                        f"[red]{', '.join(outside_times)}[/red]\n\n"
                        "[dim]Trading outside market hours may result in unreliable data:\n"
                        "• Pre-market (before 08:00 GMT): Very limited data\n"
                        "• After-hours (after 23:00 GMT): No data available\n"
                        "• Gaps between sessions: Missing OHLCV data[/dim]",
                        border_style="yellow",
                        title="Data Quality Warning",
                    )
                )

                choice = Prompt.ask(
                    "Would you like to (1) change times or (2) continue anyway?",
                    choices=["1", "2"],
                    default="1",
                    show_choices=False,
                ).strip()

                if choice == "1":
                    console.print("[yellow]Let's choose better times...[/yellow]\n")
                    continue  # Ask for times again
                else:  # choice == "2"
                    console.print(
                        "[yellow]ℹ️  Proceeding with times outside market hours. "
                        "Monitor logs for data availability issues.[/yellow]"
                    )

            console.print(f"[green]✓ Schedule times set to: {', '.join(times)} GMT[/green]")
            return times
        except (ValueError, IndexError):
            console.print("[red]Invalid format. Please use HH:MM format, e.g., 13:00,19:00[/red]")


def _prompt_engine_mode() -> EngineMode:
    """Top-level engine selection: live trading vs backtest."""
    prompt_text = (
        "Select the **execution engine**:\n\n"
        "[bold]1.[/bold] [bold green]Live / Paper Trading[/bold green]\n"
        "   • Use the live trading backend (analysis / Alpaca modes)\n\n"
        "[bold]2.[/bold] [bold cyan]Backtest[/bold cyan]\n"
        "   • Run historical backtests using the backtesting module\n"
    )
    console.print(Panel(prompt_text, title="Step 1 • Engine Selection", border_style="cyan"))

    while True:
        choice = Prompt.ask(
            "Select engine [1=Live, 2=Backtest]",
            choices=["1", "2"],
            default="1",
            show_choices=False,
        ).strip()

        if choice == "1":
            return "live"  # type: ignore[return-value]
        if choice == "2":
            return "backtest"  # type: ignore[return-value]


def _prompt_analysis_mode() -> AnalysisMode:
    """Prompt user to select analysis/trading mode (numeric 1/2/3 only)."""
    prompt_text = (
        "Select your trading mode:\n\n"
        "[bold]1.[/bold] [bold green]Investment Analysis Only[/bold green]\n"
        "   • Test strategies without actual trades\n"
        "   • Uses a theoretical portfolio file only (no broker, no Alpaca)\n\n"
        "[bold]2.[/bold] [bold yellow]Alpaca Paper Trading[/bold yellow]\n"
        "   • Execute trades on your Alpaca [bold]paper[/bold] account\n"
        "   • Uses Alpaca paper API keys and supports daemon scheduling\n\n"
        "[bold]3.[/bold] [bold cyan]Live Trading (Alpaca)[/bold cyan]\n"
        "   • Execute trades on an Alpaca broker account\n"
        "   • Use your Alpaca paper or live API keys as appropriate\n"
    )
    console.print(Panel(prompt_text, title="Step 2A • Mode Selection", border_style="cyan"))

    while True:
        choice = Prompt.ask(
            "Select mode [1=Analysis, 2=Paper (simulated), 3=Alpaca]",
            choices=["1", "2", "3"],
            default="2",
            show_choices=False,
        ).strip()

        if choice == "1":
            return "analysis"  # type: ignore[return-value]
        if choice == "2":
            return "paper"  # type: ignore[return-value]
        if choice == "3":
            return "alpaca_live"  # type: ignore[return-value]


def _prompt_alpaca_credentials() -> tuple[str, str]:
    """Prompt user for Alpaca API credentials (key + secret only).

    Whether these are used in Alpaca's paper or live environment is controlled
    by the selected mode (2 = paper account, 3 = live account) and internal
    ALPACA_PAPER settings.
    """
    prompt_text = (
        "Enter your Alpaca API credentials.\n"
        "[dim]These are stored temporarily and cleared after the session.[/dim]"
    )
    console.print(Panel(prompt_text, title="Alpaca Credentials", border_style="cyan"))

    api_key = Prompt.ask("API Key", password=True)
    api_secret = Prompt.ask("API Secret", password=True)

    return api_key, api_secret


def _prompt_portfolio_reset() -> bool:
    """
    Prompt user if they want to reset their local portfolio JSON.

    This is primarily intended for "Investment Analysis Only" mode, which uses
    the theoretical portfolio file, but the same flag is also honoured for
    paper trading via the backend load_portfolio_state logic.
    """
    live_trade_dir = Path(_get_live_trade_dir())
    theoretical_path = live_trade_dir / "theoretical_portfolio.json"
    portfolio_path = live_trade_dir / "portfolio_state.json"

    # Only show reset prompt if at least one portfolio file exists
    if not theoretical_path.exists() and not portfolio_path.exists():
        return False

    lines = [
        "You have existing local portfolio state files.",
        "",
        "- theoretical_portfolio.json  (investment / analysis-only runs)",
        "- portfolio_state.json        (paper trading runs)",
        "",
        "Resetting will back up any existing file(s) and start fresh with your",
        "configured starting capital for this session.",
    ]

    console.print(
        Panel(
            "\n".join(lines),
            title="Portfolio Reset (Optional)",
            border_style="cyan",
        )
    )
    return Confirm.ask("Reset local portfolio state?", default=False)


def _get_live_trade_dir() -> str:
    """Get live trade directory."""
    return str(LIVE_TRADE_DIR)


def _prompt_portfolio_mode() -> tuple[PortfolioMode, PortfolioSnapshot | None]:
    """Prompt user to choose between new or current portfolio."""
    console.print(
        Panel(
            "Provide your portfolio context for better trading decisions.\n"
            "- [bold]new[/bold]: This is your first portfolio (optional setup)\n"
            "- [bold]current[/bold]: You have existing positions (recommended)",
            title="Step 7 • Portfolio Context",
            border_style="cyan",
        )
    )

    mode_choice = Prompt.ask(
        "Portfolio mode",
        choices=["new", "current"],
        default="new",
        show_choices=True,
    )
    mode = mode_choice  # type: ignore[assignment]

    if mode == "new":
        console.print("[dim]Portfolio context skipped. Trading decisions will be stock-specific.[/dim]")
        return mode, None
    else:
        # Collect existing portfolio info
        portfolio = _collect_portfolio_details()
        return mode, portfolio


def _collect_portfolio_details() -> PortfolioSnapshot:
    """Collect portfolio details via natural language input."""
    console.print(
        Panel(
            "[bold]Enter your portfolio details[/bold]\n"
            "Questions will guide you through each stock position.",
            title="Portfolio Details",
            border_style="cyan",
        )
    )

    # Get overall portfolio info
    portfolio_value = float(Prompt.ask("Total portfolio value (USD)", default="100000"))
    num_stocks_str = Prompt.ask("Number of stocks you own", default="1")

    try:
        num_stocks = int(num_stocks_str)
    except ValueError:
        num_stocks = 1

    # Collect individual positions
    positions: List[PortfolioPosition] = []

    for i in range(num_stocks):
        console.print(f"\n[bold cyan]Stock {i+1} of {num_stocks}[/bold cyan]")

        ticker = Prompt.ask("  Ticker symbol").upper()
        avg_price = float(Prompt.ask("  Average purchase price", default="0.0"))
        shares = float(Prompt.ask("  Number of shares (or total value)", default="0.0"))
        holding_days_str = Prompt.ask("  Days held (e.g., 30, 180, 365)", default="0")

        try:
            holding_days = int(holding_days_str)
        except ValueError:
            holding_days = 0

        # Note: Current price will be fetched automatically from OpenBB/FMP
        # Don't ask user for it
        position = PortfolioPosition(
            ticker=ticker,
            avg_price=avg_price,
            shares=shares,
            holding_period_days=holding_days,
            current_price=0.0,  # Will be fetched later
            current_value=0.0,  # Will be calculated later
        )
        positions.append(position)

    console.print("\n[dim]ℹ️  Current prices will be fetched automatically from market data.[/dim]")

    # Create portfolio snapshot
    portfolio = PortfolioSnapshot(
        portfolio_value=portfolio_value,
        num_stocks=num_stocks,
        positions=positions,
        created_at=datetime.now().isoformat(),
    )

    return portfolio


def _prompt_analysis_portfolio_source() -> tuple[PortfolioMode, PortfolioSnapshot | None, bool]:
    """
    Analysis-mode portfolio source selector.

    Options:
      1. Start a new portfolio with this session's starting capital
      2. Manually enter portfolio details (existing positions)

    Returns:
        (portfolio_mode, portfolio_snapshot_or_none, force_reset_flag)
    """
    lines: list[str] = []
    lines.append("Choose how you want to provide portfolio context for analysis mode:\n")

    lines.append("[bold]1.[/bold] Start a [yellow]new portfolio[/yellow] with this session's starting capital")
    lines.append("[bold]2.[/bold] [cyan]Manually enter[/cyan] your existing portfolio (positions, sizes, etc.)")

    console.print(
        Panel(
            "\n".join(lines),
            title="Step 4 • Portfolio Source (Analysis)",
            border_style="cyan",
        )
    )

    # Only two sources are now supported: new or manual.
    valid_choices = ["1", "2"]
    default_choice = "1"

    while True:
        choice = Prompt.ask(
            "Select portfolio source",
            choices=valid_choices,
            default=default_choice,
            show_choices=False,
        ).strip()

        if choice == "1":
            # Fresh portfolio: start from session starting capital, no saved JSON.
            return "new", None, False
        if choice == "2":
            # Manual portfolio entry
            portfolio = _collect_portfolio_details()
            return "current", portfolio, False


def _review_config(cfg: SessionConfig) -> bool:
    table = Table(
        title="Session Summary",
        box=box.ROUNDED,
        show_edge=True,
        expand=True,
    )
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Symbols", ", ".join(cfg.symbols))
    table.add_row("Starting capital", f"${cfg.starting_capital:,.2f}")
    table.add_row("Trading mode", cfg.trade_mode)
    table.add_row("Run mode", cfg.run_mode)
    table.add_row("Portfolio mode", cfg.portfolio_mode)
    if cfg.portfolio:
        returns = cfg.portfolio.calculate_total_return()
        table.add_row(
            "Portfolio value",
            f"${cfg.portfolio.portfolio_value:,.2f} ({cfg.portfolio.num_stocks} positions)"
        )
        table.add_row(
            "Portfolio return",
            f"{returns['total_return_pct']:+.2f}% (${returns['total_unrealized_pnl']:+,.2f})"
        )
    table.add_row("Notes", cfg.notes or "—")
    table.add_row("Tool categories", ", ".join(cfg.selected_tool_categories) if cfg.selected_tool_categories else "—")
    table.add_row("Short selling", "Allowed" if cfg.allow_short_selling else "Disabled (Long Only)")
    table.add_row("Include news", "Yes" if cfg.include_news else "No")
    if cfg.technical_indicators_date_range:
        table.add_row("Tech data range", f"{cfg.technical_indicators_date_range} days")
    else:
        table.add_row("Tech data range", "Agent decides")

    panel = Panel(
        table,
        title="Review Configuration",
        border_style="bright_magenta",
    )
    console.print(panel)
    return Confirm.ask("Launch session with these settings?", default=True)


@contextlib.contextmanager
def _suppress_prints() -> None:
    """Silence stdout/stderr while the ReAct loop runs."""
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stdout = devnull
            sys.stderr = devnull
            yield
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr


def _config_file_path() -> Path:
    """Path to saved configuration file."""
    return LIVE_TRADE_DIR / "session_config.json"


def _save_config(cfg: SessionConfig) -> None:
    """Save configuration to disk."""
    config_path = _config_file_path()
    with open(config_path, "w") as f:
        json.dump(asdict(cfg), f, indent=2)
    console.print(f"[dim]Configuration saved to {config_path}[/dim]")


def _load_config() -> SessionConfig | None:
    """Load configuration from disk if it exists."""
    config_path = _config_file_path()
    if not config_path.exists():
        return None
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return SessionConfig(**data)
    except Exception:
        return None


def _reasoning_decisions_dir() -> Path:
    """Directory where ReasoningAgent writes decisions + prompt snapshots."""
    return PROJECT_ROOT / "reasoning_decisions"


def _load_decision(symbol: str, decision_date: date) -> Dict[str, Any] | None:
    """Load saved decision JSON for a symbol/date if it exists."""
    decisions_dir = _reasoning_decisions_dir()
    filename = f"{symbol}_{decision_date.isoformat()}_decision.json"
    path = decisions_dir / filename
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _two_line_summary(decision: Dict[str, Any]) -> str:
    """Return at most the last two non-empty lines of reasoning/raw_response."""
    text = (decision.get("reasoning") or decision.get("raw_response") or "").strip()
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    if len(lines) <= 2:
        return "\n".join(lines)
    return "\n".join(lines[-2:])


def _render_decision_summary(
    symbol: str,
    decision: Dict[str, Any],
    starting_capital: float,
) -> None:
    """Pretty-print compact portfolio + decision summary."""
    decision_str = (decision.get("decision") or "HOLD").upper()
    confidence = float(decision.get("confidence") or 0.0)
    amount_usd = float(decision.get("amount_usd") or 0.0)

    decision_color = {
        "BUY": "green",
        "SELL": "yellow",
        "SHORT": "red",
        "HOLD": "cyan",
        "CLOSE": "magenta",
    }.get(decision_str, "white")

    table = Table(
        title=f"Decision Summary • {symbol}",
        box=box.ROUNDED,
        show_edge=True,
        expand=True,
    )
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Decision", f"[{decision_color}]{decision_str}[/{decision_color}]")
    table.add_row("Confidence", f"{confidence:.1%}")
    table.add_row("Amount (USD)", f"${amount_usd:,.2f}")
    table.add_row("Starting Cash", f"${starting_capital:,.2f}")

    reasoning_snippet = _two_line_summary(decision)
    reasoning_panel = Panel(
        reasoning_snippet or "[dim]No reasoning summary available.[/dim]",
        title="LLM Summary (last lines)",
        border_style="grey42",
    )

    console.print()
    console.print(Panel(table, border_style="bright_magenta"))
    console.print(reasoning_panel)
    console.print()


def _run_analysis_for_symbol(cfg: SessionConfig, symbol: str) -> None:
    """Run ReasoningAgent.make_decision with a spinner and clean summary."""
    if ReasoningAgent is None:
        console.print(
            Panel(
                "ReasoningAgent could not be imported. "
                "Make sure the core `custom_TradingBot` package is available.",
                border_style="red",
            )
        )
        return

    symbol_clean = symbol.upper()
    today = date.today()

    # Minimal portfolio state – this CLI is display-only, not executing trades.
    portfolio_state: Dict[str, Any] = {
        "cash": cfg.starting_capital,
        "positions": {},
        "short_positions": {},
        "last_prices": {},
        "market_caps": {},
        "realized_short_pnl": 0.0,
        "unrealized_pnl": 0.0,
    }

    error_holder: Dict[str, Exception] = {}

    def _worker() -> None:
        try:
            agent = ReasoningAgent(
                data_dir=str(PROJECT_ROOT),
                use_mcp_client=True,
            )
            with _suppress_prints():
                # ReAct loop + MCP logs are suppressed, but prompts/decisions
                # are still saved into reasoning_decisions on disk.
                agent.make_decision(
                    symbol=symbol_clean,
                    current_date=today.isoformat(),
                    portfolio_state=portfolio_state,
                    execute_trade_after=False,
                    current_price=None,
                    max_tool_iterations=5,
                )
        except Exception as exc:  # noqa: BLE001
            error_holder["error"] = exc

    # Run the worker in a background thread while we show a spinner.
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    description = (
        f"[bold magenta]Generating analysis for '{symbol_clean}'[/bold magenta]"
    )

    with Progress(
        SpinnerColumn(style="bold magenta"),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        task_id = progress.add_task(description, start=True)
        while thread.is_alive():
            time.sleep(0.1)
            progress.refresh()
        thread.join()
        progress.update(task_id, completed=1.0)

    if "error" in error_holder:
        console.print(
            Panel(
                f"[red]Error while generating analysis for {symbol_clean}:[/red]\n"
                f"{str(error_holder['error'])}",
                border_style="red",
                title="Run Error",
            )
        )
        return

    decision = _load_decision(symbol_clean, today)
    if not decision:
        console.print(
            Panel(
                f"[red]No decision file found for {symbol_clean} on {today.isoformat()}.[/red]\n"
                "[dim]Check the `reasoning_decisions` folder for details.[/dim]",
                border_style="red",
                title="Decision Missing",
            )
        )
        return

    _render_decision_summary(symbol_clean, decision, cfg.starting_capital)


def _simulate_launch(cfg: SessionConfig) -> None:
    """Launch the live trading agent with the configured settings."""

    # Validate: Alpaca modes MUST use daemon mode, never "once"
    if cfg.analysis_mode in ("paper", "alpaca_live"):
        if cfg.run_mode == "once":
            console.print(
                Panel(
                    "[red]❌ Invalid Configuration:[/red]\n\n"
                    f"Alpaca modes ({cfg.analysis_mode}) do NOT support 'once' mode.\n\n"
                    "Alpaca is designed for scheduled trading on a fixed schedule:\n"
                    "• Default: 13:00 GMT (1 PM GMT) and 19:00 GMT (7 PM GMT)\n"
                    "• You can customize these times during configuration\n\n"
                    "[yellow]For one-shot analysis, use 'analysis' mode instead.[/yellow]\n"
                    "[yellow]For multi-symbol portfolio analysis, use 'analysis' mode.[/yellow]",
                    border_style="red",
                    title="Alpaca Mode Validation Error",
                )
            )
            return

    console.print()
    console.print(
        Panel(
            Text(
                "Launching LLM STOCK MANAGER...",
                style="bold green",
            ),
            border_style="green",
        )
    )

    steps = [
        "Validating configuration",
        "Initializing reasoning engine",
        "Preparing portfolio state",
    ]

    for step in track(steps, description="Preparing session", transient=True):
        _ = step  # noqa: F841

    console.print()

    # Save configuration for the live trading backend
    _save_config(cfg)

    console.print()
    tools_summary = ", ".join(cfg.selected_tool_categories) if cfg.selected_tool_categories else "technical_indicators"
    if cfg.include_news:
        tools_summary += " + news"
    tech_range_str = f"{cfg.technical_indicators_date_range} days" if cfg.technical_indicators_date_range else "agent decides"

    console.print(
        Panel(
            f"[bold cyan]Configuration Summary:[/bold cyan]\n"
            f"• Symbols: {', '.join(cfg.symbols)}\n"
            f"• Starting Capital: ${cfg.starting_capital:,.2f}\n"
            f"• Trade Mode: {cfg.trade_mode}\n"
            f"• Run Mode: {cfg.run_mode}\n"
            f"• Tools: {tools_summary}\n"
            f"• Tech data range: {tech_range_str}\n"
            f"• Alpaca Environment: "
            f"{'paper' if cfg.alpaca_paper_trading else 'live' if cfg.analysis_mode in ('paper', 'alpaca_live') else 'n/a'}",
            border_style="cyan",
            title="Live Trading Configuration",
        )
    )

    # Set environment variables for Alpaca if needed
    if cfg.analysis_mode in ("paper", "alpaca_live"):
        os.environ["ALPACA_ENABLED"] = "true"
        os.environ["ALPACA_API_KEY"] = cfg.alpaca_api_key
        os.environ["ALPACA_API_SECRET"] = cfg.alpaca_api_secret
        os.environ["ALPACA_PAPER"] = "true" if cfg.alpaca_paper_trading else "false"

    # Launch the live trading backend
    try:
        # Run all symbols (multi-stock or single-stock)
        if cfg.symbols:
            symbols_str = ", ".join(cfg.symbols)
            console.print()
            console.print(
                f"[bold yellow]Launching for: {symbols_str} ({cfg.analysis_mode})[/bold yellow]"
            )

            if cfg.run_mode == "daemon":
                # Daemon mode: only trade first symbol (scheduler limitation)
                first_symbol = cfg.symbols[0]
                # Format schedule times for display
                schedule_display = (
                    f"{', '.join(cfg.scheduled_times_gmt or ['13:00', '19:00'])} GMT"
                    if cfg.scheduled_times_gmt
                    else "13:00, 19:00 GMT (default)"
                )
                first_day_display = (
                    f"\n  • First day ({cfg.first_run_date}): entry at {cfg.first_day_entry_time_gmt} GMT"
                    if cfg.first_run_date and cfg.first_day_entry_time_gmt
                    else ""
                )
                console.print(
                    Panel(
                        "[bold cyan]Daemon Mode:[/bold cyan]\n"
                        f"The agent will trade {first_symbol} on a fixed schedule:\n"
                        f"  • Schedule: {schedule_display}{first_day_display}\n\n"
                        "[dim]Daemon mode trades one symbol at a time. For multi-symbol portfolio management, use 'analysis' mode.[/dim]\n"
                        "[yellow]Press Ctrl+C to stop the daemon.[/yellow]",
                        border_style="cyan",
                    )
                )
                # Engine mode: use Alpaca-backed portfolio for both paper (2) and live (3)
                engine_mode = "analysis" if cfg.analysis_mode == "analysis" else "alpaca_live"
                run_daemon(
                    symbol=first_symbol,
                    starting_capital=cfg.starting_capital,
                    notes=cfg.notes,
                    mode=engine_mode,
                    scheduled_times_gmt=cfg.scheduled_times_gmt,
                    first_run_date=cfg.first_run_date,
                    first_day_entry_time_gmt=cfg.first_day_entry_time_gmt,
                )
            else:  # once mode
                console.print("[bold cyan]Running one-shot trading cycle...[/bold cyan]")
                # Engine mode: use Alpaca-backed portfolio for both paper (2) and live (3)
                engine_mode = "analysis" if cfg.analysis_mode == "analysis" else "alpaca_live"
                run_once(
                    symbols=cfg.symbols,
                    starting_capital=cfg.starting_capital,
                    notes=cfg.notes,
                    mode=engine_mode,
                    force_reset=cfg.force_reset_portfolio,
                )
                console.print(
                    Panel(
                        "[bold green]One-shot trading cycle complete![/bold green]\n"
                        f"Check the [cyan]live_trade/[/cyan] folder for results.",
                        border_style="green",
                    )
                )

    except KeyboardInterrupt:
        console.print("\n[yellow]Daemon interrupted by user.[/yellow]")
    except Exception as exc:
        console.print(
            Panel(
                f"[red]Error launching live trading:[/red]\n{str(exc)}",
                border_style="red",
                title="Launch Error",
            )
        )


def _parse_tool_selection(input_str: str, max_tools: int) -> set:
    """
    Parse user tool selection input supporting ranges and comma-separated numbers.

    Examples:
    - "1,2,3" → {1, 2, 3}
    - "1-5" → {1, 2, 3, 4, 5}
    - "1,3,5-8,10" → {1, 3, 5, 6, 7, 8, 10}
    - "all" → {1, 2, ..., max_tools}
    - "none" → {}

    Args:
        input_str: User input string
        max_tools: Maximum tool number (for validation)

    Returns:
        Set of tool indices (1-based)
    """
    input_str = input_str.lower().strip()

    if input_str == "all":
        return set(range(1, max_tools + 1))

    if input_str == "none":
        return set()

    selected = set()
    for part in input_str.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            try:
                start, end = part.split("-")
                start, end = int(start.strip()), int(end.strip())
                if start > end:
                    start, end = end, start
                selected.update(range(start, end + 1))
            except (ValueError, AttributeError):
                console.print(f"[red]Invalid range: {part}[/red]")
                return set()
        else:
            try:
                selected.add(int(part))
            except ValueError:
                console.print(f"[red]Invalid number: {part}[/red]")
                return set()

    # Validate ranges
    invalid = selected - set(range(1, max_tools + 1))
    if invalid:
        console.print(f"[red]Invalid tool numbers: {sorted(invalid)}[/red]")
        return set()

    return selected


def _prompt_tool_selection(has_fmp_access: bool = False) -> List[str]:
    """
    Display all available tools and let user select which ones to enable.

    Returns:
        List of selected tool names (MCP tool names from registry)
    """
    # Import tool registry
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from tool_registry import TOOL_REGISTRY, resolve_enabled_tools, deduplicate_tools
    except ImportError:
        console.print("[red]Could not load tool registry. Using all default tools.[/red]")
        return []

    # Get available tools based on FMP access
    enabled_tools = resolve_enabled_tools(user_tier="free", has_fmp_access=has_fmp_access)
    enabled_tools = deduplicate_tools(enabled_tools)
    tool_list = sorted(list(enabled_tools))

    console.print(
        Panel(
            f"[bold]Available Tools ({len(tool_list)} total)[/bold]\n\n"
            "Select which tools the LLM can use for analysis.\n"
            "Enter tool numbers separated by commas, or use ranges (e.g., 1-5).\n\n"
            "Examples: '1,2,3' | '1-10' | 'all' | 'none'",
            border_style="cyan",
            title="Tool Selection",
        )
    )

    # Display tools in 2-column format
    table = Table(show_header=False, pad_edge=False, padding=(0, 2))
    table.add_column("Left", style="dim")
    table.add_column("Right", style="dim")

    # Build 2-column display
    rows = []
    for i, tool_name in enumerate(tool_list, start=1):
        metadata = TOOL_REGISTRY.get(tool_name, {})
        desc = metadata.get("description", "").split("(")[0].strip()[:40]  # Truncate description
        row_text = f"{i:2}. {tool_name:30} ({desc})"
        rows.append(row_text)

    # Add rows in pairs
    for i in range(0, len(rows), 2):
        left = rows[i]
        right = rows[i + 1] if i + 1 < len(rows) else ""
        table.add_row(left, right)

    console.print(table)
    console.print()

    # Prompt for selection
    while True:
        selection_input = Prompt.ask(
            "Enter tool numbers",
            default="all",
        ).strip()

        selected_indices = _parse_tool_selection(selection_input, len(tool_list))

        if selected_indices:
            # Convert indices to tool names
            selected_tools = [tool_list[i - 1] for i in sorted(selected_indices)]

            # Show summary
            console.print()
            console.print(
                Panel(
                    f"[green]Selected {len(selected_tools)} tools[/green]:\n\n"
                    + "\n".join(f"• {tool}" for tool in selected_tools),
                    border_style="green",
                    title="Tool Summary",
                )
            )

            if Confirm.ask("Use these tools?", default=True):
                return selected_tools
        else:
            console.print("[yellow]No tools selected. Please try again.[/yellow]")
            console.print()


def _prompt_tool_categories() -> List[str]:
    """
    Prompt user to select tool categories (technical, fundamental, sentiment/news).

    Returns:
        List of selected category names (e.g., ["technical_indicators", "fundamental"])
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from tool_registry import TOOL_CATEGORIES
    except ImportError:
        console.print("[red]Could not load tool categories.[/red]")
        return ["technical_indicators"]  # Default fallback

    prompt_text = (
        "[bold]Select Tool Categories[/bold]\n\n"
        "Choose which types of tools the LLM can use:\n\n"
    )

    categories_list = list(TOOL_CATEGORIES.keys())
    for i, cat in enumerate(categories_list, 1):
        desc = TOOL_CATEGORIES[cat]["description"]
        tool_count = len(TOOL_CATEGORIES[cat]["tools"])
        prompt_text += f"{i}. {cat:25} ({tool_count} tools) - {desc}\n"

    console.print(Panel(prompt_text, title="Step • Tool Categories", border_style="cyan"))

    # Multi-select with checkboxes
    selected = []
    for i, cat in enumerate(categories_list, 1):
        should_select = Confirm.ask(f"  Include {cat}?", default=(i == 1))
        if should_select:
            selected.append(cat)

    if not selected:
        console.print("[yellow]At least one category required. Using technical indicators as default.[/yellow]")
        selected = ["technical_indicators"]

    return selected


def _prompt_include_news() -> bool:
    """Prompt user to enable/disable news and sentiment analysis tools."""
    prompt_text = (
        "[bold]Include News & Sentiment?[/bold]\n\n"
        "News tools allow the LLM to incorporate company news, world events,\n"
        "and market sentiment into decisions.\n\n"
        "• Improves analysis quality but uses additional API calls\n"
        "• Can be turned on/off separately from other tools"
    )
    console.print(Panel(prompt_text, title="Step • News & Sentiment", border_style="cyan"))

    return Confirm.ask("Include news and sentiment tools?", default=False)


def _prompt_technical_date_range() -> int | None:
    """Prompt for technical indicators date range (optional)."""
    prompt_text = (
        "[bold]Technical Indicators Date Range[/bold]\n\n"
        "Specify how many days of historical data to fetch for technical indicators.\n\n"
        "• Leave blank to let the LLM decide based on analysis needs\n"
        "• Enter a number (e.g., 60, 90, 180) to lock a specific range\n"
        "• Shorter ranges = faster but less historical context\n"
        "• Longer ranges = slower but more context"
    )
    console.print(Panel(prompt_text, title="Step • Technical Data Range", border_style="cyan"))

    while True:
        user_input = Prompt.ask("Date range (days, or press Enter for auto)", default="").strip()

        if not user_input:
            return None  # Agent decides

        try:
            days = int(user_input)
            if days < 1:
                raise ValueError
            return days
        except ValueError:
            console.print("[red]Please enter a positive number or press Enter.[/red]")


def _check_and_setup_fmp_api_key() -> bool:
    """
    Check for FMP API key at startup and offer to set it up.

    Returns:
        True if user has FMP access (either already set or entered), False otherwise.
    """
    # Check if FMP API key is already set
    fmp_key = os.getenv("fmp_api_key")

    if fmp_key:
        console.print(
            Panel(
                f"[green]✅ FMP API Key detected[/green]\nFMP tools will be available.",
                border_style="green",
                title="FMP Access",
            )
        )
        return True

    # No FMP key found, ask if user wants to set it up
    console.print(
        Panel(
            "[bold yellow]FMP API Key Not Found[/bold yellow]\n\n"
            "FMP provides fast precomputed technical indicators (RSI, EMA, Bollinger Bands, OBV).\n"
            "Without FMP access, you'll use slower OpenBB indicators (still free, just slower).\n\n"
            "Free tier: Limited requests per day\n"
            "Paid tier: Higher limits + premium indicators",
            border_style="yellow",
            title="FMP Setup",
        )
    )

    has_fmp_key = Confirm.ask("Do you have an FMP API key?", default=False)

    if not has_fmp_key:
        console.print(
            Panel(
                "✅ Continuing without FMP\nYou'll use OpenBB indicators (free, slower).",
                border_style="blue",
            )
        )
        return False

    # User has an API key - prompt for it
    console.print("\n[dim]Enter your FMP API key. It will be saved to .env[/dim]")
    fmp_key = Prompt.ask("FMP API Key", password=False).strip()

    if not fmp_key:
        console.print("[yellow]⚠️  No key entered. Continuing without FMP access.[/yellow]")
        return False

    # Save to .env file
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        # Read existing .env if it exists
        env_content = ""
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                env_content = f.read()

        # Remove any existing fmp_api_key line
        lines = env_content.split("\n")
        lines = [line for line in lines if not line.startswith("fmp_api_key=")]

        # Add new key
        lines.append(f"fmp_api_key={fmp_key}")

        # Write back
        with open(env_file, "w") as f:
            f.write("\n".join(lines))

        # Also set in current environment
        os.environ["fmp_api_key"] = fmp_key

        console.print(
            Panel(
                f"[green]✅ FMP API Key saved to .env[/green]\nFMP tools are now enabled.",
                border_style="green",
                title="FMP Configured",
            )
        )
        return True

    except Exception as e:  # noqa: BLE001
        console.print(
            Panel(
                f"[red]Failed to save FMP key: {e}[/red]\n"
                "You can manually add `fmp_api_key=YOUR_KEY` to .env",
                border_style="red",
            )
        )
        # Still set in environment even if file write failed
        os.environ["fmp_api_key"] = fmp_key
        return True


def run_interactive() -> None:
    os.system("clear" if os.name != "nt" else "cls")
    _banner()

    # FMP API Key Check at Startup (before mode selection so it's available for all modes)
    has_fmp_access = _check_and_setup_fmp_api_key()

    # Step 1: Engine Selection (live vs backtest)
    engine_mode = _prompt_engine_mode()

    # If user selected backtest, branch into backtesting flow and exit.
    if engine_mode == "backtest":
        if not BACKTESTING_AVAILABLE or RUN_BACKTEST is None:
            console.print(
                Panel(
                    "Backtesting backend is not available.\n"
                    "Make sure the `backtesting/` package and its dependencies are installed.",
                    border_style="red",
                    title="Backtest Unavailable",
                )
            )
            return

        # Prompt for basic backtest configuration.
        console.print(
            Panel(
                "Configure your backtest run.\n"
                "- You can specify a single date or a date range.\n"
                "- Currently one symbol is backtested per run.",
                title="Backtest Configuration",
                border_style="cyan",
            )
        )

        symbols = _prompt_symbols_analysis()
        symbol = symbols[0]
        if len(symbols) > 1:
            console.print(
                f"[dim]Multiple symbols entered; backtest will run for [bold]{symbol}[/bold] only.[/dim]"
            )

        starting_cash = _prompt_starting_capital()

        # Date selection: single date or range
        choice = Prompt.ask(
            "Backtest type",
            choices=["single", "range"],
            default="single",
            show_choices=True,
        ).strip()

        if choice == "range":
            start_date = Prompt.ask(
                "Start date (YYYY-MM-DD)",
                default=date.today().isoformat(),
            )
            end_date = Prompt.ask(
                "End date (YYYY-MM-DD)",
                default=date.today().isoformat(),
            )
        else:
            single_date = Prompt.ask(
                "Backtest date (YYYY-MM-DD)",
                default=date.today().isoformat(),
            )
            start_date = single_date
            end_date = None

        console.print()
        console.print(
            Panel(
                f"[bold green]Starting backtest[/bold green]\n"
                f"• Symbol: {symbol}\n"
                f"• Start: {start_date}\n"
                f"• End: {end_date or start_date}\n"
                f"• Starting cash: ${starting_cash:,.2f}",
                border_style="green",
            )
        )

        try:
            asyncio.run(
                RUN_BACKTEST(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    starting_cash=starting_cash,
                )
            )
        except Exception as exc:  # noqa: BLE001
            console.print(
                Panel(
                    f"[red]Error while running backtest:[/red]\n{str(exc)}",
                    border_style="red",
                    title="Backtest Error",
                )
            )

        return

    # Step 2: Mode Selection (so we know how to interpret symbols/portfolio)
    analysis_mode = _prompt_analysis_mode()

    # Step 3: Strategy Selection (Long Only vs. Long/Short) - As requested (2nd question)
    allow_short_selling = _prompt_trading_strategy()


    # Step 4: Starting Capital
    capital = _prompt_starting_capital()

    # Step 5: Alpaca Credentials (for Alpaca modes: 2 = paper, 3 = live)
    alpaca_api_key = ""
    alpaca_api_secret = ""
    alpaca_paper_trading = True  # default; refined below based on mode
    if analysis_mode in ("paper", "alpaca_live"):
        alpaca_api_key, alpaca_api_secret = _prompt_alpaca_credentials()
        # Mode 2 (paper) -> always use Alpaca paper environment
        # Mode 3 (alpaca_live) -> always use Alpaca live environment
        alpaca_paper_trading = analysis_mode == "paper"

    # Initialize these variables for all paths
    portfolio_mode: PortfolioMode = "new"
    portfolio = None
    force_reset = False
    technical_indicators_date_range = None

    # Analysis vs Alpaca-specific branching
    if analysis_mode == "analysis":
        # Step 4: Portfolio Source (Analysis)
        portfolio_mode, portfolio, force_reset = _prompt_analysis_portfolio_source()

        # Step 5: Symbols for analysis
        symbols = _prompt_symbols_analysis()

        # Step 7: Run Mode (analysis is always one-shot)
        run_mode: RunMode = "once"  # type: ignore
    else:
        # Alpaca-backed modes (paper or alpaca_live)
        # Step 5: Symbols / Portfolio selection (Alpaca)
        symbols = _prompt_symbols_for_alpaca()

        # Validate symbols for Alpaca mode
        if not symbols:
            console.print(
                Panel(
                    "[red]⚠️  Alpaca modes require at least one symbol.[/red]\n\n"
                    "You pressed Enter to use all Alpaca positions, but this feature is not yet supported.\n"
                    "Please enter specific symbol(s) you want to trade (e.g., AAPL, MSFT, TSLA).\n\n"
                    "[dim]Note: You can also use 'analysis' mode for one-shot multi-symbol analysis without Alpaca integration.[/dim]",
                    border_style="red",
                    title="Invalid Configuration",
                )
            )
            return

        # Step 6: Run Mode - Alpaca only supports daemon (scheduled) mode
        # For one-shot analysis, use the "analysis" mode instead
        console.print(
            Panel(
                "[bold cyan]Alpaca Trading Schedule:[/bold cyan]\n"
                "Alpaca modes run on a fixed schedule:\n"
                "• [bold]Daemon mode[/bold]: scheduled runs (default: 13:00 GMT and 19:00 GMT each trading day)\n"
                "• You'll have the option to customize these times on the next screen\n\n"
                "[dim]Note: For one-shot analysis without broker integration, use 'analysis' mode[/dim]",
                title="Step 6 • Schedule",
                border_style="cyan",
            )
        )
        run_mode: RunMode = "daemon"  # type: ignore
        console.print("[yellow]ℹ️  Alpaca mode set to daemon (scheduled trading)[/yellow]\n")

        # For Alpaca modes, portfolio_mode/portfolio are not used
        portfolio_mode: PortfolioMode = "new"
        portfolio = None
        force_reset = False

    # Step 9: Notes
    notes = _prompt_notes()

    # Step 10: Tool Selection
    selected_tool_categories = _prompt_tool_categories()
    include_news = _prompt_include_news()
    technical_indicators_date_range = _prompt_technical_date_range()

    # Step 11: Scheduling (only if daemon mode)
    scheduled_times_gmt = None
    first_run_date = None
    first_day_entry_time_gmt = None

    if run_mode == "daemon":
        # Automatically set first-day entry to NOW + 1 minute (buffer for PM2 startup)
        from datetime import datetime as dt, timedelta
        now_utc = dt.now(timezone.utc)
        entry_time_utc = now_utc + timedelta(minutes=1)  # Add 1 minutebuffer
        first_run_date = entry_time_utc.date().isoformat()  # Today's date (YYYY-MM-DD)
        first_day_entry_time_gmt = entry_time_utc.strftime("%H:%M")  # Entry time +1 minute (HH:MM GMT)

        console.print()
        console.print(
            Panel(
                "[bold cyan]First Day Entry[/bold cyan]\n\n"
                f"Your initial trade will run in [bold]~1 minute [/bold] (buffer for PM2 startup).\n"
                f"[bold]Date:[/bold] {first_run_date}\n"
                f"[bold]Time (GMT):[/bold] {first_day_entry_time_gmt}\n\n"
                f"After today, the daemon will follow your custom schedule daily.",
                border_style="cyan",
                title="First Day Configuration",
            )
        )

        # Ask for custom scheduled times for subsequent days
        scheduled_times_gmt = _prompt_scheduled_times_gmt()

    # Trade mode is inferred from analysis_mode
    trade_mode: TradeMode = "paper"  # type: ignore
    if analysis_mode in ("paper", "alpaca_live"):
        trade_mode = "live"

    cfg = SessionConfig(
        symbols=symbols,
        starting_capital=capital,
        trade_mode=trade_mode,
        run_mode=run_mode,
        analysis_mode=analysis_mode,
        portfolio_mode=portfolio_mode,
        portfolio=portfolio,
        notes=notes,
        alpaca_api_key=alpaca_api_key,
        alpaca_api_secret=alpaca_api_secret,
        alpaca_paper_trading=alpaca_paper_trading,
        force_reset_portfolio=force_reset,
        has_fmp_access=has_fmp_access,
        scheduled_times_gmt=scheduled_times_gmt,
        first_run_date=first_run_date,
        first_day_entry_time_gmt=first_day_entry_time_gmt,
        selected_tool_categories=selected_tool_categories,
        include_news=include_news,
        technical_indicators_date_range=technical_indicators_date_range,
        allow_short_selling=allow_short_selling,
    )

    console.print()
    if _review_config(cfg):
        _simulate_launch(cfg)
    else:
        console.print(
            Panel(
                "Configuration cancelled. You can re‑run the launcher to start over.",
                border_style="red",
            )
        )


if __name__ == "__main__":
    run_interactive()


 