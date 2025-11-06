from __future__ import annotations

import argparse
import shlex
import threading
import time
from typing import Any, Dict, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

from cryptobot.cli.prompt import build_prompt
from cryptobot.cli.logo import start_animated_logo, refresh_animated_logo, stop_animated_logo
from cryptobot.cli.commands.monitor import MonitorCommand
from cryptobot.cli.commands.config import ConfigCommand
from cryptobot.cli.commands.base import Command
from cryptobot.monitor.storage import StorageManager
from cryptobot.monitor.reporter import ReportGenerator
from cryptobot.monitor.display import render_trades, render_portfolio


class InteractiveShell:
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.console = Console()
        self._status = "STOPPED"
        self._history = InMemoryHistory()
        self._session = PromptSession(history=self._history)
        self._commands: Dict[str, Command] = {}
        self._running_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._register_commands()
        # Démarrer l'animation du logo si activée dans la config
        cfg = self.context.get("config")
        logo_enabled = True
        try:
            logo_enabled = bool(getattr(getattr(cfg, "cli", None), "logo_enabled", True))
        except Exception:
            logo_enabled = True
        if logo_enabled:
            start_animated_logo()

    def _register_commands(self) -> None:
        # Built-ins
        self._commands["monitor"] = MonitorCommand(self.context)
        self._commands["config"] = ConfigCommand(self.context)
        # Aliases
        for name, cmd in list(self._commands.items()):
            for al in getattr(cmd, "aliases", []):
                self._commands[al] = cmd

    def run(self) -> None:  # pragma: no cover - interactive
        cfg = self.context.get("config")
        exchange = getattr(getattr(cfg, "general", None), "exchange_id", "hyperliquid") if cfg else "hyperliquid"
        completer = WordCompleter([
            "start", "stop", "pause", "resume", "status", "monitor",
            "trades", "performance", "portfolio", "strategies", "weights",
            "risk", "config", "logs", "help", "exit", "quit", "clear", "version",
        ], ignore_case=True)

        while True:
            try:
                prompt = build_prompt(exchange=exchange, status=self._status, fmt=getattr(getattr(cfg, "cli", None), "prompt_format", "[C4$H@{exchange}:{status}] > "))
                line = self._session.prompt(prompt, completer=completer)
            except (EOFError, KeyboardInterrupt):
                self.console.print("Exiting...")
                stop_animated_logo()
                break

            parts = shlex.split(line.strip())
            if not parts:
                continue
            cmd, *args = parts
            cmd = cmd.lower()
            if cmd in {"exit", "quit", "q"}:
                self._stop_trading()
                stop_animated_logo()
                break
            if cmd in {"clear", "cls"}:
                self.console.clear()
                # Rafraîchir le logo animé après le clear
                refresh_animated_logo()
                continue
            if cmd in {"help", "h", "?"}:
                self._print_help()
                continue
            if cmd == "version" or cmd == "v":
                self.console.print("C4$H M4CH1N3 Interactive v0.1.0")
                continue
            if cmd == "status" or cmd == "stat":
                self.console.print(f"Status: {self._status}")
                continue
            if cmd == "trades" or cmd == "t":
                self._cmd_trades(args)
                continue
            if cmd == "portfolio" or cmd == "port":
                self._cmd_portfolio()
                continue
            if cmd == "performance" or cmd == "perf":
                self._cmd_performance(args)
                continue
            if cmd == "strategies" or cmd == "strats":
                self._cmd_strategies()
                continue
            if cmd == "risk":
                self._cmd_risk()
                continue
            if cmd == "logs" or cmd == "l":
                self._cmd_logs(args)
                continue
            if cmd == "start" or cmd == "s":
                self._start_trading()
                continue
            if cmd == "stop" or cmd == "st":
                self._stop_trading()
                continue
            if cmd == "pause" or cmd == "p":
                # cooperative pause not implemented; placeholder
                self._status = "PAUSED"
                continue
            if cmd == "resume" or cmd == "r":
                self._status = "ACTIVE"
                continue

            handler = self._commands.get(cmd)
            if handler is not None:
                try:
                    handler.run(args)
                except Exception as e:
                    self.console.print(f"[red]Command error:[/red] {e}")
                continue

            self.console.print(f"Unknown command: {cmd}")

    def _print_help(self) -> None:
        self.console.print(
            "Commands: start, stop, pause, resume, status, monitor, trades, performance, portfolio, strategies, weights, risk, config, logs, help, exit, clear, version"
        )

    def _trading_target(self) -> None:
        try:
            # Run live hyperliquid loop in this background thread
            from cryptobot.cli.live_hyperliquid import run_live
            cfg_path = self.context.get("config_path") or "configs/live.hyperliquid.yaml"
            run_live(cfg_path)
        except Exception as e:
            self.console.print(f"[red]Trading loop crashed:[/red] {e}")
        finally:
            self._status = "STOPPED"

    def _start_trading(self) -> None:
        if self._running_thread and self._running_thread.is_alive():
            self.console.print("Already running")
            return
        self._stop_event.clear()
        self._running_thread = threading.Thread(target=self._trading_target, daemon=True)
        self._running_thread.start()
        self._status = "ACTIVE"
        self.console.print("Trading started")

    def _stop_trading(self) -> None:
        # Best-effort: current live loop listens to process signals; here we just flag and rely on user Ctrl+C
        if self._running_thread and self._running_thread.is_alive():
            self.console.print("Requesting stop (Ctrl+C in background loop if needed)...")
        self._status = "STOPPED"

    # Simple command handlers
    def _get_reporter(self) -> ReportGenerator:
        cfg = self.context.get("config")
        storage_path = cfg.monitor.storage_path if cfg and getattr(cfg, "monitor", None) else "~/.cryptobot/monitor.db"
        storage = StorageManager(storage_path)
        return ReportGenerator(storage)

    def _cmd_trades(self, args: List[str]) -> None:
        parser = argparse.ArgumentParser(prog="trades", add_help=False)
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--strategy", type=str, default=None)
        try:
            opts = parser.parse_args(args)
        except SystemExit:
            return
        rep = self._get_reporter()
        render_trades(rep.recent_trades(limit=int(opts.limit), strategy=opts.strategy))

    def _cmd_portfolio(self) -> None:
        rep = self._get_reporter()
        render_portfolio(rep.portfolio_summary())

    def _cmd_performance(self, args: List[str]) -> None:
        # Coarse performance summary from trades
        parser = argparse.ArgumentParser(prog="performance", add_help=False)
        parser.add_argument("--period", type=str, default="all")
        try:
            opts = parser.parse_args(args)
        except SystemExit:
            return
        rep = self._get_reporter()
        trades = rep.recent_trades(limit=200)
        total_pnl = sum(float(t.get("pnl", 0.0)) for t in trades)
        wins = [t for t in trades if float(t.get("pnl", 0.0)) > 0]
        losses = [t for t in trades if float(t.get("pnl", 0.0)) <= 0]
        win_rate = (len(wins) / max(1, len(trades))) * 100.0
        self.console.print(f"Total Trades: {len(trades)} | Win Rate: {win_rate:.1f}% | PnL: {total_pnl:,.2f}")

    def _cmd_strategies(self) -> None:
        cfg = self.context.get("config")
        weights = getattr(getattr(cfg, "strategy_weights", None), "initial_weights", {}) if cfg else {}
        if not weights:
            self.console.print("No strategy weights configured")
            return
        for name, w in weights.items():
            self.console.print(f"{name}: {float(w)*100:.1f}%")

    def _cmd_risk(self) -> None:
        cfg = self.context.get("config")
        if not cfg:
            self.console.print("No config loaded")
            return
        r = cfg.risk
        self.console.print(f"max_position_pct={r.max_position_pct}, max_daily_drawdown_pct={r.max_daily_drawdown_pct}")

    def _cmd_logs(self, args: List[str]) -> None:
        parser = argparse.ArgumentParser(prog="logs", add_help=False)
        parser.add_argument("--tail", type=int, default=50)
        try:
            opts = parser.parse_args(args)
        except SystemExit:
            return
        try:
            with open("logs/cryptobot.log", "r", encoding="utf-8") as f:
                lines = f.readlines()
            tail = lines[-int(opts.tail):]
            for ln in tail:
                self.console.print(ln.rstrip())
        except FileNotFoundError:
            self.console.print("No logs found at logs/cryptobot.log")


