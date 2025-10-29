from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from cryptobot.core.indicators import atr, ema, rsi
from cryptobot.core.types import Order


@dataclass
class Nof1Params:
    rsi_period: int = 14
    rsi_buy: float = 30.0
    rsi_sell: float = 70.0
    ema_fast: int = 12
    ema_slow: int = 26
    atr_period: int = 14
    volatility_floor: float = 0.002


class Nof1Strategy:
    def __init__(self, params: Nof1Params):
        self.params = params

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        ema_fast_series = ema(close, window=self.params.ema_fast)
        ema_slow_series = ema(close, window=self.params.ema_slow)
        rsi_series = rsi(close, period=self.params.rsi_period)
        atr_series = atr(high, low, close, period=self.params.atr_period)

        out = df.copy()
        out["ema_fast"] = ema_fast_series
        out["ema_slow"] = ema_slow_series
        out["rsi"] = rsi_series
        out["atr"] = atr_series
        out["vol_ok"] = (out["atr"] / out["close"]) > self.params.volatility_floor

        out["long_entry"] = (out["ema_fast"] > out["ema_slow"]) & (out["rsi"] < self.params.rsi_sell) & out["vol_ok"]
        out["long_exit"] = (out["ema_fast"] < out["ema_slow"]) | (out["rsi"] > self.params.rsi_sell)
        return out

    def decide(self, df: pd.DataFrame, position_qty: float) -> Optional[str]:
        row = df.iloc[-1]
        if position_qty <= 0 and bool(row["long_entry"]):
            return "buy"
        if position_qty > 0 and bool(row["long_exit"]):
            return "sell"
        return None
