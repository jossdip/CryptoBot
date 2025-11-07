from __future__ import annotations

import argparse
import shlex
import threading
import time
from typing import Any, Dict, List, Optional
import os
import signal

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console

from cryptobot.cli.prompt import build_prompt
from cryptobot.cli.logo import (
    start_animated_logo,
    refresh_animated_logo,
    stop_animated_logo,
    pause_animated_logo,
    resume_animated_logo,
)
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
            "start", "stop", "restart", "pause", "resume", "status", "monitor",
            "trades", "performance", "portfolio", "strategies", "weights",
            "risk", "config", "logs", "help", "exit", "quit", "clear", "version",
        ], ignore_case=True)

        while True:
            try:
                # Build prompt from GLOBAL bot status (not local session)
                try:
                    rs = self._get_reporter().runtime_status() or {}
                    last_hb = float(rs.get("last_heartbeat") or 0.0)
                    runtime_status = str(rs.get("status") or "STOPPED")
                    decision_interval = int(getattr(getattr(cfg, "llm", None), "decision_interval_sec", 30))
                    threshold = max(15, decision_interval * 3)
                    is_fresh = (time.time() - last_hb) < float(threshold)
                    status_for_prompt = "ACTIVE" if (runtime_status == "ACTIVE" and is_fresh) else "STOPPED"
                except Exception:
                    status_for_prompt = "STOPPED"
                prompt = build_prompt(exchange=exchange, status=status_for_prompt, fmt=getattr(getattr(cfg, "cli", None), "prompt_format", "[C4$H@{exchange}:{status}] > "))
                # Mettre l'animation en pause pendant la saisie pour éviter tout flicker
                pause_animated_logo()
                try:
                    line = self._session.prompt(ANSI(prompt), completer=completer)
                finally:
                    resume_animated_logo()
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
                self._cmd_status()
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
                self._stop_trading(args)
                continue
            if cmd == "restart" or cmd == "re":
                self._restart_trading(args)
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
                # Pause animation pendant les sous-menus interactifs
                pause_animated_logo()
                try:
                    try:
                        handler.run(args)
                    except KeyboardInterrupt:
                        self.console.print("[yellow]Commande annulée.[/yellow]")
                    except EOFError:
                        self.console.print("[yellow]Retour.[/yellow]")
                finally:
                    resume_animated_logo()
                # Gestion des erreurs classiques
                # (les KeyboardInterrupt/EOFError sont gérées ci-dessus)
                continue

            self.console.print(f"Unknown command: {cmd}")

    def _print_help(self) -> None:
        self.console.print(
            "Commands: start, stop [--force], restart [--force], pause, resume, status, monitor, trades, performance, portfolio, strategies, weights, risk, config, logs, help, exit, clear, version"
        )

    def _trading_target(self) -> None:
        try:
            # Run live hyperliquid loop in this background thread
            from cryptobot.cli.live_hyperliquid import run_live
            cfg_path = self.context.get("config_path") or "configs/live.hyperliquid.yaml"
            run_live(cfg_path, stop_event=self._stop_event)
        except Exception as e:
            self.console.print(f"[red]Trading loop crashed:[/red] {e}")
        finally:
            self._status = "STOPPED"

    def _get_storage(self) -> StorageManager:
        cfg = self.context.get("config")
        storage_path = cfg.monitor.storage_path if cfg and getattr(cfg, "monitor", None) else "~/.cryptobot/monitor.db"
        return StorageManager(storage_path)

    def _get_reporter(self) -> ReportGenerator:
        return ReportGenerator(self._get_storage())

    def _cmd_status(self) -> None:
        rep = self._get_reporter()
        rs = rep.runtime_status() or {}
        pid = rs.get("pid")
        last_hb = float(rs.get("last_heartbeat") or 0.0)
        started_at = rs.get("started_at")
        runtime_status = str(rs.get("status") or "STOPPED")
        cfg = self.context.get("config")
        decision_interval = int(getattr(getattr(cfg, "llm", None), "decision_interval_sec", 30))
        threshold = max(15, decision_interval * 3)
        is_fresh = (time.time() - last_hb) < float(threshold)
        status_for_prompt = "ACTIVE" if (runtime_status == "ACTIVE" and is_fresh) else "STOPPED"
        self.console.print(
            f"Global Bot: {status_for_prompt}"
            + (f" | pid={pid}" if pid else "")
            + (f" | last_hb={time.strftime('%H:%M:%S', time.localtime(float(last_hb))) }" if last_hb else "")
            + (f" | since={time.strftime('%H:%M:%S', time.localtime(float(started_at))) }" if started_at else "")
        )
        # Network/wallet
        testnet = rs.get("testnet")
        wallet = rs.get("wallet_address")
        if wallet is not None or testnet is not None:
            net = "testnet" if testnet else "mainnet"
            self.console.print(f"Network: {net} | Wallet: {wallet}")
        # LLM config summary
        try:
            llm = getattr(cfg, "llm")
            self.console.print(
                f"LLM: {'enabled' if bool(getattr(llm, 'enabled', True)) else 'disabled'} | model={getattr(llm, 'model', '')} | base_url={getattr(llm, 'base_url', '')}"
            )
        except Exception:
            pass
        # Latest portfolio snapshot
        latest = rep.portfolio_summary() or {}
        if latest:
            try:
                bal = float(latest.get("balance", 0.0))
                eq = float(latest.get("equity", 0.0))
                upnl = float(latest.get("unrealized_pnl", 0.0))
                self.console.print(f"Portfolio: balance={bal:.2f} | equity={eq:.2f} | uPnL={upnl:.2f}")
            except Exception:
                pass
        # Show which monitor DB path is used (to debug multi-install issues)
        try:
            storage = self._get_storage()
            self.console.print(f"Monitor DB: {storage.db_path}")
        except Exception:
            pass

    def _start_trading(self) -> None:
        # Prevent starting if a global active instance exists with a fresh heartbeat
        try:
            rs = self._get_reporter().runtime_status() or {}
            last_hb = float(rs.get("last_heartbeat") or 0.0)
            status = str(rs.get("status") or "STOPPED")
            if status == "ACTIVE" and (time.time() - last_hb) < 30.0:
                self.console.print("Already running globally. Not starting a new instance.")
                return
        except Exception:
            pass

        if self._running_thread and self._running_thread.is_alive():
            self.console.print("Already running in this session")
            return
        self._stop_event.clear()
        # Suppress console logging in background trading thread; logs still go to file
        os.environ["CRYPTOBOT_DISABLE_CONSOLE_LOG"] = "1"
        self._running_thread = threading.Thread(target=self._trading_target, daemon=True)
        self._running_thread.start()
        self.console.print("Trading started")

    def _stop_trading(self, args: Optional[List[str]] = None) -> None:
        # Signal the background loop to stop cooperatively (local + remote)
        try:
            storage = self._get_storage()
            storage.request_runtime_stop()
        except Exception:
            pass
        if self._running_thread and self._running_thread.is_alive():
            self._stop_event.set()
            self.console.print("Requesting local stop...")
        # Optional --force to kill remote pid
        force = bool(args and any(a in {"--force", "-f"} for a in args))
        if force:
            try:
                rs = self._get_reporter().runtime_status() or {}
                pid = int(rs.get("pid")) if rs.get("pid") is not None else None
                if pid:
                    os.kill(pid, signal.SIGTERM)
                    self.console.print(f"Sent SIGTERM to pid {pid}")
            except Exception as e:
                self.console.print(f"[red]Force stop failed:[/red] {e}")
        self._status = "STOPPED"

    def _restart_trading(self, args: Optional[List[str]] = None) -> None:
        # Graceful stop first
        self.console.print("Restarting bot: stopping...")
        try:
            self._stop_trading(args)
        except Exception:
            pass
        # Wait until global instance is stopped (heartbeat stale or status STOPPED)
        cfg = self.context.get("config")
        decision_interval = int(getattr(getattr(cfg, "llm", None), "decision_interval_sec", 30)) if cfg else 30
        threshold = max(15, decision_interval * 3)
        deadline = time.time() + float(threshold)
        try:
            while time.time() < deadline:
                # Join local thread if any
                if self._running_thread and self._running_thread.is_alive():
                    self._running_thread.join(timeout=0.2)
                rs = self._get_reporter().runtime_status() or {}
                last_hb = float(rs.get("last_heartbeat") or 0.0)
                runtime_status = str(rs.get("status") or "STOPPED")
                fresh = (time.time() - last_hb) < float(threshold)
                if runtime_status != "ACTIVE" or not fresh:
                    break
                time.sleep(0.3)
        except Exception:
            pass
        self.console.print("Restarting bot: starting...")
        self._start_trading()

    # Simple command handlers
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


