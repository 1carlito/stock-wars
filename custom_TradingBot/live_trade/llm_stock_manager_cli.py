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
from dataclasses import dataclass, asdict
from typing import List, Literal

from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text
from rich.progress import track

# Wire into live trading workflow
import sys
if __package__:
    # Running as module (python -m custom_TradingBot.live_trade.llm_stock_manager_cli)
    from . import live_trading_loop
else:
    # Running directly (python3 llm_stock_manager_cli.py)
    # Add the live_trade directory to path so we can import live_trading_loop from same dir
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    if _current_dir not in sys.path:
        sys.path.insert(0, _current_dir)
    # Also add parent (custom_TradingBot) for any parent-level imports
    _parent_dir = os.path.dirname(_current_dir)
    if _parent_dir not in sys.path:
        sys.path.insert(0, _parent_dir)
    import live_trading_loop


console = Console()


RiskLevel = Literal["low", "medium", "high"]
TradeMode = Literal["paper", "live"]
RunMode = Literal["once", "daemon"]
TimeHorizon = Literal["intraday", "swing", "long_term"]


@dataclass
class SessionConfig:
    symbols: List[str]
    risk_level: RiskLevel
    starting_capital: float
    trade_mode: TradeMode
    run_mode: RunMode
    notes: str = ""


def _render_header() -> Panel:
    # Generate ASCII art banner with Star Wars style and dark yellow gradient
    try:
        from pyfiglet import Figlet
        # Try Star Wars style fonts, fallback to thicker fonts
        star_wars_fonts = ['starwars', 'epic', 'isometric1', 'big']
        fig = None
        for font_name in star_wars_fonts:
            try:
                fig = Figlet(font=font_name, width=120)
                break
            except:
                continue
        
        if fig is None:
            # Fallback to big if none work
            fig = Figlet(font='big', width=120)
        
        # Render with reduced space between LLM and STOCK, but keep larger space before MANAGER
        # "LLM  STOCK    MANAGER" (2 spaces, then 4 spaces)
        ascii_art = fig.renderText('LLM  STOCK    MANAGER')
        
        # Apply dark yellow gradient: alternate between yellow and bright_yellow character by character
        title = Text()
        lines = ascii_art.split('\n')
        for line in lines:
            for i, char in enumerate(line):
                # Alternate colors for gradient effect in dark yellow tones
                if i % 2 == 0:
                    title.append(char, style="bold yellow")
                else:
                    title.append(char, style="bold bright_yellow")
            title.append("\n")
        
        # Add General Grievous ASCII art (collector/trader theme) after MANAGER
        # General Grievous collects lightsabers like a trader collects assets - perfect fit!
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
    except ImportError:
        # Fallback if pyfiglet not available
        title = Text("LLM    STOCK    MANAGER", style="bold yellow")
    
    subtitle = Text("Autonomous Live Trade Orchestrator", style="dim")

    text = Text()
    text.append(title)
    text.append("\n")
    text.append(subtitle)

    return Panel(
        text,
        border_style="bright_magenta",
        padding=(1, 2),
        expand=False,
    )


def _render_footer() -> Panel:
    footer_text = Text()
    footer_text.append("Tip: ", style="bold cyan")
    footer_text.append("This interface now launches the live trading loop.\n", style="dim")
    return Panel(footer_text, border_style="grey42")


def _banner() -> None:
    # Print header and footer directly without layout to avoid gaps
    console.print(_render_header())
    console.print(_render_footer())
    console.print()  # Single newline before prompts


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


# Removed _prompt_max_positions - not needed for once-a-day trading


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


# Removed _prompt_time_horizon - redundant for current trading strategy


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
    table.add_row("Notes", cfg.notes or "—")

    panel = Panel(
        table,
        title="Review Configuration",
        border_style="bright_magenta",
    )
    console.print(panel)
    return Confirm.ask("Launch session with these settings?", default=True)


def _launch_session(cfg: SessionConfig) -> None:
    console.print()
    console.print(
        Panel(
            Text(
                "Launching LLM STOCK MANAGER (live paper trading)...",
                style="bold green",
            ),
            border_style="green",
        )
    )

    # Only paper trading is supported end‑to‑end right now
    if cfg.trade_mode != "paper":
        console.print(
            Panel(
                Text(
                    "Live broker mode is not enabled yet.\n"
                    "Please re‑run and choose [bold]paper[/bold] trading.",
                    style="bold red",
                ),
                border_style="red",
            )
        )
        return

    # Ensure Alpaca paper trading is enabled for this process
    os.environ.setdefault("ALPACA_ENABLED", "true")
    os.environ.setdefault("ALPACA_PAPER", "true")

    # Simple progress banner
    steps = [
        "Validating configuration",
        "Initializing reasoning agent",
        "Starting live trading loop",
    ]
    for step in track(steps, description="Preparing session", transient=True):
        _ = step  # noqa: F841

    console.print()

    # Run once vs daemon - pass config through
    if cfg.run_mode == "once":
        for sym in cfg.symbols:
            console.print(
                Panel(
                    Text(
                        f"Running one‑shot live trading cycle for [bold]{sym}[/bold]...",
                        style="bold green",
                    ),
                    border_style="green",
                )
            )
            live_trading_loop.run_once(
                sym.upper(),
                starting_capital=cfg.starting_capital,
                risk_level=cfg.risk_level,
                notes=cfg.notes,
            )
    else:
        if len(cfg.symbols) > 1:
            console.print(
                Panel(
                    Text(
                        "Daemon mode currently supports one symbol per process.\n"
                        "Using the first symbol only.",
                        style="yellow",
                    ),
                    border_style="yellow",
                )
            )
        sym = cfg.symbols[0].upper()
        console.print(
            Panel(
                Text(
                    f"Starting daemon live trading loop for [bold]{sym}[/bold]...",
                    style="bold green",
                ),
                border_style="green",
            )
        )
        live_trading_loop.run_daemon(
            sym,
            starting_capital=cfg.starting_capital,
            risk_level=cfg.risk_level,
            notes=cfg.notes,
        )


def run_interactive() -> None:
    os.system("clear" if os.name != "nt" else "cls")
    _banner()

    symbols = _prompt_symbols()
    risk = _prompt_risk_level()
    capital = _prompt_starting_capital()
    trade_mode = _prompt_trade_mode()
    run_mode = _prompt_run_mode()
    notes = _prompt_notes()

    cfg = SessionConfig(
        symbols=symbols,
        risk_level=risk,
        starting_capital=capital,
        trade_mode=trade_mode,
        run_mode=run_mode,
        notes=notes,
    )

    console.print()
    if _review_config(cfg):
        _launch_session(cfg)
    else:
        console.print(
            Panel(
                "Configuration cancelled. You can re‑run the launcher to start over.",
                border_style="red",
            )
        )


if __name__ == "__main__":
    run_interactive()


