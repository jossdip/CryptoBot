from __future__ import annotations

import argparse
import time
from typing import Any, Dict, List

from cryptobot.monitor.reporter import ReportGenerator
from cryptobot.monitor.display import render_ai_insights, render_portfolio, render_trades, console
from cryptobot.monitor.storage import StorageManager

from .base import Command


class MonitorCommand(Command):
    name = "monitor"
    aliases = ["m"]

    def run(self, args: List[str]) -> None:  # pragma: no cover - simple CLI glue
        parser = argparse.ArgumentParser(prog="monitor", add_help=False)
        parser.add_argument("--trades", type=int, default=10)
        parser.add_argument("--refresh", type=int, default=5)
        parser.add_argument("--strategy", type=str, default=None)
        parser.add_argument("--symbol", type=str, default=None)
        parser.add_argument("--period", type=str, default=None)
        parser.add_argument("--format", type=str, choices=["table", "json", "compact"], default="table")
        parser.add_argument("--insights", action="store_true")
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--revenues", action="store_true")
        parser.add_argument("--gains", action="store_true")
        parser.add_argument("--losses", action="store_true")
        try:
            opts = parser.parse_args(args)
        except SystemExit:
            return

        cfg = self.context.get("config")
        storage_path = cfg.monitor.storage_path if cfg and getattr(cfg, "monitor", None) else "~/.cryptobot/monitor.db"
        storage = StorageManager(storage_path)
        reporter = ReportGenerator(storage)

        def _parse_period(p: str | None) -> float:
            import time as _time
            if not p or p == "all":
                return 0.0
            try:
                if p.endswith("h"):
                    hours = int(p[:-1])
                    return _time.time() - hours * 3600
                if p.endswith("d"):
                    days = int(p[:-1])
                    return _time.time() - days * 86400
            except Exception:
                return 0.0
            return 0.0

        def render_once() -> None:
            console.clear()
            portfolio = reporter.portfolio_summary()
            render_portfolio(portfolio)
            trades = reporter.recent_trades(limit=int(opts.trades), strategy=opts.strategy, symbol=opts.symbol)
            since = _parse_period(opts.period)
            if since > 0.0:
                trades = [t for t in trades if float(t.get("timestamp", 0.0)) >= since]
            if opts.gains:
                trades = [t for t in trades if float(t.get("pnl", 0.0)) > 0]
            if opts.losses:
                trades = [t for t in trades if float(t.get("pnl", 0.0)) <= 0]
            render_trades(trades)
            if opts.revenues:
                total = sum(float(t.get("pnl", 0.0)) for t in trades)
                console.print(f"[bold]Revenues (sum PnL):[/bold] {'[green]' if total>=0 else '[red]'}{total:,.2f}[/]")
            if opts.insights:
                render_ai_insights(reporter.ai_insights(limit=5))

        if bool(opts.live):
            while True:
                render_once()
                time.sleep(int(opts.refresh))
        else:
            render_once()


