from __future__ import annotations

import time
import argparse
from typing import Dict, Any

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


def run_live(config_path: str) -> None:
    load_local_environment()
    cfg = AppConfig.load(config_path)
    setup_logging(level="INFO")
    log = get_logger()

    log.info("Starting Hyperliquid live runner...")
    mode_manager = ModeManager(cfg)
    broker = HyperliquidBroker(
        wallet_address=mode_manager.wallet_address,
        private_key=mode_manager.private_key,
        testnet=mode_manager.is_testnet(),
    )

    llm_client = LLMClient.from_env()
    orchestrator = LLMOrchestrator(llm_client)
    weight_manager = WeightManager()

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
    if getattr(cfg, "monitor", None) and bool(cfg.monitor.enabled):
        monitor_engine = MonitorEngine(
            broker=broker,
            orchestrator=orchestrator,
            performance_tracker=performance_tracker,
            storage_path=cfg.monitor.storage_path,
            interval_sec=int(getattr(cfg.monitor, "collect_interval_sec", 5)),
        )
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
        monitor_engine.start()
    
    # Optimisation coûts: tracking pour allocation et budget
    last_allocation_ts = 0.0
    monthly_budget_usd = float(getattr(cfg.llm, "monthly_budget_usd", 0.0))
    allocation_interval_sec = int(getattr(cfg.llm, "allocation_interval_sec", cfg.llm.decision_interval_sec))
    max_opportunities_per_cycle = int(getattr(cfg.llm, "max_opportunities_per_cycle", 999))
    min_opportunity_score = float(getattr(cfg.llm, "min_opportunity_score", 0.0))

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

    while True:
        try:
            # Vérifier budget mensuel (si configuré)
            if monthly_budget_usd > 0.0:
                stats = llm_client._cost_tracker.get_stats()
                if stats["estimated_monthly_cost"] >= monthly_budget_usd:
                    log.warning(f"Budget mensuel atteint: ${stats['estimated_monthly_cost']:.2f} >= ${monthly_budget_usd:.2f}")
                    log.warning("Arrêt du bot pour éviter dépassement de budget")
                    break
            
            # 1. Gather market context
            context = context_aggregator.build_context(
                symbols=symbols,
                include_sentiment=True,
                include_orderbook=True,
            )

            # 2. LLM decides strategy weights (optimisé: moins fréquent)
            current_time = time.time()
            if current_time - last_allocation_ts >= allocation_interval_sec:
                weights = orchestrator.decide_strategy_allocation(
                    market_data=context["market"],
                    portfolio_state=context["portfolio"],
                    sentiment_data=context.get("sentiment", {}),
                    performance_metrics=performance_tracker.feed_to_llm(),
                )
                last_allocation_ts = current_time
            else:
                # Réutiliser les poids précédents
                weights = orchestrator.weights

            # 3. Update weight manager
            weight_manager.weights = weights

            # 4. For each strategy (based on weights) - OPTIMISÉ pour réduire coûts
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
                
                # OPTIMISATION: Filtrer et scorer les opportunités avant appel LLM
                scored_opportunities = []
                for opp in opportunities:
                    score = _score_opportunity(opp, strategy_name, context)
                    if score >= min_opportunity_score:
                        scored_opportunities.append((score, opp))
                
                # Trier par score décroissant et limiter le nombre
                scored_opportunities.sort(key=lambda x: x[0], reverse=True)
                scored_opportunities = scored_opportunities[:max_opportunities_per_cycle]
                
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
                    if decision.get("execute") and float(decision.get("confidence", 0.0)) > 0.7:
                        decision["symbol"] = opportunity.get("symbol", symbols[0])
                        executor.execute_strategy(strategy_name, decision, weights)
                        performance_tracker.record_trade_start(
                            strategy=strategy_name,
                            entry_price=float(opportunity.get("price", 0.0) or opportunity.get("mid", 0.0) or 0.0),
                            size=float(decision.get("size_usd", 0.0)),
                            symbol=decision["symbol"],
                        )

            # 5. Update performance tracking
            performance_tracker.update_positions(broker.get_portfolio())

            # 6. Sleep
            time.sleep(int(cfg.llm.decision_interval_sec))

        except Exception as e:  # pragma: no cover - runtime path
            log.error(f"Error in main loop: {e}")
            time.sleep(10)
        finally:
            # loop continues
            pass

    # graceful stop
    if monitor_engine:
        try:
            monitor_engine.stop()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="C4$H M4CH1N3 Hyperliquid Live Runner")
    parser.add_argument("--config", type=str, default="configs/live.hyperliquid.yaml")
    args = parser.parse_args()
    run_live(args.config)

if __name__ == "__main__":
    main()


