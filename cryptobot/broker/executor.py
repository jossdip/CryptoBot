from __future__ import annotations

from typing import Dict, Any, Optional

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

    def execute_strategy(self, strategy_name: str, decision: Dict[str, Any], weights: StrategyWeight) -> Optional[Dict[str, Any]]:
        allocated_capital = float(self.total_capital) * float(getattr(weights, strategy_name, 0.0))
        symbol = str(decision.get("symbol")) if "symbol" in decision else None
        direction = str(decision.get("direction", "flat"))
        if not symbol or direction == "flat":
            try:
                log.debug(f"Executor skip: missing symbol or flat direction | sym={symbol} dir={direction} alloc={allocated_capital:.2f}")
            except Exception:
                pass
            return None
        size_usd = min(float(decision.get("size_usd", 0.0)), allocated_capital)
        if size_usd <= 0:
            try:
                log.debug(f"Executor skip: non-positive size | size_usd={float(decision.get('size_usd', 0.0)):.2f} alloc={allocated_capital:.2f}")
            except Exception:
                pass
            return None
        leverage = int(decision.get("leverage", 1))
        stop_loss = decision.get("stop_loss_pct")
        take_profit = decision.get("take_profit_pct")
        side = "buy" if direction == "long" else "sell"
        # Convert USD sizing to coin sizing using provided entry_price when available
        try:
            entry_price = float(decision.get("entry_price", 0.0) or 0.0)
        except Exception:
            entry_price = 0.0
        coin_size = float(size_usd) / float(entry_price) if entry_price and entry_price > 0 else 0.0
        if coin_size <= 0:
            # Fallback: attempt a conservative nominal size if price missing to avoid skipping forever
            try:
                log.debug(f"Executor fallback: missing/invalid entry_price for {symbol} (entry_price={entry_price}), cannot convert USD->{symbol}. Skipping.")
            except Exception:
                pass
            return None
        try:
            log.info(f"Placing order | strat={strategy_name} sym={symbol} side={side} coin_sz={coin_size:.6f} lev={leverage} usd_sz={size_usd:.2f} entry={entry_price:.2f}")
        except Exception:
            pass
        resp = self.broker.place_order(
            symbol=symbol,
            side=side,
            size=coin_size,
            leverage=leverage,
            order_type="market",
            price=None,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        try:
            if isinstance(resp, dict) and resp.get("ok"):
                log.info(f"Order placed | strat={strategy_name} sym={symbol} side={side} coin_sz={coin_size:.6f} lev={leverage}")
            else:
                log.error(f"Order failed | strat={strategy_name} sym={symbol} side={side} resp={resp}")
        except Exception:
            pass
        return resp


