from __future__ import annotations

import time
import argparse
from typing import Dict, Any, Optional
import os
import threading
from pathlib import Path
import fcntl

from cryptobot.core.config import AppConfig
from cryptobot.core.logging import get_logger, setup_logging
from cryptobot.core.mode_manager import ModeManager
from cryptobot.core.env import load_local_environment
from cryptobot.broker.hyperliquid_broker import HyperliquidBroker
from cryptobot.llm.client import LLMClient
from cryptobot.llm.orchestrator import LLMOrchestrator
from cryptobot.strategy.weight_manager import WeightManager
from cryptobot.strategy.arbitrage import ArbitrageStrategy
from cryptobot.strategy.sniping import SnipingStrategy
from cryptobot.strategy.market_making import MarketMakingStrategy
from cryptobot.strategy.momentum import MomentumStrategy
from cryptobot.strategy.scalping import ScalpingStrategy
from cryptobot.strategy.breakout import BreakoutStrategy
from cryptobot.broker.executor import MultiStrategyExecutor
from cryptobot.monitor.performance import PerformanceTracker
from cryptobot.monitor.engine import MonitorEngine
from cryptobot.data.context_aggregator import MarketContextAggregator
from cryptobot.monitor.storage import StorageManager


def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


def _acquire_single_instance_lock() -> Optional[object]:
    """
    Prevent multiple bot instances system-wide using an exclusive lock file.
    Returns an open file handle if the lock is acquired, else None.
    The caller must keep the handle alive for the lifetime of the process.
    """
    try:
        lock_path = _expand(os.getenv("CRYPTOBOT_LOCK_PATH", "~/.cryptobot/cryptobot.lock"))
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        f = open(lock_path, "a+")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            # Lock held by another process; attempt to read incumbent pid for diagnostics
            try:
                f.seek(0)
                txt = f.read().strip()
                incumbent_pid = int(txt) if txt and txt.isdigit() else None
                if incumbent_pid:
                    try:
                        # Check if incumbent pid is alive
                        os.kill(incumbent_pid, 0)
                        # Alive -> respect existing instance
                        f.close()
                        return None
                    except OSError:
                        # Stale pid; try to acquire again
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    # Unknown holder; refuse
                    f.close()
                    return None
            except Exception:
                f.close()
                return None
        # We own the lock: write our pid
        try:
            f.seek(0)
            f.truncate()
            f.write(str(os.getpid()))
            f.flush()
            os.fsync(f.fileno())
        except Exception:
            pass
        return f
    except Exception:
        return None


