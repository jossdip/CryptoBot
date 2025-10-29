from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd


class BaseStrategy:
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:  # pragma: no cover - interface
        raise NotImplementedError

    def decide(self, df: pd.DataFrame, position_qty: float) -> Optional[str]:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class EnsembleStrategy:
    strategies: Dict[str, BaseStrategy]
    weights: Dict[str, float]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # Return the primary df with appended columns per strategy for transparency
        out = df.copy()
        for name, strat in self.strategies.items():
            sig = strat.generate_signals(df)
            for col in ["ema_fast", "ema_slow", "rsi", "atr", "vol_ok", "long_entry", "long_exit"]:
                if col in sig.columns:
                    out[f"{name}_{col}"] = sig[col]
        return out

    def decide(self, df: pd.DataFrame, position_qty: float) -> Optional[str]:
        # Weighted vote: buy = +1, sell = -1, hold = 0
        score = 0.0
        for name, strat in self.strategies.items():
            sig = strat.generate_signals(df)
            decision = strat.decide(sig, position_qty)
            w = float(self.weights.get(name, 0.0))
            if decision == "buy":
                score += w
            elif decision == "sell":
                score -= w
        if score > 0:
            return "buy"
        if score < 0:
            return "sell"
        return None
