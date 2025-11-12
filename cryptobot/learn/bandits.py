from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import math
import numpy as np

from cryptobot.core.config import LearningBanditsConfig


def _softmax(x: List[float]) -> List[float]:
    if not x:
        return []
    mx = max(x)
    exps = [math.exp(v - mx) for v in x]
    s = sum(exps) or 1.0
    return [v / s for v in exps]


@dataclass
class _ArmStats:
    rewards: List[float] = field(default_factory=list)
    mean: float = 0.0
    count: int = 0

    def update(self, r: float, max_history: int = 2000) -> None:
        self.rewards.append(float(r))
        if len(self.rewards) > max_history:
            self.rewards = self.rewards[-max_history:]
        self.count += 1
        self.mean = float(sum(self.rewards) / float(len(self.rewards)))

    @property
    def std(self) -> float:
        if len(self.rewards) < 2:
            return 1.0
        m = self.mean
        var = sum((ri - m) ** 2 for ri in self.rewards) / float(len(self.rewards) - 1)
        return float(max(1e-6, math.sqrt(var)))

    def cvar_penalty(self, alpha: float) -> float:
        if not self.rewards:
            return 0.0
        arr = sorted(self.rewards)
        n = len(arr)
        k = max(1, int(math.floor(alpha * n)))
        tail = arr[:k]  # worst losses (most negative)
        if not tail:
            return 0.0
        return float(abs(sum(tail) / float(len(tail))))


class StrategyAllocationBandit:
    def __init__(self, strategies: List[str], *, config: LearningBanditsConfig) -> None:
        self.strategies = list(strategies)
        self.cfg = config
        self._arms: Dict[str, _ArmStats] = {s: _ArmStats() for s in self.strategies}
        # Seed slight priors to avoid zero-divide; bias toward uniform
        for s in self.strategies:
            self._arms[s].update(0.0)

    def propose_weights(self) -> Dict[str, float]:
        samples: List[float] = []
        for s in self.strategies:
            st = self._arms[s]
            # Thompson-like sampling with Gaussian noise scaled by uncertainty
            noise = np.random.normal(loc=0.0, scale=st.std / math.sqrt(max(1.0, st.count)))
            samples.append(float(st.mean + noise))
        probs = _softmax(samples)
        out = {s: float(p) for s, p in zip(self.strategies, probs)}
        # Safety: ensure strictly positive and normalized
        total = sum(out.values()) or 1.0
        out = {k: max(0.0, v / total) for k, v in out.items()}
        return out

    def update(self, *, strategy: str, reward: float) -> None:
        if strategy not in self._arms:
            return
        # Apply global scaling then subtract CVaR penalty estimated from arm history
        r = float(reward) * float(self.cfg.reward_scale)
        penalty = self._arms[strategy].cvar_penalty(float(self.cfg.reward_cvar_alpha))
        self._arms[strategy].update(r - penalty)


class ParamBandit:
    """
    Lightweight per-parameter epsilon/UCB blend bandit over discrete grids.
    We treat each parameter independently for simplicity and stability.
    """
    def __init__(self, *, config: LearningBanditsConfig) -> None:
        self.cfg = config
        self._per_strategy_stats: Dict[str, Dict[str, Dict[float, _ArmStats]]] = {}
        self._last_choice: Dict[str, Dict[str, float]] = {}

    def _ensure_strategy(self, strategy: str) -> None:
        if strategy in self._per_strategy_stats:
            return
        grids = dict(self.cfg.per_strategy.get("default", {}))
        # Merge overrides
        if strategy in self.cfg.per_strategy:
            for k, v in self.cfg.per_strategy[strategy].items():
                grids[k] = v
        stats: Dict[str, Dict[float, _ArmStats]] = {}
        for name, values in grids.items():
            if not isinstance(values, list):
                continue
            stats[name] = {float(val): _ArmStats() for val in values}
            # Seed slight priors
            for st in stats[name].values():
                st.update(0.0)
        self._per_strategy_stats[strategy] = stats
        self._last_choice[strategy] = {}

    def _ucb_pick(self, choices: Dict[float, _ArmStats], c: float = 0.5) -> float:
        # UCB1-like selection on means with exploration term
        total_plays = sum(st.count for st in choices.values()) or 1
        best_val = None
        best_score = -1e9
        for val, st in choices.items():
            # exploration ~ sqrt(2 ln N / n_i), scaled by c
            exp = math.sqrt(max(0.0, 2.0 * math.log(total_plays + 1.0) / max(1.0, st.count)))
            score = st.mean + c * exp
            if best_val is None or score > best_score:
                best_val = val
                best_score = score
        assert best_val is not None
        return float(best_val)

    def propose(self, *, strategy: str, features: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        self._ensure_strategy(strategy)
        stats = self._per_strategy_stats[strategy]
        out: Dict[str, Any] = {}
        # Independent selection per parameter
        for param_name in ("leverage_grid", "tp_grid_pct", "sl_grid_pct", "min_conf_grid"):
            if param_name not in stats:
                continue
            choice = self._ucb_pick(stats[param_name], c=0.5)
            if param_name == "leverage_grid":
                out["leverage"] = int(max(1, round(choice)))
            elif param_name == "tp_grid_pct":
                out["tp_pct"] = float(choice)
            elif param_name == "sl_grid_pct":
                out["sl_pct"] = float(choice)
            elif param_name == "min_conf_grid":
                out["min_conf"] = float(choice)
            self._last_choice[strategy][param_name] = float(choice)
        return out

    def update(self, *, strategy: str, reward: float, features: Optional[Dict[str, float]] = None) -> None:
        if strategy not in self._per_strategy_stats:
            return
        stats = self._per_strategy_stats[strategy]
        last = self._last_choice.get(strategy, {})
        for param_name, value in last.items():
            if param_name in stats and float(value) in stats[param_name]:
                r = float(reward) * float(self.cfg.reward_scale)
                stats[param_name][float(value)].update(r)


