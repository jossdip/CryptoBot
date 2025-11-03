from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel


console = Console()


def _fmt_time(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except Exception:
        return "-"


def render_portfolio(summary: Dict[str, Any]) -> None:
    table = Table(title="Portfolio Summary")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Last Update", _fmt_time(summary.get("timestamp", 0)))
    table.add_row("Balance", f"${summary.get('balance', 0.0):,.2f}")
    table.add_row("Equity", f"${summary.get('equity', 0.0):,.2f}")
    table.add_row("Unrealized PnL", f"${summary.get('unrealized_pnl', 0.0):,.2f}")
    console.print(table)


def render_trades(trades: List[Dict[str, Any]], *, title: str = "Recent Trades") -> None:
    table = Table(title=title)
    table.add_column("Time")
    table.add_column("Strat")
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Size", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Exit", justify="right")
    table.add_column("PnL", justify="right")
    for t in trades:
        pnl = float(t.get("pnl", 0.0))
        pnl_str = f"[green]{pnl:,.2f}[/green]" if pnl >= 0 else f"[red]{pnl:,.2f}[/red]"
        table.add_row(
            _fmt_time(t.get("timestamp", 0)),
            str(t.get("strategy", "-"))[:14],
            str(t.get("symbol", "-"))[:10],
            str(t.get("side", "-")),
            f"{float(t.get('size', 0.0)):.4f}",
            f"{float(t.get('entry', 0.0)):.2f}",
            f"{float(t.get('exit', 0.0)):.2f}",
            pnl_str,
        )
    console.print(table)


def render_ai_insights(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        console.print(Panel("No AI insights yet", title="AI Insights"))
        return
    table = Table(title="AI Insights")
    table.add_column("Time")
    table.add_column("Type")
    table.add_column("Sentiment")
    table.add_column("Confidence")
    table.add_column("Reasoning")
    for r in rows:
        conf = r.get("confidence")
        conf_s = "-" if conf is None else f"{float(conf):.2f}"
        table.add_row(
            _fmt_time(r.get("timestamp", 0)),
            str(r.get("decision_type", "-")),
            str(r.get("sentiment", "-")),
            conf_s,
            str(r.get("reasoning", ""))[:80],
        )
    console.print(table)


