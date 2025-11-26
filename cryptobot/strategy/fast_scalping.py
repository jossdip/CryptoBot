from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from cryptobot.core.indicators import rsi, ema, atr
from cryptobot.core.logging import get_logger

logger = get_logger()

@dataclass
class Signal:
    symbol: str
    direction: str  # "long" or "short" or "flat"
    confidence: float
    price: float
    reason: str
    metadata: Dict[str, Any]

class FastScalpingStrategy:
    """
    High-frequency scalping strategy using pure technical indicators.
    Zero LLM dependency in the hot path.
    """
    def __init__(self, params: Any):
        self.params = params
        self.price_history: Dict[str, List[float]] = {}
        self.timestamps: Dict[str, List[float]] = {}
        self.max_history = 200 # Keep enough for indicators

    def update_market_data(self, symbol: str, price: float, timestamp: float):
        """Ingest a new price tick."""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            self.timestamps[symbol] = []
        
        self.price_history[symbol].append(price)
        self.timestamps[symbol].append(timestamp)
        
        if len(self.price_history[symbol]) > self.max_history:
            self.price_history[symbol].pop(0)
            self.timestamps[symbol].pop(0)

    def process_tick(self, symbol: str, current_price: float) -> Optional[Signal]:
        """
        Evaluate scalping logic on a new tick.
        Logic:
        - Trend: EMA Fast > EMA Slow (Bullish)
        - Momentum: RSI < Oversold (Buy dip) or > Overbought (Sell rip)?
          Actually, for scalping trend following:
            Long if EMA Cross Up AND RSI > 50 AND RSI < 70
          For mean reversion:
            Long if RSI < 30
        """
        if not self.params.scalping_enabled:
            return None

        history = self.price_history.get(symbol, [])
        if len(history) < max(self.params.rsi_period, self.params.ema_slow) + 5:
            return None

        # Convert to Series for vectorized calc
        # In a real HFT engine, we would update indicators incrementally, 
        # but for Python "Fast Path" (~10ms), Pandas on 200 rows is fine.
        closes = pd.Series(history)
        
        # Indicators
        rsi_val = rsi(closes, period=self.params.rsi_period).iloc[-1]
        ema_fast = ema(closes, window=self.params.ema_fast).iloc[-1]
        ema_slow = ema(closes, window=self.params.ema_slow).iloc[-1]
        
        # Logic
        direction = "flat"
        confidence = 0.0
        reason = ""
        
        # 1. Trend Following Entry
        if ema_fast > ema_slow:
            # Bullish trend
            if 40 < rsi_val < 60:
                # Healthy momentum, not overextended
                direction = "long"
                confidence = 0.6
                reason = "Trend Following: EMA Cross + Neutral RSI"
            elif rsi_val < self.params.rsi_oversold:
                # Pullback in uptrend
                direction = "long"
                confidence = 0.8
                reason = "Trend Following: Buy the dip (Oversold)"
        elif ema_fast < ema_slow:
            # Bearish trend
            if 40 < rsi_val < 60:
                direction = "short"
                confidence = 0.6
                reason = "Trend Following: EMA Cross + Neutral RSI"
            elif rsi_val > self.params.rsi_overbought:
                direction = "short"
                confidence = 0.8
                reason = "Trend Following: Sell the rip (Overbought)"

        # 2. Mean Reversion (Counter-trend) - higher risk
        # Override if extreme RSI
        if rsi_val < 20:
             direction = "long"
             confidence = 0.7
             reason = "Mean Reversion: Extreme Oversold"
        elif rsi_val > 80:
             direction = "short"
             confidence = 0.7
             reason = "Mean Reversion: Extreme Overbought"

        if direction == "flat":
            return None

        return Signal(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            price=current_price,
            reason=reason,
            metadata={
                "rsi": float(rsi_val),
                "ema_fast": float(ema_fast),
                "ema_slow": float(ema_slow),
                "last_close": float(closes.iloc[-1])
            }
        )

