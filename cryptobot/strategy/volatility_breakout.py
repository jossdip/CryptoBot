from __future__ import annotations

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from loguru import logger as log

from cryptobot.strategy.base import BaseStrategy
# LLM import removed for optimization
# from cryptobot.llm.client import LLMClient 
from cryptobot.core.types import Signal

class VolatilityBreakoutStrategy(BaseStrategy):
    """
    GUERRILLA MOMENTUM STRATEGY
    
    Logic (15m Trend Following):
    - TENDANCE: EMA 50
    - SIGNAL LONG: Close > High(5) + Vol > 1.5x Avg(20) + RSI < 70
    - SIGNAL SHORT: Close < Low(5) + Vol > 1.5x Avg(20) + RSI > 30
    - NO LLM Validation.
    """
    
    def __init__(self, broker, config: Dict[str, Any] = None) -> None:
        super().__init__(broker)
        self.config = config or {}
        # LLM Client removed
        
        # Parameters
        self.vol_multiplier = 1.5
        self.lookback_trend = 50
        self.lookback_signal = 5
        self.lookback_vol = 20
        
        # Fixed confidence for Guerrilla mode
        self.guerrilla_confidence = 0.90

    def process_tick(self, symbol: str, tick_data: Dict[str, Any], current_position: float) -> Optional[Signal]:
        """
        HFT Logic: DISABLED (Latency Constraint).
        """
        return None

    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan for Guerrilla Momentum opportunities.
        """
        opportunities = []
        
        market_data = context.get("market", {})
        candles_map = market_data.get("candles", {})
        
        for symbol, candles in candles_map.items():
            if not candles or len(candles) < self.lookback_trend + 1:
                continue
                
            # Convert to DataFrame
            df = pd.DataFrame(candles)
            # Ensure numeric columns
            cols = ['open', 'high', 'low', 'close', 'volume']
            for c in cols:
                if c in df.columns:
                    df[c] = df[c].astype(float)
            
            # Analysis on closed candles
            current = df.iloc[-1]
            
            # 1. Calculate Indicators
            # EMA 50 Trend
            ema50 = df['close'].rolling(window=self.lookback_trend).mean().iloc[-1]
            
            # Volume Average (20)
            vol_avg = df['volume'].rolling(window=self.lookback_vol).mean().iloc[-1]
            
            # High/Low 5 (Previous 5 candles, not including current if it's just closed/forming? 
            # Assuming df contains closed candles, we compare current Close to High of prev 5)
            # shift(1) to get previous 5
            high_5 = df['high'].shift(1).rolling(window=self.lookback_signal).max().iloc[-1]
            low_5 = df['low'].shift(1).rolling(window=self.lookback_signal).min().iloc[-1]
            
            # RSI
            rsi = self._calculate_rsi(df['close'])
            
            # 2. Logic Checks
            
            # Trend
            is_bull = current['close'] > ema50
            is_bear = current['close'] < ema50
            
            # Volume Condition
            is_vol_valid = current['volume'] > (self.vol_multiplier * vol_avg)
            
            direction = None
            
            # Long Logic
            # Mode BULL + Close > High(5) + Vol OK + RSI < 70
            if is_bull and (current['close'] > high_5) and is_vol_valid and (rsi < 70):
                direction = "long"
                
            # Short Logic
            # Mode BEAR + Close < Low(5) + Vol OK + RSI > 30
            elif is_bear and (current['close'] < low_5) and is_vol_valid and (rsi > 30):
                direction = "short"
            
            if direction:
                log.info(f"GUERRILLA SIGNAL: {symbol} {direction} | Close: {current['close']} | VolRatio: {current['volume']/vol_avg:.2f} | RSI: {rsi:.2f}")
                
                opp = {
                    "symbol": symbol,
                    "strategy": "guerilla_momentum",
                    "direction": direction,
                    "confidence": self.guerrilla_confidence,
                    "timestamp": current.get('timestamp', pd.Timestamp.now().isoformat()),
                    "current_price": float(current['close']),
                    "signal_data": {
                        "ema50": float(ema50),
                        "vol_avg": float(vol_avg),
                        "high5": float(high_5) if high_5 else 0,
                        "low5": float(low_5) if low_5 else 0,
                        "rsi": float(rsi)
                    }
                }
                opportunities.append(opp)
        
        return opportunities

    def _calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return float(100 - (100 / (1 + rs)).iloc[-1])

    def _calculate_atr(self, df, period=14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return float(true_range.rolling(window=period).mean().iloc[-1])
