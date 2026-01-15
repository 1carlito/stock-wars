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
from dataclasses import dataclass, asdict
from datetime import date, datetime
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


RiskLevel = Literal["low", "medium", "high"]
TradeMode = Literal["paper", "live"]
RunMode = Literal["once", "daemon"]
PortfolioMode = Literal["new", "current"]
AnalysisMode = Literal["analysis", "paper", "alpaca_live"]


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
    risk_level: RiskLevel
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
            fig = Figlet(font="big", width=120)

        # Slight spacing tweak so STOCK and MANAGER feel balanced.
        ascii_art = fig.renderText("LLM  STOCK    MANAGER")

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


def _banner() -> None:
    # Simpler banner: just header + footer, no extra empty body box.
    console.print(_render_header())
    console.print(_render_footer())
    console.print()  # Single blank line before prompts


def _prompt_symbols() -> List[str]:
    prompt_text = (
        "Enter the ticker **symbol or symbols** you want the agent to manage.\n"
        "[dim]Examples: AAPL, MSFT, NVDA[/dim]"
    )
    console.print(Panel(prompt_text, title="Step 1 • Symbols", border_style="cyan"))

    while True:
        raw = Prompt.ask("Symbols (comma‑separated)", default="AAPL")
        symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        if symbols:
            return symbols
        console.print("[red]Please enter at least one symbol.[/red]")


def _prompt_risk_level() -> RiskLevel:
    prompt_text = (
        "Select a **risk level**. This will eventually control position sizing,\n"
        "leverage, and stop‑loss aggressiveness.\n\n"
        "- [bold green]low[/bold green]: capital preservation, small positions\n"
        "- [bold yellow]medium[/bold yellow]: balanced risk / reward\n"
        "- [bold red]high[/bold red]: aggressive, higher drawdown tolerance"
    )
    console.print(Panel(prompt_text, title="Step 2 • Risk Profile", border_style="cyan"))

    choice = Prompt.ask(
        "Risk level",
        choices=["low", "medium", "high"],
        default="medium",
        show_choices=True,
    )
    return choice  # type: ignore[return-value]


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


def _prompt_notes() -> str:
    console.print(
        Panel(
            "Optional: add any [bold]session notes[/bold] or constraints "
            "(e.g. 'no earnings plays', 'focus on mega‑caps only').",
            title="Step 8 • Notes (Optional)",
            border_style="cyan",
        )
    )
    return Prompt.ask("Notes", default="")


