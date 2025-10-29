from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from cryptobot.core.types import Fill, Order, Position


@dataclass
class Portfolio:
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)

    def equity(self, prices: Dict[str, float]) -> float:
        value = self.cash
        for pos in self.positions.values():
            value += pos.qty * prices.get(pos.symbol, pos.avg_price)
        return value


class PaperBroker:
    def __init__(self, fee_bps: float = 10.0, slippage_bps: float = 5.0, starting_cash: float = 10000.0):
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.portfolio = Portfolio(cash=starting_cash)

    def _apply_slippage(self, price: float, side: str) -> float:
        adj = price * (self.slippage_bps / 10000.0)
        return price + adj if side == "buy" else price - adj

    def _fee(self, notional: float) -> float:
        return abs(notional) * (self.fee_bps / 10000.0)

    def market_order(self, order: Order, last_price: float) -> Optional[Fill]:
        exec_price = self._apply_slippage(last_price, order.side)
        notional = exec_price * order.qty
        fee = self._fee(notional)

        if order.side == "buy":
            cost = notional + fee
            if self.portfolio.cash < cost:
                return None
            self.portfolio.cash -= cost
            pos = self.portfolio.positions.get(order.symbol)
            if pos is None:
                self.portfolio.positions[order.symbol] = Position(symbol=order.symbol, qty=order.qty, avg_price=exec_price)
            else:
                new_qty = pos.qty + order.qty
                pos.avg_price = (pos.avg_price * pos.qty + exec_price * order.qty) / new_qty
                pos.qty = new_qty
        else:  # sell
            pos = self.portfolio.positions.get(order.symbol)
            if pos is None or pos.qty < order.qty:
                return None
            proceeds = notional - fee
            self.portfolio.cash += proceeds
            pos.qty -= order.qty
            if pos.qty == 0:
                del self.portfolio.positions[order.symbol]

        return Fill(order_id=order.id, symbol=order.symbol, side=order.side, qty=order.qty, price=exec_price, fee=fee, timestamp=order.timestamp)
