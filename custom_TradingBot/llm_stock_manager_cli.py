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
from rich.theme import Theme

try:
    # Optional: used only to render the big ASCII logo at the top.
    from pyfiglet import Figlet
except Exception:  # pragma: no cover - optional dependency
    Figlet = None  # type: ignore[assignment]


APP_VERSION = "LLM Stock Manager CLI v0.1"

THEME = Theme(
    {
        # Match the OpenBB-style tags the user referenced
        "param": "rgb(247,206,70)",  # Yellow/gold
        "menu": "rgb(50,115,185)",   # Blue
        "info": "rgb(224,131,48)",   # Orange
        "cmds": "rgb(102,203,228)",  # Cyan
    }
)

console = Console(theme=THEME)


RiskLevel = Literal["low", "medium", "high"]
TradeMode = Literal["paper", "live"]
RunMode = Literal["once", "daemon"]
TimeHorizon = Literal["intraday", "swing", "long_term"]


@dataclass
class SessionConfig:
    symbols: List[str]
    risk_level: RiskLevel
    starting_capital: float
    max_positions: int
    trade_mode: TradeMode
    run_mode: RunMode
    time_horizon: TimeHorizon
    notes: str = ""


def _boxed_panel(text: str, *, menu: str, border_style: str = "cyan") -> Panel:
    """
    Helper to mimic the OpenBB CLI panel pattern:

    panel.Panel(
        "\\n" + text,
        title=kwargs["menu"],
        subtitle_align="right",
        subtitle=version,
    )
    """
    return Panel(
        "\n" + text,
        title=f"[menu]{menu}[/menu]",
        subtitle=f"[param]{APP_VERSION}[/param]",
        subtitle_align="right",
        border_style=border_style,
    )


def _render_header() -> Panel:
    # If pyfiglet is available, render a big ASCII logo similar to Dexter.
    ascii_block: str
    if Figlet is not None:
        fig = Figlet(font="slant")
        ascii_block = fig.renderText("LLM STOCK\nMANAGER")
    else:
        # Fallback: hand-crafted, still bigger than a single line.
        ascii_block = (
            "██╗     ██╗██╗███╗   ███╗     ███████╗████████╗ ██████╗  ██████╗██╗  ██╗\n"
            "██║     ██║██║████╗ ████║     ██╔════╝╚══██╔══╝██╔═══██╗██╔════╝██║ ██╔╝\n"
            "██║     ██║██║██╔████╔██║     ███████╗   ██║   ██║   ██║██║     █████╔╝ \n"
            "██║     ██║██║██║╚██╔╝██║     ╚════██║   ██║   ██║   ██║██║     ██╔═██╗ \n"
            "███████╗██║██║██║ ╚═╝ ██║     ███████║   ██║   ╚██████╔╝╚██████╗██║  ██╗\n"
            "╚══════╝╚═╝╚═╝╚═╝     ╚═╝     ╚══════╝   ╚═╝    ╚═════╝  ╚═════╝╚═╝  ╚═╝\n"
        )

    header = Text()
    header.append(ascii_block, style="menu")
    header.append("\n")
    header.append("Autonomous Stock Management Agent\n", style="dim")
    header.append("\n")
    header.append(
        "Configure a live trading session using natural, high‑level inputs.",
        style="info",
    )

    return Panel(
        Align.left(header),
        title="[menu]Home[/menu]",
        subtitle=f"[param]{APP_VERSION}[/param]",
        subtitle_align="right",
        border_style="bright_magenta",
        padding=(1, 4),
    )


def _render_footer() -> Panel:
    footer_text = Text()
    footer_text.append("Tip: ", style="bold cyan")
    footer_text.append(
        "This interface is UI-only right now.\n"
        "Once wired up, these settings will feed directly into the live agent.",
        style="dim",
    )
    return Panel(footer_text, border_style="grey42")


def _banner() -> None:
    """
    Render the top banner area.

    Simpler than a full-screen Layout so we don't introduce huge vertical
    gaps: just print the header panel and the small footer panel one after
    the other.
    """
    console.print(_render_header())
    console.print(_render_footer())


def _prompt_symbols() -> List[str]:
    prompt_text = (
        "[info]Enter the ticker [param]symbol or symbols[/param] you want the agent to manage.[/info]\n\n"
        "[dim]Examples: AAPL, MSFT, NVDA • Default if left blank: AAPL[/dim]"
    )
    console.print(_boxed_panel(prompt_text, menu="Step 1 • Symbols"))

    while True:
        # Avoid showing the default in parentheses in the main prompt,
        # which can be visually confusing. We handle the default manually.
        raw = Prompt.ask("Symbols (comma‑separated)") or "AAPL"
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
    console.print(_boxed_panel(prompt_text, menu="Step 2 • Risk Profile"))

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
    console.print(_boxed_panel(prompt_text, menu="Step 3 • Capital"))

    while True:
        amount_str = Prompt.ask("Starting capital (USD)", default="10000")
        try:
            value = float(amount_str)
            if value <= 0:
                raise ValueError
            return value
        except ValueError:
            console.print("[red]Please enter a positive number (e.g. 5000, 10000).[/red]")


