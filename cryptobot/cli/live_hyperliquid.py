from __future__ import annotations

import time
import argparse
import threading
import os
import signal
import asyncio
from typing import Dict, Any, Optional, List
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
from cryptobot.monitor.performance import PerformanceTracker
from cryptobot.monitor.engine import MonitorEngine
from cryptobot.monitor.storage import StorageManager
from cryptobot.data.context_aggregator import MarketContextAggregator
from cryptobot.core.fast_engine import FastEngine
from cryptobot.strategy.fast_scalping import FastScalpingStrategy

# Legacy strategies imports (for Slow Path)
from cryptobot.strategy.arbitrage import ArbitrageStrategy
from cryptobot.strategy.sniping import SnipingStrategy
from cryptobot.strategy.market_making import MarketMakingStrategy
from cryptobot.strategy.momentum import MomentumStrategy
from cryptobot.strategy.scalping import ScalpingStrategy
from cryptobot.strategy.breakout import BreakoutStrategy
from cryptobot.broker.executor import MultiStrategyExecutor

def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))

def _acquire_single_instance_lock() -> Optional[object]:
    try:
        lock_path = _expand(os.getenv("CRYPTOBOT_LOCK_PATH", "~/.cryptobot/cryptobot.lock"))
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        f = open(lock_path, "a+")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            try:
                f.seek(0)
                txt = f.read().strip()
                incumbent_pid = int(txt) if txt and txt.isdigit() else None
                if incumbent_pid:
                    try:
                        os.kill(incumbent_pid, 0)
                        f.close()
                        return None
                    except OSError:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    f.close()
                    return None
            except Exception:
                f.close()
                return None
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

async def run_slow_loop(
    cfg: AppConfig,
    broker: HyperliquidBroker,
    orchestrator: LLMOrchestrator,
    fast_engine: FastEngine,
    stop_event: asyncio.Event,
    performance_tracker: PerformanceTracker,
    context_aggregator: MarketContextAggregator,
    monitor_engine: Optional[MonitorEngine],
    symbols: List[str]
):
    """
    Slow Path: LLM Supervision & Parameter Tuning.
    Runs every 5-15 minutes (configurable).
    """
    log = get_logger()
    log.info("Slow Path (LLM) loop started")
    
    decision_interval = int(getattr(cfg.llm, "decision_interval_sec", 300)) # Default 5 min
    
    while not stop_event.is_set():
        try:
            log.info("Slow Path: Analyzing context...")
            
            # 1. Build Context (Sync call wrapped)
            # We need to use to_thread because context_aggregator might do sync HTTP calls
            context = await asyncio.to_thread(
                context_aggregator.build_context,
                symbols=symbols,
                include_sentiment=True
            )
            
            # 2. LLM Decision: Runtime Parameters
            # This controls the Fast Path
            params = await asyncio.to_thread(
                orchestrator.decide_runtime_parameters,
                market_data=context.get("market", {}),
                portfolio_state=context.get("portfolio", {}),
                performance_metrics=performance_tracker.feed_to_llm()
            )
            
            # 3. Update Fast Engine
            if "fast_path" in params:
                await fast_engine.update_params(params["fast_path"])
                
            # 4. Legacy Slow Strategies (Optional - can be kept for complex logic)
            # For now, we focus on tuning the Fast Path.
            # If we want LLM to place trades directly (Slow Path trades), we can do it here.
            # But the goal is "Architecture Hybride" where execution is delegated.
            
            # 5. Sleep
            log.info(f"Slow Path: Sleeping for {decision_interval}s")
            await asyncio.sleep(decision_interval)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Error in Slow Loop: {e}")
            await asyncio.sleep(60)

async def run_async_main(config_path: str, stop_event_sync: Optional[threading.Event] = None) -> bool:
    load_local_environment()
    cfg = AppConfig.load(config_path)
    setup_logging(level="INFO")
    log = get_logger()
    
    lock_handle = _acquire_single_instance_lock()
    if lock_handle is None:
        log.warning("Global lock held. Exiting.")
        return False

    try:
        mode_manager = ModeManager(cfg)
        
        # Broker (Sync Init)
        broker = HyperliquidBroker(
            wallet_address=mode_manager.wallet_address,
            private_key=mode_manager.private_key,
            testnet=mode_manager.is_testnet(),
        )
        
        # LLM
        llm_client = LLMClient.from_env()
        orchestrator = LLMOrchestrator(llm_client)
        
        # Data & Monitor
        performance_tracker = PerformanceTracker()
        context_aggregator = MarketContextAggregator(broker, llm_client=llm_client, config=cfg)
        monitor_engine = None # Optional, can enable if needed
        
        symbols = cfg.general.symbols
        
        # Initialize Fast Engine
        # Pass strategies here. We use the FastScalpingStrategy.
        # Params are shared/managed by FastEngine.
        fast_strategies = []
        
        # Create engine first to get default params
        fast_engine = FastEngine(broker, strategies=[], symbols=symbols, performance_tracker=performance_tracker)
        
        # Create strategy with engine's params reference
        scalping_strat = FastScalpingStrategy(fast_engine.params)
        fast_engine.strategies.append(scalping_strat)
        
        # Start Fast Engine
        await fast_engine.start()
        
        # Async Stop Event
        async_stop_event = asyncio.Event()
        
        # Task for Slow Loop
        slow_task = asyncio.create_task(
            run_slow_loop(
                cfg, broker, orchestrator, fast_engine, async_stop_event,
                performance_tracker, context_aggregator, monitor_engine, symbols
            )
        )
        
        # Main keep-alive loop
        # Check sync stop_event from threading (if passed)
        try:
            while not async_stop_event.is_set():
                if stop_event_sync and stop_event_sync.is_set():
                    async_stop_event.set()
                    break
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            async_stop_event.set()
            
        # Shutdown
        await fast_engine.stop()
        slow_task.cancel()
        try:
            await slow_task
        except asyncio.CancelledError:
            pass
            
        return True
        
    except Exception as e:
        log.error(f"Fatal error in async main: {e}")
        return False
    finally:
        if lock_handle:
            lock_handle.close()

def run_live(config_path: str, stop_event: Optional[threading.Event] = None) -> bool:
    """Entry point wrapper."""
    try:
        return asyncio.run(run_async_main(config_path, stop_event))
    except KeyboardInterrupt:
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def main() -> None:
    parser = argparse.ArgumentParser(description="C4$H M4CH1N3 Hybrid Asynchronous Runner")
    parser.add_argument("--config", type=str, default="configs/live.hyperliquid.yaml")
    args = parser.parse_args()
    
    auto_restart = str(os.getenv("CRYPTOBOT_AUTO_RESTART", "0")).lower() in {"1", "true", "yes"}
    
    if not auto_restart:
        run_live(args.config)
        return
        
    backoff = 3.0
    while True:
        stopped = run_live(args.config)
        if stopped: # Clean exit
            break
        time.sleep(backoff)
        backoff = min(backoff * 2.0, 60.0)

if __name__ == "__main__":
    main()
