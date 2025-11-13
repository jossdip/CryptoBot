from __future__ import annotations

import time
import argparse
from typing import Dict, Any, Optional, List
import os
import threading
from pathlib import Path
import fcntl
import signal

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
from cryptobot.learn.memory import Episode, EpisodeStore
from cryptobot.learn.bandits import StrategyAllocationBandit, ParamBandit
from cryptobot.core.config import LearningConfig


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
    # Allow cooperative remote stop requests coming from the CLI/monitor DB
    # Rationale: user controls stop via the interactive CLI; honor it unconditionally
    allow_remote_stop = True

    log.info("Starting Hyperliquid live runner...")
    # Global single-instance lock (system-wide)
    lock_handle = _acquire_single_instance_lock()
    if lock_handle is None:
        log.warning("Another CryptoBot instance is already running (global lock held). Waiting for release and will retry...")
        # Brief wait so the incumbent can release its lock, then signal supervisor to retry
        try:
            time.sleep(2.0)
        except Exception:
            pass
        # Return False so the supervisor loop retries (auto-restart path)
        return False
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

    # Handle termination signals for graceful shutdown (propagate via storage + local event)
    signal_stop = threading.Event()
    def _on_signal(signum, frame) -> None:  # type: ignore[no-untyped-def]
        try:
            log.info(f"Signal {signum} received — requesting graceful shutdown...")
        except Exception:
            pass
        signal_stop.set()
        try:
            storage.request_runtime_stop()
        except Exception:
            pass
    try:
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
    except Exception:
        # Some environments disallow custom signal handlers; continue without them
        pass

    # Note: We rely on a system-wide file lock as the single source of truth.
    # The heartbeat record is informative only and should never prevent startup
    # once the lock is acquired (avoids CI/CD restart races). Proceed regardless.

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
            addr_used = pf.get("query_address_used", getattr(broker, "query_address", None))
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
            try:
                if addr_used:
                    log.info(f"Portfolio query address used: {addr_used}")
            except Exception:
                pass
        else:
            log.warning(f"Portfolio snapshot unavailable: {pf.get('error')}")
    except Exception:
        pass
    # Initialize session equity peak for circuit breaker tracking
    session_peak_equity = None
    try:
        if pf.get("ok"):
            resp = pf.get("response", {})
            eq0 = float(resp.get("equity", resp.get("balance", 0.0)))
            if eq0 > 0.0:
                session_peak_equity = eq0
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
    # Learning components (lazy-wired by config)
    learning_cfg: LearningConfig = getattr(cfg, "learning", LearningConfig())
    learning_enabled = bool(getattr(learning_cfg, "enabled", False))
    episode_store: EpisodeStore | None = None
    allocation_bandit: StrategyAllocationBandit | None = None
    param_bandit: ParamBandit | None = None
    if learning_enabled:
        try:
            episode_store = EpisodeStore(storage=storage, config=learning_cfg.memory)
        except Exception:
            episode_store = None
        try:
            allocation_bandit = StrategyAllocationBandit(
                strategies=["market_making", "momentum", "scalping", "arbitrage", "breakout", "sniping"],
                config=learning_cfg.bandits,
            )
        except Exception:
            allocation_bandit = None
        try:
            param_bandit = ParamBandit(config=learning_cfg.bandits)
        except Exception:
            param_bandit = None

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
    # Budget disabled permanently
    monthly_budget_usd = 0.0
    allocation_interval_sec = int(getattr(cfg.llm, "allocation_interval_sec", cfg.llm.decision_interval_sec))
    max_opportunities_per_cycle = int(getattr(cfg.llm, "max_opportunities_per_cycle", 999))
    min_opportunity_score = float(getattr(cfg.llm, "min_opportunity_score", 0.0))
    budget_exceeded = False
    # Online learning (PNL proxy) parameters
    evaluation_horizon_sec = int(getattr(cfg.llm, "evaluation_horizon_sec", max(30, int(getattr(cfg.llm, "decision_interval_sec", 30)))))  # default 60 in config
    adaptive_fallback_enabled = bool(getattr(cfg.llm, "adaptive_fallback_enabled", True))
    pending_evaluations: List[Dict[str, Any]] = []
    # Circuit breaker parameters
    try:
        daily_dd_limit_pct = float(getattr(getattr(cfg, "risk", object()), "max_daily_drawdown_pct", 0.0))
    except Exception:
        daily_dd_limit_pct = 0.0
    circuit_breaker_tripped = False
    # Debounce & cooldown controls
    try:
        circuit_breaker_cooldown_sec = float(getattr(getattr(cfg, "risk", object()), "circuit_breaker_cooldown_sec", 900.0))
    except Exception:
        circuit_breaker_cooldown_sec = 900.0
    dd_confirmations = 0
    cb_trip_ts: float | None = None
    # Base confidence gate
    try:
        base_min_confidence = float(getattr(getattr(cfg, "llm", object()), "min_confidence_to_execute", 0.6))
    except Exception:
        base_min_confidence = 0.6

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

    def _extract_features_for_learning(
        *,
        context: Dict[str, Any],
        strategy_name: str,
        opportunity: Dict[str, Any],
    ) -> Dict[str, float]:
        """Build a compact numeric feature set in a deterministic key order."""
        # Resolve symbol and price
        try:
            symbol = str(opportunity.get("symbol") or (context.get("symbols", [symbols[0]])[0] if isinstance(context.get("symbols"), list) else symbols[0]))
        except Exception:
            symbol = symbols[0]
        # Median price across venues
        price_map = context.get("prices", {}).get(symbol, {}) if isinstance(context.get("prices"), dict) else {}
        vals = []
        try:
            vals = [float(v) for v in (price_map.values() if isinstance(price_map, dict) else []) if float(v) > 0]
        except Exception:
            vals = []
        price_median = 0.0
        if vals:
            try:
                import statistics
                price_median = float(statistics.median(vals))
            except Exception:
                price_median = float(vals[-1])
        vol_map = context.get("volatility", {}) if isinstance(context.get("volatility"), dict) else {}
        volatility_1m = float(vol_map.get(symbol, 0.0))
        pcp_map = context.get("price_change_pct", {}) if isinstance(context.get("price_change_pct"), dict) else {}
        price_change_pct_1m = float(pcp_map.get(symbol, opportunity.get("price_change_pct", 0.0)))
        spread = float(opportunity.get("spread", 0.0))
        # Sentiment
        sentiment = context.get("sentiment", {}) if isinstance(context.get("sentiment"), dict) else {}
        sent_reddit = float(((sentiment.get("reddit", {}) or {}).get("score", 0.0)))
        sent_twitter = float(((sentiment.get("twitter", {}) or {}).get("score", 0.0)))
        sent_poly = float(((sentiment.get("polymarket", {}) or {}).get("score", 0.0)))
        # Portfolio signals
        portfolio = context.get("portfolio", {}) if isinstance(context.get("portfolio"), dict) else {}
        unrealized_pnl = float(portfolio.get("unrealized_pnl", 0.0) or 0.0)
        # Current strategy weights snapshot
        try:
            w = orchestrator.weights
            w_map = {
                "w_mm": float(getattr(w, "market_making", 0.0)),
                "w_mom": float(getattr(w, "momentum", 0.0)),
                "w_scalp": float(getattr(w, "scalping", 0.0)),
                "w_arb": float(getattr(w, "arbitrage", 0.0)),
                "w_brk": float(getattr(w, "breakout", 0.0)),
                "w_snp": float(getattr(w, "sniping", 0.0)),
            }
        except Exception:
            w_map = {"w_mm": 0.0, "w_mom": 0.0, "w_scalp": 0.0, "w_arb": 0.0, "w_brk": 0.0, "w_snp": 0.0}
        out = {
            "price_median": float(price_median),
            "price_change_pct_1m": float(price_change_pct_1m),
            "volatility_1m": float(volatility_1m),
            "spread": float(spread),
            "sent_reddit": float(sent_reddit),
            "sent_twitter": float(sent_twitter),
            "sent_polymarket": float(sent_poly),
            "unrealized_pnl": float(unrealized_pnl),
            **w_map,
        }
        return out

    stop_requested = False
    # Active local brackets: symbol -> dict(tp_pct, sl_pct, trailing_pct, entry_price, direction)
    active_brackets: Dict[str, Dict[str, float]] = {}
    last_bracket_check_ts = 0.0
    # Track open timestamps per symbol to enforce a minimum hold time before LLM-driven exits
    open_ts_by_symbol: Dict[str, float] = {}
    # LLM-decided runtime parameters (initialized with safe defaults)
    runtime_params: Dict[str, Any] = {
        "market_making": {
            "edge_margin_bps": 2.0,
            "k_vol": 1.0,
            "passive_order_fraction_of_alloc": 0.0,
            "passive_order_usd_cap": 250.0,
            "passive_order_min_usd": 0.0,
        },
        "risk": {
            "min_hold_seconds": 12.0,
        },
    }
    last_params_ts = 0.0
    while not ((stop_event and stop_event.is_set()) or signal_stop.is_set()):
        try:
            # Honor OS signal-triggered stop immediately
            if signal_stop.is_set():
                try:
                    log.info("Stop requested via OS signal. Shutting down gracefully...")
                except Exception:
                    pass
                stop_requested = True
                break
            # Honor remote stop requests (from shell/systemd)
            try:
                rs = storage.get_runtime_status() or {}
                if bool(rs.get("desired_stop", False)):
                    # Always honor a cooperative stop request recorded in storage
                    log.info("Stop requested remotely. Shutting down gracefully...")
                    stop_requested = True
                    break
                if bool(rs.get("desired_flatten", False)):
                    try:
                        log.info("Remote command: flatten positions. Closing all open positions...")
                        res = broker.close_all_positions()
                        if res.get("ok"):
                            log.info(f"Flatten completed | closed={len(res.get('closed', []))} errors={len(res.get('errors', []))}")
                        else:
                            log.error(f"Flatten failed: {res}")
                    except Exception as e:
                        log.error(f"Error while flattening positions: {e}")
                    finally:
                        try:
                            storage.clear_flatten_request()
                        except Exception:
                            pass
            except Exception:
                pass

            # Record heartbeat early each loop
            try:
                storage.record_runtime_heartbeat(pid=pid)
            except Exception:
                pass

            # Budget mensuel LLM désactivé: aucun gating par budget
            
            # 1. Gather market context
            context = context_aggregator.build_context(
                symbols=symbols,
                include_sentiment=True,
                # Default to including orderbook to support market making; can be disabled via config
                include_orderbook=bool(getattr(getattr(cfg, "data", None), "include_orderbook", True)),
            )

            # Circuit breaker: compute session drawdown and gate trading if exceeded
            try:
                portfolio_state = context.get("portfolio", {}) or {}
                cur_eq = float(portfolio_state.get("equity", portfolio_state.get("balance", 0.0)))
                if cur_eq > 0.0:
                    if session_peak_equity is None or cur_eq > float(session_peak_equity):
                        session_peak_equity = float(cur_eq)
                    if daily_dd_limit_pct > 0.0 and session_peak_equity and session_peak_equity > 0.0:
                        dd_pct = max(0.0, (float(session_peak_equity) - float(cur_eq)) / float(session_peak_equity) * 100.0)
                        # Debounce: require two consecutive exceedances
                        if dd_pct >= daily_dd_limit_pct:
                            dd_confirmations = min(dd_confirmations + 1, 3)
                            if dd_confirmations >= 2 and not circuit_breaker_tripped:
                                circuit_breaker_tripped = True
                                cb_trip_ts = time.time()
                                try:
                                    log.error(f"CIRCUIT BREAKER TRIPPED: drawdown={dd_pct:.2f}% >= limit={daily_dd_limit_pct:.2f}% — pausing new trades (heartbeat continues)")
                                except Exception:
                                    pass
                        else:
                            dd_confirmations = 0
                        # Cooldown auto-reset: resume after cooldown or strong recovery
                        if circuit_breaker_tripped:
                            recovered = dd_pct <= max(0.0, daily_dd_limit_pct * 0.5)
                            cooldown_elapsed = (cb_trip_ts is not None) and ((time.time() - cb_trip_ts) >= circuit_breaker_cooldown_sec)
                            if recovered or cooldown_elapsed:
                                circuit_breaker_tripped = False
                                dd_confirmations = 0
                                # Reset peak to current equity to avoid immediate re-trip on noise
                                session_peak_equity = float(cur_eq)
                                try:
                                    if recovered:
                                        log.info(f"Circuit breaker auto-reset on recovery: drawdown={dd_pct:.2f}% <= {daily_dd_limit_pct*0.5:.2f}%")
                                    elif cooldown_elapsed:
                                        log.info(f"Circuit breaker cooldown elapsed ({int(circuit_breaker_cooldown_sec)}s) — resuming LLM trading")
                                except Exception:
                                    pass
                # Gate allocation/trading entirely when tripped
            except Exception:
                pass

            # Dynamic confidence tuning based on recent win rate (last 50 proxy trades)
            dynamic_min_confidence = base_min_confidence
            try:
                recent = performance_tracker.trades[-50:]
                if recent:
                    wins = sum(1 for t in recent if float(t.get("pnl", 0.0)) > 0.0)
                    win_rate = float(wins) / float(max(1, len(recent)))
                    adj = -0.1 if win_rate > 0.6 else (0.1 if win_rate < 0.4 else 0.0)
                    dynamic_min_confidence = max(0.5, min(0.9, base_min_confidence + adj))
            except Exception:
                dynamic_min_confidence = base_min_confidence

            # 2. LLM decides strategy weights (optimisé: moins fréquent)
            current_time = time.time()
            # 2a. LLM decides runtime parameters (PNL-first knobs), at a similar cadence to allocation
            try:
                params_interval_sec = float(getattr(getattr(cfg, "llm", object()), "params_interval_sec", allocation_interval_sec))
            except Exception:
                params_interval_sec = allocation_interval_sec
            if not circuit_breaker_tripped and (current_time - last_params_ts >= params_interval_sec):
                try:
                    rp = orchestrator.decide_runtime_parameters(
                        market_data=context["market"],
                        portfolio_state=context["portfolio"],
                        performance_metrics=performance_tracker.feed_to_llm(),
                    )
                    if isinstance(rp, dict):
                        runtime_params = rp
                        last_params_ts = current_time
                        try:
                            log.info(
                                "LLM runtime params updated: "
                                f"edge_margin_bps={float(runtime_params['market_making']['edge_margin_bps']):.2f}, "
                                f"k_vol={float(runtime_params['market_making']['k_vol']):.2f}, "
                                f"mm_frac={float(runtime_params['market_making']['passive_order_fraction_of_alloc']):.3f}, "
                                f"mm_cap={float(runtime_params['market_making']['passive_order_usd_cap']):.2f}, "
                                f"mm_min={float(runtime_params['market_making']['passive_order_min_usd']):.2f}, "
                                f"min_hold={float(runtime_params['risk']['min_hold_seconds']):.1f}s"
                            )
                        except Exception:
                            pass
                except Exception:
                    pass
            if circuit_breaker_tripped:
                # Pas d'appels LLM — utiliser fallback adaptatif si activé, sinon réutiliser poids précédents
                if adaptive_fallback_enabled and (current_time - last_allocation_ts >= allocation_interval_sec):
                    try:
                        weights = weight_manager.calculate_adaptive_weights()
                        orchestrator.weights = weights
                        log.info(
                            "Adaptive fallback allocation (LLM paused): "
                            + ", ".join([
                                f"{n}={getattr(weights, n):.2f}" for n in [
                                    "market_making","momentum","scalping","arbitrage","breakout","sniping"
                                ]
                            ])
                        )
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
                    except Exception:
                        weights = orchestrator.weights
                else:
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

            # 2b. Learning-driven allocation blend
            if learning_enabled and allocation_bandit is not None:
                try:
                    bandit_w = allocation_bandit.propose_weights()
                    mode = str(getattr(learning_cfg, "allocation_mode", "hybrid"))
                    blend = float(getattr(learning_cfg, "allocation_hybrid_blend", 0.5))
                    from cryptobot.llm.orchestrator import StrategyWeight as _SW
                    if mode == "llm_only":
                        blended = weights
                    elif mode == "bandit_only":
                        blended = _SW(
                            market_making=float(bandit_w.get("market_making", 0.0)),
                            momentum=float(bandit_w.get("momentum", 0.0)),
                            scalping=float(bandit_w.get("scalping", 0.0)),
                            arbitrage=float(bandit_w.get("arbitrage", 0.0)),
                            breakout=float(bandit_w.get("breakout", 0.0)),
                            sniping=float(bandit_w.get("sniping", 0.0)),
                        )
                        blended.normalize()
                    else:
                        # hybrid
                        bw = bandit_w
                        lw = weights
                        blended = _SW(
                            market_making=float(blend * bw.get("market_making", 0.0) + (1.0 - blend) * float(getattr(lw, "market_making", 0.0))),
                            momentum=float(blend * bw.get("momentum", 0.0) + (1.0 - blend) * float(getattr(lw, "momentum", 0.0))),
                            scalping=float(blend * bw.get("scalping", 0.0) + (1.0 - blend) * float(getattr(lw, "scalping", 0.0))),
                            arbitrage=float(blend * bw.get("arbitrage", 0.0) + (1.0 - blend) * float(getattr(lw, "arbitrage", 0.0))),
                            breakout=float(blend * bw.get("breakout", 0.0) + (1.0 - blend) * float(getattr(lw, "breakout", 0.0))),
                            sniping=float(blend * bw.get("sniping", 0.0) + (1.0 - blend) * float(getattr(lw, "sniping", 0.0))),
                        )
                        blended.normalize()
                    weights = blended
                except Exception:
                    pass

            # 3. Update weight manager
            weight_manager.weights = weights

            # 4. For each strategy (based on weights) - OPTIMISÉ pour réduire coûts
            if not circuit_breaker_tripped:
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
                        
                        # Learning memory enrichment (append to context)
                        if learning_enabled and episode_store is not None and bool(getattr(learning_cfg.memory, "enabled", True)):
                            try:
                                feats = _extract_features_for_learning(context=context, strategy_name=strategy_name, opportunity=opportunity)
                                knn = episode_store.knn(feats, k=int(getattr(learning_cfg.memory, "knn_k", 8)))
                                similar = []
                                for ep, sim in knn[:3]:
                                    try:
                                        similar.append(
                                            {
                                                "strategy": ep.strategy,
                                                "symbol": ep.symbol,
                                                "sim": float(sim),
                                                "decision": {
                                                    "direction": ep.decision.get("direction"),
                                                    "leverage": ep.decision.get("leverage"),
                                                },
                                                "outcome": {"pnl": ep.outcome.get("pnl", 0.0)},
                                            }
                                        )
                                    except Exception:
                                        continue
                                # attach to context for LLM prompt
                                try:
                                    if isinstance(context, dict):
                                        context["learning_memory"] = {"similar_contexts": similar}
                                except Exception:
                                    pass
                            except Exception:
                                pass

                        # Appel LLM uniquement pour opportunités scorées
                        decision = orchestrator.decide_trade(
                            strategy_name=strategy_name,
                            opportunity=opportunity,
                            market_context=context,
                        )
                        # Learning param suggestions
                        if learning_enabled and param_bandit is not None and str(getattr(learning_cfg, "param_mode", "bandit")) in {"bandit", "bo"}:
                            try:
                                feats = _extract_features_for_learning(context=context, strategy_name=strategy_name, opportunity=opportunity)
                                suggestion = param_bandit.propose(strategy=strategy_name, features=feats)
                                # Merge suggestion with decision under safety shield
                                # Confidence gate: use max of both
                                if "min_conf" in suggestion:
                                    dynamic_min_confidence = max(dynamic_min_confidence, float(suggestion["min_conf"]))
                                # Leverage: prefer higher between LLM and suggestion, then clamp by config later
                                if "leverage" in suggestion:
                                    try:
                                        llm_lev = int(decision.get("leverage", 1))
                                        decision["leverage"] = int(max(llm_lev, int(suggestion["leverage"])))
                                    except Exception:
                                        pass
                                # TP/SL: adopt suggestion when LLM omitted; always enforce SL floor later
                                if "tp_pct" in suggestion and not decision.get("take_profit_pct"):
                                    decision["take_profit_pct"] = float(suggestion["tp_pct"])
                                if "sl_pct" in suggestion:
                                    cur_sl = float(decision.get("stop_loss_pct") or 0.0)
                                    decision["stop_loss_pct"] = float(max(cur_sl, float(suggestion["sl_pct"])))
                            except Exception:
                                pass
                        # Safety: apply configurable confidence threshold (default 0.6) and clamp leverage conservatively
                        min_conf = float(dynamic_min_confidence)
                        conf = float(decision.get("confidence", 0.0))
                        direction = str(decision.get("direction", "flat")).lower()
                        size_usd = float(decision.get("size_usd", 0.0) or 0.0)
                        if decision.get("execute") and conf >= min_conf and direction in {"long", "short"} and size_usd > 0.0:
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
                            # Safety shield: global max leverage
                            decision["leverage"] = max(1, min(lev, max_lev_cfg))
                            decision["symbol"] = opportunity.get("symbol", symbols[0])
                            # Provide entry price for proper USD -> coin size conversion
                            try:
                                decision["entry_price"] = float(opportunity.get("price", 0.0) or opportunity.get("mid", 0.0) or 0.0)
                            except Exception:
                                decision["entry_price"] = 0.0
                            # Safety shield: enforce minimum stop loss floor
                            try:
                                sl_floor = 0.004
                                if decision.get("stop_loss_pct") is None or float(decision.get("stop_loss_pct") or 0.0) < sl_floor:
                                    decision["stop_loss_pct"] = sl_floor
                            except Exception:
                                pass
                            # Also carry spread for maker pricing (used to avoid taker fees)
                            try:
                                decision["spread"] = float(opportunity.get("spread", 0.0))
                            except Exception:
                                decision["spread"] = 0.0
                            # Fallback: derive entry from context median if missing
                            if not decision["entry_price"] or decision["entry_price"] <= 0.0:
                                try:
                                    sym = decision["symbol"]
                                    px_map = context.get("prices", {}).get(sym, {})
                                    vals = [float(v) for v in (px_map.values() if isinstance(px_map, dict) else []) if float(v) > 0]
                                    if vals:
                                        import statistics
                                        decision["entry_price"] = float(statistics.median(vals))
                                except Exception:
                                    pass
                            # Debug gate values
                            try:
                                log.debug(f"Decision gate | strat={strategy_name} exec={bool(decision.get('execute'))} conf={conf:.2f}/{min_conf:.2f} dir={direction} size_usd={size_usd:.2f} entry={float(decision.get('entry_price',0.0)):.2f}")
                            except Exception:
                                pass
                            # Log attempt before execution
                            try:
                                log.info(f"Attempting execution | strat={strategy_name} sym={decision['symbol']} dir={direction} size_usd={size_usd:.2f} lev={int(decision.get('leverage',1))} conf={conf:.2f}")
                            except Exception:
                                pass
                            resp = executor.execute_strategy(strategy_name, decision, weights)
                            try:
                                ok = bool(resp and isinstance(resp, dict) and resp.get("ok"))
                                if ok:
                                    log.info(f"Executed {strategy_name} on {decision['symbol']} | size_usd={size_usd:.2f} | lev={int(decision.get('leverage', 1))} | dir={direction} | conf={conf:.2f}")
                            # Also record into monitor storage so it appears under Recent Trades (entry-only snapshot)
                                    if monitor_engine:
                                        try:
                                            # Prefer actual filled size/price when available from broker response
                                            entry_px = float(decision.get("entry_price", 0.0) or 0.0)
                                            coin_sz = float(size_usd) / entry_px if entry_px > 0 else 0.0
                                            try:
                                                resp_root = resp.get("response", {})
                                                # Structure: {'status':'ok','response':{'type':'order','data':{'statuses':[{'filled':{'totalSz': '0.002','avgPx': '103650.7'}}]}}}
                                                filled_list = (((resp_root or {}).get("response", {}) or {}).get("data", {}) or {}).get("statuses", [])
                                                if isinstance(filled_list, list) and filled_list:
                                                    filled = filled_list[0].get("filled", {}) if isinstance(filled_list[0], dict) else {}
                                                    f_sz = filled.get("totalSz")
                                                    f_px = filled.get("avgPx")
                                                    if f_sz is not None:
                                                        coin_sz = float(f_sz)
                                                    if f_px is not None:
                                                        entry_px = float(f_px)
                                            except Exception:
                                                # Fallback to broker-reported request size if present
                                                try:
                                                    req = resp.get("request", {}) if isinstance(resp.get("request"), dict) else {}
                                                    if "sz" in req:
                                                        coin_sz = float(req.get("sz"))
                                                except Exception:
                                                    pass
                                            # Record start with correct coin size and direction
                                            try:
                                                performance_tracker.record_trade_start(
                                                    strategy=strategy_name,
                                                    entry_price=float(entry_px if entry_px > 0 else (opportunity.get("price", 0.0) or opportunity.get("mid", 0.0) or 0.0)),
                                                    size=float(coin_sz),
                                                    symbol=decision["symbol"],
                                                    direction=direction,
                                                )
                                            except Exception:
                                                pass
                                            # Schedule evaluation for learning loop
                                            try:
                                                # Persist entry features for episode logging and bandit updates
                                                entry_feats = _extract_features_for_learning(context=context, strategy_name=strategy_name, opportunity=opportunity)
                                                pending_evaluations.append({
                                                    "strategy": strategy_name,
                                                    "symbol": decision["symbol"],
                                                    "direction": direction,
                                                    "entry_price": float(entry_px if entry_px > 0 else (opportunity.get("price", 0.0) or opportunity.get("mid", 0.0) or 0.0)),
                                                    "size": float(coin_sz),
                                                    "ts_open": time.time(),
                                                    "features": entry_feats,
                                                    "decision": {
                                                        "direction": direction,
                                                        "leverage": int(decision.get("leverage", 1)),
                                                        "stop_loss_pct": float(decision.get("stop_loss_pct") or 0.0),
                                                        "take_profit_pct": float(decision.get("take_profit_pct") or 0.0),
                                                        "confidence": float(decision.get("confidence") or 0.0),
                                                        "size_usd": float(size_usd),
                                                    },
                                                })
                                            except Exception:
                                                pass
                                            monitor_engine.record_trade(
                                                timestamp=time.time(),
                                                strategy=strategy_name,
                                                symbol=decision["symbol"],
                                                side="buy" if direction == "long" else "sell",
                                                size=float(coin_sz if coin_sz > 0 else size_usd),
                                                entry=float(entry_px if entry_px > 0 else size_usd),
                                                exit=float(entry_px if entry_px > 0 else size_usd),
                                                pnl=0.0,
                                                confidence=conf,
                                                metadata={"llm_decision": decision, "resp": resp},
                                            )
                                            # Track open time to enforce min hold before LLM exits
                                            try:
                                                open_ts_by_symbol[decision["symbol"]] = float(time.time())
                                            except Exception:
                                                pass
                                            # Place on-exchange bracket orders (best-effort)
                                            try:
                                                tp_pct = float(decision.get("take_profit_pct") or 0.0)
                                                sl_pct = float(decision.get("stop_loss_pct") or 0.0)
                                                # Sensible defaults when LLM omits brackets (risk first, strategy-aware)
                                                if (tp_pct <= 0.0 and sl_pct <= 0.0):
                                                    if strategy_name in {"momentum", "breakout"}:
                                                        tp_pct, sl_pct = 0.010, 0.006
                                                    elif strategy_name == "scalping":
                                                        tp_pct, sl_pct = 0.007, 0.005
                                                    elif strategy_name == "sniping":
                                                        tp_pct, sl_pct = 0.015, 0.010
                                                if (tp_pct and tp_pct > 0.0) or (sl_pct and sl_pct > 0.0):
                                                    br = broker.place_bracket_orders(
                                                        symbol=decision["symbol"],
                                                        direction=("long" if direction == "long" else "short"),
                                                        size=float(coin_sz),
                                                        entry_price=float(entry_px),
                                                        tp_pct=(tp_pct if tp_pct > 0.0 else None),
                                                        sl_pct=(sl_pct if sl_pct > 0.0 else None),
                                                    )
                                                    try:
                                                        if br.get("ok"):
                                                            log.info(f"On-exchange bracket placed | sym={decision['symbol']} tp={(tp_pct*100.0):.2f}% sl={(sl_pct*100.0):.2f}%")
                                                        else:
                                                            log.warning(f"Bracket placement partial/failed | sym={decision['symbol']} details={br}")
                                                    except Exception:
                                                        pass
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                                else:
                                    log.error(f"Execution failed {strategy_name} on {decision['symbol']} | dir={direction} | reason={(resp or {}).get('error') if isinstance(resp, dict) else 'unknown'}")
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
                                    # Net-edge gate: require spread >= 2*fee + margin + k*vol
                                    try:
                                        fee_bps = float(getattr(getattr(cfg, "broker", object()), "fee_bps", 0.0))
                                    except Exception:
                                        fee_bps = 0.0
                                    # Pull knobs from LLM-decided runtime params
                                    try:
                                        edge_margin_bps = float(runtime_params["market_making"]["edge_margin_bps"])
                                        k_vol = float(runtime_params["market_making"]["k_vol"])
                                        passive_frac = float(runtime_params["market_making"]["passive_order_fraction_of_alloc"])
                                        passive_cap_usd = float(runtime_params["market_making"]["passive_order_usd_cap"])
                                        min_usd = float(runtime_params["market_making"]["passive_order_min_usd"])
                                    except Exception:
                                        edge_margin_bps, k_vol, passive_frac, passive_cap_usd, min_usd = 2.0, 1.0, 0.02, 250.0, 10.0
                                    # If passive making is disabled (fraction==0), skip fallback entirely
                                    if passive_frac <= 0.0:
                                        log.debug(f"Passive maker disabled by runtime_params; skipping | sym={sym}")
                                        continue
                                    min_required_spread = (2.0 * fee_bps / 10000.0) + (edge_margin_bps / 10000.0) + (k_vol * max(0.0, vol))
                                    if mid > 0.0 and spr >= min_required_spread and passive_frac > 0.0:
                                        # Size maker orders by allocation
                                        try:
                                            alloc = float(executor.total_capital) * float(getattr(weights, "market_making", 0.0))
                                        except Exception:
                                            alloc = 0.0
                                        size_usd = min(max(min_usd, alloc * passive_frac), passive_cap_usd)
                                        if size_usd > 0.0:
                                            strategy_instance.place_maker_orders(symbol=sym, mid_price=mid, spread=spr, size_usd=size_usd, post_only=True)
                                            log.info(f"Placed passive maker orders for {sym} | mid={mid:.2f} | spread={spr:.4f} | size_usd~{size_usd:.2f}")
                                        else:
                                            log.debug(f"Skipped passive maker orders (no alloc) | alloc=0 sym={sym}")
                                    else:
                                        log.debug(f"Skipped passive maker orders | mid={mid:.2f} spr={spr:.5f} min_req={min_required_spread:.5f} vol={vol:.5f} sym={sym}")
                                except Exception:
                                    pass
                            else:
                                try:
                                    log.debug(f"Skip execution gate | exec={bool(decision.get('execute'))} conf={conf:.2f}/{min_conf:.2f} dir={direction} size_usd={size_usd:.2f} strat={strategy_name}")
                                except Exception:
                                    pass
            # 4b. Position management (LLM-driven exits)
            try:
                portfolio_state = context.get("portfolio", {}) or {}
                positions = portfolio_state.get("positions", {})
                # Build base symbol mapping from configured symbols
                base_to_symbol = {}
                for s in symbols:
                    try:
                        base = s.split("/", 1)[0].split(":", 1)[0].upper()
                        base_to_symbol[base] = s
                    except Exception:
                        continue
                # Normalize positions into iterable dicts
                pos_list = []
                if isinstance(positions, dict):
                    for k, v in positions.items():
                        if isinstance(v, dict):
                            p = dict(v)
                            p.setdefault("symbol", k)
                            pos_list.append(p)
                elif isinstance(positions, list):
                    pos_list = positions
                # Evaluate exits
                for p in pos_list:
                    try:
                        sym = str(p.get("symbol") or p.get("coin") or "")
                        if not sym:
                            continue
                        qty = float(p.get("qty") or p.get("size") or p.get("sz") or p.get("szi") or 0.0)
                        if qty == 0.0:
                            continue
                        base = sym.upper()
                        full_symbol = base_to_symbol.get(base, f"{base}/USD:USD")
                        # Attach live price to position for the LLM
                        cur_px = 0.0
                        try:
                            px_map = context.get("prices", {}).get(full_symbol, {})
                            vals = [float(v) for v in (px_map.values() if isinstance(px_map, dict) else []) if float(v) > 0]
                            if vals:
                                import statistics
                                cur_px = float(statistics.median(vals))
                        except Exception:
                            cur_px = 0.0
                        pos_for_llm = {
                            "symbol": full_symbol,
                            "base": base,
                            "qty": qty,
                            "avg_price": float(p.get("avg_price", 0.0)),
                            "leverage": float(p.get("leverage", 0.0)) if p.get("leverage") is not None else None,
                            "current_price": cur_px,
                        }
                        pm_decision = orchestrator.decide_position_management(position=pos_for_llm, market_context=context)
                        pm_conf = float(pm_decision.get("confidence", 0.0))
                        pm_close = bool(pm_decision.get("close", False))
                        # Use the same dynamic threshold as entries
                        if pm_close and pm_conf >= float(dynamic_min_confidence):
                            # Enforce minimum hold time and PnL-positive gating before LLM-driven exits
                            now = time.time()
                            # Use LLM-decided min hold seconds
                            try:
                                min_hold_sec = float(runtime_params["risk"]["min_hold_seconds"])
                            except Exception:
                                min_hold_sec = 20.0
                            opened_at = float(open_ts_by_symbol.get(full_symbol, 0.0))
                            hold_ok = True if opened_at <= 0.0 else ((now - opened_at) >= min_hold_sec)
                            # Estimate net PnL after fees
                            entry_px = float(p.get("avg_price", 0.0))
                            abs_qty = abs(qty)
                            long_pos = qty > 0.0
                            gross = ((cur_px - entry_px) * abs_qty) if long_pos else ((entry_px - cur_px) * abs_qty)
                            try:
                                fee_bps = float(getattr(getattr(cfg, "broker", object()), "fee_bps", 0.0))
                            except Exception:
                                fee_bps = 0.0
                            est_fees = ((entry_px + cur_px) * abs_qty) * (fee_bps / 10000.0) if entry_px > 0.0 and cur_px > 0.0 else 0.0
                            net = float(gross - est_fees)
                            reason_txt = str(pm_decision.get("reasoning", "") or "").lower()
                            invalidation = ("invalid" in reason_txt) or ("break" in reason_txt and "trend" in reason_txt)
                            allow_close = hold_ok and (net > 0.0 or invalidation)
                            if not allow_close:
                                try:
                                    log.debug(f"Skip LLM exit | sym={full_symbol} hold_ok={hold_ok} net={net:.6f} conf={pm_conf:.2f}")
                                except Exception:
                                    pass
                                continue
                            size_pct = float(pm_decision.get("size_pct", 1.0))
                            order_type = str(pm_decision.get("order_type", "market")).lower()
                            limit_off = float(pm_decision.get("limit_offset_pct", 0.0005))
                            close_qty = abs(qty) * max(0.1, min(1.0, size_pct))
                            limit_px = None
                            if order_type == "limit" and cur_px > 0.0:
                                # If long (qty>0) we sell above mid; if short (qty<0) we buy below mid
                                limit_px = cur_px * (1.0 + limit_off) if qty > 0 else cur_px * (1.0 - limit_off)
                            # Execute close
                            close_resp = executor.close_position(symbol=full_symbol, qty=qty if size_pct >= 0.999 else (close_qty if qty > 0 else -close_qty), order_type=order_type, limit_price=limit_px)
                            ok = bool(close_resp and isinstance(close_resp, dict) and close_resp.get("ok"))
                            try:
                                if ok:
                                    log.info(f"Position closed (partial={size_pct<0.999}) | sym={full_symbol} qty={close_qty:.6f}/{abs(qty):.6f} type={order_type} conf={pm_conf:.2f}")
                                else:
                                    log.error(f"Close failed | sym={full_symbol} qty={close_qty:.6f} reason={(close_resp or {}).get('error') if isinstance(close_resp, dict) else 'unknown'}")
                            except Exception:
                                pass
                            # Record to monitor (best-effort)
                            try:
                                if monitor_engine and ok:
                                    entry_px = float(p.get("avg_price", 0.0))
                                    exit_px = float(limit_px or cur_px or entry_px)
                                    side = "sell" if qty > 0 else "buy"
                                    pnl = (exit_px - entry_px) * (close_qty if qty > 0 else -close_qty)
                                    monitor_engine.record_trade(
                                        timestamp=time.time(),
                                        strategy="position_exit",
                                        symbol=full_symbol,
                                        side=side,
                                        size=float(close_qty),
                                        entry=float(entry_px),
                                        exit=float(exit_px),
                                        pnl=float(pnl),
                                        confidence=pm_conf,
                                        metadata={"llm_decision": pm_decision, "close_response": close_resp},
                                    )
                            except Exception:
                                pass
                    except Exception:
                        continue
            except Exception:
                # Position management errors should not stop trading
                pass
            # 4c. Bracket setup if not closing
            try:
                portfolio_state = context.get("portfolio", {}) or {}
                positions = portfolio_state.get("positions", {})
                pos_list = []
                if isinstance(positions, dict):
                    for k, v in positions.items():
                        if isinstance(v, dict):
                            p = dict(v)
                            p.setdefault("symbol", k)
                            pos_list.append(p)
                elif isinstance(positions, list):
                    pos_list = positions
                for p in pos_list:
                    try:
                        sym = str(p.get("symbol") or p.get("coin") or "")
                        if not sym:
                            continue
                        qty = float(p.get("qty") or p.get("size") or p.get("sz") or p.get("szi") or 0.0)
                        if qty == 0.0:
                            continue
                        base = sym.split("/", 1)[0].split(":", 1)[0].upper()
                        full_symbol = base + "/USD:USD" if "/" not in sym else sym
                        if full_symbol in active_brackets:
                            continue  # bracket already set; managed by 4b
                        # Build a minimal pm_decision again to get bracket suggestion only
                        cur_px = 0.0
                        try:
                            px_map = context.get("prices", {}).get(full_symbol, {})
                            vals = [float(v) for v in (px_map.values() if isinstance(px_map, dict) else []) if float(v) > 0]
                            if vals:
                                import statistics
                                cur_px = float(statistics.median(vals))
                        except Exception:
                            cur_px = 0.0
                        pos_for_llm = {
                            "symbol": full_symbol,
                            "base": base,
                            "qty": qty,
                            "avg_price": float(p.get("avg_price", 0.0)),
                            "leverage": float(p.get("leverage", 0.0)) if p.get("leverage") is not None else None,
                            "current_price": cur_px,
                        }
                        dec = orchestrator.decide_position_management(position=pos_for_llm, market_context=context)
                        if bool(dec.get("set_bracket", False)) and float(dec.get("confidence", 0.0)) >= float(dynamic_min_confidence):
                            br = {
                                "tp_pct": float(dec.get("tp_pct", 0.008)),
                                "sl_pct": float(dec.get("sl_pct", 0.005)),
                                "trailing_pct": float(dec.get("trailing_pct", 0.0)),
                                "entry_price": float(p.get("avg_price", 0.0)) or cur_px or 0.0,
                                "direction": 1.0 if qty > 0 else -1.0,
                            }
                            if br["entry_price"] > 0.0:
                                active_brackets[full_symbol] = br
                                try:
                                    log.info(f"Bracket set | sym={full_symbol} tp={br['tp_pct']*100:.2f}% sl={br['sl_pct']*100:.2f}% trail={br['trailing_pct']*100:.2f}%")
                                except Exception:
                                    pass
                    except Exception:
                        continue
            except Exception:
                pass

            # 5. Online learning: evaluate matured pending trades (PNL proxy) and feed back
            try:
                now_ts = time.time()
                price_map: Dict[str, Dict[str, float]] = context.get("prices", {}) or {}
                matured: List[Dict[str, Any]] = []
                remaining: List[Dict[str, Any]] = []
                for p in pending_evaluations:
                    if float(now_ts - float(p.get("ts_open", 0.0))) >= float(evaluation_horizon_sec):
                        matured.append(p)
                    else:
                        remaining.append(p)
                for p in matured:
                    sym = str(p.get("symbol", "BTC/USD:USD"))
                    # Best-effort exit price: prefer Hyperliquid quote, else median of venues
                    exit_price = 0.0
                    try:
                        per_ex = price_map.get(sym, {})
                        if isinstance(per_ex, dict):
                            hl_px = per_ex.get("hyperliquid")
                            if hl_px is not None and float(hl_px) > 0:
                                exit_price = float(hl_px)
                            else:
                                vals = [float(v) for v in per_ex.values() if float(v) > 0]
                                if vals:
                                    import statistics
                                    exit_price = float(statistics.median(vals))
                    except Exception:
                        exit_price = 0.0
                    entry_price = float(p.get("entry_price", 0.0))
                    size_coin = float(p.get("size", 0.0))
                    direction = str(p.get("direction", "long")).lower()
                    if entry_price > 0 and exit_price > 0 and size_coin > 0:
                        gross_pnl = (exit_price - entry_price) * size_coin if direction == "long" else (entry_price - exit_price) * size_coin
                        # Estimate round-trip fees (entry + exit)
                        try:
                            fee_bps = float(getattr(getattr(cfg, "broker", object()), "fee_bps", 0.0))
                        except Exception:
                            fee_bps = 0.0
                        est_fees = ((entry_price + exit_price) * size_coin) * (fee_bps / 10000.0)
                        pnl = float(gross_pnl - est_fees)
                        # Record into performance tracker (proxy trade completion)
                        try:
                            performance_tracker.track_trade(
                                strategy=str(p.get("strategy", "unknown")),
                                entry=float(entry_price),
                                exit=float(exit_price),
                                size=float(size_coin),
                                fees=float(est_fees),
                            )
                        except Exception:
                            pass
                        # Feed back to orchestrator/weight manager
                        try:
                            orchestrator.update_performance(strategy=str(p.get("strategy", "unknown")), pnl=float(pnl))
                        except Exception:
                            pass
                        try:
                            weight_manager.update_performance(strategy=str(p.get("strategy", "unknown")), pnl=float(pnl))
                        except Exception:
                            pass
                        # Persist realized trade to monitor if available
                        try:
                            if monitor_engine:
                                monitor_engine.record_trade(
                                    timestamp=now_ts,
                                    strategy=str(p.get("strategy", "unknown")),
                                    symbol=sym,
                                    side="sell" if direction == "long" else "buy",
                                    size=float(size_coin),
                                    entry=float(entry_price),
                                    exit=float(exit_price),
                                    pnl=float(pnl),
                                    fees=float(est_fees),
                                    confidence=None,
                                    metadata={"evaluation_horizon_sec": evaluation_horizon_sec, "proxy": True},
                                )
                        except Exception:
                            pass
                        # Learning feedback: bandit updates + episode record
                        if learning_enabled:
                            try:
                                reward = float(pnl) * float(getattr(learning_cfg.bandits, "reward_scale", 1.0))
                                strat = str(p.get("strategy", "unknown"))
                                if allocation_bandit is not None:
                                    allocation_bandit.update(strategy=strat, reward=reward)
                                if param_bandit is not None:
                                    param_bandit.update(strategy=strat, reward=reward, features=p.get("features"))
                                if episode_store is not None:
                                    ep = Episode(
                                        id=None,
                                        timestamp=float(p.get("ts_open", now_ts)),
                                        strategy=strat,
                                        symbol=sym,
                                        features={k: float(v) for k, v in ((p.get("features") or {}).items())},
                                        decision=p.get("decision") or {},
                                        outcome={"pnl": float(pnl), "fees": float(est_fees), "exit_price": float(exit_price)},
                                    )
                                    episode_store.add_episode(ep)
                            except Exception:
                                pass
                pending_evaluations = remaining
            except Exception:
                # If learning loop fails, do not impact trading
                pass

            # 6. Update performance tracking (placeholder hook)
            performance_tracker.update_positions(broker.get_portfolio())

            # 7. Sleep (short sleep chunks to react faster to stop_event), and heartbeat periodically
            total_sleep = int(cfg.llm.decision_interval_sec)
            slept = 0.0
            while slept < total_sleep and not ((stop_event and stop_event.is_set()) or signal_stop.is_set()):
                # Keep heartbeat fresh without hammering the DB
                if (slept % 2.0) < 1e-6:
                    try:
                        storage.record_runtime_heartbeat(pid=pid)
                    except Exception:
                        pass
                # Enforce proactive brackets with faster checks (every ~2s)
                try:
                    now = time.time()
                    if now - last_bracket_check_ts >= 2.0 and active_brackets:
                        last_bracket_check_ts = now
                        # Fetch fresh prices for bracketed symbols
                        bracket_symbols = list(active_brackets.keys())
                        price_map = context_aggregator._get_prices(bracket_symbols)
                        for full_symbol, br in list(active_brackets.items()):
                            pxs = price_map.get(full_symbol, {})
                            cur_px = 0.0
                            try:
                                vals = [float(v) for v in (pxs.values() if isinstance(pxs, dict) else []) if float(v) > 0]
                                if vals:
                                    import statistics
                                    cur_px = float(statistics.median(vals))
                            except Exception:
                                cur_px = 0.0
                            if cur_px <= 0.0:
                                continue
                            entry_px = float(br.get("entry_price", 0.0))
                            tp_pct = float(br.get("tp_pct", 0.0))
                            sl_pct = float(br.get("sl_pct", 0.0))
                            trailing_pct = float(br.get("trailing_pct", 0.0))
                            direction = 1.0 if float(br.get("direction", 1.0)) >= 0 else -1.0
                            # Compute triggers
                            tp_trigger = entry_px * (1.0 + (tp_pct * direction))
                            sl_trigger = entry_px * (1.0 - (sl_pct * direction))
                            # Update trailing stop if configured and in profit
                            if trailing_pct > 0.0:
                                if direction > 0 and cur_px > entry_px:
                                    new_entry = max(entry_px, cur_px * (1.0 - trailing_pct))
                                    br["entry_price"] = new_entry
                                elif direction < 0 and cur_px < entry_px:
                                    new_entry = min(entry_px, cur_px * (1.0 + trailing_pct))
                                    br["entry_price"] = new_entry
                                    entry_px = float(br["entry_price"])
                                    tp_trigger = entry_px * (1.0 + (tp_pct * direction))
                                    sl_trigger = entry_px * (1.0 - (sl_pct * direction))
                            # Check hit
                            hit_tp = (cur_px >= tp_trigger) if direction > 0 else (cur_px <= tp_trigger)
                            hit_sl = (cur_px <= sl_trigger) if direction > 0 else (cur_px >= sl_trigger)
                            if hit_tp or hit_sl:
                                # Determine qty from current portfolio snapshot (best-effort)
                                pf = broker.get_portfolio()
                                resp = pf.get("response", {}) if isinstance(pf, dict) else {}
                                positions = resp.get("positions", {})
                                qty = 0.0
                                # Look for base symbol match
                                base = full_symbol.split("/", 1)[0].split(":", 1)[0].upper()
                                if isinstance(positions, dict):
                                    p = positions.get(base) or positions.get(full_symbol) or {}
                                    try:
                                        qty = float(p.get("qty") or p.get("size") or p.get("sz") or p.get("szi") or 0.0)
                                    except Exception:
                                        qty = 0.0
                                # Execute market close
                                if qty != 0.0:
                                    close_resp = executor.close_position(symbol=full_symbol, qty=qty, order_type="market", limit_price=None)
                                    ok = bool(close_resp and isinstance(close_resp, dict) and close_resp.get("ok"))
                                    try:
                                        if ok:
                                            log.info(f"Bracket triggered ({'TP' if hit_tp else 'SL'}) | sym={full_symbol} px={cur_px:.2f}")
                                        else:
                                            log.error(f"Bracket close failed | sym={full_symbol} reason={(close_resp or {}).get('error') if isinstance(close_resp, dict) else 'unknown'}")
                                    except Exception:
                                        pass
                                # Remove bracket
                                active_brackets.pop(full_symbol, None)
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


