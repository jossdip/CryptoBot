from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, List

import pandas as pd

from cryptobot.broker.paper import PaperBroker
from cryptobot.broker.risk import RiskManager
from cryptobot.core.types import Bar, Order, PortfolioSnapshot
from cryptobot.strategy.nof1 import Nof1Strategy


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame


class BacktestEngine:
    def __init__(self, broker: PaperBroker, strategy: Nof1Strategy, symbol: str, risk: RiskManager):
        self.broker = broker
        self.strategy = strategy
        self.symbol = symbol
        self.risk = risk
        self.prices: Dict[str, float] = {}
        self.snapshots: List[PortfolioSnapshot] = []

    def run(self, bars: Iterable[Bar]) -> BacktestResult:
        # Load all bars into a DataFrame first for indicator precomputation
        rows = []
        for bar in bars:
            rows.append({
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return BacktestResult(equity_curve=pd.DataFrame(columns=["timestamp", "equity"]))

        signals = self.strategy.generate_signals(df)
        # main loop
        for idx, row in signals.iterrows():
            ts = int(row["timestamp"]) if "timestamp" in row else int(df.iloc[idx]["timestamp"])  # safety
            price = float(row["close"])
            self.prices[self.symbol] = price

            if idx < 50:  # warmup period
                self._snapshot(ts)
                continue

            pos = self.broker.portfolio.positions.get(self.symbol)
            qty = pos.qty if pos else 0.0
            decision = self.strategy.decide(signals.iloc[: idx + 1], qty)

            if decision == "buy":
                equity = self.broker.portfolio.equity({self.symbol: price})
                add_qty_cap = self.risk.additional_qty_allowed(equity=equity, price=price, current_qty=qty)
                if add_qty_cap > 0:
                    order = Order(id=str(uuid.uuid4()), symbol=self.symbol, side="buy", type="market", qty=add_qty_cap, price=None, timestamp=ts)
                    self.broker.market_order(order, price)

            elif decision == "sell" and qty > 0:
                order = Order(id=str(uuid.uuid4()), symbol=self.symbol, side="sell", type="market", qty=qty, price=None, timestamp=ts)
                self.broker.market_order(order, price)

            self._snapshot(ts)

        df_eq = pd.DataFrame([{"timestamp": s.timestamp, "equity": s.equity} for s in self.snapshots])
        return BacktestResult(equity_curve=df_eq)

    def _snapshot(self, ts: int) -> None:
        equity = self.broker.portfolio.equity(self.prices)
        cash = self.broker.portfolio.cash
        unrealized = equity - cash - sum((p.qty * p.avg_price) for p in self.broker.portfolio.positions.values())
        self.snapshots.append(PortfolioSnapshot(timestamp=ts, cash=cash, equity=equity, unrealized_pnl=unrealized))
