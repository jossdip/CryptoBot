from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import pandas as pd
import numpy as np
from loguru import logger as log

from cryptobot.core.config import RiskConfig
from cryptobot.core.indicators import ema, atr

@dataclass
class RiskManager:
    cfg: RiskConfig
    # State for circuit breaker
    daily_start_equity: float = 0.0
    last_reset_time: float = 0.0
    circuit_breaker_tripped: bool = False
    circuit_breaker_expiry: float = 0.0

    def __post_init__(self):
        # Initialize last_reset_time if not set
        if self.last_reset_time == 0.0:
            self.last_reset_time = time.time()

    def check_drawdown_circuit_breaker(self, current_equity: float) -> bool:
        """
        Check if daily drawdown limit is breached.
        Returns True if circuit breaker is ACTIVE (trading should stop).
        """
        now = time.time()

        # Reset daily reference if 24h passed
        if now - self.last_reset_time > 86400:
            self.daily_start_equity = current_equity
            self.last_reset_time = now
            self.circuit_breaker_tripped = False # Reset trip
            log.info(f"RiskManager: Daily equity reset to {self.daily_start_equity}")
        
        if self.daily_start_equity <= 0:
             self.daily_start_equity = current_equity

        # Check if already tripped
        if self.circuit_breaker_tripped:
            if now < self.circuit_breaker_expiry:
                log.warning(f"RiskManager: Circuit breaker ACTIVE. Remaining: {int(self.circuit_breaker_expiry - now)}s")
                return True
            else:
                log.info("RiskManager: Circuit breaker expired. Resuming.")
                self.circuit_breaker_tripped = False
                self.daily_start_equity = current_equity # Reset reference after cooldown
                return False

        # Calculate Drawdown
        drawdown_pct = 0.0
        if self.daily_start_equity > 0:
            drawdown_pct = (self.daily_start_equity - current_equity) / self.daily_start_equity * 100.0

        # Hard Safety: 50% max daily loss (Aggressive Mode)
        limit = 50.0 
        
        if drawdown_pct > limit:
            log.critical(f"RiskManager: CIRCUIT BREAKER TRIPPED! Drawdown {drawdown_pct:.2f}% > {limit}%")
            self.circuit_breaker_tripped = True
            self.circuit_breaker_expiry = now + 86400 # Stop for 24h
            return True
            
        return False

    def calculate_conviction_score(self, market_data: pd.DataFrame) -> float:
        """
        Calculate conviction score (0-100).
        Simple pass-through for Guerrilla mode as Strategy handles strict logic.
        """
        return 90.0

    def get_position_size_and_leverage(self, conviction_score: float, equity: float) -> Tuple[float, int]:
        """
        Calculate Size and Leverage.
        Logic: Small Account Aggression.
        - If Equity < 500: Risk 10% of Capital per trade.
        - Max Leverage: 20x.
        """
        # Validation threshold
        if conviction_score < 75:
            return 0.0, 0
            
        # Parameters
        is_small_account = equity < 500.0
        
        if is_small_account:
            risk_pct = 0.10 # 10% Risk Aggressive
        else:
            risk_pct = 0.02 # 2% Standard
            
        # Stop Loss Distance (Fixed assumption for calculation based on Strategy Config)
        # Ideally this should be passed dynamically, but we use the standard 1.5% 
        # defined in the prompt context / strategy config as the basis for sizing.
        stop_loss_dist = 0.015 
        
        # 1. Calculate Risk Amount in USD
        risk_amount_usd = equity * risk_pct
        
        # 2. Calculate Position Size
        # Risk = Size * SL_Dist -> Size = Risk / SL_Dist
        position_size_usd = risk_amount_usd / stop_loss_dist
        
        # 3. Calculate Required Leverage
        # Leverage = Size / Equity
        if equity > 0:
            leverage = position_size_usd / equity
        else:
            leverage = 0
            
        # 4. Apply Hard Caps
        max_leverage = 20
        if leverage > max_leverage:
            leverage = max_leverage
            # Recalculate size based on max leverage
            position_size_usd = equity * max_leverage * 0.95 # 95% usage to leave room for fees
            log.warning(f"Leverage capped at {max_leverage}x. Size adjusted to {position_size_usd:.2f}")
        
        # Ensure integer leverage
        leverage_int = int(leverage)
        if leverage_int < 1:
            leverage_int = 1
            
        log.info(f"Risk Calculation: Equity {equity:.2f} | Risk {risk_pct*100}% (${risk_amount_usd:.2f}) | Size ${position_size_usd:.2f} | Lev {leverage_int}x")
        
        return position_size_usd, leverage_int

    def validate_signal(self, conviction_score: float) -> bool:
        return conviction_score >= 75.0

    def calculate_dynamic_size(self, equity: float, price: float, confidence: float, tp_pct: float, sl_pct: float) -> float:
        """
        Calculate dynamic position size in COINS (not USD).
        Used by FastEngine.
        """
        # Map confidence (0-1) to score (0-100)
        score = confidence * 100.0
        
        usd_size, leverage = self.get_position_size_and_leverage(score, equity)
        
        if usd_size <= 0 or price <= 0:
            return 0.0
            
        return usd_size / price
