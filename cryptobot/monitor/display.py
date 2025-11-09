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


def render_positions(summary: Dict[str, Any]) -> None:
    positions = summary.get("positions") or {}
    # Normalize to dict of symbol -> position dicts
    if isinstance(positions, list):
        pos_list = positions
    elif isinstance(positions, dict) and "data" in positions and isinstance(positions["data"], list):
        pos_list = positions["data"]
    elif isinstance(positions, dict):
        # positions as map -> convert to list
        pos_list = []
        for k, v in positions.items():
            if isinstance(v, dict):
                p = dict(v)
                p.setdefault("symbol", k)
                pos_list.append(p)
    else:
        pos_list = []
    table = Table(title="Open Positions")
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Price", justify="right")
    table.add_column("Leverage", justify="right")
    if not pos_list:
        console.print(Panel("No open positions", title="Positions"))
        return
    for p in pos_list:
        try:
            sym = str(p.get("symbol") or p.get("coin") or "-")
            qty = float(p.get("qty") or p.get("size") or p.get("sz") or 0.0)
            side = "LONG" if qty > 0 else ("SHORT" if qty < 0 else "-")
            avg_px = float(p.get("avg_price") or p.get("entryPx") or p.get("entryPrice") or 0.0)
            lev = p.get("leverage")
            lev_s = f"{float(lev):.0f}x" if lev is not None else "-"
            table.add_row(sym, side, f"{abs(qty):.6f}", f"{avg_px:.2f}", lev_s)
        except Exception:
            continue
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


def render_trades_with_status(trades: List[Dict[str, Any]], positions_summary: Dict[str, Any]) -> None:
    # Build a quick symbol->qty map from latest positions for OPEN/CLOSED inference
    positions = positions_summary.get("positions") or {}
    symbol_qty: Dict[str, float] = {}
    # Normalize maps and lists
    if isinstance(positions, list):
        for p in positions:
            try:
                sym = str(p.get("symbol") or p.get("coin") or "")
                qty = float(p.get("qty") or p.get("size") or p.get("sz") or 0.0)
                if sym:
                    symbol_qty[sym.upper()] = qty
            except Exception:
                continue
    elif isinstance(positions, dict):
        for k, v in positions.items():
            try:
                if isinstance(v, dict):
                    sym = str(v.get("symbol") or v.get("coin") or k)
                    qty = float(v.get("qty") or v.get("size") or v.get("sz") or 0.0)
                    if sym:
                        symbol_qty[sym.upper()] = qty
            except Exception:
                continue

    def _base_symbol(s: str) -> str:
        s = (s or "").upper()
        if "/" in s:
            s = s.split("/", 1)[0]
        if ":" in s:
            s = s.split(":", 1)[0]
        return s

    table = Table(title="Recent Trades")
    table.add_column("Time")
    table.add_column("Strat")
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Size", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Exit", justify="right")
    table.add_column("PnL", justify="right")
    table.add_column("Status")
    for t in trades:
        pnl = float(t.get("pnl", 0.0))
        pnl_str = f"[green]{pnl:,.2f}[/green]" if pnl >= 0 else f"[red]{pnl:,.2f}[/red]"
        sym = str(t.get("symbol", "-"))
        side = str(t.get("side", "-")).lower()
        base = _base_symbol(sym)
        qty = symbol_qty.get(base, 0.0)
        is_open = (qty != 0.0)
        status = "[yellow]OPEN[/yellow]" if is_open else "CLOSED"
        table.add_row(
            _fmt_time(t.get("timestamp", 0)),
            str(t.get("strategy", "-"))[:14],
            str(t.get("symbol", "-"))[:10],
            str(t.get("side", "-")),
            f"{float(t.get('size', 0.0)):.4f}",
            f"{float(t.get('entry', 0.0)):.2f}",
            f"{float(t.get('exit', 0.0)):.2f}",
            pnl_str if not is_open else "—",
            status,
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