def _prompt_max_positions(default: int) -> int:
    prompt_text = (
        "How many **concurrent positions** should the agent allow?\n"
        "This caps diversification and overall exposure."
    )
    console.print(_boxed_panel(prompt_text, menu="Step 4 • Position Limits"))
    return IntPrompt.ask("Max open positions", default=default)


def _prompt_trade_mode() -> TradeMode:
    prompt_text = (
        "Choose whether this configuration is intended for **paper** or **live** trading.\n"
        "Right now this is informational only, but it will guide safety checks later."
    )
    console.print(_boxed_panel(prompt_text, menu="Step 5 • Mode"))

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
    console.print(_boxed_panel(prompt_text, menu="Step 6 • Schedule"))

    choice = Prompt.ask(
        "Run mode",
        choices=["once", "daemon"],
        default="once",
        show_choices=True,
    )
    return choice  # type: ignore[return-value]


def _prompt_time_horizon() -> TimeHorizon:
    prompt_text = (
        "What is your **intended holding period**?\n"
        "- [bold]intraday[/bold]: same‑day entries and exits\n"
        "- [bold]swing[/bold]: multi‑day to multi‑week\n"
        "- [bold]long_term[/bold]: months to years"
    )
    console.print(_boxed_panel(prompt_text, menu="Step 7 • Time Horizon"))

    choice = Prompt.ask(
        "Time horizon",
        choices=["intraday", "swing", "long_term"],
        default="swing",
        show_choices=True,
    )
    return choice  # type: ignore[return-value]


def _prompt_notes() -> str:
    console.print(
        _boxed_panel(
            "Optional: add any [bold]session notes[/bold] or constraints "
            "(e.g. 'no earnings plays', 'focus on mega‑caps only').",
            menu="Step 8 • Notes (Optional)",
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
    table.add_row("Max positions", str(cfg.max_positions))
    table.add_row("Trading mode", cfg.trade_mode)
    table.add_row("Run mode", cfg.run_mode)
    table.add_row("Time horizon", cfg.time_horizon.replace("_", " "))
    table.add_row("Notes", cfg.notes or "—")

    panel = Panel(
        table,
        title="Review Configuration",
        border_style="bright_magenta",
    )
    console.print(panel)
    return Confirm.ask("Launch session with these settings?", default=True)


def _simulate_launch(cfg: SessionConfig) -> None:
    console.print()
    console.print(
        Panel(
            Text(
                "Launching LLM STOCK MANAGER (simulation only)...",
                style="bold green",
            ),
            border_style="green",
        )
    )

    steps = [
        "Validating configuration",
        "Initializing reasoning engine",
        "Loading market calendar",
        "Preparing portfolio state",
        "Scheduling first decision cycle",
    ]

    for step in track(steps, description="Preparing session", transient=True):
        _ = step  # noqa: F841
        # We don't actually sleep here to keep the CLI snappy.

    console.print()
    console.print(
        Panel(
            Text(
                "Session ready.\n\n"
                "In a future version, this is where the live trading loop would start.\n"
                "You can now wire this configuration into the existing "
                "`live_trading_loop.py` entrypoint.",
                style="bold",
            ),
            border_style="green",
        )
    )

    # Show the raw config dict for developers who want to copy‑paste it.
    dev_panel = Panel(
        str(asdict(cfg)),
        title="Developer View • SessionConfig",
        border_style="grey50",
    )
    console.print(dev_panel)


def run_interactive() -> None:
    os.system("clear" if os.name != "nt" else "cls")
    _banner()

    symbols = _prompt_symbols()
    risk = _prompt_risk_level()
    capital = _prompt_starting_capital()
    max_pos_default = max(1, len(symbols))
    max_positions = _prompt_max_positions(default=max_pos_default)
    trade_mode = _prompt_trade_mode()
    run_mode = _prompt_run_mode()
    horizon = _prompt_time_horizon()
    notes = _prompt_notes()

    cfg = SessionConfig(
        symbols=symbols,
        risk_level=risk,
        starting_capital=capital,
        max_positions=max_positions,
        trade_mode=trade_mode,
        run_mode=run_mode,
        time_horizon=horizon,
        notes=notes,
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


