from __future__ import annotations

from dataclasses import dataclass

from cryptobot.core.config import RiskConfig


@dataclass
class RiskManager:
    cfg: RiskConfig

    def max_position_value(self, equity: float) -> float:
        return max(0.0, equity * float(self.cfg.max_position_pct))

    def additional_qty_allowed(self, equity: float, price: float, current_qty: float) -> float:
        max_val = self.max_position_value(equity)
        cur_val = max(0.0, current_qty * price)
        room = max(0.0, max_val - cur_val)
        return room / price if price > 0 else 0.0
