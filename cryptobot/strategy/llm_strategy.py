from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from cryptobot.llm.client import LLMClient


@dataclass
class LLMStrategy:
    client: LLMClient
    min_call_cooldown_sec: int = int(os.getenv("LLM_MIN_COOLDOWN_SEC", "60"))
    min_atr_ratio: float = float(os.getenv("LLM_MIN_ATR_RATIO", "0.001"))

    _last_call_ts: float = 0.0
    _last_decision: Optional[str] = None

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def _should_call(self, df: pd.DataFrame) -> bool:
        now = time.time()
        if now - self._last_call_ts < self.min_call_cooldown_sec:
            return False
        if "atr" in df.columns and "close" in df.columns:
            atr_ratio = float(df["atr"].iloc[-1]) / max(1e-12, float(df["close"].iloc[-1]))
            if atr_ratio < self.min_atr_ratio:
                return False
        return True

    def decide(self, df: pd.DataFrame, position_qty: float) -> Optional[str]:
        if not self._should_call(df):
            return self._last_decision
        recent = df.iloc[-120:].to_dict(orient="list")
        ctx = {"position_qty": position_qty, "recent": {k: v[-20:] for k, v in recent.items() if k in {"open","high","low","close","volume"}}}
        mult = self.client.score_risk(ctx)
        decision: Optional[str] = None
        if mult > 1.02 and position_qty <= 0:
            decision = "buy"
        elif mult < 0.98 and position_qty > 0:
            decision = "sell"
        else:
            decision = None
        self._last_call_ts = time.time()
        self._last_decision = decision
        return decision
