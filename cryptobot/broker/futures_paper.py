from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from cryptobot.core.types import Fill, Order, Position


@dataclass
class FuturesPortfolio:
    # Margin balance (USDT or quote currency)
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    # isolated margin per symbol
    isolated_margin: Dict[str, float] = field(default_factory=dict)
    leverage_map: Dict[str, int] = field(default_factory=dict)

    def equity(self, prices: Dict[str, float]) -> float:
        value = self.cash
        for sym, pos in self.positions.items():
            price = prices.get(sym, pos.avg_price)
            value += (price - pos.avg_price) * pos.qty
        return float(value)


class FuturesPaperBroker:
    def __init__(
        self,
        fee_bps: float = 2.0,  # futures taker ~0.02%
        slippage_bps: float = 5.0,
        starting_cash: float = 100.0,
        default_leverage: int = 5,
        max_leverage: int = 20,
        margin_mode: str = "isolated",
    ):
        self.fee_bps = float(fee_bps)
        self.slippage_bps = float(slippage_bps)
        self.portfolio = FuturesPortfolio(cash=float(starting_cash))
        self.default_leverage = int(default_leverage)
        self.max_leverage = int(max_leverage)
        self.margin_mode = margin_mode

    def _apply_slippage(self, price: float, side: str) -> float:
        adj = price * (self.slippage_bps / 10000.0)
        return price + adj if side == "buy" else price - adj

    def _fee(self, notional: float) -> float:
        return abs(notional) * (self.fee_bps / 10000.0)

    def _symbol_leverage(self, symbol: str, leverage: Optional[int]) -> int:
        lev = int(leverage or self.portfolio.leverage_map.get(symbol, self.default_leverage))
        lev = max(1, min(self.max_leverage, lev))
        self.portfolio.leverage_map[symbol] = lev
        return lev

    def _required_margin_delta(self, symbol: str, new_notional: float, old_notional: float, leverage: int) -> float:
        # Isolated margin per symbol scales with absolute notional
        new_margin = abs(new_notional) / float(leverage)
        old_margin = abs(old_notional) / float(leverage)
        return float(new_margin - old_margin)

    def market_order(self, order: Order, last_price: float, leverage: Optional[int] = None) -> Optional[Fill]:
        exec_price = self._apply_slippage(last_price, order.side)
        # In futures, side determines direction delta. Positive qty always provided in Order.
        delta_qty = float(order.qty) if order.side == "buy" else -float(order.qty)

        pos = self.portfolio.positions.get(order.symbol)
        prev_qty = float(pos.qty) if pos is not None else 0.0
        prev_avg = float(pos.avg_price) if pos is not None else float(exec_price)

        new_qty = prev_qty + delta_qty
        # If crossing through flat, treat as reduce then open
        # Compute notional change for margin update
        old_notional = prev_qty * exec_price
        new_notional = new_qty * exec_price

        # Determine leverage to apply
        lev = self._symbol_leverage(order.symbol, leverage)

        # Compute fee on traded notional
        trade_notional = abs(delta_qty * exec_price)
        fee = self._fee(trade_notional)

        # Update margin for isolated mode
        margin_delta = 0.0
        if self.margin_mode == "isolated":
            margin_delta = self._required_margin_delta(order.symbol, new_notional, old_notional, lev)
            # If we need more margin, ensure cash is sufficient
            if margin_delta > 0 and self.portfolio.cash < (margin_delta + fee):
                return None

        # Update cash (margin changes + fees)
        self.portfolio.cash -= max(0.0, margin_delta)
        # Release margin when margin_delta negative
        self.portfolio.cash += max(0.0, -margin_delta)
        self.portfolio.cash -= fee

        # Update position average price per standard weighted formula on increases
        if new_qty == 0.0:
            # Position fully closed
            if order.symbol in self.portfolio.positions:
                del self.portfolio.positions[order.symbol]
        elif (prev_qty >= 0 and new_qty > 0) or (prev_qty <= 0 and new_qty < 0):
            # Increase in same direction → recompute avg price
            if pos is None:
                self.portfolio.positions[order.symbol] = Position(symbol=order.symbol, qty=new_qty, avg_price=exec_price)
            else:
                # Weighted average only when increasing the absolute size
                if abs(new_qty) > abs(prev_qty):
                    total_cost = abs(prev_qty) * prev_avg + abs(delta_qty) * exec_price
                    self.portfolio.positions[order.symbol] = Position(symbol=order.symbol, qty=new_qty, avg_price=(total_cost / abs(new_qty)))
                else:
                    # Reduced in same direction (rare due to sign), keep avg
                    self.portfolio.positions[order.symbol] = Position(symbol=order.symbol, qty=new_qty, avg_price=prev_avg)
        else:
            # Direction flip (reduce then reopen): new avg is exec price
            self.portfolio.positions[order.symbol] = Position(symbol=order.symbol, qty=new_qty, avg_price=exec_price)

        return Fill(order_id=order.id, symbol=order.symbol, side=order.side, qty=order.qty, price=exec_price, fee=fee, timestamp=order.timestamp)


