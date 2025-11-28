from __future__ import annotations

import argparse
import shlex
import threading
import time
from typing import Any, Dict, List, Optional
import os
import sys
import subprocess
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
from cryptobot.monitor.display import render_trades, render_portfolio, render_positions, render_trades_with_status
from pathlib import Path
from typing import List


class InteractiveShell:
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.console = Console()
        self._status = "STOPPED"
        self._history = InMemoryHistory()
        self._session = PromptSession(history=self._history)
        self._commands: Dict[str, Command] = {}
        self._running_thread: Optional[threading.Thread] = None
        self._running_pid: Optional[int] = None
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
            "tank start", "tank stop", "tank restart", "pause", "resume", "status", "ps", "pids", "enforce", "killdups", "monitor",
            "trades", "positions", "flatten", "performance", "portfolio", "strategies", "weights",
            "risk", "config", "logs", "help", "exit", "quit", "clear", "version",
        ], ignore_case=True)

        while True:
            try:
                # Build prompt from GLOBAL bot status (not local session)
                try:
                    rs = self._get_reporter().runtime_status() or {}
                    last_hb = float(rs.get("last_heartbeat") or 0.0)
                    runtime_status = str(rs.get("status") or "STOPPED")
                    pid_for_status = rs.get("pid")
                    decision_interval = int(getattr(getattr(cfg, "llm", None), "decision_interval_sec", 30))
                    threshold = max(15, decision_interval * 3)
                    is_fresh = (time.time() - last_hb) < float(threshold)
                    status_for_prompt = "ACTIVE" if (runtime_status == "ACTIVE" and is_fresh) else "STOPPED"
                    # Heuristic: if heartbeat is stale but the pid is alive, treat as ACTIVE and refresh heartbeat
                    if status_for_prompt == "STOPPED" and pid_for_status:
                        try:
                            if self._pid_alive(int(pid_for_status)):
                                try:
                                    self._get_storage().record_runtime_heartbeat(pid=int(pid_for_status))
                                except Exception:
                                    pass
                                status_for_prompt = "ACTIVE"
                        except Exception:
                            pass
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
                # Exit shell without stopping the bot
                self.console.print("Closing shell (bot continues running).")
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
            if cmd in {"ps", "pids"}:
                self._cmd_ps()
                continue
            if cmd in {"enforce", "killdups"}:
                self._cmd_enforce_single()
                continue
            if cmd == "trades" or cmd == "t":
                self._cmd_trades(args)
                continue
            if cmd == "positions" or cmd == "pos":
                self._cmd_positions()
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
            if cmd == "weights" or cmd == "w":
                self._cmd_weights()
                continue
            if cmd == "risk":
                self._cmd_risk()
                continue
            if cmd == "logs" or cmd == "l":
                self._cmd_logs(args)
                continue
            if cmd == "tank" and args and args[0] == "start":
                self._start_trading()
                continue
            if cmd == "tank" and args and args[0] == "stop":
                self._stop_trading(args[1:])
                continue
            if cmd == "tank" and args and args[0] == "restart":
                self._restart_trading(args[1:])
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
            "Commands: tank start, tank stop [--force], tank restart [--force], pause, resume, status, ps/pids, enforce, monitor, trades, positions, flatten, performance, portfolio, strategies, weights, risk, config, logs, help, exit, clear, version"
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
        # Heuristic: if heartbeat is stale but the pid is alive, consider ACTIVE and refresh heartbeat immediately
        if status_for_prompt == "STOPPED" and pid:
            try:
                if self._pid_alive(int(pid)):
                    try:
                        self._get_storage().record_runtime_heartbeat(pid=int(pid))
                        # Recompute freshness after bump
                        rs2 = rep.runtime_status() or {}
                        last_hb2 = float(rs2.get("last_heartbeat") or 0.0)
                        is_fresh2 = (time.time() - last_hb2) < float(threshold)
                        if is_fresh2:
                            status_for_prompt = "ACTIVE"
                    except Exception:
                        pass
            except Exception:
                pass
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
        # Show detected processes
        try:
            pids = self._list_bot_pids()
            if pids:
                self.console.print(f"Processes detected: {len(pids)} -> {', '.join(str(p) for p in pids)}")
            else:
                self.console.print("Processes detected: 0")
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

        # Spawn detached background process so it survives shell exit
        try:
            cfg_path = self.context.get("config_path") or "configs/live.hyperliquid.yaml"
            env = os.environ.copy()
            env["CRYPTOBOT_DISABLE_CONSOLE_LOG"] = "1"
            # Enable in-process supervisor in the runner so it auto-restarts if it exits unexpectedly
            env["CRYPTOBOT_AUTO_RESTART"] = "1"
            # Force the runner to use the same monitor DB as the CLI to avoid status desync
            try:
                env["CRYPTOBOT_MONITOR_DB"] = self._get_storage().db_path
            except Exception:
                pass
            # Ensure monitor DB is the same between shells and runner if set
            # (uses existing CRYPTOBOT_MONITOR_DB env if provided)
            os.makedirs("logs", exist_ok=True)
            out_path = os.path.join("logs", "runner.out")
            cmd = [sys.executable, "-m", "cryptobot.cli.live_hyperliquid", "--config", str(cfg_path)]
            with open(out_path, "ab") as out:
                proc = subprocess.Popen(
                    cmd,
                    stdout=out,
                    stderr=out,
                    env=env,
                    start_new_session=True,
                )
            self._running_pid = int(proc.pid)
            # Persist run metadata to interoperate with deploy scripts and allow external restart
            try:
                Path(".").joinpath(".run_pid").write_text(str(self._running_pid))
                Path(".").joinpath(".run_cmd").write_text(" ".join(shlex.quote(c) for c in cmd))
                Path(".").joinpath(".run_session").write_text("cryptobot")
            except Exception:
                pass
            self.console.print(f"Trading started (pid={self._running_pid})")
            # Wait briefly for the runtime to flip ACTIVE (best-effort)
            try:
                cfg = self.context.get("config")
                decision_interval = int(getattr(getattr(cfg, "llm", None), "decision_interval_sec", 30)) if cfg else 30
                threshold = max(15, decision_interval * 3)
                deadline = time.time() + 8.0
                while time.time() < deadline:
                    rs = self._get_reporter().runtime_status() or {}
                    last_hb = float(rs.get("last_heartbeat") or 0.0)
                    status = str(rs.get("status") or "STOPPED")
                    fresh = (time.time() - last_hb) < float(threshold)
                    if status == "ACTIVE" and fresh:
                        break
                    time.sleep(0.2)
            except Exception:
                pass
        except Exception as e:
            self.console.print(f"[red]Failed to start bot:[/red] {e}")

    def _stop_trading(self, args: Optional[List[str]] = None) -> None:
        # Signal the background loop to stop cooperatively via monitor DB first
        service_name = os.getenv("CRYPTOBOT_SERVICE_NAME", "").strip()
        # If a systemd service name is provided, prefer stopping the service
        if service_name:
            try:
                res = subprocess.run(["systemctl", "stop", service_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out = res.stdout.decode(errors="ignore").strip()
                err = res.stderr.decode(errors="ignore").strip()
                if out:
                    self.console.print(out)
                if err:
                    self.console.print(f"[red]{err}[/red]")
                if res.returncode == 0:
                    self.console.print(f"Requested systemd stop for service '{service_name}'.")
                    self._status = "STOPPED"
                    return
            except Exception:
                # Fallback to local stop flow below
                pass
        force = bool(args and any(a in {"--force", "-f"} for a in args))
        sent_signal = False
        # 1) Request cooperative stop via monitor DB (runner polls this and exits gracefully)
        try:
            storage = self._get_storage()
            storage.request_runtime_stop()
            self.console.print("Requested remote cooperative stop.")
        except Exception:
            pass
        # Always request local in-process thread stop if any
        if self._running_thread and self._running_thread.is_alive():
            self._stop_event.set()
        # 2) Wait briefly for the bot to acknowledge stop (based on runtime_status + heartbeat freshness)
        try:
            cfg = self.context.get("config")
            decision_interval = int(getattr(getattr(cfg, "llm", None), "decision_interval_sec", 30)) if cfg else 30
            freshness_threshold = max(15, decision_interval * 3)
            deadline = time.time() + 6.0
            while time.time() < deadline:
                rs = self._get_reporter().runtime_status() or {}
                last_hb = float(rs.get("last_heartbeat") or 0.0)
                runtime_status = str(rs.get("status") or "STOPPED")
                fresh = (time.time() - last_hb) < float(freshness_threshold)
                if runtime_status != "ACTIVE" or not fresh:
                    break
                time.sleep(0.2)
        except Exception:
            pass
        # Re-check; if still active, escalate
        needs_escalation = False
        try:
            rs = self._get_reporter().runtime_status() or {}
            last_hb = float(rs.get("last_heartbeat") or 0.0)
            runtime_status = str(rs.get("status") or "STOPPED")
            cfg = self.context.get("config")
            decision_interval = int(getattr(getattr(cfg, "llm", None), "decision_interval_sec", 30)) if cfg else 30
            freshness_threshold = max(15, decision_interval * 3)
            fresh = (time.time() - last_hb) < float(freshness_threshold)
            needs_escalation = (runtime_status == "ACTIVE" and fresh)
        except Exception:
            needs_escalation = True
        if needs_escalation or force:
            # 3) Try to gracefully terminate the known DB pid first
            try:
                rs = self._get_reporter().runtime_status() or {}
                db_pid = int(rs.get("pid")) if rs.get("pid") is not None else None
            except Exception:
                db_pid = None
            target_pids = []
            if db_pid:
                target_pids.append(db_pid)
            # Also consider any other matching bot processes (avoid dups)
            try:
                for p in self._list_bot_pids():
                    if not db_pid or p != db_pid:
                        target_pids.append(p)
            except Exception:
                pass
            target_pids = list({p for p in target_pids if p and p > 0})
            if target_pids:
                for p in target_pids:
                    try:
                        os.kill(p, signal.SIGTERM)
                        sent_signal = True
                        self.console.print(f"Sent SIGTERM to pid {p}")
                    except ProcessLookupError:
                        pass
                    except Exception as e:
                        self.console.print(f"[yellow]SIGTERM failed for pid {p}:[/yellow] {e}")
                # Wait up to 8s for processes to exit, then escalate to SIGKILL
                waited = 0.0
                try:
                    while waited < 8.0:
                        alive = []
                        for p in list(target_pids):
                            try:
                                os.kill(p, 0)
                                alive.append(p)
                            except ProcessLookupError:
                                continue
                            except Exception:
                                alive.append(p)
                        if not alive:
                            break
                        time.sleep(0.5)
                        waited += 0.5
                    # SIGKILL any stubborn survivors
                    for p in list(target_pids):
                        try:
                            os.kill(p, 0)
                            os.kill(p, signal.SIGKILL)
                            self.console.print(f"Sent SIGKILL to pid {p}")
                        except ProcessLookupError:
                            pass
                        except Exception:
                            pass
                except Exception:
                    pass
        # 4) Best-effort cleanup: mark STOPPED in runtime DB and clear stop flag
        try:
            storage = self._get_storage()
            storage.set_runtime_stopped()
            storage.clear_runtime_stop_request()
        except Exception:
            pass
        # Remove local run metadata (if created by this shell)
        try:
            run_pid_path = Path(".").joinpath(".run_pid")
            if run_pid_path.exists():
                run_pid_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:
            pass
        self._status = "STOPPED"

    def _restart_trading(self, args: Optional[List[str]] = None) -> None:
        # Graceful stop first
        service_name = os.getenv("CRYPTOBOT_SERVICE_NAME", "").strip()
        if service_name:
            # If systemd service configured, prefer systemd restart
            try:
                res = subprocess.run(["systemctl", "restart", service_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out = res.stdout.decode(errors="ignore").strip()
                err = res.stderr.decode(errors="ignore").strip()
                if out:
                    self.console.print(out)
                if err:
                    self.console.print(f"[red]{err}[/red]")
                if res.returncode == 0:
                    self.console.print(f"Requested systemd restart for service '{service_name}'.")
                    # Post-start verification still applies below
                else:
                    self.console.print("[yellow]systemd restart failed; falling back to local restart.[/yellow]")
            except Exception:
                self.console.print("[yellow]systemd not available; falling back to local restart.[/yellow]")
        else:
            self.console.print("Restarting bot: stopping...")
            try:
                self._stop_trading(args)
            except Exception:
                pass
        # Short, non-blocking wait for stop (max ~5s), then force if needed
        cfg = self.context.get("config")
        decision_interval = int(getattr(getattr(cfg, "llm", None), "decision_interval_sec", 30)) if cfg else 30
        threshold = max(15, decision_interval * 3)
        force_requested = bool(args and any(a in {"--force", "-f"} for a in args))
        deadline = time.time() + 5.0
        try:
            while time.time() < deadline:
                if self._running_thread and self._running_thread.is_alive():
                    self._running_thread.join(timeout=0.1)
                rs = self._get_reporter().runtime_status() or {}
                last_hb = float(rs.get("last_heartbeat") or 0.0)
                runtime_status = str(rs.get("status") or "STOPPED")
                fresh = (time.time() - last_hb) < float(threshold)
                if runtime_status != "ACTIVE" or not fresh:
                    break
                time.sleep(0.2)
            else:
                # Still active after short grace
                if not force_requested:
                    try:
                        rs = self._get_reporter().runtime_status() or {}
                        pid = int(rs.get("pid")) if rs.get("pid") is not None else None
                        if pid:
                            os.kill(pid, signal.SIGTERM)
                            self.console.print(f"Sent SIGTERM to pid {pid} (auto-force)")
                            # Clear status so new start isn't blocked by fresh heartbeat
                            try:
                                self._get_storage().set_runtime_stopped()
                            except Exception:
                                pass
                            # Wait up to 10s for process to exit, then escalate to SIGKILL if needed
                            waited = 0.0
                            while waited < 10.0:
                                try:
                                    os.kill(pid, 0)
                                    time.sleep(0.5)
                                    waited += 0.5
                                except ProcessLookupError:
                                    break
                                except Exception:
                                    time.sleep(0.5)
                                    waited += 0.5
                            try:
                                os.kill(pid, 0)
                                os.kill(pid, signal.SIGKILL)
                                self.console.print(f"Sent SIGKILL to pid {pid}")
                            except ProcessLookupError:
                                pass
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass
        # If the bot was launched via deploy scripts, prefer delegating to them for a clean restart
        used_external = False
        if not service_name:
            try:
                repo_root = Path(__file__).resolve().parents[2]
                script = repo_root / "deploy" / "restart_if_running.sh"
                if script.exists() and os.access(str(script), os.X_OK):
                    res = subprocess.run(["bash", str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out = res.stdout.decode(errors="ignore").strip()
                    err = res.stderr.decode(errors="ignore").strip()
                    if out:
                        self.console.print(out)
                    if err:
                        self.console.print(f"[red]{err}[/red]")
                    used_external = (res.returncode == 0)
            except Exception:
                used_external = False
        if not service_name and not used_external:
            self.console.print("Restarting bot: starting...")
            self._start_trading()
        # Post-start verification: ensure it became ACTIVE shortly after
        try:
            verify_deadline = time.time() + 8.0
            while time.time() < verify_deadline:
                rs = self._get_reporter().runtime_status() or {}
                last_hb = float(rs.get("last_heartbeat") or 0.0)
                runtime_status = str(rs.get("status") or "STOPPED")
                fresh = (time.time() - last_hb) < float(threshold)
                if runtime_status == "ACTIVE" and fresh:
                    break
                time.sleep(0.25)
            else:
                self.console.print("[yellow]Warning:[/yellow] Bot did not report ACTIVE shortly after restart. Check logs/runner.out and logs/cryptobot.log.")
        except Exception:
            pass

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
        # Enrich with latest positions to infer OPEN/CLOSED and show better status
        trades = rep.recent_trades(limit=int(opts.limit), strategy=opts.strategy)
        summary = rep.portfolio_summary()
        render_trades_with_status(trades, summary)

    def _cmd_portfolio(self) -> None:
        rep = self._get_reporter()
        summary = rep.portfolio_summary()
        render_portfolio(summary)
        # Also show open positions
        render_positions(summary)

    def _cmd_positions(self) -> None:
        rep = self._get_reporter()
        render_positions(rep.portfolio_summary())

    def _cmd_flatten(self) -> None:
        # Request the running bot to close all open positions (non-blocking)
        try:
            storage = StorageManager(self.context.get("storage_path", "~/.cryptobot/monitor.db"))
            storage.request_flatten_positions()
            self.console.print("[green]Requested flatten of all positions. Runner will act shortly.[/green]")
        except Exception as e:
            self.console.print(f"[red]Flatten error:[/red] {e}")

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

    def _cmd_weights(self) -> None:
        # Show latest runtime weights from storage if present; else show configured initial weights
        try:
            storage = self._get_storage()
            latest = storage.latest_weights()
            if latest:
                self.console.print("Runtime Weights:")
                for k, v in latest.items():
                    self.console.print(f"- {k}: {float(v):.2f}")
                return
        except Exception:
            pass
        # Fallback to configured
        self._cmd_strategies()
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

    def _list_bot_pids(self) -> List[int]:
        pids: List[int] = []
        try:
            # Try to detect via pgrep first
            pattern = r"cryptobot-live-hl|cryptobot-live|cryptobot\.cli\.live_hyperliquid|cryptobot\.cli\.live"
            res = subprocess.run(["pgrep", "-f", pattern], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                for line in res.stdout.decode().strip().splitlines():
                    try:
                        pids.append(int(line.strip()))
                    except Exception:
                        pass
        except Exception:
            pass
        # Add known pid files if present
        try:
            run_pid_path = Path(".").joinpath(".run_pid")
            if run_pid_path.exists():
                pid_txt = run_pid_path.read_text().strip()
                if pid_txt.isdigit():
                    pids.append(int(pid_txt))
        except Exception:
            pass
        # De-duplicate
        return sorted(list({p for p in pids if p > 0}))

    def _pid_alive(self, pid: int) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return False

    def _cmd_ps(self) -> None:
        # Show runtime + process list to spot duplicates
        try:
            rep = self._get_reporter()
            rs = rep.runtime_status() or {}
            pid = rs.get("pid")
            status = rs.get("status")
            last_hb = rs.get("last_heartbeat")
            self.console.print(f"Runtime DB: status={status} pid={pid} last_hb={last_hb}")
        except Exception:
            pass
        try:
            pids = self._list_bot_pids()
            if not pids:
                self.console.print("No matching bot processes found.")
                return
            self.console.print(f"Found {len(pids)} process(es): {', '.join(str(p) for p in pids)}")
            # If a DB pid exists, highlight if it mismatches
            try:
                rs = self._get_reporter().runtime_status() or {}
                db_pid = int(rs.get("pid")) if rs.get("pid") is not None else None
            except Exception:
                db_pid = None
            for p in pids:
                mark = " (DB pid)" if (db_pid and p == db_pid) else ""
                self.console.print(f"- pid {p}{mark}")
            if len(pids) > 1:
                self.console.print("[yellow]Warning:[/yellow] Multiple bot processes detected. Consider `restart --force`.")
        except Exception as e:
            self.console.print(f"[red]ps failed:[/red] {e}")

    def _cmd_enforce_single(self) -> None:
        # Kill all duplicate processes, keep the DB pid if available
        try:
            pids = self._list_bot_pids()
            if not pids:
                self.console.print("No bot process detected.")
                return
            try:
                rs = self._get_reporter().runtime_status() or {}
                keep_pid = int(rs.get("pid")) if rs.get("pid") is not None else None
            except Exception:
                keep_pid = None
            killed = []
            for p in pids:
                if keep_pid and p == keep_pid:
                    continue
                try:
                    os.kill(p, signal.SIGTERM)
                    time.sleep(0.5)
                    try:
                        os.kill(p, 0)
                        os.kill(p, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    killed.append(p)
                except Exception:
                    pass
            if keep_pid:
                self.console.print(f"Kept pid {keep_pid}. Killed: {', '.join(str(x) for x in killed) if killed else 'none'}.")
            else:
                self.console.print(f"Killed: {', '.join(str(x) for x in killed) if killed else 'none'}.")
        except Exception as e:
            self.console.print(f"[red]enforce failed:[/red] {e}")


