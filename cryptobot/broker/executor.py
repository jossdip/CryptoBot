from __future__ import annotations

from typing import Dict, Any

from cryptobot.llm.orchestrator import StrategyWeight
from loguru import logger as log


class MultiStrategyExecutor:
    def __init__(self, broker, orchestrator) -> None:
        self.broker = broker
        self.orchestrator = orchestrator
        # Portfolio handle expected on broker.get_portfolio() path

    @property
    def total_capital(self) -> float:
        pf = self.broker.get_portfolio() or {}
        resp = pf.get("response", {})
        # Best effort extraction
        for k in ("equity", "cash", "balance"):
            if k in resp:
                try:
                    return float(resp[k])
                except Exception:
                    continue
        return 0.0

    def execute_strategy(self, strategy_name: str, decision: Dict[str, Any], weights: StrategyWeight) -> None:
        allocated_capital = float(self.total_capital) * float(getattr(weights, strategy_name, 0.0))
        symbol = str(decision.get("symbol")) if "symbol" in decision else None
        direction = str(decision.get("direction", "flat"))
        if not symbol or direction == "flat":
            try:
                log.debug(f"Executor skip: missing symbol or flat direction | sym={symbol} dir={direction} alloc={allocated_capital:.2f}")
            except Exception:
                pass
            return
        size_usd = min(float(decision.get("size_usd", 0.0)), allocated_capital)
        if size_usd <= 0:
            try:
                log.debug(f"Executor skip: non-positive size | size_usd={float(decision.get('size_usd', 0.0)):.2f} alloc={allocated_capital:.2f}")
            except Exception:
                pass
            return
        leverage = int(decision.get("leverage", 1))
        stop_loss = decision.get("stop_loss_pct")
        take_profit = decision.get("take_profit_pct")
        side = "buy" if direction == "long" else "sell"
        self.broker.place_order(
            symbol=symbol,
            side=side,
            size=size_usd,  # Assuming USD sizing; adapt per broker conventions
            leverage=leverage,
            order_type="market",
            price=None,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


