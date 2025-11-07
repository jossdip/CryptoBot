from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from cryptobot.llm.client import LLMClient
from cryptobot.core.logging import get_llm_logger


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
            reason = "cooldown" if (time.time() - self._last_call_ts) < self.min_call_cooldown_sec else "atr_low"
            get_llm_logger().debug({
                "event": "llm_strategy_skip",
                "call": "spot_decide",
                "reason": reason,
                "since_last_call_sec": round(time.time() - self._last_call_ts, 2),
                "min_cooldown_sec": self.min_call_cooldown_sec,
                "min_atr_ratio": self.min_atr_ratio,
            })
            return self._last_decision
        recent = df.iloc[-120:].to_dict(orient="list")
        ctx = {"position_qty": position_qty, "recent": {k: v[-20:] for k, v in recent.items() if k in {"open","high","low","close","volume"}}}
        get_llm_logger().debug({
            "event": "llm_strategy_call",
            "call": "score_risk",
            "context_keys": list(ctx.keys()),
            "recent_lengths": {k: len(v) for k, v in ctx.get("recent", {}).items()},
        })
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
        get_llm_logger().debug({
            "event": "llm_strategy_result",
            "call": "score_risk",
            "multiplier": mult,
            "mapped_decision": decision,
        })
        return decision

    def decide_futures(self, df: pd.DataFrame, extra_context: Optional[Dict] = None) -> Dict:
        """Return {direction,long|short|flat; leverage:int; confidence:float}. Cools down calls."""
        if not self._should_call(df):
            # reuse last decision when on cooldown
            last = self._last_decision or None
            if last == "buy":
                return {"direction": "long", "leverage": 1, "confidence": 0.0}
            if last == "sell":
                return {"direction": "short", "leverage": 1, "confidence": 0.0}
            return {"direction": "flat", "leverage": 1, "confidence": 0.0}

        recent = df.iloc[-180:].copy()
        # Downsample to reduce token cost
        sample = recent.iloc[-60:]
        ctx = {
            "recent": {k: [float(x) for x in sample[k].tolist()] for k in sample.columns if k in {"open","high","low","close","volume"}},
        }
        if extra_context:
            ctx.update(extra_context)
        get_llm_logger().debug({
            "event": "llm_strategy_call",
            "call": "decide_futures",
            "context_keys": list(ctx.keys()),
            "recent_lengths": {k: len(v) for k, v in ctx.get("recent", {}).items()},
        })
        decision = self.client.decide_futures(ctx)
        self._last_call_ts = time.time()
        # store a coarse mapping for compatibility with last_decision
        dir_map = {"long": "buy", "short": "sell", "flat": None}
        self._last_decision = dir_map.get(str(decision.get("direction", "flat")), None)
        get_llm_logger().debug({
            "event": "llm_strategy_result",
            "call": "decide_futures",
            "decision": decision,
        })
        return decision
