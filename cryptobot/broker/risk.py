from __future__ import annotations

from dataclasses import dataclass

from cryptobot.core.config import RiskConfig


@dataclass
class RiskManager:
    cfg: RiskConfig

    def max_position_value(self, equity: float) -> float:
        return max(0.0, equity * float(self.cfg.max_position_pct))

    def additional_qty_allowed(self, equity: float, price: float, current_qty: float, leverage: float = 1.0) -> float:
        # Enforce both leverage and max_position_pct constraints.
        # Cap is the stricter of:
        #  - leverage-based notional limit (equity * leverage)
        #  - risk-based notional limit (equity * max_position_pct * leverage)
        lev = max(1.0, float(leverage))
        if price <= 0:
            return 0.0

        current_notional = abs(float(current_qty)) * float(price)
        leverage_cap = float(equity) * lev
        risk_cap = float(self.max_position_value(float(equity))) * lev
        max_notional = min(leverage_cap, risk_cap)
        available_notional = max(0.0, max_notional - current_notional)
        return available_notional / float(price)