def run_live(config_path: str, stop_event: Optional[threading.Event] = None) -> bool:
    load_local_environment()
    cfg = AppConfig.load(config_path)
    setup_logging(level="INFO")
    log = get_logger()
    # Disable Polymarket and Twitter sentiment sources for now (keep Reddit optional)
    try:
        if getattr(cfg, "sentiment", None):
            if getattr(cfg.sentiment, "twitter", None):
                cfg.sentiment.twitter.enabled = False
            if getattr(cfg.sentiment, "polymarket", None):
                cfg.sentiment.polymarket.enabled = False
    except Exception:
        pass
    # Gate remote stop behavior behind an env flag to prevent unintended halts
    allow_remote_stop = str(os.getenv("CRYPTOBOT_ALLOW_REMOTE_STOP", "0")).lower() in {"1", "true", "yes"}

    log.info("Starting Hyperliquid live runner...")
    # Global single-instance lock (system-wide)
    lock_handle = _acquire_single_instance_lock()
    if lock_handle is None:
        log.warning("Another CryptoBot instance is already running (global lock held). Refusing to start.")
        # Return True so the supervisor loop does NOT retry
        return True
    try:
        log.info(f"Config: {config_path}")
        env_path = os.getenv("CRYPTOBOT_ENV_PATH")
        if env_path:
            log.info(f"Env: {env_path}")
    except Exception:
        pass
    mode_manager = ModeManager(cfg)

    # Global runtime storage (singleton status)
    storage_path = cfg.monitor.storage_path if getattr(cfg, "monitor", None) else "~/.cryptobot/monitor.db"
    storage = StorageManager(storage_path)

    # Enforce single active instance (recent heartbeat)
    try:
        rs = storage.get_runtime_status() or {}
        last_hb = float(rs.get("last_heartbeat") or 0.0)
        status = str(rs.get("status") or "STOPPED")
        threshold = max(15, int(getattr(cfg.llm, "decision_interval_sec", 30)) * 3)
        if status == "ACTIVE" and (time.time() - last_hb) < float(threshold):
            log.warning("Another CryptoBot instance appears ACTIVE (recent heartbeat). Refusing to start.")
            # Return True so supervisor loop exits and does not retry
            return True
    except Exception:
        pass

    # Startup safety checks: require LLM and exchange keys
    if bool(getattr(cfg.llm, "enabled", True)):
        if not os.getenv("LLM_API_KEY", "").strip():
            project_root = Path(__file__).resolve().parents[2]
            canonical_env = project_root / ".env"
            raise RuntimeError(
                f"LLM_API_KEY is missing. Create {canonical_env} with LLM_API_KEY and restart."
            )
        else:
            try:
                log.info(
                    f"LLM enabled | base_url={os.getenv('LLM_BASE_URL','')} | model={os.getenv('LLM_MODEL','')} | decision_interval={int(getattr(cfg.llm,'decision_interval_sec',30))}s"
                )
                mb = float(getattr(cfg.llm, 'monthly_budget_usd', 0.0))
                if mb > 0:
                    log.info(f"LLM budget: monthly_budget_usd={mb}")
            except Exception:
                pass
    if not mode_manager.wallet_address or not mode_manager.private_key:
        raise RuntimeError(
            "Hyperliquid keys missing. Set HYPERLIQUID_WALLET_ADDRESS and "
            + ("HYPERLIQUID_TESTNET_PRIVATE_KEY" if mode_manager.is_testnet() else "HYPERLIQUID_LIVE_PRIVATE_KEY")
            + ". See docs/ENV_HYPERLIQUID_EXAMPLE.txt."
        )
    broker = HyperliquidBroker(
        wallet_address=mode_manager.wallet_address,
        private_key=mode_manager.private_key,
        testnet=mode_manager.is_testnet(),
    )
    try:
        log.info(
            f"Connected to Hyperliquid | network={'testnet' if mode_manager.is_testnet() else 'mainnet'} | wallet={getattr(broker, 'query_address', mode_manager.wallet_address)}"
        )
        # First portfolio snapshot
        pf = broker.get_portfolio()
        if pf.get("ok"):
            resp = pf.get("response", {})
            raw = pf.get("raw")
            if raw is not None:
                log.debug(f"Raw portfolio payload: {raw}")
            bal = None
            eq = None
            upnl = None
            try:
                # Best-effort numeric extract
                bal = float(resp.get("balance", 0.0))
                eq = float(resp.get("equity", bal))
                upnl = float(resp.get("unrealized_pnl", 0.0))
            except Exception:
                pass
            log.info(f"Portfolio: balance={bal if bal is not None else '?'} | equity={eq if eq is not None else '?'} | uPnL={upnl if upnl is not None else '?'}")
        else:
            log.warning(f"Portfolio snapshot unavailable: {pf.get('error')}")
    except Exception:
        pass

    # Record runtime start and clear any old stop requests
    try:
        pid = os.getpid()
        actual_address = getattr(broker, "query_address", mode_manager.wallet_address)
        storage.set_runtime_started(pid=pid, config_path=str(config_path), testnet=bool(mode_manager.is_testnet()), wallet_address=str(actual_address))
        storage.clear_runtime_stop_request()
    except Exception:
        pass

    # Heartbeat watchdog: keep runtime heartbeat fresh regardless of main loop pace
    heartbeat_stop = threading.Event()
    def _heartbeat_maintainer() -> None:
        while not heartbeat_stop.is_set():
            try:
                storage.record_runtime_heartbeat(pid=pid)
            except Exception:
                pass
            try:
                time.sleep(2.0)
            except Exception:
                # If sleep interrupted, loop will re-check stop flag
                pass
    hb_thread = threading.Thread(target=_heartbeat_maintainer, daemon=True)
    try:
        hb_thread.start()
    except Exception:
        # If watchdog cannot start, continue without it (main loop still records heartbeats)
        pass

    llm_client = LLMClient.from_env()
    orchestrator = LLMOrchestrator(llm_client)
    weight_manager = WeightManager()

    # Seed initial weights from configuration if provided
    try:
        init_w = getattr(getattr(cfg, "strategy_weights", None), "initial_weights", None)
        if isinstance(init_w, dict) and init_w:
            from cryptobot.llm.orchestrator import StrategyWeight
            sw = StrategyWeight(
                market_making=float(init_w.get("market_making", 0.35)),
                momentum=float(init_w.get("momentum", 0.25)),
                scalping=float(init_w.get("scalping", 0.15)),
                arbitrage=float(init_w.get("arbitrage", 0.12)),
                breakout=float(init_w.get("breakout", 0.08)),
                sniping=float(init_w.get("sniping", 0.05)),
            )
            sw.normalize()
            orchestrator.weights = sw
    except Exception:
        pass

    # Strategy instances (trading strategies only)
    strategies = {
        "market_making": MarketMakingStrategy(broker),
        "momentum": MomentumStrategy(broker),
        "scalping": ScalpingStrategy(broker),
        "arbitrage": ArbitrageStrategy(broker),
        "breakout": BreakoutStrategy(broker),
        "sniping": SnipingStrategy(broker, llm_client),
    }

    executor = MultiStrategyExecutor(broker, orchestrator)
    performance_tracker = PerformanceTracker()
    context_aggregator = MarketContextAggregator(broker, llm_client=llm_client, config=cfg)

    symbols = cfg.general.symbols

    # Monitoring engine (optional)
    monitor_engine: MonitorEngine | None = None
    try:
        monitor_engine = MonitorEngine(
            broker=broker,
            orchestrator=orchestrator,
            performance_tracker=performance_tracker,
            storage_path=getattr(cfg.monitor, "storage_path", "~/.cryptobot/monitor.db"),
            interval_sec=int(getattr(cfg.monitor, "collect_interval_sec", 5)),
        )
        log.info(f"Monitor engine started | storage={getattr(cfg.monitor, 'storage_path', '~/.cryptobot/monitor.db')} | interval={int(getattr(cfg.monitor, 'collect_interval_sec', 5))}s")
        # Wire LLM decisions into storage
        orchestrator.set_decision_sink(
            lambda d: monitor_engine.record_llm_decision(
                timestamp=float(d.get("timestamp", 0.0)),
                decision_type=str(d.get("decision_type", "")),
                prompt=str(d.get("prompt", "")),
                response=str(d.get("response", "")),
                reasoning=str(d.get("reasoning", "")),
                sentiment=str(d.get("sentiment", "neutral")),
                confidence=d.get("confidence"),
                metadata=d.get("metadata"),
            )
            if monitor_engine
            else None
        )
        # Load latest persisted weights to warm start
        try:
            latest = monitor_engine.storage.latest_weights()
            if latest:
                from cryptobot.llm.orchestrator import StrategyWeight
                sw = StrategyWeight(
                    market_making=float(latest.get("market_making", orchestrator.weights.market_making)),
                    momentum=float(latest.get("momentum", orchestrator.weights.momentum)),
                    scalping=float(latest.get("scalping", orchestrator.weights.scalping)),
                    arbitrage=float(latest.get("arbitrage", orchestrator.weights.arbitrage)),
                    breakout=float(latest.get("breakout", orchestrator.weights.breakout)),
                    sniping=float(latest.get("sniping", orchestrator.weights.sniping)),
                )
                sw.normalize()
                orchestrator.weights = sw
        except Exception:
            pass
        # Warm performance history from persisted metrics
        try:
            perf_rows = monitor_engine.storage.recent_performance(limit=200)
            for r in reversed(perf_rows):
                orchestrator.performance_history.append({
                    "strategy": r.get("strategy", "unknown"),
                    "pnl": float(r.get("pnl", 0.0)),
                    "timestamp": float(r.get("timestamp", 0.0)),
                })
        except Exception:
            pass
        monitor_engine.start()
    except Exception:
        monitor_engine = None
    
    # Optimisation coûts: tracking pour allocation et budget
    last_allocation_ts = 0.0
    monthly_budget_usd = float(getattr(cfg.llm, "monthly_budget_usd", 0.0))
    allocation_interval_sec = int(getattr(cfg.llm, "allocation_interval_sec", cfg.llm.decision_interval_sec))
    max_opportunities_per_cycle = int(getattr(cfg.llm, "max_opportunities_per_cycle", 999))
    min_opportunity_score = float(getattr(cfg.llm, "min_opportunity_score", 0.0))
    budget_exceeded = False

    def _score_opportunity(opportunity: Dict[str, Any], strategy_name: str, context: Dict[str, Any]) -> float:
        """Score préalable d'une opportunité (0-1) avant appel LLM pour réduire coûts."""
        if min_opportunity_score <= 0.0:
            return 1.0  # Pas de filtre
        
        score = 0.5  # Base score
        
        # Arbitrage: score basé sur spread
        if strategy_name == "arbitrage":
            spread_pct = float(opportunity.get("spread_pct", 0.0))
            score = min(1.0, spread_pct * 10.0)  # 0.1% spread = 1.0
        
        # Market Making: score basé sur spread et volatilité
        elif strategy_name == "market_making":
            spread = float(opportunity.get("spread", 0.0))
            vol = float(context.get("volatility", {}).get(opportunity.get("symbol", ""), 0.01))
            score = min(1.0, (spread / vol) * 5.0) if vol > 0 else 0.5
        
        # Momentum: score basé sur volume et mouvement
        elif strategy_name == "momentum":
            volume = float(opportunity.get("volume", 0.0))
            price_change = float(opportunity.get("price_change_pct", 0.0))
            score = min(1.0, (abs(price_change) * 10.0 + volume / 1000.0) / 2.0)
        
        # Breakout: score basé sur volume et résistance
        elif strategy_name == "breakout":
            volume = float(opportunity.get("volume", 0.0))
            score = min(1.0, volume / 5000.0)
        
        # Scalping: score basé sur volatilité
        elif strategy_name == "scalping":
            vol = float(context.get("volatility", {}).get(opportunity.get("symbol", ""), 0.01))
            score = min(1.0, vol * 50.0)
        
        # Sniping: toujours scorer bas (risqué)
        elif strategy_name == "sniping":
            score = 0.3  # Bas score pour limiter appels
        
        return max(0.0, min(1.0, score))

    stop_requested = False
    while not (stop_event and stop_event.is_set()):
        try:
            # Honor remote stop requests (from shell/systemd)
            try:
                rs = storage.get_runtime_status() or {}
                if bool(rs.get("desired_stop", False)):
                    if allow_remote_stop:
                        log.info("Stop requested remotely. Shutting down gracefully...")
                        stop_requested = True
                        break
                    else:
                        # Ignore and clear unintended remote stop requests
                        log.warning("Remote stop requested but ignored (CRYPTOBOT_ALLOW_REMOTE_STOP disabled). Clearing flag.")
                        try:
                            storage.clear_runtime_stop_request()
                        except Exception:
                            pass
            except Exception:
                pass

            # Record heartbeat early each loop
            try:
                storage.record_runtime_heartbeat(pid=pid)
            except Exception:
                pass

            # Vérifier budget mensuel (si configuré) — ne plus quitter; passer en mode budget_exceeded
            if monthly_budget_usd > 0.0:
                try:
                    stats = llm_client._cost_tracker.get_stats()
                    if float(stats.get("estimated_monthly_cost", 0.0)) >= monthly_budget_usd:
                        if not budget_exceeded:
                            log.warning(
                                f"Budget mensuel atteint: ${float(stats.get('estimated_monthly_cost', 0.0)):.2f} >= ${monthly_budget_usd:.2f} — pause des appels LLM, maintien du heartbeat"
                            )
                        budget_exceeded = True
                    else:
                        if budget_exceeded:
                            log.info("Budget sous le seuil à nouveau — reprise des appels LLM")
                        budget_exceeded = False
                except Exception:
                    pass
            
            # 1. Gather market context
            context = context_aggregator.build_context(
                symbols=symbols,
                include_sentiment=True,
                # Default to including orderbook to support market making; can be disabled via config
                include_orderbook=bool(getattr(getattr(cfg, "data", None), "include_orderbook", True)),
            )

            # 2. LLM decides strategy weights (optimisé: moins fréquent)
            current_time = time.time()
            if budget_exceeded:
                # Pas d'appels LLM — réutiliser poids précédents
                weights = orchestrator.weights
            else:
                if current_time - last_allocation_ts >= allocation_interval_sec:
                    weights = orchestrator.decide_strategy_allocation(
                        market_data=context["market"],
                        portfolio_state=context["portfolio"],
                        sentiment_data=context.get("sentiment", {}),
                        performance_metrics=performance_tracker.feed_to_llm(),
                    )
                    try:
                        log.info(
                            "Strategy allocation updated: "
                            + ", ".join([
                                f"{n}={getattr(weights, n):.2f}" for n in [
                                    "market_making","momentum","scalping","arbitrage","breakout","sniping"
                                ]
                            ])
                        )
                    except Exception:
                        pass
                    last_allocation_ts = current_time
                    # Persist new weights for future warm start
                    try:
                        if monitor_engine:
                            monitor_engine.storage.record_weights(
                                timestamp=current_time,
                                weights={
                                    "market_making": float(weights.market_making),
                                    "momentum": float(weights.momentum),
                                    "scalping": float(weights.scalping),
                                    "arbitrage": float(weights.arbitrage),
                                    "breakout": float(weights.breakout),
                                    "sniping": float(weights.sniping),
                                },
                            )
                    except Exception:
                        pass
                else:
                    # Réutiliser les poids précédents
                    weights = orchestrator.weights

            # 3. Update weight manager
            weight_manager.weights = weights

            # 4. For each strategy (based on weights) - OPTIMISÉ pour réduire coûts
            if not budget_exceeded:
                opportunities_processed = 0
                for strategy_name, strategy_instance in strategies.items():
                    weight = float(getattr(weights, strategy_name, 0.0))
                    if weight < 0.05:
                        continue
                    # Detect opportunities
                    detect_fn = getattr(strategy_instance, "detect_opportunities", None)
                    if detect_fn is None:
                        continue
                    # All strategies use context (which includes all signals: Reddit, Twitter, Polymarket, market cap, volume, etc.)
                    opportunities = detect_fn(context)
                    try:
                        log.debug(f"{strategy_name}: detected {len(opportunities)} opportunities before scoring")
                    except Exception:
                        pass
                    
                    # OPTIMISATION: Filtrer et scorer les opportunités avant appel LLM
                    scored_opportunities = []
                    for opp in opportunities:
                        score = _score_opportunity(opp, strategy_name, context)
                        if score >= min_opportunity_score:
                            scored_opportunities.append((score, opp))
                    
                    # Trier par score décroissant et limiter le nombre
                    scored_opportunities.sort(key=lambda x: x[0], reverse=True)
                    scored_opportunities = scored_opportunities[:max_opportunities_per_cycle]
                    try:
                        log.debug(f"{strategy_name}: {len(scored_opportunities)} opportunities after scoring/filtering (processed cap {max_opportunities_per_cycle})")
                    except Exception:
                        pass
                    
                    # Traiter les meilleures opportunités
                    for score, opportunity in scored_opportunities:
                        if opportunities_processed >= max_opportunities_per_cycle:
                            break
                        opportunities_processed += 1
                        
                        # Appel LLM uniquement pour opportunités scorées
                        decision = orchestrator.decide_trade(
                            strategy_name=strategy_name,
                            opportunity=opportunity,
                            market_context=context,
                        )
                        # Safety: apply configurable confidence threshold (default 0.6) and clamp leverage conservatively
                        min_conf = float(getattr(cfg.llm, "min_confidence_to_execute", 0.6))
                        if decision.get("execute") and float(decision.get("confidence", 0.0)) >= min_conf:
                            # Clamp leverage to config max (and stricter cap for market making)
                            try:
                                max_lev_cfg = int(getattr(getattr(cfg, "hyperliquid", object()), "max_leverage", 10))
                            except Exception:
                                max_lev_cfg = 10
                            try:
                                lev = int(decision.get("leverage", 1))
                            except Exception:
                                lev = 1
                            # Market making: prefer very low leverage
                            if strategy_name == "market_making":
                                lev = min(lev, 3)
                            decision["leverage"] = max(1, min(lev, max_lev_cfg))
                            decision["symbol"] = opportunity.get("symbol", symbols[0])
                            executor.execute_strategy(strategy_name, decision, weights)
                            performance_tracker.record_trade_start(
                                strategy=strategy_name,
                                entry_price=float(opportunity.get("price", 0.0) or opportunity.get("mid", 0.0) or 0.0),
                                size=float(decision.get("size_usd", 0.0)),
                                symbol=decision["symbol"],
                            )
                            try:
                                log.info(f"Executed {strategy_name} on {decision['symbol']} | size_usd={float(decision.get('size_usd', 0.0)):.2f} | conf={float(decision.get('confidence', 0.0)):.2f}")
                            except Exception:
                                pass
                        else:
                            # Fallback for market making: place passive maker orders in tight spreads, low risk
                            if strategy_name == "market_making":
                                try:
                                    sym = opportunity.get("symbol", symbols[0])
                                    mid = float(opportunity.get("mid", 0.0))
                                    spr = float(opportunity.get("spread", 0.0))
                                    vol = float(context.get("volatility", {}).get(sym, 0.01))
                                    # Safe condition: valid mid and modest spread vs volatility
                                    if mid > 0.0 and spr > 0.0 and vol > 0.0 and spr <= max(0.002, 3.0 * vol):
                                        strategy_instance.place_maker_orders(symbol=sym, mid_price=mid, spread=spr)
                                        log.info(f"Placed passive maker orders for {sym} | mid={mid:.2f} | spread={spr:.4f}")
                                except Exception:
                                    pass

            # 5. Update performance tracking
            performance_tracker.update_positions(broker.get_portfolio())

            # 6. Sleep (short sleep chunks to react faster to stop_event), and heartbeat periodically
            total_sleep = int(cfg.llm.decision_interval_sec)
            slept = 0.0
            while slept < total_sleep and not (stop_event and stop_event.is_set()):
                # Keep heartbeat fresh without hammering the DB
                if (slept % 2.0) < 1e-6:
                    try:
                        storage.record_runtime_heartbeat(pid=pid)
                    except Exception:
                        pass
                time.sleep(0.5)
                slept += 0.5

        except Exception as e:  # pragma: no cover - runtime path
            log.error(f"Error in main loop: {e}")
            # Sleep a bit but allow early exit on stop
            for _ in range(20):
                try:
                    storage.record_runtime_heartbeat(pid=pid)
                except Exception:
                    pass
                if stop_event and stop_event.is_set():
                    break
                time.sleep(0.5)
        finally:
            # loop continues
            pass

    # graceful stop
    if monitor_engine:
        try:
            monitor_engine.stop()
        except Exception:
            pass
    # Stop heartbeat watchdog
    try:
        heartbeat_stop.set()
        if hb_thread and hb_thread.is_alive():
            hb_thread.join(timeout=2.0)
    except Exception:
        pass
    # Only mark STOPPED in storage if a remote stop was explicitly requested.
    # For unexpected exits/crashes, we let the heartbeat freshness determine status.
    if stop_requested:
        try:
            storage.set_runtime_stopped()
        except Exception:
            pass
        # Release single-instance lock
        try:
            if lock_handle:
                lock_handle.close()
        except Exception:
            pass
        return True

    # If we reach here without an explicit stop request, it means the loop exited unexpectedly
    # (e.g., due to external factors). Return False so a supervisor can decide to restart.
    # Release single-instance lock before exiting.
    try:
        if lock_handle:
            lock_handle.close()
    except Exception:
        pass
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="C4$H M4CH1N3 Hyperliquid Live Runner")
    parser.add_argument("--config", type=str, default="configs/live.hyperliquid.yaml")
    args = parser.parse_args()
    # Optional supervisor loop: restart automatically unless a cooperative stop was requested
    auto_restart = str(os.getenv("CRYPTOBOT_AUTO_RESTART", "0")).lower() in {"1", "true", "yes"}
    if not auto_restart:
        run_live(args.config)
        return
    backoff = 3.0
    while True:
        stopped = run_live(args.config)
        if stopped:
            break
        try:
            time.sleep(backoff)
        except Exception:
            pass
        backoff = min(backoff * 2.0, 60.0)

if __name__ == "__main__":
    main()


