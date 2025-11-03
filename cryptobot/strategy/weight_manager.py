from __future__ import annotations

from typing import Dict, List

import numpy as np

from cryptobot.llm.orchestrator import StrategyWeight


class WeightManager:
    def __init__(self) -> None:
        self.weights = StrategyWeight()
        self.performance_tracker: Dict[str, List[float]] = {}

    def update_performance(self, strategy: str, pnl: float) -> None:
        if strategy not in self.performance_tracker:
            self.performance_tracker[strategy] = []
        self.performance_tracker[strategy].append(float(pnl))
        if len(self.performance_tracker[strategy]) > 100:
            self.performance_tracker[strategy] = self.performance_tracker[strategy][-100:]

    def get_performance_score(self, strategy: str, window: int = 24) -> float:
        if strategy not in self.performance_tracker:
            return 0.0
        recent = self.performance_tracker[strategy][-window:]
        if not recent:
            return 0.0
        return float(sum(recent)) / float(len(recent))

    def calculate_adaptive_weights(self) -> StrategyWeight:
        strategies = [
            "market_making",
            "momentum",
            "scalping",
            "arbitrage",
            "breakout",
            "sniping",
        ]
        scores = {s: self.get_performance_score(s) for s in strategies}
        exp_scores = {k: float(np.exp(v * 10.0)) for k, v in scores.items()}
        total = float(sum(exp_scores.values())) or 1.0
        new_weights = StrategyWeight(
            market_making=max(0.25, exp_scores["market_making"] / total),  # Min 25%
            momentum=exp_scores["momentum"] / total,
            scalping=exp_scores["scalping"] / total,
            arbitrage=exp_scores["arbitrage"] / total,
            breakout=exp_scores["breakout"] / total,
            sniping=min(0.10, exp_scores["sniping"] / total),  # Max 10%
        )
        new_weights.normalize()

        # Smooth blend (70% new, 30% old)
        self.weights = StrategyWeight(
            market_making=self.weights.market_making * 0.3 + new_weights.market_making * 0.7,
            momentum=self.weights.momentum * 0.3 + new_weights.momentum * 0.7,
            scalping=self.weights.scalping * 0.3 + new_weights.scalping * 0.7,
            arbitrage=self.weights.arbitrage * 0.3 + new_weights.arbitrage * 0.7,
            breakout=self.weights.breakout * 0.3 + new_weights.breakout * 0.7,
            sniping=self.weights.sniping * 0.3 + new_weights.sniping * 0.7,
        )
        self.weights.normalize()
        return self.weights