def _prompt_analysis_mode() -> AnalysisMode:
    """Prompt user to select analysis/trading mode (numeric 1/2/3 only)."""
    prompt_text = (
        "Select your trading mode:\n\n"
        "[bold]1.[/bold] [bold green]Investment Analysis Only[/bold green]\n"
        "   • Test strategies without actual trades\n"
        "   • Uses a theoretical portfolio file only (no broker, no Alpaca)\n\n"
        "[bold]2.[/bold] [bold yellow]Paper Trading (Simulated)[/bold yellow]\n"
        "   • Simulate trades with virtual capital using a local paper portfolio file\n"
        "   • Supports daemon scheduling\n\n"
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
    live_trade_dir = _get_live_trade_dir()
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
    table.add_row("Risk level", cfg.risk_level)
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

    if not LIVE_TRADING_AVAILABLE:
        console.print(
            Panel(
                "[red]Live trading backend not available.[/red]\n"
                "Running analysis mode only (no actual trading).",
                border_style="yellow",
            )
        )
        # Run analysis for each symbol with a spinner and compact summary.
        for sym in cfg.symbols:
            _run_analysis_for_symbol(cfg, sym)
        return

    console.print()
    console.print(
        Panel(
            f"[bold cyan]Configuration Summary:[/bold cyan]\n"
            f"• Symbols: {', '.join(cfg.symbols)}\n"
            f"• Risk Level: {cfg.risk_level}\n"
            f"• Starting Capital: ${cfg.starting_capital:,.2f}\n"
            f"• Trade Mode: {cfg.trade_mode}\n"
            f"• Run Mode: {cfg.run_mode}\n"
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
                console.print(
                    Panel(
                        "[bold cyan]Daemon Mode:[/bold cyan]\n"
                        f"The agent will trade {first_symbol} once per trading day at 15:00 ET.\n"
                        "[yellow]Note: Daemon mode supports single stock. For multi-stock, use 'once' mode.[/yellow]\n"
                        "[yellow]Press Ctrl+C to stop the daemon.[/yellow]",
                        border_style="cyan",
                    )
                )
                # Engine mode: use Alpaca-backed portfolio for both paper (2) and live (3)
                engine_mode = "analysis" if cfg.analysis_mode == "analysis" else "alpaca_live"
                run_daemon(
                    symbol=first_symbol,
                    starting_capital=cfg.starting_capital,
                    risk_level=cfg.risk_level,
                    notes=cfg.notes,
                    mode=engine_mode,
                )
            else:  # once mode
                console.print("[bold cyan]Running one-shot trading cycle...[/bold cyan]")
                # Engine mode: use Alpaca-backed portfolio for both paper (2) and live (3)
                engine_mode = "analysis" if cfg.analysis_mode == "analysis" else "alpaca_live"
                run_once(
                    symbols=cfg.symbols,
                    starting_capital=cfg.starting_capital,
                    risk_level=cfg.risk_level,
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


def run_interactive() -> None:
    os.system("clear" if os.name != "nt" else "cls")
    _banner()

    # Step 1: Symbols
    symbols = _prompt_symbols()

    # Step 2A: Mode Selection (NEW)
    analysis_mode = _prompt_analysis_mode()

    # Step 3: Risk Level
    risk = _prompt_risk_level()

    # Step 4: Starting Capital
    capital = _prompt_starting_capital()

    # Step 2B: Alpaca Credentials (for Alpaca modes: 2 = paper, 3 = live)
    alpaca_api_key = ""
    alpaca_api_secret = ""
    alpaca_paper_trading = True  # default; refined below based on mode
    if analysis_mode in ("paper", "alpaca_live"):
        alpaca_api_key, alpaca_api_secret = _prompt_alpaca_credentials()
        # Mode 2 (paper) -> always use Alpaca paper environment
        # Mode 3 (alpaca_live) -> always use Alpaca live environment
        alpaca_paper_trading = analysis_mode == "paper"

    # Step 5: Portfolio Reset (analysis-only; Alpaca modes use broker state)
    force_reset = False
    if analysis_mode == "analysis":
        force_reset = _prompt_portfolio_reset()

    # Step 6: Run Mode (skip for analysis mode, default to "once")
    run_mode: RunMode = "once"  # type: ignore
    if analysis_mode != "analysis":
        console.print(
            Panel(
                "How should the agent run?\n"
                "- [bold]once[/bold]: run a single decision cycle and exit\n"
                "- [bold]daemon[/bold]: schedule one run per trading day (15:00 NY time)",
                title="Step 6 • Schedule",
                border_style="cyan",
            )
        )
        choice = Prompt.ask(
            "Run mode",
            choices=["once", "daemon"],
            default="once",
            show_choices=True,
        )
        run_mode = choice  # type: ignore[assignment]

    # Step 7: Portfolio Mode (skip for Alpaca modes, get context for analysis only)
    portfolio_mode: PortfolioMode = "new"
    portfolio = None
    if analysis_mode == "analysis":
        portfolio_mode, portfolio = _prompt_portfolio_mode()

    # Step 8: Notes
    notes = _prompt_notes()

    # Trade mode is inferred from analysis_mode
    trade_mode: TradeMode = "paper"  # type: ignore
    if analysis_mode in ("paper", "alpaca_live"):
        trade_mode = "live"

    cfg = SessionConfig(
        symbols=symbols,
        risk_level=risk,
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


 