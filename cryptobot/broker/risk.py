from __future__ import annotations

from dataclasses import dataclass

from cryptobot.core.config import RiskConfig


@dataclass
class RiskManager:
    cfg: RiskConfig

    def max_position_value(self, equity: float) -> float:
        return max(0.0, equity * float(self.cfg.max_position_pct))

    def additional_qty_allowed(self, equity: float, price: float, current_qty: float, leverage: float = 1.0) -> float:
        # No position size limit (similar to nof1.ai approach)
        # Only limited by available margin for leverage
        lev = max(1.0, float(leverage))
        # Maximum notional = available equity * leverage
        max_notional = equity * lev
        current_notional = abs(current_qty) * price
        available_notional = max(0.0, max_notional - current_notional)
        return available_notional / price if price > 0 else 0.0
